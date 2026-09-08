"""Administrator-only, same-origin HTTP interface behind trusted HA Ingress."""

from __future__ import annotations

import json
import os
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from .ha import HAError, HomeAssistant

TRUSTED_INGRESS = "172.30.32.2"
MAX_REQUEST_BYTES = 16 * 1024
STATIC = Path(__file__).with_name("static")
CODE = re.compile(r"[a-z][a-z0-9_]{0,79}\Z")
ERROR_MESSAGES = {
    "forbidden": "Open Suite Manager from Home Assistant using an administrator account.",
    "origin_rejected": "The request must come from this Home Assistant interface.",
    "invalid_request": "The request is invalid. Refresh the interface and try again.",
    "request_too_large": "The request exceeds the allowed size.",
    "busy": "Another operation is running. Wait for it to finish.",
    "ha_unavailable": "Home Assistant is unavailable. Management is paused until it returns.",
    "ha_auth_unavailable": "The App cannot verify Home Assistant access. Check App permissions.",
    "ha_response_invalid": "Home Assistant returned an unexpected response. No action was taken.",
    "ha_request_rejected": "Home Assistant rejected the read-only verification request.",
    "config_entries_exist": "Remove this integration in Home Assistant first, then uninstall code.",
    "configured": "Remove this integration in Home Assistant first, then uninstall code.",
    "remove_native_config_entries_first": (
        "Remove this integration in Home Assistant first, then uninstall code."
    ),
    "ha_status_unavailable": "Home Assistant status is unavailable. File changes are blocked.",
    "rollback_unavailable": "There is no previous code version available for this integration.",
    "dependency_unavailable": (
        "A required integration is missing or incompatible. Install its required version first."
    ),
    "recovery_required": (
        "Recovery needs attention. File changes are blocked; use the recovery instructions."
    ),
    "ownership_conflict": "Existing code belongs to another installation. It will not be replaced.",
    "externally_modified": "Installed files have changed outside Suite Manager. No files replaced.",
    "operation_failed": "The operation failed safely. Review recovery status before retrying.",
}


class WebError(Exception):
    def __init__(self, code: str, status: int = 400) -> None:
        self.code = code
        self.status = status
        super().__init__(code)


def public_error(error: Exception) -> dict:
    code = getattr(error, "code", "operation_failed")
    if not isinstance(code, str) or not CODE.fullmatch(code):
        code = "operation_failed"
    return {"code": code, "message": ERROR_MESSAGES.get(code, "Operation blocked: " + code + ".")}


def authorize(peer: str, headers: Any, ha: Any, *, mutation: bool = False) -> None:
    """Identity headers are trusted only from Supervisor's actual network peer.

    Supervisor 2026.08.0 api/ingress.py removes client identity headers and
    derives X-Remote-User-Id from its authenticated Ingress session. Neither
    X-Forwarded-For, usernames, nor sidebar visibility establish this boundary.
    """
    if peer != TRUSTED_INGRESS:
        raise WebError("forbidden", 403)
    identities = headers.get_all("X-Remote-User-Id", [])
    if len(identities) != 1 or not ha.is_admin(identities[0]):
        raise WebError("forbidden", 403)
    if mutation:
        hosts = headers.get_all("Host", [])
        origins = headers.get_all("Origin", [])
        try:
            origin = urlsplit(origins[0]) if len(origins) == 1 else None
            valid_origin = (
                origin is not None
                and origin.scheme in ("http", "https")
                and len(hosts) == 1
                and origin.netloc == hosts[0]
                and origin.path in ("", "/")
                and not origin.query
                and not origin.fragment
                and not origin.username
                and not origin.password
            )
        except ValueError:
            valid_origin = False
        if not valid_origin or headers.get_all("X-HAHAPent-Request", []) != ["1"]:
            raise WebError("origin_rejected", 403)
        if headers.get("Sec-Fetch-Site", "same-origin") != "same-origin":
            raise WebError("origin_rejected", 403)


def strict_json(raw: bytes) -> dict:
    def unique(pairs: list) -> dict:
        output = {}
        for key, value in pairs:
            if key in output:
                raise ValueError("duplicate")
            output[key] = value
        return output

    try:
        value = json.loads(
            raw,
            object_pairs_hook=unique,
            parse_constant=lambda _: (_ for _ in ()).throw(ValueError("constant")),
        )
    except (ValueError, UnicodeError, RecursionError):
        raise WebError("invalid_request") from None
    if not isinstance(value, dict):
        raise WebError("invalid_request")
    return value


class Application:
    """Small job wrapper; the engine owns persistent transaction recovery."""

    def __init__(self, manager: Any, ha: Any) -> None:
        self.manager = manager
        self.ha = ha
        self._lock = threading.Lock()
        self._job: dict = {"state": "idle"}

    def job(self) -> dict:
        with self._lock:
            result = dict(self._job)
        phase = getattr(self.manager, "operation", {}).get("phase")
        if result["state"] == "running" and phase in (
            "downloading",
            "staging",
            "backing_up",
            "prepared",
            "staged",
            "old_moved",
            "new_moved",
            "committed",
            "complete",
        ):
            result["phase"] = phase
        return result

    def submit(self, operation: str, body: dict) -> dict:
        contracts = {
            "refresh": {},
            "source_add": {"repository_url": str, "trusted": bool},
            "source_remove": {"source_id": str},
            "test_mode": {"enabled": bool},
            "install": {"source_id": str, "module_id": str, "version": str},
            "rollback": {"domain": str, "confirmed": bool},
            "remove": {"domain": str, "confirmed": bool},
        }
        contract = contracts.get(operation)
        if (
            contract is None
            or body.keys() != contract.keys()
            or any(
                type(body[key]) is not kind or (kind is str and not 0 < len(body[key]) <= 512)
                for key, kind in contract.items()
            )
        ):
            raise WebError("invalid_request")
        if operation in ("remove", "rollback") and body["confirmed"] is not True:
            raise WebError("invalid_request")
        if operation == "source_add" and body["trusted"] is not True:
            raise WebError("invalid_request")
        with self._lock:
            if self._job["state"] == "running":
                raise WebError("busy", 409)
            self._job = {"state": "running", "operation": operation}
            threading.Thread(target=self._run, args=(operation, body), daemon=True).start()
            return dict(self._job)

    def _run(self, operation: str, body: dict) -> None:
        try:
            if operation == "refresh":
                self.manager.refresh_catalogs()
            elif operation == "source_add":
                self.manager.add_source(body["repository_url"], trusted=True)
            elif operation == "source_remove":
                self.manager.remove_source(body["source_id"])
            elif operation == "test_mode":
                self.manager.set_test_mode(body["enabled"])
            elif operation == "install":
                self.manager.install(body["source_id"], body["module_id"], body["version"])
            elif operation == "rollback":
                self.manager.rollback(body["domain"])
            elif operation == "remove":
                self.manager.remove(body["domain"], confirmed=True)
            result = {"state": "complete", "operation": operation}
        except Exception as error:
            result = {"state": "failed", "operation": operation, "error": public_error(error)}
        with self._lock:
            self._job = result

    def state(self) -> dict:
        current = self.manager.status()
        return {**current, "job": self.job()}


class IngressServer(ThreadingHTTPServer):
    daemon_threads = True
    request_queue_size = 16

    def __init__(self, address: tuple, application: Application) -> None:
        self.application = application
        self._slots = threading.BoundedSemaphore(24)
        super().__init__(address, Handler)

    def process_request(self, request: Any, client_address: Any) -> None:
        if not self._slots.acquire(blocking=False):
            self.shutdown_request(request)
            return
        super().process_request(request, client_address)

    def process_request_thread(self, request: Any, client_address: Any) -> None:
        try:
            super().process_request_thread(request, client_address)
        finally:
            self._slots.release()

    def handle_error(self, request: Any, client_address: Any) -> None:
        # Base implementation prints traceback/request data. Public errors are fixed.
        pass


class Handler(BaseHTTPRequestHandler):
    server_version = "HAHAPent"
    sys_version = ""
    protocol_version = "HTTP/1.0"

    def setup(self) -> None:
        super().setup()
        self.connection.settimeout(12)

    def log_message(self, format: str, *args: Any) -> None:
        # Ingress paths can contain session identifiers. Never log request lines.
        pass

    def _response(self, status: int, content: bytes, mime: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Frame-Options", "SAMEORIGIN")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'none'; script-src 'self'; style-src 'self'; "
            "connect-src 'self'; img-src 'self'; base-uri 'none'; "
            "form-action 'self'; frame-ancestors 'self'; object-src 'none'",
        )
        self.end_headers()
        self.wfile.write(content)

    def _json(self, status: int, content: dict) -> None:
        self._response(status, json.dumps(content).encode(), "application/json; charset=utf-8")

    def send_error(self, code: int, message: str | None = None, explain: str | None = None) -> None:
        self._json(code, {"error": {"code": "invalid_request", "message": "Invalid request."}})

    def _body(self) -> dict:
        lengths = self.headers.get_all("Content-Length", [])
        if len(lengths) != 1 or not re.fullmatch(r"[0-9]{1,8}", lengths[0]):
            raise WebError("invalid_request")
        if self.headers.get_all("Transfer-Encoding", []):
            raise WebError("invalid_request")
        content_types = self.headers.get_all("Content-Type", [])
        if len(content_types) != 1 or content_types[0].lower() not in (
            "application/json",
            "application/json; charset=utf-8",
        ):
            raise WebError("invalid_request")
        length = int(lengths[0])
        if length > MAX_REQUEST_BYTES:
            raise WebError("request_too_large", 413)
        raw = self.rfile.read(length)
        if len(raw) != length:
            raise WebError("invalid_request")
        return strict_json(raw)

    def _dispatch(self, mutation: bool = False) -> None:
        try:
            application = self.server.application
            authorize(self.client_address[0], self.headers, application.ha, mutation=mutation)
            path = self.path
            if mutation:
                if not path.startswith("/api/") or "?" in path:
                    raise WebError("invalid_request", 404)
                self._json(202, {"job": application.submit(path[5:], self._body())})
            elif path == "/api/status":
                self._json(200, application.state())
            elif path == "/api/job":
                self._json(200, {"job": application.job()})
            elif path in ("/", "/index.html", "/app.js", "/style.css"):
                filename = "index.html" if path == "/" else path[1:]
                mime = {
                    "index.html": "text/html; charset=utf-8",
                    "app.js": "text/javascript; charset=utf-8",
                    "style.css": "text/css; charset=utf-8",
                }[filename]
                self._response(200, (STATIC / filename).read_bytes(), mime)
            else:
                raise WebError("invalid_request", 404)
        except WebError as error:
            self._json(error.status, {"error": public_error(error)})
        except HAError as error:
            self._json(503, {"error": public_error(error)})
        except Exception as error:
            self._json(500, {"error": public_error(error)})

    def do_GET(self) -> None:
        self._dispatch()

    def do_POST(self) -> None:
        self._dispatch(mutation=True)


def main() -> None:
    # Imports are delayed so isolated HTTP/auth smoke tests do not need engine state.
    from .engine import Manager

    os.umask(0o077)
    ha = HomeAssistant()
    manager = Manager(
        Path(os.environ.get("HAHAPENT_DATA_DIR", "/data")),
        Path(os.environ.get("HAHAPENT_CONFIG_DIR", "/homeassistant")),
        ha_adapter=ha,
        test_catalog=Path(__file__).parents[1] / "test-catalog.json",
    )
    IngressServer(("0.0.0.0", 8099), Application(manager, ha)).serve_forever()


if __name__ == "__main__":
    main()
