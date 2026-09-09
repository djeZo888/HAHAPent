"""Exact-target native HA routes for private Task 004 acceptance workers."""

from __future__ import annotations

import ipaddress
import json
import re
import socket
import ssl
from dataclasses import dataclass, replace
from urllib.parse import urlsplit

if __package__:
    from . import aquarius_ha_validation as legacy
    from . import aquarius_validation as base
else:
    import aquarius_ha_validation as legacy
    import aquarius_validation as base

HAServiceError = legacy.HAServiceError
HACompletionUnknown = legacy.HACompletionUnknown


@dataclass(frozen=True)
class Configuration:
    device: base.Configuration
    action: str
    scheme: str
    host: str
    port: int
    number_entity: str
    light_entity: str
    resume_entity: str

    @classmethod
    def parse(cls, data, *, simulation=False):
        if (
            not isinstance(data, dict)
            or set(data) != {"schema_version", "device", "action", "ha"}
            or type(data["schema_version"]) is not int
            or data["schema_version"] != 1
            or data["action"]
            not in ("channel", "power_manual", "power_automatic", "resume_program")
        ):
            raise ValueError("invalid Task 004 HA validation configuration")
        action, raw = data["action"], data["device"]
        if action != "channel":
            if not isinstance(raw, dict) or type(raw.get("delta")) is not int or raw["delta"] != 0:
                raise ValueError("power and Resume validation require an explicit zero delta")
            device = replace(
                base.Configuration.parse({**raw, "delta": -1}, simulation=simulation), delta=0
            )
        else:
            device = base.Configuration.parse(raw, simulation=simulation)
        ha = data["ha"]
        if not isinstance(ha, dict) or set(ha) != {
            "origin",
            "number_entity",
            "light_entity",
            "resume_entity",
        }:
            raise ValueError("one exact HA origin and exact Aquarius entity IDs are required")
        if not isinstance(ha["origin"], str):
            raise ValueError("HA origin must be a private HTTP(S) endpoint string")
        origin = urlsplit(ha["origin"])
        if (
            origin.scheme not in ("http", "https")
            or origin.path not in ("", "/")
            or origin.username is not None
            or origin.password is not None
            or origin.query
            or origin.fragment
        ):
            raise ValueError("HA origin must be a private HTTP(S) endpoint only")
        host = str(ipaddress.ip_address(origin.hostname))
        address = ipaddress.ip_address(host)
        if address.version != 4:
            raise ValueError("HA origin must select a private IPv4 endpoint")
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
        expressions = {
            "number_entity": rf"number\.aquarius_plant_led_channel_{channel}(?:_[1-9][0-9]*)?",
            "light_entity": r"light\.aquarius_plant_led_lamp(?:_[1-9][0-9]*)?",
            "resume_entity": r"button\.aquarius_plant_led_resume_schedule(?:_[1-9][0-9]*)?",
        }
        for key, expression in expressions.items():
            if not isinstance(ha[key], str) or not re.fullmatch(expression, ha[key]):
                raise ValueError("entity IDs must identify the exact supported Aquarius controls")
        return cls(
            device,
            action,
            origin.scheme,
            host,
            port,
            ha["number_entity"],
            ha["light_entity"],
            ha["resume_entity"],
        )


class Service(legacy.HAService):
    """Reuse token/deadline validation, with a separate fixed native-service allowlist.

    The frozen predecessor inlines its route selection. The bounded HTTP exchange
    is reproduced here to add routes without modifying that reviewed executable.
    An HTTP response establishes service completion, never physical lamp state.
    """

    def call(self, action, value, deadline):
        permitted = {
            "channel": ("channel",),
            "power_manual": ("off", "on"),
            "power_automatic": ("off", "on"),
            "resume_program": ("resume",),
        }
        if action not in permitted[self.config.action]:
            raise ValueError("HA action is outside the configured validation transaction")
        if action == "channel":
            if type(value) is not int or not 0 <= value <= 100:
                raise ValueError("invalid HA channel percentage")
            path = "/api/services/number/set_value"
            payload = {"entity_id": self.config.number_entity, "value": value}
        elif value is not None:
            raise ValueError("power and Resume accept no brightness or other service data")
        elif action in ("off", "on"):
            path = "/api/services/light/turn_" + action
            payload = {"entity_id": self.config.light_entity}
        else:
            path = "/api/services/button/press"
            payload = {"entity_id": self.config.resume_entity}
        body = json.dumps(payload, separators=(",", ":")).encode("ascii")
        request = (
            f"POST {path} HTTP/1.1\r\nHost: {self.config.host}:{self.config.port}\r\n"
            f"Authorization: Bearer {self.token}\r\nContent-Type: application/json\r\n"
            f"Content-Length: {len(body)}\r\nConnection: close\r\n\r\n"
        ).encode("ascii") + body
        connection = None
        delivery_started = False
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
            delivery_started = True
            connection.sendall(request)
            header = bytearray()
            while b"\r\n\r\n" not in header:
                connection.settimeout(self._remaining(deadline))
                chunk = connection.recv(1024)
                if not chunk:
                    raise HACompletionUnknown("HA closed HTTP before reporting service completion")
                header.extend(chunk)
                if len(header) > legacy.MAX_HTTP_HEADER_BYTES:
                    raise HACompletionUnknown("HA response headers exceeded the bounded limit")
            first_line = bytes(header).split(b"\r\n", 1)[0]
            match = re.fullmatch(rb"HTTP/1\.[01] ([0-9]{3})(?: [\x20-\x7e]*)?", first_line)
            if match is None:
                raise HACompletionUnknown("HA did not return a supported HTTP status line")
            status = int(match[1])
            if status in (400, 401, 403, 404):
                raise HAServiceError("HA returned an unsuccessful service status")
            if status != 200:
                raise HACompletionUnknown("HA did not establish successful service completion")
        except HAServiceError:
            raise
        except (OSError, ValueError, base.DeadlineError):
            if delivery_started:
                raise HACompletionUnknown("HTTP delivery or HA completion is uncertain") from None
            raise HAServiceError("HA connection failed before request delivery") from None
        finally:
            if connection is not None:
                connection.close()
