"""Bounded optical sampling and explicit original-mode Shutdown validation.

This private operator extension imports the frozen Task 003 transport and
cleanup safeguards. It contains no camera, HA API, discovery or runtime-control
configuration. Optical reports describe a sampling interval, not a colour
measurement. Shutdown probes restore only the selected original operating mode.
Manual snapshot restoration requires confirmed zero output both during Shutdown
and after the first, independently confirmed Manual resume.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import signal
import stat
from dataclasses import asdict, dataclass, replace
from pathlib import Path

if __package__:
    from . import aquarius_validation as base
else:
    import aquarius_validation as base

MAX_SAMPLE_SECONDS = 2.0
MAX_SAMPLE_PERCENTAGE = 20
SAMPLE_STOP_INTERVAL = 0.05
MODE_SHUTDOWN = 8
ZERO_CHANNELS = (0, 0, 0, 0, 0, 0)
MANUAL_ZERO_RESTORE_RESERVE = 3.0
MANUAL_MODE_AND_FALLBACK_MARGIN = base.WRITE_RECOVERY_MARGIN + MANUAL_ZERO_RESTORE_RESERVE


@dataclass(frozen=True)
class Configuration:
    device: base.Configuration
    action: str
    sample_seconds: float = 0.0
    maximum_sample_percentage: int = 0

    @classmethod
    def parse(cls, data, *, simulation=False):
        if not isinstance(data, dict) or type(data.get("schema_version")) is not int:
            raise ValueError("invalid Task 004 validation configuration")
        action = data.get("action")
        required = {"schema_version", "device", "action"}
        if action == "optical":
            required |= {"sample_seconds", "maximum_sample_percentage"}
        if set(data) != required or data["schema_version"] != 1:
            raise ValueError("invalid Task 004 validation fields")
        if action in ("shutdown_automatic", "shutdown_manual"):
            device = data["device"]
            if not isinstance(device, dict) or type(device.get("delta")) is not int:
                raise ValueError("Shutdown requires an explicit zero channel delta")
            if device["delta"] != 0:
                raise ValueError("Shutdown validation cannot change channel percentages")
            device = replace(
                base.Configuration.parse({**device, "delta": -1}, simulation=simulation), delta=0
            )
            return cls(device, action)
        if action != "optical":
            raise ValueError("unsupported optical or Shutdown validation action")
        duration = data["sample_seconds"]
        ceiling = data["maximum_sample_percentage"]
        if (
            type(duration) not in (int, float)
            or not math.isfinite(duration)
            or not 0 < duration <= MAX_SAMPLE_SECONDS
            or type(ceiling) is not int
            or not 1 <= ceiling <= MAX_SAMPLE_PERCENTAGE
        ):
            raise ValueError("optical sampling requires at most two seconds and twenty percent")
        return cls(
            base.Configuration.parse(data["device"], simulation=simulation),
            action,
            float(duration),
            ceiling,
        )


class Task004ValidationWorker(base.ValidationWorker):
    """Recheck the exact baseline after durable intent, before starting the excursion."""

    def _event(self, stage, **details):
        super()._event(stage, **details)
        if stage == "experiment_intent":
            current = self._read(self.started + base.PREFLIGHT_SECONDS, fresh=True)
            if current != self.baseline:
                raise base.UnsafeState("baseline changed after durable intent; no write was sent")
            # Do not fsync again between this final guard and the first command.
            self.report["prewrite_guard_monotonic_seconds"] = self.clock()


class OpticalValidationWorker(Task004ValidationWorker):
    """Hold a verified modest single-channel change inside the original deadline."""

    def __init__(self, config, **kwargs):
        if config.action != "optical":
            raise ValueError("an optical validation configuration is required")
        super().__init__(config.device, **kwargs)
        self.optical = config
        self.rejected_observation = False
        self.report.update(action="optical", optical_observation="NOT_MEASURED")

    def _read(self, deadline, *, fresh=False):
        try:
            return super()._read(deadline, fresh=fresh)
        except (OSError, EOFError):
            observed = getattr(self.session, "last_system", None)
            if (
                self.excursion_started is not None
                and not self.cleaning
                and observed is not None
                and observed[0] != 1
            ):
                raise base.UnsafeState("competing mode observed before transport failure") from None
            raise

    def _command(self, channels, mode, deadline, stage):
        if stage != "experiment":
            return super()._command(channels, mode, deadline, stage)
        try:
            return self._sample(channels, mode, deadline, stage)
        except base.UnsafeState:
            self.rejected_observation = True
            raise

    def _recover(self, deadline):
        if self.rejected_observation:
            observed = self._fresh_recovery_read(
                deadline, reserve=0.0, stage="unsafe_experiment_observation"
            )
            self._event("unsafe_experiment_guard_observed", state=asdict(observed))
            raise base.UnsafeState("contradictory optical observations prevent restoration writes")
        return super()._recover(deadline)

    def _sample(self, channels, mode, deadline, stage):
        if not 1 <= channels[self.config.channel] <= self.optical.maximum_sample_percentage:
            raise base.UnsafeState("selected optical output exceeds the modest sampling range")
        after = super()._command(channels, mode, deadline, stage)
        if after.mode != 1 or after.channels != channels:
            raise base.UnsafeState("optical sample requires exact fresh Manual output")
        end = self.clock() + self.optical.sample_seconds
        if end > deadline:
            raise base.DeadlineError("sample duration would consume the cleanup reserve")
        self._event("optical_sample_started", state=asdict(after), end_monotonic_seconds=end)
        while self.clock() < end:
            self._check_stop()
            self.sleeper(min(SAMPLE_STOP_INTERVAL, end - self.clock()))
        self._check_stop()
        if self.clock() > deadline:
            raise base.DeadlineError("optical sampling exceeded its experiment allowance")
        self._event("optical_sample_finished")
        # The inherited fresh recovery guard checks the state after this window.
        # Camera capture is independent and cannot postpone local finally cleanup.
        return after


class ShutdownWireSession(base.WireSession):
    """Permit reading mode 8 without changing Task 003's transport policy."""

    def read_state(self, deadline):
        mode, controller, version, count = self.system(deadline)
        if (controller, version, count) != self.config.profile or mode not in (0, 1, 8):
            raise base.UnsafeState("profile or mode differs from the validation profile")
        self.quarantine(base.QUERY_PAUSE, deadline)
        response = self.query(base.CHANNEL_QUERY, deadline)
        values = list(base._channels(response[3:9]))
        if controller == (0x14, 0x32):
            values[2], values[3] = values[3], values[2]
        return base.State(mode, controller, version, count, tuple(values))


class ShutdownValidationWorker(Task004ValidationWorker):
    """Probe mode 8, then restore the explicitly selected original mode safely."""

    def __init__(self, config, *, session_factory=ShutdownWireSession, **kwargs):
        if config.action not in ("shutdown_automatic", "shutdown_manual"):
            raise ValueError("an explicit original-mode Shutdown configuration is required")
        super().__init__(config.device, session_factory=session_factory, **kwargs)
        self.original_mode = 0 if config.action == "shutdown_automatic" else 1
        self.shutdown_state = None
        self.shutdown_delivery_started = False
        self.rejected_observation = False
        self.manual_resume_barrier_confirmed = False
        self.report.update(
            action=config.action,
            channel_writes_permitted=False,
            channel_restoration_path="not_needed",
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
            permitted = (self.original_mode, 8) if self.cleaning else (8,)
            if (
                self.shutdown_delivery_started
                and observed is not None
                and observed[0] not in permitted
            ):
                self.rejected_observation = True
                raise base.UnsafeState("competing mode observed before transport failure") from None
            raise
        self._check_stop()
        if state.profile != self.config.profile or state.mode not in (0, 1, 8):
            self.rejected_observation = True
            raise base.UnsafeState("profile or mode differs from the validation profile")
        return state

    def _send_mode(self, mode, deadline, stage):
        self._check_stop()
        if mode not in (self.original_mode, 8) or type(mode) is not int:
            raise base.UnsafeState("this probe permits only Shutdown and the original mode")
        reserve = MANUAL_ZERO_RESTORE_RESERVE if self.cleaning and mode == 1 else 0.0
        minimum = base.WRITE_RECOVERY_MARGIN + reserve
        if deadline - self.clock() < minimum:
            raise base.DeadlineError("too little time remains for a mode command and readback")
        command = base.frame(bytes((0xE1, 0xFA, 0xDB, mode)))
        self._event(stage + "_mode_send", mode=mode)
        if mode == MODE_SHUTDOWN:
            self.shutdown_delivery_started = True
        self.session.send(command, deadline)
        self._check_stop()
        self.session.quarantine(base.WRITE_DRAIN_PAUSE, deadline, (command,))
        self._check_stop()
        try:
            actual_mode, controller, version, count = self.session.system(deadline)
        except (OSError, EOFError) as error:
            if not self.cleaning:
                raise
            self._event(
                stage + "_system_barrier_transport_failed",
                reason=type(error).__name__,
                phase=self._failure_phase(),
            )
            return self._fresh_recovery_read(
                deadline, reserve=reserve, stage=stage, expected_mode=mode
            )
        if (controller, version, count) != self.config.profile or actual_mode != mode:
            self.rejected_observation = True
            raise base.UnsafeState("queried system barrier did not confirm the requested mode")
        self._event(stage + "_system_barrier_confirmed", mode=mode)
        if self.cleaning and mode == 1:
            self.manual_resume_barrier_confirmed = True
        if self.cleaning:
            return self._fresh_recovery_read(
                deadline, reserve=reserve, stage=stage, expected_mode=mode
            )
        return self._read(deadline, fresh=True)

    def _recover(self, deadline):
        self._event("recovery_started")
        current = self._fresh_recovery_read(
            deadline,
            reserve=(
                MANUAL_MODE_AND_FALLBACK_MARGIN
                if self.original_mode == 1
                else base.RECOVERY_COMMAND_RESERVE
            ),
            stage="recovery_guard",
            expected_mode=8 if self.shutdown_state is not None else None,
        )
        self._event("recovery_guard_confirmed", state=asdict(current))
        if self.rejected_observation:
            raise base.UnsafeState("a contradictory observation prevents mode restoration")
        if current == self.baseline and self.shutdown_state is None:
            self._event("recovery_already_original")
            return
        if not self.shutdown_delivery_started or current.mode != MODE_SHUTDOWN:
            raise base.UnsafeState("a competing mode prevents original-mode restoration")
        if current.channels not in (self.baseline.channels, ZERO_CHANNELS):
            raise base.UnsafeState("unexplained Shutdown channels prevent restoration")
        if self.shutdown_state is not None and current != self.shutdown_state:
            raise base.UnsafeState("Shutdown state changed before the restoration guard")
        shutdown_was_zero = current.channels == ZERO_CHANNELS
        restored = self._send_mode(self.original_mode, deadline, "restore_original_mode")
        if restored.mode != self.original_mode:
            raise base.UnsafeState("the original operating mode was not confirmed")
        if self.original_mode == 1 and restored.channels != self.baseline.channels:
            if not shutdown_was_zero or restored.channels != ZERO_CHANNELS:
                raise base.UnsafeState("unexplained Manual channels prevent snapshot restoration")
            if not self.manual_resume_barrier_confirmed:
                raise base.UnsafeState("uncertain Manual processing cannot permit a channel replay")
            guard = self._fresh_recovery_read(
                deadline,
                reserve=base.WRITE_RECOVERY_MARGIN,
                stage="manual_zero_restore_guard",
                expected_mode=1,
            )
            if guard.channels != ZERO_CHANNELS:
                raise base.UnsafeState("Manual zero state changed before snapshot restoration")
            self._event("manual_zero_restore_guard_confirmed", state=asdict(guard))
            self.report["channel_restoration_path"] = "confirmed_shutdown_zero_then_manual_zero"
            self.report["channel_writes_permitted"] = True
            # This declared restoration is not a replay of an uncertain mode
            # command: Manual already completed its barrier and independent read.
            restored = super()._command(
                self.baseline.channels, 1, deadline, "restore_manual_channels"
            )
            if restored.mode != 1 or restored.channels != self.baseline.channels:
                raise base.UnsafeState("the original Manual vector was not confirmed")
        self._event(
            "recovery_confirmed",
            state=asdict(restored),
            original_channels_match=restored.channels == self.baseline.channels,
            restoration=(
                "original_automatic_program" if self.original_mode == 0 else "exact_original_manual"
            ),
        )

    def run(self):
        experiment_ok = False
        recovery_ok = False
        try:
            deadline = self.started + base.PREFLIGHT_SECONDS
            self._event("preflight_started")
            first = self._read(deadline, fresh=True)
            self.baseline = self._read(deadline)
            if first != self.baseline or self.baseline.mode != self.original_mode:
                raise base.UnsafeState("Shutdown requires two stable reads of the selected mode")
            self._event("baseline_confirmed", state=asdict(self.baseline))
            self.report["recovery"] = "PENDING"
            self._event("experiment_intent", requested_mode=8, restoration_mode=self.original_mode)
            self._check_stop()
            self.excursion_started = self.clock()
            after = self._send_mode(
                8, self.excursion_started + base.EXPERIMENT_SECONDS, "experiment"
            )
            if after.mode != 8 or after.channels not in (self.baseline.channels, ZERO_CHANNELS):
                self.rejected_observation = True
                raise base.UnsafeState("Shutdown did not return retained or all-zero channels")
            self.shutdown_state = after
            experiment_ok = True
            self.report["experiment"] = "PASS"
            self._event(
                "experiment_confirmed",
                state=asdict(after),
                channel_observation=(
                    "all_zero_baseline_ambiguous"
                    if self.baseline.channels == ZERO_CHANNELS
                    else "retained"
                    if after.channels == self.baseline.channels
                    else "all_zero"
                ),
            )
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
                    self._recover(self.excursion_started + base.RECOVERY_DEADLINE_SECONDS)
                    self.recovery_confirmed_at = self.clock()
                    recovery_ok = (
                        self.recovery_confirmed_at - self.excursion_started <= base.MAX_EXCURSION
                    )
                    self.report["recovery"] = "PASS" if recovery_ok else "FAIL"
                except BaseException as error:
                    self.report["recovery"] = "FAIL"
                    self._event(
                        "recovery_unconfirmed",
                        reason=type(error).__name__,
                        phase=self._failure_phase(),
                    )
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
        config = _configuration(args.config)
        worker_class = (
            OpticalValidationWorker if config.action == "optical" else ShutdownValidationWorker
        )
        worker = worker_class(config, sink=base.PrivateReport(args.report))
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
