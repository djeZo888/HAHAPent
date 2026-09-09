"""Native Automatic-origin power acceptance with exact original Manual recovery.

This separate Task 004 procedure has a six-second experiment, a 19.5-second
cleanup deadline and a twenty-second maximum. Frozen single-action and optical
workers retain their original limits. HTTP uncertainty never authorizes replay.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import signal
import socket
import ssl
import stat
import sys
import time
from dataclasses import asdict, dataclass, replace
from pathlib import Path

if __package__:
    from . import aquarius_ha_validation as legacy
    from . import aquarius_task004_ha_service as native
    from . import aquarius_task004_validation as direct
    from . import aquarius_validation as base
else:
    import aquarius_ha_validation as legacy
    import aquarius_task004_ha_service as native
    import aquarius_task004_validation as direct
    import aquarius_validation as base

EXPERIMENT_SECONDS = 6.0
CLEANUP_SECONDS = 19.5
MAXIMUM_SECONDS = 20.0
MAX_STATE_BYTES = 65536
AUTOMATIC_ORIGIN_BEHAVIOR = "On resumes the lamp's stored schedule"


class HAObservationError(base.ValidationError):
    """An exact HA entity read did not provide the expected bounded observation."""


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _reject_constant(_value):
    raise ValueError("nonfinite JSON constant")


@dataclass(frozen=True)
class Configuration:
    service: native.Configuration
    expected_manual_channels: tuple
    mode_status_entity: str

    @property
    def device(self):
        return self.service.device

    @classmethod
    def parse(cls, data, *, simulation=False):
        if (
            not isinstance(data, dict)
            or set(data) != {"schema_version", "action", "device", "expected_manual_channels", "ha"}
            or type(data["schema_version"]) is not int
            or data["schema_version"] != 1
            or data["action"] != "automatic_power_composite"
        ):
            raise ValueError("invalid Automatic power composite configuration")
        ha = data["ha"]
        if not isinstance(ha, dict) or set(ha) != {
            "origin",
            "number_entity",
            "light_entity",
            "resume_entity",
            "mode_status_entity",
        }:
            raise ValueError("exact native Aquarius entities and one private origin are required")
        status = ha["mode_status_entity"]
        if not isinstance(status, str) or not re.fullmatch(
            r"sensor\.aquarius_plant_led_mode_status(?:_[1-9][0-9]*)?", status
        ):
            raise ValueError("the status entity must identify Aquarius mode status")
        parsed = native.Configuration.parse(
            {
                "schema_version": 1,
                "action": "power_automatic",
                "device": data["device"],
                "ha": {key: value for key, value in ha.items() if key != "mode_status_entity"},
            },
            simulation=simulation,
        )
        try:
            original = tuple(base._channels(data["expected_manual_channels"]))
        except base.UnsafeState:
            raise ValueError(
                "the original Manual state must contain six exact percentages"
            ) from None
        return cls(parsed, original, status)


class HAStateReader:
    """Bounded authenticated GETs for two configured entities; never log raw bodies."""

    def __init__(self, config, token, clock=time.monotonic):
        self.config, self.token, self.clock = config, legacy._token(token), clock

    def _remaining(self, deadline):
        remaining = deadline - self.clock()
        if remaining <= 0:
            raise HAObservationError("HA state observation deadline reached")
        return remaining

    def read(self, entity_id, deadline):
        if entity_id not in (self.config.service.light_entity, self.config.mode_status_entity):
            raise HAObservationError("HA state route is outside the configured entity allowlist")
        origin = self.config.service
        connection = None
        try:
            connection = socket.create_connection(
                (origin.host, origin.port), timeout=self._remaining(deadline)
            )
            if origin.scheme == "https":
                connection.settimeout(self._remaining(deadline))
                connection = ssl.create_default_context().wrap_socket(
                    connection, server_hostname=origin.host
                )
            request = (
                f"GET /api/states/{entity_id} HTTP/1.1\r\nHost: {origin.host}:{origin.port}\r\n"
                f"Authorization: Bearer {self.token}\r\nAccept-Encoding: identity\r\n"
                "Connection: close\r\n\r\n"
            ).encode("ascii")
            connection.settimeout(self._remaining(deadline))
            connection.sendall(request)
            received = bytearray()
            while b"\r\n\r\n" not in received:
                connection.settimeout(self._remaining(deadline))
                chunk = connection.recv(1024)
                if not chunk:
                    raise HAObservationError("HA state headers were incomplete")
                received.extend(chunk)
                if len(received) > legacy.MAX_HTTP_HEADER_BYTES:
                    raise HAObservationError("HA state headers exceeded their limit")
            header, body = bytes(received).split(b"\r\n\r\n", 1)
            lines = header.split(b"\r\n")
            if not re.fullmatch(rb"HTTP/1\.[01] 200(?: [\x20-\x7e]*)?", lines[0]):
                raise HAObservationError("HA state did not return successful HTTP completion")
            headers = {}
            for line in lines[1:]:
                key, separator, value = line.partition(b":")
                if (
                    not separator
                    or not re.fullmatch(rb"[A-Za-z0-9-]+", key)
                    or key.lower() in headers
                ):
                    raise HAObservationError("HA state headers were ambiguous")
                headers[key.lower()] = value.strip()
            length = headers.get(b"content-length", b"")
            if (
                not re.fullmatch(rb"[0-9]+", length)
                or int(length) > MAX_STATE_BYTES
                or b"transfer-encoding" in headers
                or headers.get(b"content-encoding", b"identity").lower() != b"identity"
            ):
                raise HAObservationError("HA state response framing was unsupported")
            while len(body) < int(length):
                connection.settimeout(self._remaining(deadline))
                chunk = connection.recv(min(4096, int(length) - len(body)))
                if not chunk:
                    raise HAObservationError("HA state body was incomplete")
                body += chunk
            if len(body) != int(length):
                raise HAObservationError("HA state response contained trailing data")
            decoded = json.loads(
                body, object_pairs_hook=_unique_object, parse_constant=_reject_constant
            )
            if (
                not isinstance(decoded, dict)
                or decoded.get("entity_id") != entity_id
                or not isinstance(decoded.get("state"), str)
                or not isinstance(decoded.get("attributes"), dict)
            ):
                raise HAObservationError("HA state did not identify the configured entity")
            attributes = decoded["attributes"]
            # Retain only the fields needed for the declared acceptance check.
            return {
                "state": decoded["state"],
                "on_behavior": attributes.get("on_behavior"),
                "power_control_validated": attributes.get("power_control_validated"),
            }
        except HAObservationError:
            raise
        except (OSError, ValueError, TypeError, OverflowError):
            raise HAObservationError("HA state observation could not be verified") from None
        finally:
            if connection is not None:
                connection.close()


class AutomaticCompositeWorker(direct.ShutdownValidationWorker):
    """Native Resume/Off/On followed by one guarded restoration of the owner state."""

    def __init__(
        self,
        config,
        token,
        *,
        service_factory=native.Service,
        reader_factory=HAStateReader,
        **kwargs,
    ):
        super().__init__(direct.Configuration(config.device, "shutdown_manual"), **kwargs)
        self.composite = config
        self.power = service_factory(config.service, token, self.clock)
        self.resume = service_factory(
            replace(config.service, action="resume_program"), token, self.clock
        )
        self.ha_reader = reader_factory(config, token, self.clock)
        self.phase = "original"
        self.read_modes = (1,)
        self.completion_unknown = False
        self.pending_until = None
        self.report.update(
            action="automatic_power_composite",
            actuator="home_assistant_native_service",
            maximum_excursion_seconds=MAXIMUM_SECONDS,
            experiment_phase_seconds=EXPERIMENT_SECONDS,
            recovery_reserved_seconds=CLEANUP_SECONDS - EXPERIMENT_SECONDS,
            final_read_deadline_seconds=CLEANUP_SECONDS,
            normal_duration_goal_seconds=10.0,
            ha_completion="NOT_SENT",
            automatic_origin_confirmed=False,
        )

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
                self.rejected_observation = True
                raise base.UnsafeState(
                    "a contradictory system reply preceded transport failure"
                ) from None
            raise
        except base.UnsafeState:
            self.rejected_observation = True
            raise
        if state.profile != self.config.profile or state.mode not in self.read_modes:
            self.rejected_observation = True
            raise base.UnsafeState("mode or profile contradicted the owned native transaction")
        self._check_stop()
        return state

    def _ha_call(self, action, deadline, expected_mode):
        self._check_stop()
        if self.completion_unknown:
            raise base.UnsafeState("unknown HA completion forbids another actuator call")
        if action in ("off", "on"):
            # HA state GETs can take time. Re-establish this procedure's own
            # phase before HA's coordinator can admit a later controller state.
            current = self._read(deadline, fresh=True)
            if action == "on" and current.channels != direct.ZERO_CHANNELS:
                self.rejected_observation = True
                raise base.UnsafeState("Off zero changed before native On admission")
            self._event(action + "_fresh_guard_confirmed", state=asdict(current))
        self._close()
        if deadline - self.clock() < base.WRITE_RECOVERY_MARGIN:
            raise base.DeadlineError("insufficient time for another native experiment action")
        sent_at = self.clock()
        self.io_phase = "ha_service"
        self._event(action + "_ha_service_send")
        try:
            actuator = self.resume if action == "resume" else self.power
            actuator.call(action, None, min(deadline, sent_at + legacy.HA_COORDINATOR_SECONDS))
        except native.HACompletionUnknown:
            self.completion_unknown = True
            self.pending_until = (
                sent_at + legacy.HA_COORDINATOR_SECONDS + legacy.UNCERTAIN_SETTLE_MARGIN
            )
            self.report["ha_completion"] = "UNKNOWN"
            self._event(action + "_ha_completion_unknown")
            raise
        except native.HAServiceError:
            self.report["ha_completion"] = "REJECTED_OR_NOT_DELIVERED"
            self._event(action + "_ha_service_rejected")
            raise
        self.report["ha_completion"] = "HTTP_COMPLETED"
        self.phase = "off" if expected_mode == 8 else "automatic"
        self.read_modes = (expected_mode,)
        self._event(action + "_ha_service_completed")
        self._check_stop()
        after = self._read(deadline, fresh=True)
        if expected_mode == 8 and after.channels != direct.ZERO_CHANNELS:
            self.rejected_observation = True
            raise base.UnsafeState("native Off did not confirm the known all-zero state")
        self._event(action + "_tcp_confirmed", state=asdict(after))
        return after

    def _ha_state(self, entity_id, deadline):
        self._check_stop()
        self._close()
        self.io_phase = "ha_state_read"
        return self.ha_reader.read(entity_id, deadline)

    def _require_ha_mode(self, mode, deadline):
        state = self._ha_state(self.composite.mode_status_entity, deadline)
        if state["state"] != mode:
            raise HAObservationError("native HA mode status did not match the required state")
        self._event("ha_mode_status_confirmed", mode=mode)

    def _recover(self, deadline):
        self._event("recovery_started", owned_phase=self.phase)
        if self.completion_unknown or self.rejected_observation:
            if self.completion_unknown:
                # A precautionary wait never establishes cancellation/admission.
                legacy.HAValidationWorker._settle_uncertain(self, deadline)
            self.read_modes = (0, 1, 8)
            observed = self._fresh_recovery_read(deadline, reserve=0.0, stage="read_only_failure")
            self._event(
                "failure_state_observed_without_replay", original_matches=observed == self.baseline
            )
            raise base.UnsafeState(
                "unknown HA completion or contradiction forbids restoration writes"
            )
        mode = {"original": 1, "automatic": 0, "off": 8}[self.phase]
        self.read_modes = (mode,)
        reserve = (
            direct.MANUAL_MODE_AND_FALLBACK_MARGIN if mode == 8 else base.RECOVERY_COMMAND_RESERVE
        )
        current = self._fresh_recovery_read(
            deadline, reserve=reserve, stage="original_manual_guard", expected_mode=mode
        )
        self._event("original_manual_guard_confirmed", state=asdict(current))
        if mode == 1:
            if current != self.baseline:
                raise base.UnsafeState("state changed before a known native mutation")
            self._event("recovery_already_original")
            return
        if mode == 8:
            if current.channels != direct.ZERO_CHANNELS:
                raise base.UnsafeState("Off state changed before Manual restoration")
            self.read_modes = (1,)
            current = super()._send_mode(1, deadline, "restore_manual_mode")
            if current == self.baseline:
                self._event("recovery_confirmed", state=asdict(current))
                return
            if current.channels != direct.ZERO_CHANNELS or not self.manual_resume_barrier_confirmed:
                raise base.UnsafeState("Manual zero processing was not independently established")
            current = self._fresh_recovery_read(
                deadline,
                reserve=base.WRITE_RECOVERY_MARGIN,
                stage="manual_zero_guard",
                expected_mode=1,
            )
            if current.channels != direct.ZERO_CHANNELS:
                raise base.UnsafeState("Manual zero changed before original-vector restoration")
        # Only our deliberately resumed Automatic program may have changing
        # channel percentages. The fresh raw-mode/profile guard is mandatory.
        self.read_modes = (1,)
        self.report["channel_writes_permitted"] = True
        self.report["channel_restoration_path"] = "guarded_original_manual_vector"
        restored = base.ValidationWorker._command(
            self, self.baseline.channels, 1, deadline, "restore_original_manual"
        )
        if restored != self.baseline:
            raise base.UnsafeState("the exact original Manual vector was not confirmed")
        self._event("recovery_confirmed", state=asdict(restored))

    def run(self):
        experiment_ok = recovery_ok = False
        try:
            deadline = self.started + base.PREFLIGHT_SECONDS
            self._event("preflight_started")
            first = self._read(deadline, fresh=True)
            self.baseline = self._read(deadline)
            if (
                first != self.baseline
                or self.baseline.channels != self.composite.expected_manual_channels
            ):
                raise base.UnsafeState("the stable original Manual vector must match configuration")
            self._require_ha_mode("manual_override", deadline)
            initial = self._ha_state(self.composite.service.light_entity, deadline)
            if initial["state"] != "on" or initial["power_control_validated"] is not True:
                raise HAObservationError("the configured native power entity is not ready")
            self._event("baseline_confirmed", state=asdict(self.baseline))
            self.report["recovery"] = "PENDING"
            self._event(
                "experiment_intent", original=asdict(self.baseline), actions=["resume", "off", "on"]
            )
            self._check_stop()
            self.excursion_started = self.clock()
            deadline = self.excursion_started + EXPERIMENT_SECONDS
            self._ha_call("resume", deadline, 0)
            self._require_ha_mode("following_schedule", deadline)
            self._ha_call("off", deadline, 8)
            off = self._ha_state(self.composite.service.light_entity, deadline)
            if (
                off["state"] != "off"
                or off["power_control_validated"] is not True
                or off["on_behavior"] != AUTOMATIC_ORIGIN_BEHAVIOR
            ):
                raise HAObservationError("HA did not expose a confirmed saved Automatic Off origin")
            self.report["automatic_origin_confirmed"] = True
            self._event("ha_automatic_origin_confirmed")
            self._ha_call("on", deadline, 0)
            self._require_ha_mode("following_schedule", deadline)
            on = self._ha_state(self.composite.service.light_entity, deadline)
            if on["state"] != "on" or on["power_control_validated"] is not True:
                raise HAObservationError("native HA did not expose restored Automatic power")
            if self.clock() >= deadline:
                raise base.DeadlineError("native experiment exceeded its six-second phase")
            self._event("experiment_confirmed")
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
                    self._recover(self.excursion_started + CLEANUP_SECONDS)
                    self.recovery_confirmed_at = self.clock()
                    recovery_ok = (
                        self.recovery_confirmed_at - self.excursion_started <= MAXIMUM_SECONDS
                    )
                    self.report["recovery"] = "PASS" if recovery_ok else "FAIL"
                except BaseException as error:
                    self.report["recovery"] = "FAIL"
                    self._event(
                        "recovery_unconfirmed",
                        reason=type(error).__name__,
                        phase=self._failure_phase(),
                    )
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


def _configuration(path):
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        info = os.fstat(descriptor)
        if (
            not stat.S_ISREG(info.st_mode)
            or stat.S_IMODE(info.st_mode) != 0o600
            or info.st_uid != os.geteuid()
            or info.st_size > 16384
        ):
            raise ValueError("private configuration must be an owner-only regular file")
        with os.fdopen(descriptor, "r", encoding="utf-8", closefd=False) as source:
            return Configuration.parse(json.load(source))
    finally:
        os.close(descriptor)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        token = sys.stdin.read(legacy.MAX_TOKEN_BYTES + 1).removesuffix("\n")
        worker = AutomaticCompositeWorker(
            _configuration(args.config), token, sink=base.PrivateReport(args.report)
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
