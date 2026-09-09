"""Detached native HA acceptance with independent bounded lamp readback/cleanup.

Credentials arrive only on stdin. Unknown HTTP completion always remains FAIL:
the settling interval cannot prove that an arbitrarily delayed HA task will not
run. No service or uncertain write is retried. UI-driven external actions and
Light brightness are deliberately outside this worker's configured routes.
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import stat
from dataclasses import asdict
from pathlib import Path

if __package__:
    from . import aquarius_ha_validation as legacy
    from . import aquarius_task004_validation as direct
    from . import aquarius_validation as base
    from .aquarius_task004_ha_service import Configuration, HACompletionUnknown, Service
else:
    import aquarius_ha_validation as legacy
    import aquarius_task004_validation as direct
    import aquarius_validation as base
    from aquarius_task004_ha_service import Configuration, HACompletionUnknown, Service


class HAActuatorMixin:
    def _initialize_ha(self, config, token, service_factory):
        self.ha_config = config
        self.service = service_factory(config, token, self.clock)
        self.pending_until = None
        self.completion_unknown = False
        self.rejected_observation = False
        self.experiment_delivery_possible = False
        self._expected_read_mode = None
        self.report.update(
            action=config.action,
            actuator="home_assistant_native_service",
            ha_completion="NOT_SENT",
        )

    def _read(self, deadline, *, fresh=False):
        try:
            state = super()._read(deadline, fresh=fresh)
            if self._expected_read_mode is not None and state.mode != self._expected_read_mode:
                raise base.UnsafeState("fresh readback did not confirm the requested HA mode")
            return state
        except (OSError, EOFError):
            observed = getattr(self.session, "last_system", None)
            if (
                observed is not None
                and self._expected_read_mode is not None
                and observed[0] != self._expected_read_mode
            ):
                self.rejected_observation = True
                raise base.UnsafeState("competing mode observed before transport failure") from None
            raise
        except base.UnsafeState:
            if self.excursion_started is not None:
                self.rejected_observation = True
            raise

    def _ha_call(self, action, value, deadline, stage, *, expected_mode):
        self._check_stop()
        self._close()
        self.io_phase = "ha_service"
        self._event(stage + "_observer_connection_released")
        minimum = legacy.HA_CLEANUP_MARGIN if self.cleaning else base.WRITE_RECOVERY_MARGIN
        if deadline - self.clock() < minimum:
            raise base.DeadlineError("insufficient time for an HA action and independent readback")
        sent_at = self.clock()
        self._event(stage + "_ha_service_send", action=action)
        if not self.cleaning:
            self.experiment_delivery_possible = True
        try:
            self.service.call(action, value, min(deadline, sent_at + legacy.HA_COORDINATOR_SECONDS))
        except HACompletionUnknown:
            self.completion_unknown = True
            self.pending_until = (
                sent_at + legacy.HA_COORDINATOR_SECONDS + legacy.UNCERTAIN_SETTLE_MARGIN
            )
            self.report["ha_completion"] = "UNKNOWN"
            self._event(stage + "_ha_completion_unknown")
            raise
        except legacy.HAServiceError:
            if not self.cleaning:
                self.experiment_delivery_possible = False
            self.report["ha_completion"] = "REJECTED_OR_NOT_DELIVERED"
            self._event(stage + "_ha_service_rejected")
            raise
        self.report["ha_completion"] = "UNKNOWN" if self.completion_unknown else "HTTP_COMPLETED"
        self._event(stage + "_ha_service_completed")
        self._check_stop()
        self._expected_read_mode = expected_mode
        try:
            if self.cleaning:
                return self._fresh_recovery_read(
                    deadline, reserve=0.0, stage=stage + "_ha_readback", expected_mode=expected_mode
                )
            return self._read(deadline, fresh=True)
        finally:
            self._expected_read_mode = None

    def _recover(self, deadline):
        legacy.HAValidationWorker._settle_uncertain(self, deadline)
        if not self.experiment_delivery_possible:
            observed = self._fresh_recovery_read(deadline, reserve=0.0, stage="undelivered_action")
            self._event("undelivered_action_guard_observed", state=asdict(observed))
            if observed != self.baseline:
                raise base.UnsafeState("state changed without a delivered HA experiment")
            return
        if self.rejected_observation:
            observed = self._fresh_recovery_read(
                deadline, reserve=0.0, stage="unsafe_experiment_observation"
            )
            self._event("unsafe_experiment_guard_observed", state=asdict(observed))
            raise base.UnsafeState("contradictory HA observations prevent restoration writes")
        try:
            self._recover_transaction(deadline)
        except HACompletionUnknown:
            # On was delivered without known completion. Never queue another HA
            # request or a raw snapshot replay behind that uncertain action.
            legacy.HAValidationWorker._settle_uncertain(self, deadline)
            observed = self._fresh_recovery_read(
                deadline, reserve=0.0, stage="ha_unknown_cleanup_observation"
            )
            self._event("ha_unknown_cleanup_observed", state=asdict(observed))
            raise base.UnsafeState("HA restoration completion remains unknown") from None
        if self.completion_unknown:
            self._event("original_state_observed_but_ha_completion_unknown")
            raise base.UnsafeState("a late HA task cannot be excluded despite observed cleanup")


class HAPowerWorker(HAActuatorMixin, direct.ShutdownValidationWorker):
    def __init__(self, config, token, *, service_factory=Service, **kwargs):
        if config.action not in ("power_manual", "power_automatic"):
            raise ValueError("a native HA power transaction is required")
        original = "shutdown_manual" if config.action == "power_manual" else "shutdown_automatic"
        super().__init__(direct.Configuration(config.device, original), **kwargs)
        self._initialize_ha(config, token, service_factory)

    def _send_mode(self, mode, deadline, stage):
        if stage == "experiment":
            if mode != 8:
                raise base.UnsafeState("the power experiment requires explicit Off")
            # As with a raw send, delivery may have happened before HTTP fails.
            self.shutdown_delivery_started = True
            return self._ha_call("off", None, deadline, stage, expected_mode=8)
        if self.completion_unknown:
            return super()._send_mode(mode, deadline, stage)
        if mode != self.original_mode:
            raise base.UnsafeState("native On must restore the selected original mode")
        return self._ha_call("on", None, deadline, stage, expected_mode=mode)

    def _recover_transaction(self, deadline):
        direct.ShutdownValidationWorker._recover(self, deadline)


class HANumberWorker(HAActuatorMixin, direct.Task004ValidationWorker):
    def __init__(self, config, token, *, service_factory=Service, **kwargs):
        if config.action != "channel":
            raise ValueError("a native HA channel transaction is required")
        super().__init__(config.device, **kwargs)
        self._initialize_ha(config, token, service_factory)

    def _command(self, channels, mode, deadline, stage):
        if stage != "experiment":
            return super()._command(channels, mode, deadline, stage)
        if mode != 1 or channels != self.changed:
            raise base.UnsafeState("unexpected native channel target")
        after = self._ha_call(
            "channel", channels[self.config.channel], deadline, stage, expected_mode=1
        )
        if after.channels != channels:
            self.rejected_observation = True
            raise base.UnsafeState("native Number changed an unexpected channel vector")
        return after

    def _recover_transaction(self, deadline):
        base.ValidationWorker._recover(self, deadline)


class HAResumeWorker(HAActuatorMixin, direct.Task004ValidationWorker):
    """Explicitly resume Automatic, then restore the owner's original Manual mix."""

    def __init__(self, config, token, *, service_factory=Service, **kwargs):
        if config.action != "resume_program":
            raise ValueError("a native Resume-program transaction is required")
        super().__init__(config.device, **kwargs)
        self._initialize_ha(config, token, service_factory)
        self.resume_confirmed = False

    def _recover_transaction(self, deadline):
        current = self._fresh_recovery_read(
            deadline,
            reserve=base.RECOVERY_COMMAND_RESERVE,
            stage="resume_recovery_guard",
            expected_mode=0 if self.resume_confirmed else None,
        )
        self._event("resume_recovery_guard_confirmed", state=asdict(current))
        if not self.resume_confirmed and current == self.baseline:
            self._event("recovery_already_original")
            return
        if current.mode != 0:
            raise base.UnsafeState("a competing mode prevents original Manual restoration")
        # Automatic percentages may advance; only the program deliberately
        # resumed by this experiment is replaced with the owner's prior Manual mix.
        restored = base.ValidationWorker._command(
            self, self.baseline.channels, 1, deadline, "restore_original_manual"
        )
        if restored != self.baseline:
            raise base.UnsafeState("the exact original Manual mix was not confirmed")
        self._event("recovery_confirmed", state=asdict(restored))

    def run(self):
        experiment_ok = recovery_ok = False
        try:
            deadline = self.started + base.PREFLIGHT_SECONDS
            self._event("preflight_started")
            first = self._read(deadline, fresh=True)
            self.baseline = self._read(deadline)
            if first != self.baseline or self.baseline.mode != 1:
                raise base.UnsafeState("Resume validation requires stable original Manual state")
            self._event("baseline_confirmed", state=asdict(self.baseline))
            self.report["recovery"] = "PENDING"
            self._event("experiment_intent", requested_mode=0, restoration_mode=1)
            self._check_stop()
            self.excursion_started = self.clock()
            resumed = self._ha_call(
                "resume",
                None,
                self.excursion_started + base.EXPERIMENT_SECONDS,
                "experiment",
                expected_mode=0,
            )
            self.resume_confirmed = True
            experiment_ok = True
            self.report["experiment"] = "PASS"
            self._event("experiment_confirmed", state=asdict(resumed))
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
                    recovery_ok = self.recovery_confirmed_at - self.excursion_started <= 10
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
            raise ValueError("private HA configuration must be an owner-only regular file")
        with os.fdopen(descriptor, "r", encoding="utf-8", closefd=False) as source:
            data = json.load(source)
    finally:
        os.close(descriptor)
    return Configuration.parse(data)


def main(argv=None):
    import sys

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        config = _configuration(args.config)
        raw_token = sys.stdin.buffer.read(legacy.MAX_TOKEN_BYTES + 2)
        if len(raw_token) > legacy.MAX_TOKEN_BYTES + 1:
            raise ValueError("authorization input exceeds its bounded limit")
        token = legacy._token(raw_token.decode("ascii").rstrip("\r\n"))
        worker_type = {
            "channel": HANumberWorker,
            "power_manual": HAPowerWorker,
            "power_automatic": HAPowerWorker,
            "resume_program": HAResumeWorker,
        }[config.action]
        worker = worker_type(config, token, sink=base.PrivateReport(args.report))
        for name in ("SIGINT", "SIGTERM", "SIGHUP"):
            signal.signal(getattr(signal, name), worker.request_stop)
        result = worker.run()
    except BaseException:
        print('{"status":"FAIL","reason":"ha_worker_setup_or_reporting_failed"}')
        return 1
    finally:
        token = ""
    print(json.dumps({key: result[key] for key in ("status", "experiment", "recovery")}))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
