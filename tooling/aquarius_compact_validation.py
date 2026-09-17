"""Bounded native compact-control acceptance; independent of the production mixer.

Run only the frozen, independently reviewed worker on the authorized HA-side host.
The token arrives on stdin. Unknown completion permanently prohibits writes.
Cleanup can send one Automatic command and can never replay channel snapshots.
"""

from __future__ import annotations

import argparse
import ipaddress
import json
import os
import re
import signal
import socket
import ssl
import stat
import sys
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlsplit

if __package__:
    from . import aquarius_automatic_composite as observations
    from . import aquarius_ha_validation as legacy
    from . import aquarius_task004_validation as direct
    from . import aquarius_validation as base
else:
    import aquarius_automatic_composite as observations
    import aquarius_ha_validation as legacy
    import aquarius_task004_validation as direct
    import aquarius_validation as base

MAX_OUTPUT = 5
HACompletionUnknown = legacy.HACompletionUnknown
HAServiceError = legacy.HAServiceError


def _percent(value):
    if type(value) is not int or not 0 <= value <= MAX_OUTPUT:
        raise ValueError("acceptance intensity must be an integer from zero to five")
    return value


@dataclass(frozen=True)
class Action:
    kind: str
    rgb_color: tuple[int, ...] | None
    intensity: int | None
    expected_channels: tuple[int, ...]

    @property
    def mode(self):
        return 8 if not any(self.expected_channels) else 1

    @classmethod
    def parse(cls, data):
        if not isinstance(data, dict):
            raise ValueError("each action must be an explicit object")
        kind = data.get("kind")
        fields = {"kind", "expected_channels"}
        if kind == "colour":
            if set(data) not in (fields | {"rgb_color"}, fields | {"rgb_color", "intensity"}):
                raise ValueError("colour requires only RGB and optional intensity")
            rgb = data["rgb_color"]
            if (
                not isinstance(rgb, list)
                or len(rgb) != 3
                or any(type(value) is not int or not 0 <= value <= 255 for value in rgb)
            ):
                raise ValueError("RGB requires three exact byte values")
            rgb = tuple(rgb)
            level = _percent(data["intensity"]) if "intensity" in data else None
            zero = not any(rgb) or level == 0
        elif kind == "intensity" and set(data) == fields | {"value"}:
            rgb, level = None, _percent(data["value"])
            zero = level == 0
        else:
            raise ValueError("only declared colour and Intensity Number actions are supported")
        expected = data["expected_channels"]
        if not isinstance(expected, list) or len(expected) != 6:
            raise ValueError("each action needs six independently supplied expected levels")
        expected = tuple(_percent(value) for value in expected)
        if zero != (not any(expected)):
            raise ValueError("expected output contradicts the explicit zero/nonzero request")
        return cls(kind, rgb, level, expected)


@dataclass(frozen=True)
class Configuration:
    device: base.Configuration
    scheme: str
    host: str
    port: int
    light_entity: str
    intensity_entity: str
    mode_status_entity: str
    actions: tuple[Action, ...]

    @property
    def experiment_seconds(self):
        return 3.0 if len(self.actions) == 1 else 6.0

    @property
    def cleanup_seconds(self):
        return 9.5 if len(self.actions) == 1 else 19.5

    @property
    def maximum_seconds(self):
        return self.cleanup_seconds + 0.5

    @classmethod
    def parse(cls, data, *, simulation=False):
        if (
            not isinstance(data, dict)
            or set(data) != {"schema_version", "device", "ha", "actions"}
            or type(data["schema_version"]) is not int
            or data["schema_version"] != 1
        ):
            raise ValueError("invalid compact acceptance configuration")
        device = data["device"]
        if not isinstance(device, dict) or set(device) != {
            "schema_version",
            "host",
            "port",
            "profile",
        }:
            raise ValueError("one exact device endpoint and profile are required")
        # Reuse the strict private endpoint/profile parser. Its single-channel
        # fields are inert compatibility values; no channel operation is reused.
        parsed = base.Configuration.parse(
            {**device, "channel_index": 0, "delta": -1}, simulation=simulation
        )
        ha = data["ha"]
        if not isinstance(ha, dict) or set(ha) != {
            "origin",
            "light_entity",
            "intensity_entity",
            "mode_status_entity",
        }:
            raise ValueError("one exact HA origin and three owned entities are required")
        if not isinstance(ha["origin"], str):
            raise ValueError("HA origin must be an explicit endpoint")
        origin = urlsplit(ha["origin"])
        if (
            origin.scheme not in ("http", "https")
            or origin.path not in ("", "/")
            or origin.username is not None
            or origin.password is not None
            or origin.query
            or origin.fragment
        ):
            raise ValueError("HA origin must contain only scheme, address and port")
        address = ipaddress.ip_address(origin.hostname)
        private = address.version == 4 and any(
            address in ipaddress.ip_network(network)
            for network in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16")
        )
        if not private and not (simulation and address.version == 4 and address.is_loopback):
            raise ValueError("HA must be an explicitly selected private IPv4 endpoint")
        port = origin.port if origin.port is not None else (443 if origin.scheme == "https" else 80)
        if not 1 <= port <= 65535:
            raise ValueError("invalid HA port")
        for key, prefix in (
            ("light_entity", "light.aquarius_plant_led_lamp"),
            ("intensity_entity", "number.aquarius_plant_led_intensity"),
            ("mode_status_entity", "sensor.aquarius_plant_led_mode_status"),
        ):
            if not isinstance(ha[key], str) or not re.fullmatch(
                re.escape(prefix) + r"(?:_[1-9][0-9]*)?", ha[key]
            ):
                raise ValueError("an exact supported Aquarius entity is required")
        actions = data["actions"]
        if not isinstance(actions, list) or not 1 <= len(actions) <= 3:
            raise ValueError("one to three immutable acceptance actions are required")
        return cls(
            parsed,
            origin.scheme,
            str(address),
            port,
            ha["light_entity"],
            ha["intensity_entity"],
            ha["mode_status_entity"],
            tuple(Action.parse(action) for action in actions),
        )


class Service(legacy.HAService):
    """Fixed routes and immutable planned payloads; no retry or redirect."""

    def call(self, index, deadline):
        if type(index) is not int or index not in range(len(self.config.actions)):
            raise ValueError("service request must identify one configured action")
        action = self.config.actions[index]
        if action.kind == "colour":
            path = "/api/services/light/turn_on"
            payload = {"entity_id": self.config.light_entity, "rgb_color": action.rgb_color}
            if action.intensity is not None:
                payload["brightness_pct"] = action.intensity
        else:
            path = "/api/services/number/set_value"
            payload = {"entity_id": self.config.intensity_entity, "value": action.intensity}
        body = json.dumps(payload, separators=(",", ":")).encode("ascii")
        request = (
            f"POST {path} HTTP/1.1\r\nHost: {self.config.host}:{self.config.port}\r\n"
            f"Authorization: Bearer {self.token}\r\nContent-Type: application/json\r\n"
            f"Content-Length: {len(body)}\r\nConnection: close\r\n\r\n"
        ).encode("ascii") + body
        connection, delivered = None, False
        try:
            connection = socket.create_connection(
                (self.config.host, self.config.port), timeout=self._remaining(deadline)
            )
            if self.config.scheme == "https":
                connection.settimeout(self._remaining(deadline))
                connection = ssl.create_default_context().wrap_socket(
                    connection, server_hostname=self.config.host
                )
            connection.settimeout(self._remaining(deadline))
            delivered = True
            connection.sendall(request)
            header = bytearray()
            while b"\r\n\r\n" not in header:
                connection.settimeout(self._remaining(deadline))
                chunk = connection.recv(1024)
                if not chunk:
                    raise HACompletionUnknown("HA closed before successful service completion")
                header.extend(chunk)
                if len(header) > legacy.MAX_HTTP_HEADER_BYTES:
                    raise HACompletionUnknown("HA response headers exceeded their limit")
            status = re.fullmatch(
                rb"HTTP/1\.[01] ([0-9]{3})(?: [\x20-\x7e]*)?",
                bytes(header).split(b"\r\n", 1)[0],
            )
            if status is None:
                raise HACompletionUnknown("HA service status was not supported")
            if int(status[1]) in (400, 401, 403, 404):
                raise HAServiceError("HA rejected the configured service request")
            if int(status[1]) != 200:
                raise HACompletionUnknown("HA did not establish successful completion")
        except HAServiceError:
            raise
        except (OSError, ValueError, base.DeadlineError):
            if delivered:
                raise HACompletionUnknown("HA delivery or completion is uncertain") from None
            raise HAServiceError("HA connection failed before delivery") from None
        finally:
            if connection is not None:
                connection.close()


class CompactWorker(base.ValidationWorker):
    """Exact compact states belong to this run; Automatic percentages never do."""

    def __init__(self, config, token, *, service_factory=Service, reader_factory=None, **kwargs):
        kwargs.setdefault("session_factory", direct.ShutdownWireSession)
        super().__init__(config.device, **kwargs)
        self.plan = config
        self.service = service_factory(config, token, self.clock)
        adapter = SimpleNamespace(service=config, mode_status_entity=config.mode_status_entity)
        self.reader = (reader_factory or observations.HAStateReader)(adapter, token, self.clock)
        self.owned = None
        self.read_modes = (0,)
        self.rejected_observation = False
        self.completion_unknown = False
        self.pending_until = None
        self.cleanup_sent = False
        self.completed_actions = 0
        self.report.update(
            action="compact_native_plan",
            ha_completion="NOT_SENT",
            maximum_excursion_seconds=config.maximum_seconds,
            experiment_phase_seconds=config.experiment_seconds,
            recovery_reserved_seconds=config.cleanup_seconds - config.experiment_seconds,
            final_read_deadline_seconds=config.cleanup_seconds,
            channel_writes_permitted=False,
            cleanup_mode=0,
            actions=[],
        )

    def _unsafe(self, message):
        self.rejected_observation = True
        raise base.UnsafeState(message)

    def _read(self, deadline, *, fresh=False):
        self._check_stop()
        if fresh or self.session is None:
            self._connect(deadline)
        self.io_phase = "state_query"
        try:
            state = self.session.read_state(deadline)
        except (OSError, EOFError):
            observed = getattr(self.session, "last_system", None)
            if observed is not None and (
                observed[0] not in self.read_modes or tuple(observed[1:]) != self.config.profile
            ):
                self._unsafe("contradictory system observation preceded a transport failure")
            raise
        except base.UnsafeState:
            self.rejected_observation = True
            raise
        if state.profile != self.config.profile or state.mode not in self.read_modes:
            self._unsafe("profile or mode contradicts the owned phase")
        self._check_stop()
        return state

    def _require_owned(self, current):
        if current != self.owned:
            self._unsafe("the exact owned channel vector changed before actuation")

    def _ha_mode(self, expected, deadline):
        self._close()
        self.io_phase = "ha_state_read"
        observed = self.reader.read(self.plan.mode_status_entity, deadline)
        if observed["state"] != {0: "following_schedule", 1: "manual_override", 8: "off"}[expected]:
            self._unsafe("native HA mode status contradicts independent lamp state")

    def _actuate(self, index, deadline):
        self._check_stop()
        if self.completion_unknown or self.rejected_observation:
            raise base.UnsafeState("an unsafe or uncertain observation forbids another action")
        if index:
            self._require_owned(self._read(deadline, fresh=True))
        self._close()
        if deadline - self.clock() < base.WRITE_RECOVERY_MARGIN:
            raise base.DeadlineError("insufficient phase allowance for HA action and readback")
        action = self.plan.actions[index]
        sent_at = self.clock()
        self.io_phase = "ha_service"
        self._event("ha_action_send", index=index, kind=action.kind)
        try:
            self.service.call(index, min(deadline, sent_at + legacy.HA_COORDINATOR_SECONDS))
        except HACompletionUnknown:
            self.completion_unknown = True
            self.pending_until = (
                sent_at + legacy.HA_COORDINATOR_SECONDS + legacy.UNCERTAIN_SETTLE_MARGIN
            )
            self.report["ha_completion"] = "UNKNOWN"
            raise
        except HAServiceError:
            self.report["ha_completion"] = "REJECTED_OR_NOT_DELIVERED"
            raise
        except BaseException:
            # An unexpected transport/adapter failure is not evidence that the
            # service was never admitted. Fail closed even for an interruption.
            self.completion_unknown = True
            self.pending_until = (
                sent_at + legacy.HA_COORDINATOR_SECONDS + legacy.UNCERTAIN_SETTLE_MARGIN
            )
            self.report["ha_completion"] = "UNKNOWN"
            raise
        self.report["ha_completion"] = "HTTP_COMPLETED"
        self.owned = replace(self.baseline, mode=action.mode, channels=action.expected_channels)
        self.read_modes = (action.mode,)
        self._event("ha_action_completed", index=index)
        self._check_stop()
        observed = self._read(deadline, fresh=True)
        self._require_owned(observed)
        self._ha_mode(action.mode, deadline)
        if self.clock() >= deadline:
            raise base.DeadlineError("experiment phase exhausted")
        self.completed_actions += 1
        self.report["actions"].append(
            {"index": index, "completion": "HTTP_COMPLETED", "state": "PASS"}
        )
        self._event("action_confirmed", index=index, state=asdict(observed))

    def _command(self, channels, mode, deadline, stage):
        if (
            channels is not None
            or mode != 0
            or not self.cleaning
            or self.cleanup_sent
            or self.completion_unknown
            or self.rejected_observation
        ):
            raise base.UnsafeState("only one guarded Automatic cleanup command is permitted")
        self.cleanup_sent = True
        self.read_modes = (0,)
        return super()._command(None, 0, deadline, stage)

    def _recover(self, deadline):
        self._event("recovery_started")
        if self.completion_unknown or self.rejected_observation:
            if self.completion_unknown:
                legacy.HAValidationWorker._settle_uncertain(self, deadline)
            self.read_modes = (0, 1, 8)
            observed = self._fresh_recovery_read(deadline, reserve=0.0, stage="failure_observation")
            self._event("failure_observed_without_write", automatic_observed=observed.mode == 0)
            raise base.UnsafeState("unknown completion or contradiction prohibits cleanup writes")
        self.read_modes = tuple({self.owned.mode, 0})
        current = self._fresh_recovery_read(
            deadline, reserve=base.RECOVERY_COMMAND_RESERVE, stage="automatic_cleanup_guard"
        )
        if current.mode == 0:
            self._event("automatic_already_active_preserved", state=asdict(current))
            return
        self._require_owned(current)
        self._event("automatic_cleanup_guard_confirmed", state=asdict(current))
        restored = self._command(None, 0, deadline, "restore_automatic")
        if restored.profile != self.config.profile or restored.mode != 0:
            self._unsafe("Automatic recovery was not independently confirmed")
        self._event("automatic_recovery_confirmed", state=asdict(restored))

    def run(self):
        experiment_ok = recovery_ok = False
        try:
            deadline = self.started + base.PREFLIGHT_SECONDS
            self._event("preflight_started")
            first = self._read(deadline, fresh=True)
            self.baseline = self._read(deadline, fresh=True)
            if first != self.baseline or max(self.baseline.channels) > MAX_OUTPUT:
                self._unsafe("preflight requires stable Automatic output no greater than five")
            self.owned = self.baseline
            self._ha_mode(0, deadline)
            self._event(
                "experiment_intent",
                baseline=asdict(self.baseline),
                plan=[asdict(a) for a in self.plan.actions],
            )
            # Every sink/fsync precedes the final complete guard. No subsequent
            # persistence or HA GET can make this initial baseline stale.
            self._require_owned(self._read(deadline, fresh=True))
            self._close()
            self._check_stop()
            self.excursion_started = self.clock()
            self.report["recovery"] = "PENDING"
            for index in range(len(self.plan.actions)):
                self._actuate(index, self.excursion_started + self.plan.experiment_seconds)
            experiment_ok = True
            self.report["experiment"] = "PASS"
        except BaseException as error:
            if isinstance(error, base.UnsafeState):
                self.rejected_observation = True
            self.report["experiment"] = (
                "FAIL" if self.excursion_started is not None else "NOT_TESTED"
            )
            self._event(
                "experiment_failed", reason=type(error).__name__, phase=self._failure_phase()
            )
        finally:
            if self.excursion_started is not None:
                self.cleaning = True
                try:
                    self._recover(self.excursion_started + self.plan.cleanup_seconds)
                    self.recovery_confirmed_at = self.clock()
                    recovery_ok = (
                        self.recovery_confirmed_at - self.excursion_started
                        <= self.plan.maximum_seconds
                    )
                    self.report["recovery"] = "PASS" if recovery_ok else "FAIL"
                except BaseException as error:
                    self.report["recovery"] = "FAIL"
                    self._event(
                        "recovery_unconfirmed",
                        reason=type(error).__name__,
                        phase=self._failure_phase(),
                    )
            self._close()
        self.report["status"] = (
            "PASS" if experiment_ok and recovery_ok and not self.interrupted else "FAIL"
        )
        self.report["interrupted"] = self.interrupted
        self.report["excursion_seconds"] = (
            round((self.recovery_confirmed_at or self.clock()) - self.excursion_started, 6)
            if self.excursion_started is not None
            else None
        )
        self.report["completed_actions"] = self.completed_actions
        self._event("finished")
        if self.report.get("reporting_error"):
            self.report["status"] = "FAIL"
        return self.report


def _configuration(path, *, simulation=False):
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        info = os.fstat(descriptor)
        if (
            not stat.S_ISREG(info.st_mode)
            or stat.S_IMODE(info.st_mode) != 0o600
            or info.st_uid != os.geteuid()
            or info.st_size > 16384
        ):
            raise ValueError("configuration must be a bounded owner-only regular file")
        with os.fdopen(descriptor, "r", encoding="utf-8", closefd=False) as source:
            data = json.load(
                source,
                object_pairs_hook=observations._unique_object,
                parse_constant=observations._reject_constant,
            )
        return Configuration.parse(data, simulation=simulation)
    finally:
        os.close(descriptor)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument(
        "--check-config", action="store_true", help="validate only; no token or network"
    )
    args = parser.parse_args(argv)
    try:
        config = _configuration(args.config)
        if args.check_config:
            print(json.dumps({"status": "CONFIG_VALID", "actions": len(config.actions)}))
            return 0
        if args.report is None:
            raise ValueError("a new private report is required")
        token = sys.stdin.read(legacy.MAX_TOKEN_BYTES + 1).removesuffix("\n")
        worker = CompactWorker(config, token, sink=base.PrivateReport(args.report))
        for name in ("SIGINT", "SIGTERM", "SIGHUP"):
            signal.signal(getattr(signal, name), worker.request_stop)
        result = worker.run()
    except BaseException:
        print('{"status":"FAIL","reason":"worker_setup_or_reporting_failed"}')
        return 1
    print(json.dumps({key: result[key] for key in ("status", "experiment", "recovery")}))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
