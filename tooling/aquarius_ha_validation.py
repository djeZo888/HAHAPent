"""Bounded native HA-service validation with independent Aquarius TCP recovery.

The frozen base worker supplies local deadlines, durable intent, fresh state
guards and finally cleanup. This adapter exercises only explicitly configured
Aquarius Number/Select entities. Authentication is supplied on stdin, retained
in memory, and never included in arguments, reports or exception messages.

An HTTP timeout does not cancel Home Assistant's shielded service task. Unknown
delivery therefore remains FAIL even if cleanup observes the original lamp
state. The bounded settling interval is a recovery precaution, not proof that
an arbitrarily delayed HA task cannot subsequently run.
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
import time
from dataclasses import dataclass, replace
from pathlib import Path
from urllib.parse import urlsplit

if __package__:
    from . import aquarius_validation as base
else:
    import aquarius_validation as base

HA_COORDINATOR_SECONDS = 3.0
UNCERTAIN_SETTLE_MARGIN = 0.25
MAX_HTTP_HEADER_BYTES = 16384
MAX_TOKEN_BYTES = 8192
HA_CLEANUP_MARGIN = HA_COORDINATOR_SECONDS + 0.5


class HAServiceError(base.ValidationError):
    """HA rejected the request or delivery is known not to have begun."""


class HACompletionUnknown(HAServiceError):
    """The HTTP connection cannot establish whether HA's service task has finished."""


@dataclass(frozen=True)
class Configuration:
    device: base.Configuration
    scheme: str
    host: str
    port: int
    number_entity: str
    mode_entity: str
    action: str
    restore_mode_via_ha: bool

    @classmethod
    def parse(cls, data, *, simulation=False):
        required = {"schema_version", "device", "ha", "action", "restore_mode_via_ha"}
        if (
            not isinstance(data, dict)
            or set(data) != required
            or type(data["schema_version"]) is not int
            or data["schema_version"] != 1
            or data["action"] not in ("channel", "manual")
            or type(data["restore_mode_via_ha"]) is not bool
        ):
            raise ValueError("invalid HA validation configuration")
        if data["restore_mode_via_ha"] and data["action"] != "manual":
            raise ValueError("HA Automatic restoration is reserved for the Manual-only test")
        device_data = data["device"]
        if data["action"] == "manual":
            if (
                not isinstance(device_data, dict)
                or type(device_data.get("delta")) is not int
                or device_data["delta"] != 0
            ):
                raise ValueError("a Manual-only test must explicitly specify zero channel change")
            # Zero is allowed only for the separately validated mode-only action.
            device = replace(
                base.Configuration.parse({**device_data, "delta": -1}, simulation=simulation),
                delta=0,
            )
        else:
            device = base.Configuration.parse(device_data, simulation=simulation)
        ha = data["ha"]
        if not isinstance(ha, dict) or set(ha) != {"origin", "number_entity", "mode_entity"}:
            raise ValueError("an exact HA origin and two exact entities are required")
        origin = urlsplit(ha["origin"])
        if (
            origin.scheme not in ("http", "https")
            or origin.path not in ("", "/")
            or (
                origin.username is not None
                or origin.password is not None
                or origin.query
                or origin.fragment
            )
        ):
            raise ValueError("HA origin must contain only an HTTP(S) scheme and private endpoint")
        host = str(ipaddress.ip_address(origin.hostname))
        address = ipaddress.ip_address(host)
        private = any(
            address in ipaddress.ip_network(network)
            for network in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16")
        )
        if not private and not (simulation and address.is_loopback):
            raise ValueError("an explicitly selected private IPv4 HA endpoint is required")
        port = origin.port if origin.port is not None else (443 if origin.scheme == "https" else 80)
        if not 1 <= port <= 65535:
            raise ValueError("invalid HA port")
        channel = "abcdef"[device.channel]
        if not isinstance(ha["number_entity"], str) or not re.fullmatch(
            rf"number\.aquarius_plant_led_channel_{channel}(?:_[1-9][0-9]*)?", ha["number_entity"]
        ):
            raise ValueError("the Number entity must identify the selected Aquarius channel")
        if not isinstance(ha["mode_entity"], str) or not re.fullmatch(
            r"select\.aquarius_plant_led_operating_mode(?:_[1-9][0-9]*)?", ha["mode_entity"]
        ):
            raise ValueError("the Select entity must identify Aquarius operating mode")
        return cls(
            device,
            origin.scheme,
            host,
            port,
            ha["number_entity"],
            ha["mode_entity"],
            data["action"],
            data["restore_mode_via_ha"],
        )


def _token(value):
    if (
        not isinstance(value, str)
        or not 1 <= len(value) <= MAX_TOKEN_BYTES
        or any(not 0x21 <= ord(character) <= 0x7E for character in value)
    ):
        raise ValueError("a single in-memory authorization token is required")
    return value


class HAService:
    """One fixed-origin HTTP request at a time; no redirects or response-body logging."""

    def __init__(self, config, token, clock=time.monotonic):
        self.config = config
        self.token = _token(token)
        self.clock = clock

    def _remaining(self, deadline):
        remaining = deadline - self.clock()
        if remaining <= 0:
            raise base.DeadlineError("HA request deadline reached")
        return remaining

    def call(self, action, value, deadline):
        if action == "channel":
            if type(value) is not int or not 0 <= value <= 100:
                raise ValueError("invalid HA channel percentage")
            path = "/api/services/number/set_value"
            payload = {"entity_id": self.config.number_entity, "value": value}
        elif action in ("manual", "automatic_program") and value is None:
            path = "/api/services/select/select_option"
            payload = {"entity_id": self.config.mode_entity, "option": action}
        else:
            raise ValueError("only the configured Aquarius Number and Select actions are permitted")
        body = json.dumps(payload, separators=(",", ":")).encode("ascii")
        host = self.config.host
        # Origin validation restricts hosts to IPv4 literals; no DNS or alternate destination.
        authority = f"{host}:{self.config.port}"
        request = (
            f"POST {path} HTTP/1.1\r\nHost: {authority}\r\n"
            f"Authorization: Bearer {self.token}\r\nContent-Type: application/json\r\n"
            f"Content-Length: {len(body)}\r\nConnection: close\r\n\r\n"
        ).encode("ascii") + body
        connection = None
        delivery_started = False
        try:
            connection = socket.create_connection(
                (host, self.config.port), timeout=self._remaining(deadline)
            )
            if self.config.scheme == "https":
                connection.settimeout(self._remaining(deadline))
                connection = ssl.create_default_context().wrap_socket(
                    connection, server_hostname=host
                )
            connection.settimeout(self._remaining(deadline))
            delivery_started = True
            connection.sendall(request)
            header = bytearray()
            while b"\r\n\r\n" not in header:
                connection.settimeout(self._remaining(deadline))
                chunk = connection.recv(1024)
                if not chunk:
                    raise HACompletionUnknown("HA closed HTTP before reporting service completion")
                header.extend(chunk)
                if len(header) > MAX_HTTP_HEADER_BYTES:
                    raise HACompletionUnknown("HA response headers exceeded the bounded limit")
            first_line = bytes(header).split(b"\r\n", 1)[0]
            match = re.fullmatch(rb"HTTP/1\.[01] ([0-9]{3})(?: [\x20-\x7e]*)?", first_line)
            if match is None:
                raise HACompletionUnknown("HA did not return a supported HTTP status line")
            status = int(match[1])
            if status in (400, 401, 403, 404):
                # Never follow Location or inspect/print a raw error response body.
                raise HAServiceError("HA returned an unsuccessful service status")
            if status != 200:
                raise HACompletionUnknown("HA did not establish successful service completion")
            # HA's blocking service endpoint has completed. The response body is
            # not a lamp confirmation; independent TCP readback is still mandatory.
        except (HAServiceError, HACompletionUnknown):
            raise
        except (OSError, ValueError, base.DeadlineError):
            if delivery_started:
                raise HACompletionUnknown("HTTP delivery or HA completion is uncertain") from None
            raise HAServiceError("HA connection failed before request delivery") from None
        finally:
            if connection is not None:
                connection.close()


class HAValidationWorker(base.ValidationWorker):
    """Use native HA services as the actuator and the frozen worker's guarded cleanup."""

    def __init__(self, config, token, *, service_factory=HAService, sleeper=time.sleep, **kwargs):
        super().__init__(config.device, sleeper=sleeper, **kwargs)
        self.ha_config = config
        self.service = service_factory(config, token, self.clock)
        self.sleeper = sleeper
        self.pending_until = None
        self.completion_unknown = False
        self.report["actuator"] = "home_assistant_native_service"
        self.report["ha_action"] = config.action
        self.report["restore_mode_via_ha"] = config.restore_mode_via_ha
        self.report["ha_completion"] = "NOT_SENT"

    def _ha_call(self, action, value, deadline, stage):
        self._check_stop()
        # HA's integration needs its own lamp connection. Release the observer
        # after the fresh guard, including before HA-based Automatic cleanup.
        # Keeping it open can starve controllers that process one client at a time.
        self._close()
        self.io_phase = "ha_service"
        self._event(stage + "_observer_connection_released")
        minimum = HA_CLEANUP_MARGIN if self.cleaning else base.WRITE_RECOVERY_MARGIN
        if deadline - self.clock() < minimum:
            raise base.DeadlineError("insufficient time for an HA action and independent readback")
        sent_at = self.clock()
        self._event(stage + "_ha_service_send", action=action)
        try:
            self.service.call(action, value, deadline)
        except HACompletionUnknown:
            self.completion_unknown = True
            self.pending_until = sent_at + HA_COORDINATOR_SECONDS + UNCERTAIN_SETTLE_MARGIN
            self.report["ha_completion"] = "UNKNOWN"
            self._event(stage + "_ha_completion_unknown")
            raise
        self.report["ha_completion"] = "UNKNOWN" if self.completion_unknown else "HTTP_COMPLETED"
        self._event(stage + "_ha_service_completed")
        self._check_stop()
        if self.cleaning:
            return self._fresh_recovery_read(
                deadline,
                reserve=0.0,
                stage=stage + "_ha_readback",
                expected_mode=0 if action == "automatic_program" else 1,
            )
        return self._read(deadline, fresh=True)

    def _command(self, channels, mode, deadline, stage):
        if stage == "experiment":
            if self.ha_config.action == "manual":
                if self.baseline.mode != 0 or channels != self.baseline.channels or mode != 1:
                    raise base.UnsafeState(
                        "Manual validation requires Automatic with unchanged channels"
                    )
                return self._ha_call("manual", None, deadline, stage)
            if channels != self.changed or mode != 1:
                raise base.UnsafeState("unexpected HA experiment target")
            return self._ha_call("channel", channels[self.config.channel], deadline, stage)
        if (
            stage == "restore_original_mode"
            and self.ha_config.restore_mode_via_ha
            and not self.completion_unknown
        ):
            if channels is not None or mode != 0:
                raise base.UnsafeState("only original Automatic mode may be restored through HA")
            return self._ha_call("automatic_program", None, deadline, stage)
        return super()._command(channels, mode, deadline, stage)

    def _settle_uncertain(self, deadline):
        if self.pending_until is None:
            return
        remaining = self.pending_until - self.clock()
        if remaining > 0:
            self._event("ha_unknown_completion_wait_started")
            self.sleeper(min(remaining, max(0, deadline - self.clock())))
            self._event("ha_unknown_completion_wait_finished")
        if self.clock() >= deadline:
            raise base.DeadlineError("HA completion uncertainty consumed the cleanup allowance")

    def _recover(self, deadline):
        self._settle_uncertain(deadline)
        try:
            super()._recover(deadline)
        except HACompletionUnknown:
            # A timed-out HA Automatic-restoration request must never be retried.
            self._settle_uncertain(deadline)
            observed = self._fresh_recovery_read(
                deadline,
                reserve=0.0,
                stage="ha_uncertain_restoration",
                expected_mode=self.baseline.mode,
            )
            self._event("ha_uncertain_restoration_observed", mode=observed.mode)
            raise base.UnsafeState("HA restoration completion remains unknown") from None
        if self.completion_unknown:
            self._event("original_state_observed_but_ha_completion_unknown")
            raise base.UnsafeState("a late HA task cannot be excluded despite observed cleanup")


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
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        config = _configuration(args.config)
        raw_token = sys.stdin.buffer.read(MAX_TOKEN_BYTES + 2)
        if len(raw_token) > MAX_TOKEN_BYTES + 1:
            raise ValueError("authorization input exceeds its bounded limit")
        token = _token(raw_token.decode("ascii").rstrip("\r\n"))
        worker = HAValidationWorker(config, token, sink=base.PrivateReport(args.report))
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
