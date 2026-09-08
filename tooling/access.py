"""Restricted, read-only Task 001 access checks.

Secrets are loaded from owner-only files outside checkouts, are never represented
in exceptions, and never become report fields. HTTP and WebSocket redirects are
rejected before credentials can be sent to another origin. This is local tooling,
not an installed integration or a general-purpose Home Assistant client.
"""

from __future__ import annotations

import http.client
import io
import ipaddress
import json
import os
import queue
import re
import socket
import ssl
import stat
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlsplit

EXPECTED_REPOSITORY = "djeZo888/HAHAPent"
DEFAULT_PROFILE = Path.home() / ".config/hahapent/bootstrap.json"
MAX_PRIVATE_BYTES = 65536
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
REQUEST_TIMEOUT = 15.0
STATUS_VALUES = frozenset(
    {"PASS", "FAIL", "BLOCKED", "NOT_TESTED", "AVAILABLE_NOT_EXERCISED", "NOT_REQUIRED"}
)
_ERROR_CODES = frozenset(
    {
        "private_file_rejected",
        "private_file_unavailable",
        "profile_invalid",
        "credentials_invalid",
        "target_rejected",
        "redirect_rejected",
        "response_too_large",
        "request_timeout",
        "request_failed",
        "http_rejected",
        "response_invalid",
        "ha_not_identified",
        "websocket_unavailable",
        "authentication_rejected",
        "command_rejected",
        "report_path_rejected",
        "git_invocation_required",
    }
)


class AccessError(Exception):
    """An allowlisted error code, never a remote body, URL, or exception string."""

    def __init__(self, code: str):
        self.code = code if code in _ERROR_CODES else "request_failed"
        super().__init__(self.code)


@dataclass(frozen=True, repr=False)
class Credentials:
    github_url: str
    github_token: str
    ha_host: str
    ha_username: str
    ha_password: str
    ha_token: str

    def __repr__(self) -> str:
        return "Credentials(<redacted>)"


_LABELS = {
    "github url": "github_url",
    "github api token": "github_token",
    "homeassistant ip": "ha_host",
    "homeassistant username": "ha_username",
    "homeassistant password": "ha_password",
    "homeassistant token": "ha_token",
}
_PLACEHOLDERS = frozenset(
    {
        "changeme",
        "change_me",
        "change-me",
        "replace_me",
        "replace-me",
        "placeholder",
        "redacted",
        "todo",
        "tbd",
        "none",
        "null",
        "password",
        "token",
        "example",
    }
)


def parse_credentials(text: str) -> Credentials:
    """Parse first-colon records, removing at most one formatting space.

    Label matching is case-insensitive and ignores label whitespace. Values are
    preserved byte-for-character after decoding, including colons, backslashes,
    leading spaces beyond the one separator space, tabs, and trailing spaces.
    LF and CRLF are accepted. Unknown records, duplicates, missing labels, NUL,
    embedded CR, and recognizable placeholders fail without echoing their input.
    """
    values: dict[str, str] = {}
    if not isinstance(text, str) or len(text) > MAX_PRIVATE_BYTES or "\x00" in text:
        raise AccessError("credentials_invalid")
    for raw in text.split("\n"):
        line = raw[:-1] if raw.endswith("\r") else raw
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        label, separator, value = line.partition(":")
        key = _LABELS.get(" ".join(label.casefold().split()))
        if not separator or key is None or key in values:
            raise AccessError("credentials_invalid")
        if value.startswith(" "):
            value = value[1:]
        normalized = value.strip().casefold()
        if (
            not normalized
            or any(ord(character) < 32 and character != "\t" for character in value)
            or normalized in _PLACEHOLDERS
            or normalized.startswith(("your_", "your-", "insert_", "insert-", "replace_with"))
            or re.fullmatch(r"[<\[{].*[>\]}]", normalized)
            or re.fullmatch(r"[x*]{3,}", normalized)
        ):
            raise AccessError("credentials_invalid")
        values[key] = value
    if set(values) != set(_LABELS.values()):
        raise AccessError("credentials_invalid")
    return Credentials(**values)


def _within(path: Path, root: Path) -> bool:
    return path == root or root in path.parents


def _outside_worktrees(path: Path, worktree_roots: tuple[Path, ...]) -> None:
    roots = (Path(__file__).resolve().parents[1],) + worktree_roots
    if any(_within(path, root.resolve()) for root in roots):
        raise AccessError("private_file_rejected")
    if any((parent / ".git").exists() for parent in (path.parent, *path.parents)):
        raise AccessError("private_file_rejected")


def read_private_file(path: Path, worktree_roots: tuple[Path, ...] = ()) -> str:
    """Read an ordinary, single-link, owner-only file from a private directory."""
    descriptor: Optional[int] = None
    try:
        expanded = Path(path).expanduser()
        if not expanded.is_absolute() or expanded.is_symlink():
            raise AccessError("private_file_rejected")
        resolved = expanded.resolve(strict=True)
        _outside_worktrees(resolved, worktree_roots)
        # Both bootstrap and its optional secrets child are private directories.
        directories = [resolved.parent]
        if resolved.parent.name == "secrets":
            directories.append(resolved.parent.parent)
        for directory in directories:
            info = directory.stat()
            if (
                not stat.S_ISDIR(info.st_mode)
                or info.st_uid != os.getuid()
                or stat.S_IMODE(info.st_mode) != 0o700
            ):
                raise AccessError("private_file_rejected")
        descriptor = os.open(resolved, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        info = os.fstat(descriptor)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != os.getuid()
            or stat.S_IMODE(info.st_mode) != 0o600
            or info.st_nlink != 1
            or info.st_size > MAX_PRIVATE_BYTES
        ):
            raise AccessError("private_file_rejected")
        with os.fdopen(descriptor, "rb") as source:
            descriptor = None
            data = source.read(MAX_PRIVATE_BYTES + 1)
        if len(data) > MAX_PRIVATE_BYTES:
            raise AccessError("private_file_rejected")
        return data.decode("utf-8")
    except AccessError:
        raise
    except Exception:
        raise AccessError("private_file_unavailable") from None
    finally:
        if descriptor is not None:
            os.close(descriptor)


def _host(value: Any) -> str:
    try:
        if not isinstance(value, str) or value != value.strip() or "%" in value:
            raise ValueError
        address = ipaddress.ip_address(value)
        approved_ranges = (
            ipaddress.ip_network("10.0.0.0/8"),
            ipaddress.ip_network("172.16.0.0/12"),
            ipaddress.ip_network("192.168.0.0/16"),
            ipaddress.ip_network("fc00::/7"),
        )
        if not any(address in network for network in approved_ranges):
            raise ValueError
        return str(address)
    except Exception:
        raise AccessError("target_rejected") from None


def _repository_url(value: str, repository: str) -> None:
    try:
        parsed = urlsplit(value)
        if (
            value != value.strip()
            or parsed.scheme != "https"
            or parsed.netloc != "github.com"
            or parsed.path not in (f"/{repository}", f"/{repository}.git")
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError
    except Exception:
        raise AccessError("target_rejected") from None


@dataclass(frozen=True, repr=False)
class Profile:
    github_repository: str
    ha_host: str
    credential_file: Path
    credentials: Credentials = field(repr=False)
    ha_url: str = ""
    ha_ssh_key: Path = field(
        default_factory=lambda: Path.home() / ".config/hahapent/secrets/hahapent_ha_dev_ed25519"
    )
    ha_ssh_known_hosts: Path = field(
        default_factory=lambda: Path.home() / ".config/hahapent/ha_known_hosts"
    )
    ha_ssh_port: int = 22
    ha_config_dir: str = "/config"

    def __post_init__(self) -> None:
        if self.github_repository != EXPECTED_REPOSITORY:
            raise AccessError("target_rejected")
        _repository_url(self.credentials.github_url, self.github_repository)
        host = _host(self.ha_host)
        if _host(self.credentials.ha_host) != host:
            raise AccessError("target_rejected")
        authority = f"[{host}]" if ":" in host else host
        value = self.ha_url or f"http://{authority}:8123"
        try:
            parsed = urlsplit(value)
            if (
                value != value.strip()
                or parsed.scheme not in ("http", "https")
                or parsed.hostname != host
                or parsed.username is not None
                or parsed.password is not None
                or parsed.port not in (None, 80, 443, 8123)
                or parsed.path not in ("", "/")
                or parsed.query
                or parsed.fragment
            ):
                raise ValueError
        except Exception:
            raise AccessError("target_rejected") from None
        object.__setattr__(self, "ha_host", host)
        object.__setattr__(self, "ha_url", value.rstrip("/"))
        if (
            not isinstance(self.ha_ssh_port, int)
            or isinstance(self.ha_ssh_port, bool)
            or not 1 <= self.ha_ssh_port <= 65535
            or self.ha_config_dir != "/config"
        ):
            raise AccessError("profile_invalid")
        try:
            for field_name in ("ha_ssh_key", "ha_ssh_known_hosts"):
                path = Path(getattr(self, field_name)).expanduser()
                if not path.is_absolute():
                    raise AccessError("profile_invalid")
                _outside_worktrees(path.resolve(), ())
                object.__setattr__(self, field_name, path)
        except AccessError:
            raise
        except Exception:
            raise AccessError("profile_invalid") from None

    @property
    def repository(self) -> str:
        return self.github_repository

    def __repr__(self) -> str:
        return "Profile(<private configuration redacted>)"


def _unique_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise AccessError("profile_invalid")
        result[key] = value
    return result


def load_private_profile(
    profile_path: Optional[Path] = None, worktree_roots: tuple[Path, ...] = ()
) -> Profile:
    """Resolve the durable private profile; do not discover credentials in Git."""
    try:
        raw = json.loads(
            read_private_file(profile_path or DEFAULT_PROFILE, worktree_roots),
            object_pairs_hook=_unique_json_object,
        )
        if not isinstance(raw, dict):
            raise AccessError("profile_invalid")
        credential_file = Path(
            raw.get("credential_file", "~/.config/hahapent/secrets/credentials.txt")
        ).expanduser()
        credentials = parse_credentials(read_private_file(credential_file, worktree_roots))
        expected_username = raw.get("ha_expected_username", credentials.ha_username)
        if expected_username != credentials.ha_username:
            raise AccessError("profile_invalid")
        ssh_settings = {
            key: raw[key]
            for key in ("ha_ssh_key", "ha_ssh_known_hosts", "ha_ssh_port", "ha_config_dir")
            if key in raw
        }
        return Profile(
            github_repository=raw["github_repository"],
            ha_host=raw["ha_host"],
            credential_file=credential_file,
            credentials=credentials,
            ha_url=raw.get("ha_url", ""),
            **ssh_settings,
        )
    except AccessError:
        raise
    except Exception:
        raise AccessError("profile_invalid") from None


class _BoundedReader(io.RawIOBase):
    def __init__(self, stream: BoundedSocket):
        self.stream = stream

    def readable(self) -> bool:
        return True

    def readinto(self, buffer: bytearray) -> int:
        data = self.stream.recv(len(buffer))
        buffer[: len(data)] = data
        return len(data)


class BoundedSocket:
    """Apply a total receive byte budget and wall-clock deadline to socket I/O."""

    def __init__(self, stream: Any, deadline: float, byte_limit: int = MAX_RESPONSE_BYTES):
        self.stream = stream
        self.deadline = deadline
        self.remaining = byte_limit

    def _timeout(self) -> None:
        remaining_time = self.deadline - time.monotonic()
        if remaining_time <= 0:
            raise AccessError("request_timeout")
        self.stream.settimeout(remaining_time)

    def recv(self, size: int, *args: Any) -> bytes:
        self._timeout()
        data = self.stream.recv(min(size, self.remaining + 1), *args)
        self.remaining -= len(data)
        if self.remaining < 0:
            raise AccessError("response_too_large")
        return data

    def send(self, data: bytes, *args: Any) -> int:
        self._timeout()
        return self.stream.send(data, *args)

    def sendall(self, data: bytes, *args: Any) -> None:
        view = memoryview(data)
        while view:
            count = self.send(view, *args)
            if count <= 0:
                raise AccessError("request_failed")
            view = view[count:]

    def makefile(self, mode: str, *args: Any, **kwargs: Any) -> io.BufferedReader:
        if mode != "rb":
            raise AccessError("request_failed")
        return io.BufferedReader(_BoundedReader(self))

    def __getattr__(self, name: str) -> Any:
        return getattr(self.stream, name)


def _resolve_address(host: str, port: int, deadline: float) -> list[Any]:
    """Bound DNS too; an unresolved daemon worker cannot hold the CLI open."""
    results: queue.Queue[Any] = queue.Queue(maxsize=1)

    def resolve() -> None:
        try:
            results.put(socket.getaddrinfo(host, port, type=socket.SOCK_STREAM))
        except Exception:
            results.put(None)

    threading.Thread(target=resolve, daemon=True).start()
    try:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise AccessError("request_timeout")
        addresses = results.get(timeout=remaining)
        if not addresses:
            raise AccessError("request_failed")
        return addresses
    except queue.Empty:
        raise AccessError("request_timeout") from None


def _connect(url: str, timeout: float) -> BoundedSocket:
    """Direct connection: environment HTTP proxy settings are deliberately unused."""
    parsed = urlsplit(url)
    deadline = time.monotonic() + timeout
    port = parsed.port or (443 if parsed.scheme in ("https", "wss") else 80)
    stream: Any = None
    for family, kind, protocol, _, address in _resolve_address(parsed.hostname, port, deadline):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise AccessError("request_timeout")
        candidate = socket.socket(family, kind, protocol)
        try:
            candidate.settimeout(remaining)
            candidate.connect(address)
            stream = candidate
            break
        except OSError:
            candidate.close()
    if stream is None:
        raise AccessError("request_failed")
    try:
        if parsed.scheme in ("https", "wss"):
            stream.settimeout(max(0.001, deadline - time.monotonic()))
            stream = ssl.create_default_context().wrap_socket(
                stream, server_hostname=parsed.hostname
            )
        return BoundedSocket(stream, deadline)
    except Exception:
        stream.close()
        raise


class AccessClient:
    """Only the exact selected origins and explicit Task 001 GET paths are allowed."""

    def __init__(self, profile: Profile, timeout: float = REQUEST_TIMEOUT):
        if not isinstance(profile, Profile) or not 0 < timeout <= REQUEST_TIMEOUT:
            raise AccessError("target_rejected")
        profile.__post_init__()
        self.profile = profile
        self.timeout = timeout
        self.ha_identified = False

    def get(self, service: str, path: str, authenticated: bool = False) -> Any:
        if service == "github":
            if path not in ("/user", f"/repos/{self.profile.repository}") or not authenticated:
                raise AccessError("target_rejected")
            origin = "https://api.github.com"
            token = self.profile.credentials.github_token
        elif service == "ha":
            allowed = ("/api/", "/api/config") if authenticated else ("/auth/providers", "/")
            if path not in allowed or (authenticated and not self.ha_identified):
                raise AccessError("target_rejected")
            origin = self.profile.ha_url
            token = self.profile.credentials.ha_token if authenticated else None
        else:
            raise AccessError("target_rejected")
        connection: Optional[http.client.HTTPConnection] = None
        try:
            parsed = urlsplit(origin)
            connection = http.client.HTTPConnection(parsed.hostname, parsed.port)
            connection.sock = _connect(origin, self.timeout)
            headers = {"Accept": "application/json", "User-Agent": "HAHAPent-Task001"}
            if token is not None:
                headers["Authorization"] = "Bearer " + token
            if service == "github":
                headers["X-GitHub-Api-Version"] = "2022-11-28"
            connection.request("GET", path, headers=headers)
            response = connection.getresponse()
            if 300 <= response.status < 400:
                raise AccessError("redirect_rejected")
            if response.status != 200:
                # Never read or attach a raw HTTP error body.
                raise AccessError("http_rejected")
            content = response.read(MAX_RESPONSE_BYTES + 1)
            if len(content) > MAX_RESPONSE_BYTES:
                raise AccessError("response_too_large")
            if service == "ha" and path == "/":
                return content.decode("utf-8")
            return json.loads(content)
        except AccessError:
            raise
        except (TimeoutError, socket.timeout):
            raise AccessError("request_timeout") from None
        except Exception:
            raise AccessError("request_failed") from None
        finally:
            if connection is not None:
                connection.close()

    def identify_ha(self) -> None:
        try:
            providers = self.get("ha", "/auth/providers")
            if isinstance(providers, dict):
                providers = providers.get("providers")
            if (
                isinstance(providers, list)
                and providers
                and all(isinstance(item, dict) and "type" in item for item in providers)
                and any(item.get("type") == "homeassistant" for item in providers)
            ):
                self.ha_identified = True
                return
        except AccessError as error:
            if error.code == "redirect_rejected":
                raise
        frontend = self.get("ha", "/")
        if isinstance(frontend, str) and (
            "<home-assistant" in frontend or "home-assistant-frontend" in frontend
        ):
            self.ha_identified = True
            return
        raise AccessError("ha_not_identified")

    def websocket(self) -> HAWebSocket:
        if not self.ha_identified:
            raise AccessError("target_rejected")
        return HAWebSocket(self.profile, self.timeout, _identified=True)


class HAWebSocket:
    """A bounded connection exposing only three read-only WebSocket commands."""

    ALLOWED_COMMANDS = frozenset({"auth/current_user", "get_config", "config/auth/list"})

    def __init__(
        self, profile: Profile, timeout: float = REQUEST_TIMEOUT, *, _identified: bool = False
    ):
        if not isinstance(profile, Profile) or not 0 < timeout <= REQUEST_TIMEOUT:
            raise AccessError("target_rejected")
        profile.__post_init__()
        self.profile = profile
        self.timeout = timeout
        self.identified = _identified
        self.connection: Any = None
        self.next_id = 1

    def __enter__(self) -> HAWebSocket:
        try:
            import websocket

            if not self.identified:
                AccessClient(self.profile, self.timeout).identify_ha()
            websocket.enableTrace(False)
            url = self.profile.ha_url.replace("http", "ws", 1) + "/api/websocket"
            self.connection = websocket.WebSocket()
            self.connection.connect(
                url,
                socket=_connect(url, self.timeout),
                timeout=self.timeout,
                redirect_limit=0,
                suppress_origin=True,
            )
            # websocket-client 1.9.0 can return after redirect_limit=0 without
            # raising; inspect the status before receiving/sending authentication.
            status = self.connection.getstatus()
            if isinstance(status, int) and 300 <= status < 400:
                raise AccessError("redirect_rejected")
            if status != 101:
                raise AccessError("response_invalid")
            if self._receive().get("type") != "auth_required":
                raise AccessError("response_invalid")
            self.connection.send(
                json.dumps({"type": "auth", "access_token": self.profile.credentials.ha_token})
            )
            if self._receive().get("type") != "auth_ok":
                raise AccessError("authentication_rejected")
            return self
        except AccessError:
            self.close()
            raise
        except ImportError:
            self.close()
            raise AccessError("websocket_unavailable") from None
        except Exception:
            self.close()
            raise AccessError("request_failed") from None

    def _receive(self) -> dict[str, Any]:
        try:
            raw = self.connection.recv()
            if not isinstance(raw, (str, bytes)) or len(raw) > MAX_RESPONSE_BYTES:
                raise AccessError("response_too_large")
            parsed = json.loads(raw)
            if not isinstance(parsed, dict):
                raise AccessError("response_invalid")
            return parsed
        except AccessError:
            raise
        except Exception:
            raise AccessError("response_invalid") from None

    def command(self, command: str) -> Any:
        if command not in self.ALLOWED_COMMANDS:
            raise AccessError("target_rejected")
        try:
            identifier = self.next_id
            self.next_id += 1
            self.connection.send(json.dumps({"id": identifier, "type": command}))
            response = self._receive()
            if (
                response.get("id") != identifier
                or response.get("type") != "result"
                or response.get("success") is not True
            ):
                raise AccessError("command_rejected")
            return response.get("result")
        except AccessError:
            raise
        except Exception:
            raise AccessError("request_failed") from None

    def close(self) -> None:
        if self.connection is not None:
            try:
                # Shut down locally without waiting on a potentially untrusted peer.
                self.connection.shutdown()
            except Exception:
                pass
            self.connection = None

    def __exit__(self, *args: Any) -> None:
        self.close()


def _version(value: Any) -> Optional[str]:
    if isinstance(value, str) and re.fullmatch(
        r"\d{4}\.\d{1,2}\.\d{1,3}(?:[ab]\d+|\.dev\d+)?", value
    ):
        return value
    return None


def _result(status: str, reason: Optional[str] = None) -> dict[str, str]:
    result = {"status": status}
    if reason is not None:
        result["reason"] = AccessError(reason).code
    return result


def check_access(profile: Profile, client: Optional[AccessClient] = None) -> dict[str, Any]:
    """Return allowlisted evidence only; no login, IP, user list, or raw config."""
    client = client or AccessClient(profile)
    checks = {
        name: _result("NOT_TESTED")
        for name in (
            "github_identity",
            "github_repository_read",
            "github_write",
            "ha_identification",
            "ha_rest_authentication",
            "ha_rest_config",
            "ha_websocket_authentication",
            "ha_current_user",
            "ha_token_username_binding",
            "ha_password_login",
            "ha_websocket_config",
            "ha_administrator_read",
            "ha_write",
        )
    }
    facts: dict[str, Any] = {}
    report: dict[str, Any] = {"schema_version": 1, "checks": checks, "facts": facts}
    for name, path in (
        ("github_identity", "/user"),
        ("github_repository_read", f"/repos/{profile.repository}"),
    ):
        try:
            response = client.get("github", path, authenticated=True)
            if not isinstance(response, dict):
                raise AccessError("response_invalid")
            if name == "github_identity":
                if not isinstance(response.get("login"), str) or not response.get("login"):
                    raise AccessError("response_invalid")
            else:
                if response.get("full_name") != profile.repository:
                    raise AccessError("target_rejected")
                permissions = response.get("permissions", {})
                if isinstance(permissions, dict) and permissions.get("push") is True:
                    checks["github_write"] = _result("AVAILABLE_NOT_EXERCISED")
            checks[name] = _result("PASS")
        except AccessError as error:
            checks[name] = _result("FAIL", error.code)
        except Exception:
            checks[name] = _result("FAIL", "request_failed")
    current = "ha_identification"
    try:
        client.identify_ha()
        checks[current] = _result("PASS")
        current = "ha_rest_authentication"
        response = client.get("ha", "/api/", authenticated=True)
        if not isinstance(response, dict) or response.get("message") != "API running.":
            raise AccessError("response_invalid")
        checks[current] = _result("PASS")
        current = "ha_rest_config"
        config = client.get("ha", "/api/config", authenticated=True)
        if not isinstance(config, dict):
            raise AccessError("response_invalid")
        version = _version(config.get("version"))
        if version:
            facts["ha_core_version"] = version
        checks[current] = _result("PASS")
        current = "ha_websocket_authentication"
        with client.websocket() as connection:
            checks[current] = _result("PASS")
            current = "ha_current_user"
            user = connection.command("auth/current_user")
            if not isinstance(user, dict):
                raise AccessError("response_invalid")
            for key in ("is_owner", "is_admin"):
                if isinstance(user.get(key), bool):
                    facts[f"ha_{key}"] = user[key]
            checks[current] = _result("PASS")
            current = "ha_websocket_config"
            config = connection.command("get_config")
            if not isinstance(config, dict):
                raise AccessError("response_invalid")
            checks[current] = _result("PASS")
            current = "ha_administrator_read"
            users = connection.command("config/auth/list")
            if not isinstance(users, list):
                raise AccessError("response_invalid")
            # No user records or counts leave this check.
            del users
            checks[current] = _result("PASS")
    except AccessError as error:
        checks[current] = _result(
            "BLOCKED" if error.code == "websocket_unavailable" else "FAIL", error.code
        )
    except Exception:
        checks[current] = _result("FAIL", "request_failed")
    return report
