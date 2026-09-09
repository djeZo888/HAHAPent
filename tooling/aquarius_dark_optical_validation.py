"""Isolated low-output optical sample with a guarded exact Manual restoration.

This separate procedure combines independently validated Shutdown-zero, Manual-
zero and modest channel commands. Its experiment phase is four seconds, while
the original 9.5-second recovery deadline and ten-second maximum remain intact.
No camera operation, HA service, Automatic command or schedule change is present.
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
    from . import aquarius_task004_validation as task
    from . import aquarius_validation as base
else:
    import aquarius_task004_validation as task
    import aquarius_validation as base

EXPERIMENT_SECONDS = 4.0
MAX_HOLD_SECONDS = 0.3
ZERO = (0,) * 6
OFF_RECOVERY_RESERVE = 4.8
MANUAL_RECOVERY_RESERVE = 4.0


@dataclass(frozen=True)
class Configuration:
    device: base.Configuration
    expected_manual_channels: tuple
    selected_percentage: int
    sample_seconds: float

    @classmethod
    def parse(cls, data, *, simulation=False):
        if (
            not isinstance(data, dict)
            or set(data)
            != {
                "schema_version",
                "action",
                "device",
                "expected_manual_channels",
                "selected_percentage",
                "sample_seconds",
            }
            or type(data["schema_version"]) is not int
            or data["schema_version"] != 1
            or data["action"] != "dark_optical"
        ):
            raise ValueError("invalid dark optical validation configuration")
        raw = data["device"]
        if not isinstance(raw, dict) or type(raw.get("delta")) is not int or raw["delta"] != 0:
            raise ValueError("dark sampling requires zero relative channel delta")
        device = replace(
            base.Configuration.parse({**raw, "delta": -1}, simulation=simulation), delta=0
        )
        original = tuple(base._channels(data["expected_manual_channels"]))
        percentage, duration = data["selected_percentage"], data["sample_seconds"]
        if (
            type(percentage) is not int
            or not 1 <= percentage <= 5
            or type(duration) not in (int, float)
            or not math.isfinite(duration)
            or not 0 < duration <= MAX_HOLD_SECONDS
        ):
            raise ValueError("dark sampling permits one to five percent for at most 0.3 seconds")
        return cls(device, original, percentage, float(duration))


class DarkOpticalWorker(task.Task004ValidationWorker):
    """One declared composite experiment; every subsequent write needs owned state."""

    def __init__(self, config, *, session_factory=task.ShutdownWireSession, **kwargs):
        super().__init__(config.device, session_factory=session_factory, **kwargs)
        self.optical = config
        values = [0] * 6
        values[config.device.channel] = config.selected_percentage
        self.changed = tuple(values)
        self.phase = "original"
        self.pending = False
        self.boundary_complete = False
        self.barrier_confirmed = False
        self.target = None
        self.unsafe = False
        self.sample_confirmed = False
        self.read_modes = (1,)
        self.report.update(
            action="dark_optical",
            experiment_phase_seconds=EXPERIMENT_SECONDS,
            recovery_reserved_seconds=base.RECOVERY_DEADLINE_SECONDS - EXPERIMENT_SECONDS,
            optical_observation="NOT_MEASURED",
            sample_window="NOT_TESTED",
            selected_percentage=config.selected_percentage,
            sample_seconds=config.sample_seconds,
            off_recovery_reserve_seconds=OFF_RECOVERY_RESERVE,
            manual_recovery_reserve_seconds=MANUAL_RECOVERY_RESERVE,
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
                self.unsafe = True
                raise base.UnsafeState("contradictory system state preceded read failure") from None
            raise
        except base.UnsafeState:
            self.unsafe = True
            raise
        if state.profile != self.config.profile or state.mode not in self.read_modes:
            self.unsafe = True
            raise base.UnsafeState("a competing mode or profile prevents restoration")
        self._check_stop()
        return state

    def _expect(self, state, channels, mode, message):
        if state.mode != mode or state.channels != channels:
            self.unsafe = True
            raise base.UnsafeState(message)

    def _transaction(self, channels, mode, deadline, phase, *, reserve_after=0.0):
        self._check_stop()
        if type(mode) is not int or mode not in (1, 8):
            raise base.UnsafeState("this procedure permits only Manual and Shutdown")
        if channels is not None and channels not in (self.changed, self.baseline.channels):
            raise base.UnsafeState("only the declared sample or exact original vector is permitted")
        if deadline - self.clock() < base.WRITE_RECOVERY_MARGIN + reserve_after:
            raise base.DeadlineError(
                "insufficient time for a new command and its remaining recovery"
            )
        self.phase = phase
        self.read_modes = (mode,)
        self.target = base.State(
            mode,
            *self.config.profile[:2],
            self.config.profile[2],
            ZERO if channels is None else channels,
        )
        self.pending, self.boundary_complete, self.barrier_confirmed = True, False, False
        echoes = []
        try:
            if channels is not None:
                command = base.channel_frame(channels, self.config.controller)
                self._event(phase + "_channels_send")
                self.session.send(command, deadline)
                echoes.append(command)
                self.session.quarantine(base.MANUAL_PAUSE, deadline, tuple(echoes))
            command = base.frame(bytes((0xE1, 0xFA, 0xDB, mode)))
            self._event(phase + "_mode_send", mode=mode)
            self.session.send(command, deadline)
            echoes.append(command)
            self.session.quarantine(base.WRITE_DRAIN_PAUSE, deadline, tuple(echoes))
            self.boundary_complete = True
        except BaseException:
            # A failed send or incomplete quarantine has no processing proof.
            self.unsafe = True
            raise
        try:
            actual_mode, controller, version, count = self.session.system(deadline)
        except (OSError, EOFError):
            self._event(phase + "_barrier_transport_uncertain")
            if not self.cleaning:
                raise
            after = self._fresh_recovery_read(
                deadline, reserve=reserve_after, stage=phase + "_settle", expected_mode=mode
            )
            self._expect(
                after, self.target.channels, mode, "pending cleanup target was not confirmed"
            )
            self.pending = False
            self._event(phase + "_fresh_processing_confirmed", state=asdict(after))
            return after
        except base.UnsafeState:
            self.unsafe = True
            raise
        if (controller, version, count) != self.config.profile or actual_mode != mode:
            self.unsafe = True
            raise base.UnsafeState("queried processing barrier contradicted the requested state")
        self.pending, self.barrier_confirmed = False, True
        self._event(phase + "_system_barrier_confirmed", mode=mode)
        # Signals are observed at complete processing boundaries. They cannot
        # interrupt a save midway and then authorize an uncertain replay.
        self._check_stop()
        if self.cleaning:
            return self._fresh_recovery_read(
                deadline, reserve=reserve_after, stage=phase, expected_mode=mode
            )
        return self._read(deadline, fresh=True)

    def _recover(self, deadline):
        self._event("recovery_started", interrupted_phase=self.phase)
        mode = 8 if self.phase == "off" else 1
        self.read_modes = (mode,)
        reserve = OFF_RECOVERY_RESERVE if mode == 8 else MANUAL_RECOVERY_RESERVE
        current = self._fresh_recovery_read(
            deadline,
            reserve=0.0 if self.unsafe else reserve,
            stage="recovery_guard",
            expected_mode=mode,
        )
        self._event("recovery_guard_confirmed", state=asdict(current))
        if self.unsafe:
            raise base.UnsafeState("a latched contradiction or unsafe processing prevents writes")
        if self.pending:
            if not self.boundary_complete or self.target is None or current != self.target:
                raise base.UnsafeState("uncertain processing was not resolved by its exact target")
            self.pending = False
            self._event("pending_processing_freshly_confirmed", state=asdict(current))
        if self.phase == "original":
            self._expect(current, self.baseline.channels, 1, "the original state changed")
            return
        if mode == 8:
            self._expect(current, ZERO, 8, "Shutdown output is not the owned zero state")
            current = self._transaction(
                None, 1, deadline, "cleanup_manual", reserve_after=task.MANUAL_ZERO_RESTORE_RESERVE
            )
            self._expect(
                current, ZERO, 1, "Manual resume did not preserve the confirmed zero state"
            )
            current = self._fresh_recovery_read(
                deadline,
                reserve=base.WRITE_RECOVERY_MARGIN,
                stage="cleanup_manual_zero_guard",
                expected_mode=1,
            )
            self._expect(current, ZERO, 1, "Manual zero changed before restoration")
        else:
            permitted = (
                (ZERO,)
                if self.phase == "manual"
                else (self.changed,)
                if self.sample_confirmed
                else (ZERO, self.changed)
            )
            if current.channels not in permitted:
                self.unsafe = True
                raise base.UnsafeState("Manual output is outside the known owned states")
        restored = self._transaction(self.baseline.channels, 1, deadline, "restore_original")
        self._expect(
            restored, self.baseline.channels, 1, "original Manual output was not confirmed"
        )
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
                or self.baseline.channels != self.optical.expected_manual_channels
            ):
                raise base.UnsafeState("two reads must match the declared original Manual vector")
            self._event("baseline_confirmed", state=asdict(self.baseline))
            self.report["recovery"] = "PENDING"
            self._event(
                "experiment_intent", original=asdict(self.baseline), selected_channels=self.changed
            )
            self._check_stop()
            self.excursion_started = self.clock()
            deadline = self.excursion_started + EXPERIMENT_SECONDS
            off = self._transaction(None, 8, deadline, "off")
            self._expect(off, ZERO, 8, "Shutdown must independently confirm all-zero output")
            self._event("off_zero_confirmed")
            manual = self._transaction(None, 1, deadline, "manual")
            self._expect(manual, ZERO, 1, "Manual must independently confirm all-zero output")
            guard = self._read(deadline, fresh=True)
            self._expect(guard, ZERO, 1, "fresh Manual zero guard changed")
            self._event("manual_zero_guard_confirmed")
            sample = self._transaction(self.changed, 1, deadline, "sample")
            if sample.channels != self.changed:
                if sample.channels != ZERO:
                    self.unsafe = True
                raise base.ValidationError("selected optical output was not confirmed")
            self.sample_confirmed = True
            self._event("sample_confirmed", state=asdict(sample))
            end = self.clock() + self.optical.sample_seconds
            if end > min(
                deadline,
                self.excursion_started + base.RECOVERY_DEADLINE_SECONDS - MANUAL_RECOVERY_RESERVE,
            ):
                self.report["sample_window"] = "SKIPPED_DEADLINE"
                raise base.DeadlineError("sample hold would consume the reserved cleanup time")
            self._event("optical_sample_started", state=asdict(sample), end_monotonic_seconds=end)
            while self.clock() < end:
                self._check_stop()
                self.sleeper(min(task.SAMPLE_STOP_INTERVAL, end - self.clock()))
            self._check_stop()
            if self.clock() > deadline:
                raise base.DeadlineError("sample window exceeded the four-second phase")
            self.report["sample_window"] = "COMPLETED"
            self._event("optical_sample_finished")
            experiment_ok = True
            self.report["experiment"] = "PASS"
        except BaseException as error:
            if isinstance(error, base.UnsafeState):
                self.unsafe = True
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
        worker = DarkOpticalWorker(
            _configuration(args.config), sink=base.PrivateReport(args.report)
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
