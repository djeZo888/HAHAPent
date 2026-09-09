"""Bounded passive, exact-target command audit; no device connection or transmission.

Linux capture requires an existing CAP_NET_RAW grant. No package, interface,
firewall, capability, or promiscuous-mode change is attempted. Only summary
evidence is persisted privately; packet payloads remain bounded in memory.
"""

from __future__ import annotations

import argparse
import ctypes
import ipaddress
import json
import os
import re
import signal
import socket
import stat
import struct
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

MAX_BYTES = 1048576
MAX_STREAM = 65536
MAX_PACKETS = 50000
MAX_FLOWS = 256
SNAPLEN = 65599
ETH_P_IP = 0x0800
ETH_P_ALL = 0x0003
SO_ATTACH_FILTER = 26
SOL_PACKET = 263
PACKET_STATISTICS = 6
SYSTEM_QUERY = b"\xf1\xe1\xfc" + bytes(16) + b"\xf3"
CHANNEL_QUERY = b"\xf1\xe2\xfc" + bytes(16) + b"\xf3"


@dataclass(frozen=True)
class Configuration:
    host: str
    port: int
    interface: str
    duration_seconds: int

    @classmethod
    def parse(cls, data):
        if not isinstance(data, dict) or set(data) != {
            "schema_version", "host", "port", "interface", "duration_seconds"
        }:
            raise ValueError("invalid audit configuration")
        if type(data["schema_version"]) is not int or data["schema_version"] != 1:
            raise ValueError("unsupported audit schema")
        if not isinstance(data["host"], str):
            raise ValueError("an exact private IPv4 address is required")
        address = ipaddress.ip_address(data["host"])
        if address.version != 4 or not any(
            address in ipaddress.ip_network(network)
            for network in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16")
        ):
            raise ValueError("an exact private IPv4 address is required")
        if type(data["port"]) is not int or data["port"] != 8080:
            raise ValueError("only the authorized protocol port is permitted")
        interface = data["interface"]
        if not isinstance(interface, str) or not re.fullmatch(r"[A-Za-z0-9_.-]{1,15}", interface):
            raise ValueError("one explicit existing interface is required")
        duration = data["duration_seconds"]
        if type(duration) is not int or not 1 <= duration <= 600:
            raise ValueError("capture duration must be one to 600 seconds")
        return cls(str(address), 8080, interface, duration)


def capture_filter(config):
    """Classic BPF: untagged IPv4 TCP, exact endpoint and its port, both directions.

    Initial IPv4 fragments are retained and invalidate completeness. Noninitial
    fragments cannot be assigned a TCP port and are excluded by this narrow
    filter. Fragmentation is never reconstructed or silently treated as complete.
    """
    target = int(ipaddress.IPv4Address(config.host))
    instructions = [
        ("ether", 0x28, 0, 0, 12),
        (None, 0x15, "protocol", "reject", ETH_P_IP),
        ("protocol", 0x30, 0, 0, 23),
        (None, 0x15, "fragment", "reject", 6),
        ("fragment", 0x28, 0, 0, 20),
        (None, 0x45, "reject", "destination", 0x1FFF),
        ("destination", 0x20, 0, 0, 30),
        (None, 0x15, "destination_port", "source", target),
        ("source", 0x20, 0, 0, 26),
        (None, 0x15, "source_port", "reject", target),
        ("destination_port", 0xB1, 0, 0, 14),
        (None, 0x48, 0, 0, 16),
        (None, 0x15, "accept", "reject", config.port),
        ("source_port", 0xB1, 0, 0, 14),
        (None, 0x48, 0, 0, 14),
        (None, 0x15, "accept", "reject", config.port),
        ("accept", 0x06, 0, 0, SNAPLEN),
        ("reject", 0x06, 0, 0, 0),
    ]
    labels = {row[0]: index for index, row in enumerate(instructions) if row[0]}
    return tuple(
        (
            code,
            labels[yes] - index - 1 if isinstance(yes, str) else yes,
            labels[no] - index - 1 if isinstance(no, str) else no,
            value,
        )
        for index, (_, code, yes, no, value) in enumerate(instructions)
    )


def attach_filter(capture, program):
    class Instruction(ctypes.Structure):
        _fields_ = [
            ("code", ctypes.c_ushort), ("jt", ctypes.c_ubyte),
            ("jf", ctypes.c_ubyte), ("k", ctypes.c_uint32),
        ]

    class Program(ctypes.Structure):
        _fields_ = [("length", ctypes.c_ushort), ("instructions", ctypes.POINTER(Instruction))]

    rows = (Instruction * len(program))(*(Instruction(*row) for row in program))
    descriptor = Program(len(program), rows)
    # setsockopt copies the pointed-to instructions while both objects are alive.
    capture.setsockopt(socket.SOL_SOCKET, SO_ATTACH_FILTER, bytes(descriptor))


@dataclass
class Flow:
    isn: object = None
    segments: list = field(default_factory=list)
    acknowledgements: list = field(default_factory=list)
    fin_sequence: object = None
    reset: bool = False
    response_bytes: int = 0
    first_seen: object = None
    last_seen: object = None
    problems: set = field(default_factory=set)


class Audit:
    """Reassemble client bytes by sequence; an ambiguity can never become PASS."""

    def __init__(self, config):
        self.config = config
        self.target = ipaddress.IPv4Address(config.host).packed
        self.flows = []
        self.current = {}
        self.problems = set()
        self.packets = self.bytes = 0

    def feed(self, packet, *, truncated=False, observed_at=None):
        self.packets += 1
        self.bytes += len(packet)
        if self.packets > MAX_PACKETS or self.bytes > MAX_BYTES:
            self.problems.add("capture_budget_exceeded")
            return False
        if truncated:
            self.problems.add("truncated_packet")
        if len(packet) < 54 or packet[12:14] != b"\x08\x00":
            self.problems.add("unsupported_or_short_packet")
            return True
        ip = packet[14:]
        ihl, total = (ip[0] & 15) * 4, int.from_bytes(ip[2:4], "big")
        if ip[0] >> 4 != 4 or ihl < 20 or total < ihl + 20 or len(ip) < total:
            self.problems.add("invalid_or_truncated_ipv4")
            return True
        if ip[9] != 6:
            self.problems.add("filter_scope_mismatch")
            return True
        if int.from_bytes(ip[6:8], "big") & 0x3FFF:
            self.problems.add("ipv4_fragmentation")
            return True
        tcp = ip[ihl:total]
        source, destination, sequence, acknowledgement = struct.unpack("!HHII", tcp[:12])
        header = (tcp[12] >> 4) * 4
        if header < 20 or len(tcp) < header:
            self.problems.add("invalid_tcp_header")
            return True
        outbound = ip[16:20] == self.target and destination == self.config.port
        inbound = ip[12:16] == self.target and source == self.config.port
        if outbound == inbound:
            self.problems.add("filter_scope_mismatch")
            return True
        key = (ip[12:16], source) if outbound else (ip[16:20], destination)
        flags, payload = tcp[13], tcp[header:]
        flow = self.current.get(key)
        if outbound and flags & 2 and not flags & 16:
            if flow is not None and flow.isn is not None and flow.isn != sequence:
                if flow.fin_sequence is None and not flow.reset:
                    flow.problems.add("tuple_reused_before_close")
                flow = None
        if flow is None:
            if len(self.flows) >= MAX_FLOWS:
                self.problems.add("flow_budget_exceeded")
                return False
            flow = Flow()
            self.current[key] = flow
            self.flows.append(flow)
        if flow.first_seen is None:
            flow.first_seen = observed_at
        flow.last_seen = observed_at
        if outbound:
            if flags & 2:
                if flags & 16:
                    flow.problems.add("unexpected_client_syn_ack")
                flow.isn = sequence
            if payload:
                flow.segments.append(((sequence + bool(flags & 2)) & 0xFFFFFFFF, payload))
            if flags & 1:
                end = (sequence + len(payload) + bool(flags & 2)) & 0xFFFFFFFF
                if flow.fin_sequence is not None and flow.fin_sequence != end:
                    flow.problems.add("conflicting_fin")
                flow.fin_sequence = end
        else:
            if flags & 16:
                flow.acknowledgements.append(acknowledgement)
            flow.response_bytes += len(payload)
        flow.reset |= bool(flags & 4)
        return True

    def finish(self, *, kernel_packets=None, kernel_drops=None):
        counts = {"system_queries": 0, "channel_queries": 0, "write_frames": 0,
                  "other_frames": 0, "unparsed_bytes": 0, "client_bytes": 0}
        problems = set(self.problems)
        if kernel_packets is None or kernel_drops is None:
            problems.add("capture_statistics_unavailable")
        else:
            if kernel_drops:
                problems.add("kernel_packet_drops")
            if kernel_packets != self.packets + kernel_drops:
                problems.add("packet_statistics_mismatch")
        responses = 0
        for flow in self.flows:
            problems.update(flow.problems)
            responses += flow.response_bytes
            if flow.isn is None:
                problems.add("stream_start_not_observed")
                continue
            origin = (flow.isn + 1) & 0xFFFFFFFF
            values = {}
            for sequence, payload in flow.segments:
                offset = (sequence - origin) & 0xFFFFFFFF
                if offset + len(payload) > MAX_STREAM:
                    problems.add("stream_range_or_budget_exceeded")
                    continue
                for index, value in enumerate(payload, offset):
                    if index in values and values[index] != value:
                        problems.add("conflicting_retransmission")
                    values.setdefault(index, value)
            end = max(values, default=-1) + 1
            if flow.fin_sequence is not None:
                fin = (flow.fin_sequence - origin) & 0xFFFFFFFF
                if fin != end:
                    problems.add("unobserved_bytes_before_fin")
            elif not flow.reset:
                problems.add("stream_end_not_observed")
            acknowledged = max(
                ((value - origin) & 0xFFFFFFFF for value in flow.acknowledgements), default=0
            )
            allowance = end + (flow.fin_sequence is not None)
            if acknowledged > allowance:
                problems.add("acknowledgement_exceeds_observed_bytes")
            if end and acknowledged < end:
                problems.add("client_payload_not_acknowledged")
            prefix = 0
            while prefix in values:
                prefix += 1
            if prefix != end:
                problems.add("tcp_sequence_gap")
            stream = bytes(values[index] for index in range(prefix))
            counts["client_bytes"] += len(values)
            cursor = 0
            while cursor + 20 <= len(stream):
                command = stream[cursor:cursor + 20]
                if command == SYSTEM_QUERY:
                    counts["system_queries"] += 1
                elif command == CHANNEL_QUERY:
                    counts["channel_queries"] += 1
                elif command[0] == 0xF1 and command[-1] == 0xF3:
                    counts["write_frames" if command[2] == 0xFA else "other_frames"] += 1
                else:
                    break
                cursor += 20
            counts["unparsed_bytes"] += len(values) - cursor
        if counts["unparsed_bytes"]:
            problems.add("unparsed_or_partial_client_payload")
        if not counts["system_queries"] or not counts["channel_queries"] or not responses:
            problems.add("positive_control_not_observed")
        status = (
            "WRITE_OBSERVED" if counts["write_frames"] else
            "OTHER_COMMAND_OBSERVED" if counts["other_frames"] else
            "INCONCLUSIVE" if problems else "QUERY_ONLY_OBSERVED"
        )
        return {
            "schema_version": 1, "status": status, "no_write_proof": False,
            "scope": "configured_interface_and_exact_ipv4_tcp_endpoint",
            "lifecycle_interval_coverage": "REQUIRES_OPERATOR_CORRELATION",
            "counts": counts, "connections": len(self.flows), "packets": self.packets,
            "response_bytes": responses, "kernel_packets": kernel_packets,
            "kernel_drops": kernel_drops, "visibility_problems": sorted(problems),
            "connection_windows": [
                {"first_monotonic_seconds": flow.first_seen,
                 "last_monotonic_seconds": flow.last_seen}
                for flow in self.flows
            ],
        }


def private_configuration(path):
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        info = os.fstat(descriptor)
        if (not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o600
                or info.st_uid != os.geteuid() or info.st_size > 4096):
            raise ValueError("private configuration permissions or size are invalid")
        with os.fdopen(descriptor, "r", encoding="utf-8", closefd=False) as source:
            return Configuration.parse(json.load(source))
    finally:
        os.close(descriptor)


class Report:
    def __init__(self, path):
        self.path = Path(path)
        parent = self.path.parent.stat()
        if (not self.path.is_absolute() or self.path.exists() or self.path.is_symlink()
                or not stat.S_ISDIR(parent.st_mode) or stat.S_IMODE(parent.st_mode) != 0o700
                or parent.st_uid != os.geteuid()):
            raise ValueError("a new report in an owner-only private directory is required")

    def write(self, data):
        descriptor, name = tempfile.mkstemp(prefix=".audit-", dir=self.path.parent)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as output:
                os.fchmod(output.fileno(), 0o600)
                json.dump(data, output, sort_keys=True)
                output.write("\n")
                output.flush()
                os.fsync(output.fileno())
            os.replace(name, self.path)
        finally:
            if os.path.exists(name):
                os.unlink(name)


def capture(config, report, *, clock=time.monotonic):
    audit, stopping = Audit(config), False

    def stop(*_args):
        nonlocal stopping
        stopping = True

    for name in ("SIGTERM", "SIGINT", "SIGHUP"):
        signal.signal(getattr(signal, name), stop)
    # Protocol zero cannot receive packets. Install the narrow filter first,
    # then activate only one existing interface, without membership/promiscuity.
    with socket.socket(socket.AF_PACKET, socket.SOCK_RAW, 0) as observer:
        attach_filter(observer, capture_filter(config))
        # ETH_P_ALL supplies outgoing taps too; the already-installed kernel
        # filter rejects everything except the exact IPv4/TCP endpoint.
        observer.bind((config.interface, ETH_P_ALL))
        started = clock()
        report.write({"status": "READY", "started_monotonic_seconds": started})
        end = started + config.duration_seconds
        observer.settimeout(0.25)
        try:
            while not stopping and clock() < end:
                observer.settimeout(min(0.25, max(0.001, end - clock())))
                try:
                    packet, _, flags, _ = observer.recvmsg(SNAPLEN)
                except socket.timeout:
                    continue
                if not audit.feed(packet, truncated=bool(flags & socket.MSG_TRUNC),
                                  observed_at=clock()):
                    break
        except OSError:
            audit.problems.add("capture_receive_failed")
        # Stop accepting new packets before draining the bounded pending queue.
        attach_filter(observer, ((0x06, 0, 0, 0),))
        stopped = clock()
        observer.setblocking(False)
        while clock() - stopped < 0.5:
            try:
                packet, _, flags, _ = observer.recvmsg(SNAPLEN)
            except BlockingIOError:
                break
            if not audit.feed(packet, truncated=bool(flags & socket.MSG_TRUNC),
                              observed_at=clock()):
                break
        else:
            audit.problems.add("capture_drain_budget_exceeded")
        try:
            packets, drops = struct.unpack("II", observer.getsockopt(
                SOL_PACKET, PACKET_STATISTICS, 8
            ))
        except OSError:
            packets = drops = None
    result = audit.finish(kernel_packets=packets, kernel_drops=drops)
    result.update(started_monotonic_seconds=started, stopped_monotonic_seconds=stopped,
                  duration_seconds=round(stopped - started, 6), stopped_by_signal=stopping)
    report.write(result)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        result = capture(private_configuration(args.config), Report(args.report))
    except BaseException:
        print('{"status":"INCONCLUSIVE","reason":"audit_setup_or_capture_failed"}')
        return 1
    print(json.dumps({"status": result["status"]}))
    return 0 if result["status"] == "QUERY_ONLY_OBSERVED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
