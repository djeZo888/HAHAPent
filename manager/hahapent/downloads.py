"""Public, credential-free HTTPS and bounded, non-executing ZIP extraction."""

import hashlib
import http.client
import io
import ipaddress
import queue
import re
import socket
import ssl
import stat
import threading
import time
import zipfile
import zlib
from pathlib import Path, PurePosixPath
from urllib.parse import urljoin, urlsplit

from .catalog import ManagerError, loads_json

MAX_ARTIFACT_BYTES = 32 * 1024 * 1024
MAX_EXTRACT_BYTES = 64 * 1024 * 1024
MAX_FILE_BYTES = 8 * 1024 * 1024
MAX_FILES = 2000
PUBLIC_HOSTS = frozenset({"github.com", "raw.githubusercontent.com"})
ASSET_HOSTS = frozenset({"release-assets.githubusercontent.com", "objects.githubusercontent.com"})


def validate_download_url(url, redirect=False):
    try:
        parsed = urlsplit(url)
        if (
            not isinstance(url, str)
            or len(url) > 8192
            or parsed.scheme != "https"
            or parsed.hostname not in (PUBLIC_HOSTS | ASSET_HOSTS if redirect else PUBLIC_HOSTS)
            or parsed.port not in (None, 443)
            or parsed.username is not None
            or parsed.password is not None
            or parsed.fragment
            or "\\" in url
            or any(c.isspace() or ord(c) < 32 for c in url)
            or (parsed.query and not (redirect and parsed.hostname in ASSET_HOSTS))
            or not parsed.path.startswith("/")
        ):
            raise ManagerError("unsafe_download_url")
        if parsed.hostname in ASSET_HOSTS and not parsed.path.startswith(
            "/github-production-release-asset"
        ):
            raise ManagerError("unsafe_redirect")
        return parsed
    except (TypeError, ValueError):
        raise ManagerError("unsafe_download_url") from None


_DNS_SLOTS = threading.BoundedSemaphore(4)


def public_addresses(host, resolver=socket.getaddrinfo, deadline=None):
    deadline = deadline if deadline is not None else time.monotonic() + 30
    if not _DNS_SLOTS.acquire(blocking=False):
        raise ManagerError("download_dns_busy")
    results = queue.Queue(maxsize=1)

    def resolve():
        try:
            results.put(resolver(host, 443, type=socket.SOCK_STREAM))
        except Exception:
            results.put(None)
        finally:
            _DNS_SLOTS.release()

    threading.Thread(target=resolve, daemon=True).start()
    try:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise ManagerError("download_timeout")
        try:
            records = results.get(timeout=remaining)
        except queue.Empty:
            raise ManagerError("download_timeout") from None
        if records is None:
            raise ManagerError("download_dns_failed")
        addresses = list(dict.fromkeys(record[4][0] for record in records))
        if not addresses or any(not ipaddress.ip_address(addr).is_global for addr in addresses):
            raise ManagerError("private_download_target")
        return addresses
    except ManagerError:
        raise
    except (OSError, ValueError):
        raise ManagerError("download_dns_failed") from None


class _BudgetReader(io.RawIOBase):
    def __init__(self, stream):
        super().__init__()
        self.stream = stream

    def readable(self):
        return True

    def readinto(self, buffer):
        data = self.stream.recv(len(buffer))
        buffer[: len(data)] = data
        return len(data)

    def close(self):
        self.stream.close()
        super().close()


class _BudgetSocket:
    """Count every receive, including buffered headers and chunk framing."""

    def __init__(self, stream, deadline, byte_limit):
        self.stream, self.deadline, self.remaining = stream, deadline, byte_limit

    def _timeout(self):
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise ManagerError("download_timeout")
        self.stream.settimeout(remaining)

    def recv(self, size, *args):
        self._timeout()
        content = self.stream.recv(min(size, self.remaining + 1), *args)
        self.remaining -= len(content)
        if self.remaining < 0:
            raise ManagerError("download_too_large")
        return content

    def sendall(self, content, *args):
        view = memoryview(content)
        while view:
            self._timeout()
            sent = self.stream.send(view, *args)
            if sent <= 0:
                raise ManagerError("download_failed")
            view = view[sent:]

    def makefile(self, mode, *args, **kwargs):
        if mode != "rb":
            raise ManagerError("download_failed")
        return io.BufferedReader(_BudgetReader(self))

    def __getattr__(self, name):
        return getattr(self.stream, name)


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    def __init__(self, host, address, timeout):
        super().__init__(host, timeout=timeout, context=ssl.create_default_context())
        self.address = address
        self.deadline = time.monotonic() + timeout
        self.byte_limit = MAX_ARTIFACT_BYTES + 128 * 1024

    def connect(self):
        # DNS was checked once. Connect to that literal public IP, retaining host
        # for SNI/certificate validation and Host; no proxy/environment credentials.
        sock = socket.create_connection((self.address, 443), self.timeout)
        try:
            remaining = self.deadline - time.monotonic()
            if remaining <= 0:
                raise ManagerError("download_timeout")
            sock.settimeout(remaining)
            secure = self._context.wrap_socket(sock, server_hostname=self.host)
            self.sock = _BudgetSocket(secure, self.deadline, self.byte_limit)
        except BaseException:
            sock.close()
            raise


class Downloader:
    def __init__(self, timeout=30, resolver=socket.getaddrinfo, connection_factory=None):
        self.timeout = min(max(timeout, 1), 60)
        self.resolver = resolver
        self.connection_factory = connection_factory or _PinnedHTTPSConnection

    def download(self, url, max_bytes=MAX_ARTIFACT_BYTES):
        if not 1 <= max_bytes <= MAX_ARTIFACT_BYTES:
            raise ManagerError("invalid_download_limit")
        deadline = time.monotonic() + self.timeout
        current = url
        for redirects in range(4):
            parsed = validate_download_url(current, redirect=redirects > 0)
            addresses = public_addresses(parsed.hostname, self.resolver, deadline)
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise ManagerError("download_timeout")
            connection = self.connection_factory(parsed.hostname, addresses[0], min(15, remaining))
            connection.deadline = deadline
            connection.byte_limit = max_bytes + 128 * 1024
            response = None
            try:
                path = parsed.path + ("?" + parsed.query if parsed.query else "")
                connection.request(
                    "GET",
                    path,
                    headers={"User-Agent": "HAHAPent/0.1", "Accept": "application/octet-stream"},
                )
                response = connection.getresponse()
                if response.status in (301, 302, 303, 307, 308):
                    location = response.getheader("Location")
                    if not location or redirects == 3:
                        raise ManagerError("download_redirect_limit")
                    following = urljoin(current, location)
                    next_url = validate_download_url(following, redirect=True)
                    if parsed.hostname in ASSET_HOSTS and next_url.hostname != parsed.hostname:
                        raise ManagerError("unsafe_redirect")
                    # Raw catalog requests never need the release-asset trust path.
                    if (
                        parsed.hostname == "raw.githubusercontent.com"
                        and next_url.hostname != parsed.hostname
                    ):
                        raise ManagerError("unsafe_redirect")
                    current = following
                    continue
                if response.status != 200:
                    raise ManagerError("download_http_failed")
                length = response.getheader("Content-Length")
                if length is not None and (not length.isdigit() or int(length) > max_bytes):
                    raise ManagerError("download_too_large")
                chunks, total = [], 0
                while True:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise ManagerError("download_timeout")
                    if getattr(connection, "sock", None) is not None:
                        connection.sock.settimeout(min(15, remaining))
                    block = response.read(min(65536, max_bytes + 1 - total))
                    if not block:
                        break
                    total += len(block)
                    if total > max_bytes:
                        raise ManagerError("download_too_large")
                    chunks.append(block)
                if length is not None and total != int(length):
                    raise ManagerError("download_truncated")
                return b"".join(chunks)
            except ManagerError:
                raise
            except (OSError, http.client.HTTPException, ValueError):
                raise ManagerError("download_failed") from None
            finally:
                if response is not None:
                    response.close()
                connection.close()
        raise ManagerError("download_redirect_limit")


def extract_artifact(content, destination, module):
    """Validate every archive member before writing inside an empty stage directory."""
    if not isinstance(content, bytes) or len(content) > MAX_ARTIFACT_BYTES:
        raise ManagerError("download_too_large")
    if hashlib.sha256(content).hexdigest() != module["artifact"]["sha256"]:
        raise ManagerError("artifact_digest_mismatch")
    destination = Path(destination)
    if destination.is_symlink() or not destination.is_dir() or any(destination.iterdir()):
        raise ManagerError("invalid_stage")
    domain = module["integration_domain"]
    prefix = "custom_components/" + domain + "/"
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            members = archive.infolist()
            if not members or len(members) > MAX_FILES:
                raise ManagerError("archive_limit")
            seen, files, directories, extracted, total = set(), set(), set(), [], 0
            aliases = {}
            for item in members:
                name = item.filename
                mode = item.external_attr >> 16
                if (
                    item.flag_bits & 1
                    or "\\" in name
                    or "\x00" in item.orig_filename
                    or name.startswith("/")
                    or "__pycache__" in name.split("/")
                    or name.endswith((".pyc", ".pyo"))
                    or len(name) > 500
                    or any(p in ("", ".", "..") for p in name.rstrip("/").split("/"))
                    or not re.fullmatch(r"[A-Za-z0-9_./-]+", name)
                    or (stat.S_IFMT(mode) not in (0, stat.S_IFREG, stat.S_IFDIR))
                    or item.file_size > MAX_FILE_BYTES
                    or item.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED)
                ):
                    raise ManagerError("unsafe_archive")
                if stat.S_ISDIR(mode) and not item.is_dir():
                    raise ManagerError("unsafe_archive")
                for count in range(1, len(name.rstrip("/").split("/")) + 1):
                    part = "/".join(name.rstrip("/").split("/")[:count])
                    if aliases.get(part.casefold(), part) != part:
                        raise ManagerError("duplicate_archive_path")
                    aliases[part.casefold()] = part
                canonical = name.rstrip("/").casefold()
                if canonical in seen:
                    raise ManagerError("duplicate_archive_path")
                seen.add(canonical)
                if item.is_dir() and name in ("custom_components/", prefix):
                    continue
                if not name.startswith(prefix) or name == prefix:
                    raise ManagerError("archive_domain_mismatch")
                relative = name[len(prefix) :].rstrip("/")
                parts = PurePosixPath(relative).parts
                parents = {"/".join(parts[:i]).casefold() for i in range(1, len(parts))}
                key = relative.casefold()
                if parents & files or (not item.is_dir() and key in directories):
                    raise ManagerError("archive_path_conflict")
                directories.update(parents)
                (directories if item.is_dir() else files).add(key)
                total += item.file_size
                if total > MAX_EXTRACT_BYTES:
                    raise ManagerError("archive_limit")
                extracted.append((item, relative))
            exact_files = {relative for item, relative in extracted if not item.is_dir()}
            if "manifest.json" not in exact_files or "__init__.py" not in exact_files:
                raise ManagerError("missing_manifest")
            manifest_info = next(item for item, rel in extracted if rel == "manifest.json")
            manifest = loads_json(archive.read(manifest_info))
            if (
                not isinstance(manifest, dict)
                or manifest.get("domain") != domain
                or manifest.get("version") != module["version"]
            ):
                raise ManagerError("manifest_identity_mismatch")
            if manifest.get("requirements", []) != []:
                raise ManagerError("unsupported_python_requirements")
            dependencies = manifest.get("dependencies", [])
            after_dependencies = manifest.get("after_dependencies", [])
            if (
                not isinstance(dependencies, list)
                or not isinstance(after_dependencies, list)
                or any(
                    not isinstance(d, str) or not re.fullmatch(r"[a-z][a-z0-9_]{0,99}", d)
                    for d in dependencies + after_dependencies
                )
            ):
                raise ManagerError("invalid_manifest")
            for item, relative in extracted:
                target = destination / relative
                if item.is_dir():
                    target.mkdir(parents=True, exist_ok=True, mode=0o755)
                else:
                    target.parent.mkdir(parents=True, exist_ok=True, mode=0o755)
                    # CRC/decompression failures are caught; no package code runs.
                    with target.open("xb") as output:
                        output.write(archive.read(item))
                    target.chmod(0o644)
            return manifest
    except ManagerError:
        raise
    except (
        zipfile.BadZipFile,
        RuntimeError,
        ValueError,
        KeyError,
        EOFError,
        NotImplementedError,
        zlib.error,
        RecursionError,
    ):
        raise ManagerError("invalid_archive") from None
