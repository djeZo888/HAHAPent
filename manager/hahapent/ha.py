"""Read-only Core bridge using the App's Supervisor-provided credential.

No workstation profile, owner token, service calls, or configuration writes.
The fixed internal proxy is provided by Supervisor's homeassistant_api option.
"""

from __future__ import annotations

import json
import os
import re
import socket
import time
from typing import Any

import websocket

DOMAIN = re.compile(r"[a-z][a-z0-9_]{0,99}\Z")
USER_ID = re.compile(r"[a-f0-9]{32}\Z")
MAX_RESPONSE_BYTES = 4 * 1024 * 1024
REQUEST_TIMEOUT = 8


class HAError(Exception):
    """A public, credential-free error code."""

    def __init__(self, code: str = "ha_unavailable") -> None:
        self.code = code
        super().__init__(code)


class _BudgetSocket:
    """Bound a whole WebSocket exchange, including framing and slow responses."""

    def __init__(self, stream: Any) -> None:
        self.stream = stream
        self.deadline = time.monotonic() + REQUEST_TIMEOUT
        self.remaining = MAX_RESPONSE_BYTES

    def _timeout(self) -> None:
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise HAError()
        self.stream.settimeout(remaining)

    def recv(self, size: int, *args: Any) -> bytes:
        self._timeout()
        data = self.stream.recv(min(size, self.remaining + 1), *args)
        self.remaining -= len(data)
        if self.remaining < 0:
            raise HAError("ha_response_invalid")
        return data

    def send(self, data: bytes, *args: Any) -> int:
        self._timeout()
        return self.stream.send(data, *args)

    def __getattr__(self, name: str) -> Any:
        return getattr(self.stream, name)


class HomeAssistant:
    """Minimum read-only data for authorization and safe integration lifecycle."""

    def __init__(self, token: str | None = None) -> None:
        self._token = token if token is not None else os.environ.get("SUPERVISOR_TOKEN", "")

    @staticmethod
    def _message(connection: Any) -> dict:
        raw = connection.recv()
        if not isinstance(raw, str) or len(raw) > MAX_RESPONSE_BYTES:
            raise HAError("ha_response_invalid")
        value = json.loads(raw)
        if not isinstance(value, dict):
            raise HAError("ha_response_invalid")
        return value

    def _command(self, command: str, **parameters: Any) -> Any:
        if not self._token:
            raise HAError("ha_auth_unavailable")
        # No arbitrary host, caller-supplied command, proxy environment, or redirect.
        connection = None
        stream = None
        try:
            stream = _BudgetSocket(socket.create_connection(("supervisor", 80), REQUEST_TIMEOUT))
            connection = websocket.create_connection(
                "ws://supervisor/core/websocket",
                socket=stream,
                timeout=REQUEST_TIMEOUT,
                suppress_origin=True,
                redirect_limit=0,
            )
            if self._message(connection).get("type") != "auth_required":
                raise HAError("ha_auth_unavailable")
            connection.send(json.dumps({"type": "auth", "access_token": self._token}))
            if self._message(connection).get("type") != "auth_ok":
                raise HAError("ha_auth_unavailable")
            connection.send(json.dumps({"id": 1, "type": command, **parameters}))
            result = self._message(connection)
            if result.get("type") != "result" or result.get("id") != 1:
                raise HAError("ha_response_invalid")
            if result.get("success") is not True:
                if result.get("error", {}).get("code") == "not_found":
                    raise HAError("ha_not_found")
                raise HAError("ha_request_rejected")
            return result.get("result")
        except HAError:
            raise
        except Exception:
            # Never forward raw HTTP/WS errors, response bodies, or tokens.
            raise HAError() from None
        finally:
            if connection is not None:
                try:
                    connection.close(timeout=0)
                except Exception:
                    pass
            elif stream is not None:
                stream.close()

    def is_admin(self, user_id: str) -> bool:
        """Recheck current roles every time; never cache an administrator grant."""
        if not isinstance(user_id, str) or not USER_ID.fullmatch(user_id):
            return False
        users = self._command("config/auth/list")
        if not isinstance(users, list):
            raise HAError("ha_response_invalid")
        matches = [u for u in users if isinstance(u, dict) and u.get("id") == user_id]
        if len(matches) != 1:
            return False
        user = matches[0]
        groups = user.get("group_ids")
        if not isinstance(groups, list) or any(not isinstance(group, str) for group in groups):
            return False
        return (
            user.get("is_active") is True
            and user.get("system_generated") is False
            and (user.get("is_owner") is True or "system-admin" in groups)
        )

    def core_version(self) -> str:
        config = self._command("get_config")
        if not isinstance(config, dict) or not isinstance(config.get("version"), str):
            raise HAError("ha_response_invalid")
        return config["version"]

    @staticmethod
    def _domain(domain: str) -> None:
        if not isinstance(domain, str) or not DOMAIN.fullmatch(domain):
            raise HAError("invalid_domain")

    def config_entries(self, domain: str) -> list[dict]:
        self._domain(domain)
        entries = self._command("config_entries/get", domain=domain)
        if not isinstance(entries, list) or any(
            not isinstance(entry, dict) or entry.get("domain") != domain for entry in entries
        ):
            raise HAError("ha_response_invalid")
        # Keep user configuration and display names out of manager state/UI/logs.
        return [
            {key: entry.get(key) for key in ("domain", "entry_id", "state")} for entry in entries
        ]

    def _manifest(self, domain: str) -> dict | None:
        self._domain(domain)
        try:
            manifest = self._command("manifest/get", integration=domain)
        except HAError as error:
            if error.code == "ha_not_found":
                return None
            raise
        if not isinstance(manifest, dict) or manifest.get("domain") != domain:
            raise HAError("ha_response_invalid")
        return manifest

    def is_core_domain(self, domain: str) -> bool:
        manifest = self._manifest(domain)
        if manifest is None:
            return False
        if not isinstance(manifest.get("is_built_in"), bool) or not isinstance(
            manifest.get("overwrites_built_in"), bool
        ):
            raise HAError("ha_response_invalid")
        return manifest["is_built_in"] or manifest["overwrites_built_in"]

    def domain_status(self, domain: str) -> dict:
        entries = self.config_entries(domain)
        loaded = any(entry.get("state") == "loaded" for entry in entries)
        manifest = self._manifest(domain) if loaded else None
        return {
            "configured": bool(entries),
            "config_entry_count": len(entries),
            "loaded": loaded,
            "loaded_version": manifest.get("version") if manifest else None,
        }
