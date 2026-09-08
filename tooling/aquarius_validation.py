"""Autonomous, bounded HA-side Aquarius validation; standard library only.

This operator tool is not part of the integration's runtime or write allowlist.
Run only after review and explicit authorization, detached on the HA-side host.
Its private JSON target/profile and private report must never enter public Git.
SIGINT, SIGTERM and SIGHUP request early cleanup; SIGKILL or network loss cannot
guarantee physical restoration. Every report distinguishes confirmed recovery
from merely attempting it. Nothing in this tool scans or provisions a network.
"""

from __future__ import annotations

import argparse
import ipaddress
import json
import os
import signal
import socket
import stat
import tempfile
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Optional

MAX_EXCURSION = 10.0
EXPERIMENT_SECONDS = 3.0
RECOVERY_DEADLINE_SECONDS = 9.5
PREFLIGHT_SECONDS = 8.0
IO_TIMEOUT = 0.8
WRITE_RECOVERY_MARGIN = 1.8
QUERY_PAUSE = 0.2
MANUAL_PAUSE = 0.1
WRITE_DRAIN_PAUSE = 0.2
MAX_RECEIVED = 32768
MAX_BUFFER = 4096


class ValidationError(Exception):
    """A bounded operation failed without exposing private endpoint/reply data."""


class DeadlineError(ValidationError):
    """A phase exhausted its own budget, preserving a separate cleanup reserve."""


class UnsafeState(ValidationError):
    """Current state cannot safely justify another output command."""


class StopRequested(BaseException):
    """An operator signal requests immediate finally-based cleanup."""


def frame(payload: bytes) -> bytes:
    if len(payload) > 18:
        raise ValueError("unsupported payload")
    return b"\xf1" + payload.ljust(18, b"\0") + b"\xf3"


SYSTEM_QUERY = frame(b"\xe1\xfc")
CHANNEL_QUERY = frame(b"\xe2\xfc")


@dataclass(frozen=True)
class State:
    mode: int
    controller: tuple[int, int]
    version: tuple[int, int]
    count: int
    channels: tuple[int, ...]

    @property
    def profile(self):
        return self.controller, self.version, self.count


@dataclass(frozen=True)
class Configuration:
    host: str
    port: int
    controller: tuple[int, int]
    version: tuple[int, int]
    count: int
    channel: int
    delta: int

    @property
    def profile(self):
        return self.controller, self.version, self.count

    @classmethod
    def parse(cls, data: dict, *, simulation: bool = False):
        """Require an explicit endpoint and isolated profile; no shipped guard changes."""
        required = {"schema_version", "host", "port", "profile", "channel_index", "delta"}
        if (
            not isinstance(data, dict)
            or set(data) != required
            or type(data["schema_version"]) is not int
            or data["schema_version"] != 1
        ):
            raise ValueError("invalid validation configuration")
        host = str(ipaddress.ip_address(data["host"]))
        address = ipaddress.ip_address(host)
        networks = ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16")
        if not any(address in ipaddress.ip_network(network) for network in networks) and not (
            simulation and address.is_loopback
        ):
            raise ValueError("an explicitly selected private IPv4 target is required")
        if type(data["port"]) is not int or not 1 <= data["port"] <= 65535:
            raise ValueError("invalid target port")
        if not simulation and data["port"] != 8080:
            raise ValueError("only the authorized protocol port is supported")
        profile = data["profile"]
        if not isinstance(profile, dict) or set(profile) != {
            "controller_bytes",
            "version_bytes",
            "channel_count_raw",
        }:
            raise ValueError("an exact validation-only profile is required")
        pairs = []
        for key in ("controller_bytes", "version_bytes"):
            values = profile[key]
            if (
                not isinstance(values, list)
                or len(values) != 2
                or any(type(value) is not int or not 0 <= value <= 255 for value in values)
            ):
                raise ValueError("invalid raw profile bytes")
            pairs.append(tuple(values))
        if type(profile["channel_count_raw"]) is not int or profile["channel_count_raw"] != 6:
            raise ValueError("only the six-channel family can be validated")
        channel, delta = data["channel_index"], data["delta"]
        if type(channel) is not int or channel not in range(6):
            raise ValueError("invalid channel index")
        if type(delta) is not int or not 1 <= abs(delta) <= 5:
            raise ValueError("one channel may change by one to five percentage points")
        return cls(host, data["port"], pairs[0], pairs[1], 6, channel, delta)


def _channels(values):
    values = tuple(values)
    if len(values) != 6 or any(type(value) is not int or not 0 <= value <= 100 for value in values):
        raise UnsafeState("invalid six-channel percentage response")
    return values


def channel_frame(values, controller):
    values = list(_channels(values))
    if controller == (0x14, 0x32):
        values[2], values[3] = values[3], values[2]
    return frame(b"\xe2\xfa" + bytes(values))


def mode_frame(mode):
    if type(mode) is not int or mode not in (0, 1):
        raise UnsafeState("validation only permits Manual or Automatic")
    return frame(bytes((0xE1, 0xFA, 0xDB, mode)))


class Decoder:
    """Bounded core/extended decoder; interior markers never delimit a frame."""

    def __init__(self):
        self.buffer = bytearray()

    def feed(self, data):
        if len(self.buffer) + len(data) > MAX_BUFFER:
            raise UnsafeState("receive buffer exceeded")
        self.buffer.extend(data)
        messages = []
        while self.buffer:
            first = self.buffer[0]
            if first == 0xF1:
                if len(self.buffer) < 20:
                    break
                if self.buffer[19] != 0xF3:
                    raise UnsafeState("malformed core frame")
                messages.append(bytes(self.buffer[:20]))
                del self.buffer[:20]
            elif first == 1:
                header = b"\x01\xfe\x68"
                prefix = min(3, len(self.buffer))
                if self.buffer[:prefix] != header[:prefix]:
                    raise UnsafeState("malformed extended header")
                if len(self.buffer) < 4:
                    break
                size = 7 + self.buffer[3]
                if len(self.buffer) < size:
                    break
                if self.buffer[size - 3 : size] != b"\x67\xfd\x02":
                    raise UnsafeState("malformed extended trailer")
                del self.buffer[:size]
            elif first in (0xF5, 0xF6):
                del self.buffer[0]
            else:
                raise UnsafeState("unexpected unframed response")
        return messages


class WireSession:
    """Native TCP transport; a fresh connection verifies channel output after writes."""

    def __init__(self, config, deadline, clock=time.monotonic):
        self.config = config
        self.clock = clock
        self.decoder = Decoder()
        self.received = 0
        self.socket = socket.create_connection(
            (config.host, config.port), timeout=self._timeout(deadline)
        )

    def _timeout(self, deadline):
        remaining = deadline - self.clock()
        if remaining <= 0:
            raise DeadlineError("phase deadline reached")
        return min(IO_TIMEOUT, remaining)

    def close(self):
        self.socket.close()

    def send(self, command, deadline):
        self.socket.settimeout(self._timeout(deadline))
        self.socket.sendall(command)

    def _receive(self, deadline):
        self.socket.settimeout(self._timeout(deadline))
        data = self.socket.recv(1024)
        if not data:
            raise ValidationError("TCP connection closed before confirmation")
        self.received += len(data)
        if self.received > MAX_RECEIVED:
            raise UnsafeState("session receive limit exceeded")
        return self.decoder.feed(data)

    def quarantine(self, duration, deadline, echoes=()):
        """Drain only known write echoes, ACKs and extended frames for a fixed interval."""
        end = min(deadline, self.clock() + duration)
        if end - self.clock() < duration - 0.001:
            raise DeadlineError("insufficient time for the processing interval")
        while self.clock() < end:
            try:
                messages = self._receive(end)
            except socket.timeout:
                continue
            if any(message not in echoes for message in messages):
                raise UnsafeState("unsolicited status before an explicit query")
        if self.decoder.buffer:
            raise UnsafeState("unfinished unsolicited frame")

    def query(self, command, deadline):
        self.send(command, deadline)
        end = min(deadline, self.clock() + IO_TIMEOUT)
        while self.clock() < end:
            messages = self._receive(end)
            for response in messages:
                operations = (0xFC, 0xFA) if command == CHANNEL_QUERY else (0xFC,)
                if response[1] != command[1] or response[2] not in operations:
                    raise UnsafeState("unexpected command reply")
                if response == command:
                    raise UnsafeState("query echo is not device status")
                if len(messages) != 1 or self.decoder.buffer:
                    raise UnsafeState("extra or partial reply is ambiguous")
                return response
        raise DeadlineError("query deadline reached")

    def system(self, deadline):
        response = self.query(SYSTEM_QUERY, deadline)
        return response[4], (response[9], response[10]), (response[7], response[8]), response[11]

    def read_state(self, deadline):
        mode, controller, version, count = self.system(deadline)
        self.quarantine(QUERY_PAUSE, deadline)
        response = self.query(CHANNEL_QUERY, deadline)
        values = list(_channels(response[3:9]))
        if controller == (0x14, 0x32):
            values[2], values[3] = values[3], values[2]
        return State(mode, controller, version, count, tuple(values))


class PrivateReport:
    """Atomically persist private stage evidence; never overwrite an earlier run."""

    def __init__(self, path):
        self.path = Path(path)
        parent = self.path.parent.stat()
        if (
            not self.path.is_absolute()
            or not stat.S_ISDIR(parent.st_mode)
            or stat.S_IMODE(parent.st_mode) != 0o700
            or parent.st_uid != os.geteuid()
            or self.path.exists()
            or self.path.is_symlink()
        ):
            raise ValueError("a new report in an owner-only private directory is required")

    def __call__(self, report):
        descriptor, name = tempfile.mkstemp(prefix=".aquarius-", dir=self.path.parent)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as output:
                os.fchmod(output.fileno(), 0o600)
                json.dump(report, output, sort_keys=True)
                output.write("\n")
                output.flush()
                os.fsync(output.fileno())
            os.replace(name, self.path)
        finally:
            if os.path.exists(name):
                os.unlink(name)


class ValidationWorker:
    """One experiment and independent, guarded finally cleanup with local deadlines."""

    def __init__(
        self,
        config: Configuration,
        *,
        session_factory: Callable = WireSession,
        clock: Callable = time.monotonic,
        sink: Optional[Callable] = None,
    ):
        self.config = config
        self.factory = session_factory
        self.clock = clock
        self.sink = sink
        self.started = clock()
        self.excursion_started = None
        self.recovery_confirmed_at = None
        self.cleaning = False
        self.interrupted = False
        self.session = None
        self.baseline = None
        self.changed = None
        self.report = {
            "schema_version": 1,
            "status": "RUNNING",
            "experiment": "NOT_TESTED",
            "recovery": "NOT_REQUIRED",
            "maximum_excursion_seconds": MAX_EXCURSION,
            "experiment_phase_seconds": EXPERIMENT_SECONDS,
            "recovery_reserved_seconds": RECOVERY_DEADLINE_SECONDS - EXPERIMENT_SECONDS,
            "events": [],
        }

    def request_stop(self, *_args):
        # Signal handlers never throw asynchronously: a second signal while
        # entering finally or recording an error must not bypass restoration.
        self.interrupted = True

    def _check_stop(self):
        if self.interrupted and not self.cleaning:
            raise StopRequested()

    def _event(self, stage, **details):
        event = {"stage": stage, "elapsed_seconds": round(self.clock() - self.started, 6)}
        if self.excursion_started is not None:
            event["excursion_seconds"] = round(self.clock() - self.excursion_started, 6)
        event.update(details)
        self.report["events"].append(event)
        # Persist intent before the first write, then keep stage timings in
        # memory until cleanup finishes. Evidence fsync cannot spend the lamp's
        # recovery allowance. An interrupted worker retains its pending intent.
        if self.sink is not None and (self.excursion_started is None or stage == "finished"):
            try:
                self.sink(self.report)
            except Exception:
                # A failing evidence filesystem must never disable cleanup.
                self.sink = None
                self.report["reporting_error"] = True
                if not self.cleaning and stage != "finished":
                    raise ValidationError("private evidence could not be persisted") from None

    def _close(self):
        if self.session is not None:
            try:
                self.session.close()
            finally:
                self.session = None

    def _connect(self, deadline):
        self._check_stop()
        self._close()
        self.session = self.factory(self.config, deadline, self.clock)
        self._check_stop()

    def _read(self, deadline, *, fresh=False):
        self._check_stop()
        if fresh or self.session is None:
            self._connect(deadline)
        state = self.session.read_state(deadline)
        self._check_stop()
        if state.profile != self.config.profile or state.mode not in (0, 1):
            raise UnsafeState("profile or operating mode differs from the validation profile")
        return state

    def _command(self, channels, mode, deadline, stage):
        """One deliberate command sequence; no retries and no echoed-read confirmation."""
        self._check_stop()
        if deadline - self.clock() < WRITE_RECOVERY_MARGIN:
            raise DeadlineError("too little time remains to send and verify a command")
        echoes = []
        if channels is not None:
            command = channel_frame(channels, self.config.controller)
            self._event(stage + "_channels_send")
            self.session.send(command, deadline)
            self._check_stop()
            echoes.append(command)
            self.session.quarantine(MANUAL_PAUSE, deadline, tuple(echoes))
        command = mode_frame(mode)
        self._check_stop()
        self._event(stage + "_mode_send", mode=mode)
        self.session.send(command, deadline)
        self._check_stop()
        echoes.append(command)
        self.session.quarantine(WRITE_DRAIN_PAUSE, deadline, tuple(echoes))
        self._check_stop()
        # Keep the write connection alive until a queried system reply proves
        # the requested mode/profile. Only a new connection can confirm channels.
        actual_mode, controller, version, count = self.session.system(deadline)
        if (controller, version, count) != self.config.profile or actual_mode != mode:
            raise UnsafeState("queried system barrier did not confirm the requested mode")
        self._event(stage + "_system_barrier_confirmed", mode=mode)
        return self._read(deadline, fresh=True)

    def _recover(self, deadline):
        self._event("recovery_started")
        current = self._read(deadline, fresh=True)
        self._event("recovery_guard_confirmed", state=asdict(current))
        baseline = self.baseline
        if baseline.mode == 1 and current.mode != 1:
            raise UnsafeState("a competing mode change prevents manual snapshot restoration")
        if self.report["experiment"] == "PASS" and current.mode != 1:
            self._event(
                "recovery_competing_mode_observed", original_mode=current.mode == baseline.mode
            )
            raise UnsafeState("mode changed after verified Manual output; preserve competing state")
        if current == baseline:
            self._event("recovery_already_original")
            return
        if (
            baseline.mode == 0
            and current.mode == 0
            and current.channels not in (baseline.channels, self.changed)
        ):
            # An active automatic program may have advanced while status was
            # uncertain. It is safer to preserve it than replay stale percentages.
            self._event("recovery_automatic_active_snapshot_not_replayed", original_mode=True)
            raise UnsafeState(
                "automatic is active but uncertain channels do not confirm restoration"
            )
        if current.channels not in (baseline.channels, self.changed):
            raise UnsafeState("competing channel changes prevent snapshot restoration")
        if current.channels != baseline.channels:
            current = self._command(baseline.channels, 1, deadline, "restore_channels")
            if current.channels != baseline.channels or current.mode != 1:
                raise UnsafeState("restored channel values were not independently confirmed")
            self._event("restore_channels_confirmed")
        if current.mode != baseline.mode:
            # Mode restoration is a separately held, queried and verified action.
            current = self._command(None, baseline.mode, deadline, "restore_original_mode")
        if current.mode != baseline.mode or (
            baseline.mode == 1 and current.channels != baseline.channels
        ):
            raise UnsafeState("original operating mode was not confirmed")
        self._event("recovery_confirmed", state=asdict(current))

    def run(self):
        experiment_ok = False
        recovery_ok = False
        try:
            preflight_deadline = self.started + PREFLIGHT_SECONDS
            self._event("preflight_started")
            first = self._read(preflight_deadline, fresh=True)
            self.baseline = self._read(preflight_deadline)
            if first != self.baseline:
                raise UnsafeState("two fresh baselines differed; no write was sent")
            values = list(self.baseline.channels)
            values[self.config.channel] += self.config.delta
            self.changed = _channels(values)
            self._event("baseline_confirmed", state=asdict(self.baseline))
            self.report["recovery"] = "PENDING"
            self._event(
                "experiment_intent",
                channel_index=self.config.channel,
                delta=self.config.delta,
                planned_channels=self.changed,
                original_mode=self.baseline.mode,
            )
            self._check_stop()
            self.excursion_started = self.clock()
            deadline = self.excursion_started + EXPERIMENT_SECONDS
            after = self._command(self.changed, 1, deadline, "experiment")
            if after.mode != 1 or after.channels != self.changed:
                raise UnsafeState("experiment readback differed from the single-channel change")
            experiment_ok = True
            self.report["experiment"] = "PASS"
            self._event("experiment_confirmed", state=asdict(after))
        except BaseException as error:
            self.report["experiment"] = (
                "FAIL" if self.excursion_started is not None else "NOT_TESTED"
            )
            self._event("experiment_failed", reason=type(error).__name__)
        finally:
            if self.excursion_started is not None:
                self.cleaning = True
                try:
                    self._recover(self.excursion_started + RECOVERY_DEADLINE_SECONDS)
                    self.recovery_confirmed_at = self.clock()
                    recovery_ok = (
                        self.recovery_confirmed_at - self.excursion_started <= MAX_EXCURSION
                    )
                    self.report["recovery"] = "PASS" if recovery_ok else "FAIL"
                except BaseException as error:
                    self.report["recovery"] = "FAIL"
                    self._event("recovery_unconfirmed", reason=type(error).__name__)
                finally:
                    self._close()
            else:
                self.report["recovery"] = "NOT_REQUIRED"
                self._close()
        self.report["status"] = (
            "PASS"
            if experiment_ok
            and recovery_ok
            and not self.interrupted
            and not self.report.get("reporting_error")
            else "FAIL"
        )
        self.report["interrupted"] = self.interrupted
        self.report["excursion_seconds"] = (
            round((self.recovery_confirmed_at or self.clock()) - self.excursion_started, 6)
            if self.excursion_started is not None
            else None
        )
        self._event("finished")
        if self.report.get("reporting_error"):
            self.report["status"] = "FAIL"
        return self.report


def _private_configuration(path):
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        info = os.fstat(descriptor)
        if (
            not stat.S_ISREG(info.st_mode)
            or stat.S_IMODE(info.st_mode) != 0o600
            or info.st_uid != os.geteuid()
            or info.st_size > 16384
        ):
            raise ValueError("private configuration must be a small owner-only regular file")
        with os.fdopen(descriptor, "r", encoding="utf-8", closefd=False) as source:
            data = json.load(source)
    finally:
        os.close(descriptor)
    return Configuration.parse(data)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        worker = ValidationWorker(
            _private_configuration(args.config), sink=PrivateReport(args.report)
        )
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
