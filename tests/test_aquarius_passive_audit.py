"""Synthetic packets only; no packet socket, private target, or device access."""

import ipaddress
import json
import socket
import struct
import unittest
from unittest.mock import patch

from tooling import aquarius_passive_audit as audit

TARGET = "192.168.50.80"
CLIENT = "192.168.50.10"


def config(**changes):
    return audit.Configuration.parse({
        "schema_version": 1, "host": TARGET, "port": 8080,
        "interface": "eth0", "duration_seconds": 1, **changes,
    })


def packet(payload=b"", *, sequence=101, ack=0, flags=0x18, inbound=False,
           source=None, destination=None, source_port=None, destination_port=None,
           options=b"", fragment=0):
    src, dst = (TARGET, CLIENT) if inbound else (CLIENT, TARGET)
    sport, dport = (8080, 44000) if inbound else (44000, 8080)
    tcp = struct.pack("!HHIIBBHHH", source_port or sport, destination_port or dport,
                      sequence & 0xFFFFFFFF, ack & 0xFFFFFFFF, 0x50, flags, 4096, 0, 0)
    ip = struct.pack("!BBHHHBBH4s4s", 0x45 + len(options) // 4, 0,
                     20 + len(options) + len(tcp) + len(payload), 1, fragment, 64, 6, 0,
                     ipaddress.IPv4Address(source or src).packed,
                     ipaddress.IPv4Address(destination or dst).packed)
    return bytes(12) + b"\x08\x00" + ip + options + tcp + payload


def evaluate(program, data):
    """Small independent interpreter for the emitted classic BPF subset."""
    accumulator = index_register = cursor = 0
    while cursor < len(program):
        code, yes, no, value = program[cursor]
        try:
            if code in (0x20, 0x28, 0x30, 0x48):
                width = {0x20: 4, 0x28: 2, 0x30: 1, 0x48: 2}[code]
                offset = value + (index_register if code == 0x48 else 0)
                if offset + width > len(data):
                    return 0
                accumulator = int.from_bytes(data[offset:offset + width], "big")
            elif code == 0xB1:
                index_register = (data[value] & 15) * 4
            elif code == 0x15:
                cursor += yes if accumulator == value else no
            elif code == 0x45:
                cursor += yes if accumulator & value else no
            elif code == 0x06:
                return value
            else:
                raise AssertionError("unexpected BPF opcode")
        except IndexError:
            return 0
        cursor += 1
    raise AssertionError("BPF program fell through")


def conversation(payload=None, *, isn=100):
    payload = audit.SYSTEM_QUERY + audit.CHANNEL_QUERY if payload is None else payload
    return [
        packet(sequence=isn, flags=2),
        packet(inbound=True, sequence=700, ack=isn + 1, flags=0x12),
        packet(payload, sequence=isn + 1),
        packet(b"synthetic response", inbound=True, sequence=701, ack=isn + 1 + len(payload)),
        packet(sequence=isn + 1 + len(payload), flags=0x11),
        packet(inbound=True, sequence=719, ack=isn + 2 + len(payload), flags=0x10),
    ]


def inspect(rows, **stats):
    observer = audit.Audit(config())
    for row in rows:
        observer.feed(row)
    return observer.finish(kernel_packets=stats.get("packets", len(rows)),
                           kernel_drops=stats.get("drops", 0))


class FilterTests(unittest.TestCase):
    def test_exact_endpoint_both_directions_and_variable_ipv4_header(self):
        program = audit.capture_filter(config())
        for inbound in (False, True):
            for options in (b"", bytes(12)):
                self.assertEqual(evaluate(program, packet(inbound=inbound, options=options)),
                                 audit.SNAPLEN)

    def test_other_hosts_ports_udp_ipv6_vlan_and_noninitial_fragments_are_rejected(self):
        program = audit.capture_filter(config())
        udp = bytearray(packet())
        udp[23] = 17
        ipv6 = bytearray(packet())
        ipv6[12:14] = b"\x86\xdd"
        vlan = bytearray(packet())
        vlan[12:14] = b"\x81\x00"
        for row in (
            packet(destination="192.168.50.81"), packet(destination_port=8081),
            packet(inbound=True, source="192.168.50.81"),
            packet(inbound=True, source_port=8081), packet(fragment=1), udp, ipv6, vlan,
            b"", bytes(20),
        ):
            self.assertEqual(evaluate(program, row), 0)

    def test_first_fragment_is_visible_so_it_invalidates_completeness(self):
        row = packet(fragment=0x2000)
        self.assertEqual(evaluate(audit.capture_filter(config()), row), audit.SNAPLEN)
        result = inspect(conversation() + [row])
        self.assertEqual(result["status"], "INCONCLUSIVE")
        self.assertIn("ipv4_fragmentation", result["visibility_problems"])

    def test_configuration_rejects_discovery_and_unbounded_inputs(self):
        for changes in (
            {"host": "example.invalid"}, {"host": "::1"}, {"host": "8.8.8.8"},
            {"host": 1}, {"port": 8081}, {"port": True}, {"interface": ""},
            {"interface": "eth0;cmd"}, {"duration_seconds": 601},
            {"duration_seconds": True}, {"schema_version": True},
        ):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                config(**changes)


class ReassemblyTests(unittest.TestCase):
    def test_complete_queries_are_observed_but_not_unqualified_no_write_proof(self):
        result = inspect(conversation())
        self.assertEqual(result["status"], "QUERY_ONLY_OBSERVED", result)
        self.assertFalse(result["no_write_proof"])
        self.assertEqual(result["counts"]["system_queries"], 1)
        self.assertEqual(result["counts"]["channel_queries"], 1)
        self.assertEqual(result["visibility_problems"], [])
        for private in (TARGET, CLIENT, "synthetic response"):
            self.assertNotIn(private, json.dumps(result))

    def test_every_fragment_boundary_retransmit_reordering_and_coalescing(self):
        whole = audit.SYSTEM_QUERY + audit.CHANNEL_QUERY
        for split in range(1, len(whole)):
            rows = conversation()
            rows[2:3] = [packet(whole[split:], sequence=101 + split),
                         packet(whole[:split]), packet(whole[split:], sequence=101 + split)]
            result = inspect(rows)
            with self.subTest(split=split):
                self.assertEqual(result["status"], "QUERY_ONLY_OBSERVED", result)
                self.assertEqual(result["counts"]["client_bytes"], 40)

    def test_sequence_wrap_and_syn_payload_are_reassembled(self):
        self.assertEqual(inspect(conversation(isn=0xFFFFFFF0))["status"], "QUERY_ONLY_OBSERVED")
        rows = conversation()
        rows[0] = packet(audit.SYSTEM_QUERY, sequence=100, flags=2)
        rows[2] = packet(audit.CHANNEL_QUERY, sequence=121)
        rows[1] = packet(inbound=True, sequence=700, ack=121, flags=0x12)
        self.assertEqual(inspect(rows)["status"], "QUERY_ONLY_OBSERVED")

    def test_modes_channels_and_other_command_families_cannot_pass(self):
        for family in (0xE1, 0xE2, 0xE3):
            command = b"\xf1" + bytes((family, 0xFA)) + bytes(16) + b"\xf3"
            result = inspect(conversation(audit.SYSTEM_QUERY + audit.CHANNEL_QUERY + command))
            self.assertEqual(result["status"], "WRITE_OBSERVED")
            self.assertEqual(result["counts"]["write_frames"], 1)
        command = b"\xf1\xe1\xfc\x01" + bytes(15) + b"\xf3"
        self.assertEqual(inspect(conversation(command))["status"], "OTHER_COMMAND_OBSERVED")

    def test_loss_partial_prefix_unknown_bytes_and_conflicts_never_pass(self):
        complete = conversation()
        alternatives = [
            complete[1:], complete[:-2], complete[:2] + complete[3:],
            complete[:2] + [packet(audit.SYSTEM_QUERY[:8]),
                            packet(audit.CHANNEL_QUERY, sequence=121)] + complete[3:],
            complete[:3] + [packet(b"different")] + complete[3:],
            conversation(audit.SYSTEM_QUERY + b"\xf1\xe2"),
            conversation(b"garbage" + audit.SYSTEM_QUERY + audit.CHANNEL_QUERY),
        ]
        for rows in alternatives:
            self.assertEqual(inspect(rows)["status"], "INCONCLUSIVE")

    def test_missing_trailing_payload_is_detected_by_fin_or_server_ack(self):
        rows = conversation()
        rows[4] = packet(sequence=181, flags=0x11)
        rows[5] = packet(inbound=True, ack=182, flags=0x10)
        result = inspect(rows)
        self.assertEqual(result["status"], "INCONCLUSIVE")
        self.assertIn("unobserved_bytes_before_fin", result["visibility_problems"])
        self.assertIn("acknowledgement_exceeds_observed_bytes", result["visibility_problems"])

    def test_port_reuse_does_not_join_separate_streams(self):
        result = inspect(conversation() + conversation(isn=1000))
        self.assertEqual(result["status"], "QUERY_ONLY_OBSERVED")
        self.assertEqual(result["connections"], 2)
        self.assertEqual(result["counts"]["system_queries"], 2)
        result = inspect(conversation()[:-2] + conversation(isn=1000))
        self.assertEqual(result["status"], "INCONCLUSIVE")

    def test_empty_inbound_only_capture_or_missing_drop_statistics_is_inconclusive(self):
        for rows in ([], [packet(inbound=True, ack=101)], conversation()[::2]):
            self.assertEqual(inspect(rows)["status"], "INCONCLUSIVE")
        self.assertEqual(inspect(conversation(), drops=1, packets=7)["status"], "INCONCLUSIVE")
        self.assertEqual(inspect(conversation(), packets=7)["status"], "INCONCLUSIVE")
        observer = audit.Audit(config())
        for row in conversation():
            observer.feed(row)
        self.assertEqual(observer.finish()["status"], "INCONCLUSIVE")

    def test_truncation_and_resource_limits_are_explicit(self):
        observer = audit.Audit(config())
        observer.feed(packet(), truncated=True)
        self.assertIn("truncated_packet", observer.finish()["visibility_problems"])
        with patch.object(audit, "MAX_BYTES", 20):
            self.assertFalse(observer.feed(packet()))
        self.assertIn("capture_budget_exceeded", observer.finish()["visibility_problems"])


class CaptureOrderingTests(unittest.TestCase):
    def test_dormant_socket_filtered_before_activation_and_no_send_or_membership(self):
        order, reports, now = [], [], [0.0]
        rows = conversation()

        class Observer:
            blocking = True

            def __enter__(self):
                return self

            def __exit__(self, *args):
                order.append("close")

            def bind(self, address):
                order.append(("bind", address))

            def settimeout(self, value):
                pass

            def setblocking(self, value):
                self.blocking = value

            def recvmsg(self, size):
                if rows:
                    return rows.pop(0), [], 0, None
                if self.blocking:
                    now[0] = 1.0
                    raise socket.timeout()
                raise BlockingIOError()

            def getsockopt(self, *args):
                return struct.pack("II", 6, 0)

        class Sink:
            def write(self, report):
                reports.append(report)

        with patch.object(audit.socket, "AF_PACKET", 17, create=True), patch.object(
            audit.socket, "socket", side_effect=lambda *args: order.append(("socket", args))
            or Observer()
        ), patch.object(audit, "attach_filter", side_effect=lambda sock, program:
                        order.append(("filter", program))), patch.object(audit.signal, "signal"):
            result = audit.capture(config(), Sink(), clock=lambda: now[0])
        self.assertEqual(order[0], ("socket", (17, socket.SOCK_RAW, 0)))
        self.assertEqual(order[1], ("filter", audit.capture_filter(config())))
        self.assertEqual(order[2], ("bind", ("eth0", audit.ETH_P_ALL)))
        self.assertEqual(order[3], ("filter", ((0x06, 0, 0, 0),)))
        self.assertEqual(result["status"], "QUERY_ONLY_OBSERVED")
        self.assertEqual([report["status"] for report in reports],
                         ["READY", "QUERY_ONLY_OBSERVED"])


if __name__ == "__main__":
    unittest.main()
