"""No-network HTTPS boundary, archive abuse and resource-limit tests."""

import hashlib
import http.client
import io
import socket
import stat
import sys
import tempfile
import threading
import time
import unittest
import warnings
import zipfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "manager"))
from hahapent.catalog import ManagerError  # noqa: E402
from hahapent.downloads import (  # noqa: E402
    MAX_ARTIFACT_BYTES,
    Downloader,
    _BudgetSocket,
    _PinnedHTTPSConnection,
    extract_artifact,
    public_addresses,
    validate_download_url,
)

from tests.test_manager_engine import artifact, release_catalog  # noqa: E402

URL = "https://github.com/example/synthetic/releases/download/v1/helper-1.2.3.zip"
ASSET = "https://release-assets.githubusercontent.com/github-production-release-asset/1/asset?sig=synthetic"


def resolver(_host, _port, type):
    return [(socket.AF_INET, type, 6, "", ("1.1.1.1", 443))]


class Response:
    def __init__(self, body=b"body", status=200, headers=None):
        self.body = io.BytesIO(body)
        self.status = status
        self.headers = headers or {}

    def getheader(self, name):
        return self.headers.get(name)

    def read(self, count):
        return self.body.read(count)

    def close(self):
        self.body.close()


class DownloadTests(unittest.TestCase):
    def downloader(self, responses):
        requests, connections = [], []

        class Connection:
            sock = None

            def __init__(self, host, address, timeout):
                self.host, self.address, self.timeout = host, address, timeout
                self.closed = False
                connections.append(self)

            def request(self, method, path, headers):
                requests.append((self.host, self.address, method, path, headers))

            def getresponse(self):
                return responses.pop(0)

            def close(self):
                self.closed = True

        return Downloader(resolver=resolver, connection_factory=Connection), requests, connections

    def test_valid_redirect_uses_public_ip_and_never_forwards_credentials(self):
        downloader, requests, connections = self.downloader(
            [
                Response(status=302, headers={"Location": ASSET}),
                Response(b"asset", headers={"Content-Length": "5"}),
            ]
        )
        self.assertEqual(downloader.download(URL), b"asset")
        self.assertEqual(
            [req[0] for req in requests], ["github.com", "release-assets.githubusercontent.com"]
        )
        self.assertTrue(all(req[1] == "1.1.1.1" for req in requests))
        self.assertTrue(all(set(req[4]) == {"User-Agent", "Accept"} for req in requests))
        self.assertTrue(all(connection.closed for connection in connections))

    def test_bad_urls_and_redirect_hosts_rejected(self):
        values = [
            "http://github.com/example/synthetic",
            "https://127.0.0.1/asset",
            "https://localhost/asset",
            "https://github.com.evil.invalid/asset",
            "https://DO-NOT-ECHO@github.com/asset",
            URL + "?token=DO-NOT-ECHO",
            URL + "#fragment",
            "https://github.com:444/asset",
            "https://github.com\\@example.invalid/asset",
            "https://evil.githubusercontent.com/asset",
        ]
        for value in values:
            with self.subTest(value=value), self.assertRaises(ManagerError) as result:
                validate_download_url(value)
            self.assertNotIn("DO-NOT-ECHO", str(result.exception))
        for value in (
            "https://example.invalid/asset",
            "http://github.com/example/asset",
            "https://objects.githubusercontent.com/arbitrary/path",
            "https://localhost/asset",
        ):
            downloader, requests, _ = self.downloader(
                [Response(status=302, headers={"Location": value})]
            )
            with self.assertRaises(ManagerError):
                downloader.download(URL)
            self.assertEqual(len(requests), 1)

    def test_raw_catalog_cannot_redirect_into_asset_trust_boundary(self):
        downloader, _, _ = self.downloader([Response(status=302, headers={"Location": ASSET})])
        with self.assertRaisesRegex(ManagerError, "unsafe_redirect"):
            downloader.download("https://raw.githubusercontent.com/example/repo/HEAD/hahapent.json")

    def test_dns_rejects_every_private_or_mixed_address_set(self):
        for addresses in (
            ["127.0.0.1"],
            ["10.0.0.1"],
            ["169.254.169.254"],
            ["::1"],
            ["fc00::1"],
            ["1.1.1.1", "192.168.1.1"],
            ["0.0.0.0"],
        ):
            with self.subTest(addresses=addresses):

                def private(_host, _port, type):
                    return [(socket.AF_INET, type, 6, "", (address, 443)) for address in addresses]

                with self.assertRaisesRegex(ManagerError, "private_download_target"):
                    public_addresses("github.com", private)

    def test_dns_failure_and_deadline_are_bounded_and_redacted(self):
        with self.assertRaisesRegex(ManagerError, "download_dns_failed"):
            public_addresses(
                "github.com", lambda *args, **kwargs: (_ for _ in ()).throw(OSError("DO-NOT-ECHO"))
            )
        unblock = threading.Event()

        def delayed(*args, **kwargs):
            unblock.wait(2)
            return resolver(*args, **kwargs)

        start = time.monotonic()
        try:
            with self.assertRaisesRegex(ManagerError, "download_timeout"):
                public_addresses("github.com", delayed, deadline=start + 0.03)
            self.assertLess(time.monotonic() - start, 0.5)
        finally:
            unblock.set()

    def test_size_truncated_http_and_redirect_limits(self):
        cases = [
            ([Response(b"12345")], 4, "download_too_large"),
            ([Response(b"123", headers={"Content-Length": "5"})], 10, "download_truncated"),
            ([Response(headers={"Content-Length": "9999999999"})], 10, "download_too_large"),
            ([Response(headers={"Content-Length": "invalid"})], 10, "download_too_large"),
            ([Response(status=500, body=b"DO-NOT-ECHO")], 10, "download_http_failed"),
            (
                [Response(status=302, headers={"Location": URL}) for _ in range(4)],
                10,
                "download_redirect_limit",
            ),
        ]
        for responses, maximum, code in cases:
            downloader, _, _ = self.downloader(responses)
            with self.subTest(code=code), self.assertRaisesRegex(ManagerError, code) as result:
                downloader.download(URL, max_bytes=maximum)
            self.assertNotIn("DO-NOT-ECHO", str(result.exception))

    def test_socket_budget_enforces_deadline_during_buffered_slow_headers_and_body(self):
        class Stream:
            def __init__(self):
                self.closed = False
                self.timeout = None

            def settimeout(self, value):
                self.timeout = value

            def recv(self, count):
                return b"x"

            def send(self, view):
                return 1

            def close(self):
                self.closed = True

        stream = Stream()
        budget = _BudgetSocket(stream, 10, 100)
        with patch("hahapent.downloads.time.monotonic", side_effect=[1, 2, 11]):
            with self.assertRaisesRegex(ManagerError, "download_timeout"):
                budget.makefile("rb").read(10)
        self.assertTrue(stream.closed)
        stream = Stream()
        budget = _BudgetSocket(stream, 10, 2)
        with patch("hahapent.downloads.time.monotonic", return_value=1):
            with self.assertRaisesRegex(ManagerError, "download_too_large"):
                budget.makefile("rb").read(10)

    def test_real_http_response_body_and_socket_lifetimes(self):
        # Use Python's real HTTP parser, with only its wire socket synthetic.
        # A body larger than the header buffer exposes early-close regressions.
        body = b"versioned-asset" * 2000
        for connection_header in ("keep-alive", "close"):
            with self.subTest(connection_header=connection_header):
                wire = (
                    "HTTP/1.1 200 OK\r\nContent-Length: {}\r\nConnection: {}\r\n\r\n".format(
                        len(body), connection_header
                    ).encode()
                    + body
                )
                streams = []

                class Wire:
                    def __init__(self):
                        self.content = io.BytesIO(wire)
                        self.closed = False
                        streams.append(self)

                    def close(self):
                        self.closed = True

                    def settimeout(self, _value):
                        if self.closed:
                            raise OSError(9, "synthetic closed socket")

                    def recv(self, count):
                        if self.closed:
                            raise OSError(9, "synthetic closed socket")
                        return self.content.read(min(count, 2048))

                    def send(self, value):
                        return len(value)

                class Connection(http.client.HTTPConnection):
                    def __init__(self, host, _address, timeout):
                        super().__init__(host, timeout=timeout)

                    def connect(self):
                        self.sock = _BudgetSocket(Wire(), self.deadline, self.byte_limit)

                downloader = Downloader(resolver=resolver, connection_factory=Connection)
                self.assertEqual(downloader.download(URL, max_bytes=len(body)), body)
                self.assertTrue(streams[0].closed)

    def test_socket_connections_pin_ip_and_keep_certificate_validation_and_sni(self):
        class Stream:
            def close(self):
                pass

            def settimeout(self, _value):
                pass

        with patch("socket.create_connection", return_value=Stream()) as connect:
            connection = _PinnedHTTPSConnection("github.com", "1.1.1.1", 5)
            connection.deadline = time.monotonic() + 5
            connection.byte_limit = 1000
            self.assertTrue(connection._context.check_hostname)
            self.assertNotEqual(connection._context.verify_mode, 0)
            with patch.object(connection._context, "wrap_socket", return_value=Stream()) as wrap:
                connection.connect()
            self.assertEqual(connect.call_args.args[0], ("1.1.1.1", 443))
            self.assertEqual(wrap.call_args.kwargs["server_hostname"], "github.com")
            connection.close()


class ArchiveTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.stage = Path(self.temporary.name).resolve() / "stage"
        self.stage.mkdir()
        self.module = release_catalog()[0]["modules"][0]

    def tearDown(self):
        self.temporary.cleanup()

    def extract(self, blob):
        self.module["artifact"]["sha256"] = hashlib.sha256(blob).hexdigest()
        return extract_artifact(blob, self.stage, self.module)

    def zip(self, additions):
        output = io.BytesIO()
        with zipfile.ZipFile(io.BytesIO(artifact())) as original:
            with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
                for info in original.infolist():
                    archive.writestr(info, original.read(info))
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore", UserWarning)
                    for name, content in additions:
                        archive.writestr(name, content)
        return output.getvalue()

    def test_safe_archive_is_extracted_without_executing_code(self):
        blob = self.zip([("custom_components/synthetic_helper/install.sh", "exit 99\n")])
        manifest = self.extract(blob)
        self.assertEqual(manifest["domain"], "synthetic_helper")
        self.assertTrue((self.stage / "manifest.json").is_file())
        self.assertEqual((self.stage / "install.sh").stat().st_mode & 0o777, 0o644)

    def test_traversal_escape_foreign_domain_and_path_aliases_rejected_before_writes(self):
        names = [
            "../escape",
            "/tmp/escape",
            "custom_components/synthetic_helper/../escape",
            "custom_components/synthetic_helper//escape",
            "custom_components/synthetic_helper/./escape",
            "custom_components/synthetic_helper/evil\\file",
            "custom_components/other/manifest.json",
            "custom_components/synthetic_helper/manifest.json",
            "custom_components/synthetic_helper/Manifest.json",
            "custom_components/synthetic_helper/unsafe:name.py",
            "custom_components/synthetic_helper/__pycache__/__init__.cpython-313.pyc",
            "custom_components/synthetic_helper/compiled.pyc",
        ]
        for name in names:
            with self.subTest(name=name), self.assertRaises(ManagerError):
                self.extract(self.zip([(name, "bad")]))
            self.assertEqual(list(self.stage.iterdir()), [])

    def test_implicit_directory_case_alias_and_file_directory_conflict_rejected(self):
        for additions in (
            [
                ("custom_components/synthetic_helper/Case/one.py", "x"),
                ("custom_components/synthetic_helper/case/two.py", "x"),
            ],
            [
                ("custom_components/synthetic_helper/dir/one.py", "x"),
                ("custom_components/synthetic_helper/dir", "x"),
            ],
            [
                ("custom_components/synthetic_helper/dir", "x"),
                ("custom_components/synthetic_helper/dir/one.py", "x"),
            ],
        ):
            with self.assertRaises(ManagerError):
                self.extract(self.zip(additions))
            self.assertEqual(list(self.stage.iterdir()), [])

    def test_symlinks_devices_and_fifo_rejected(self):
        for mode in (stat.S_IFLNK | 0o777, stat.S_IFCHR | 0o600, stat.S_IFIFO | 0o600):
            info = zipfile.ZipInfo("custom_components/synthetic_helper/link")
            info.create_system = 3
            info.external_attr = mode << 16
            with self.assertRaisesRegex(ManagerError, "unsafe_archive"):
                self.extract(self.zip([(info, "../outside")]))
            self.assertEqual(list(self.stage.iterdir()), [])

    def test_corrupt_zip_and_manifest_identity_or_dependencies_rejected(self):
        for blob, code in (
            (b"not-a-zip", "invalid_archive"),
            (artifact("9.9.9"), "manifest_identity_mismatch"),
            (artifact(domain="other"), "archive_domain_mismatch"),
            (
                artifact(manifest_extra={"requirements": ["package>=1"]}),
                "unsupported_python_requirements",
            ),
            (artifact(manifest_extra={"dependencies": "invalid"}), "invalid_manifest"),
        ):
            with self.subTest(code=code), self.assertRaisesRegex(ManagerError, code):
                self.extract(blob)
            self.assertEqual(list(self.stage.iterdir()), [])

    def test_digest_required_before_any_writes(self):
        with self.assertRaisesRegex(ManagerError, "artifact_digest_mismatch"):
            extract_artifact(b"different", self.stage, self.module)
        self.assertEqual(list(self.stage.iterdir()), [])

    def test_extraction_file_count_file_size_and_total_limits(self):
        blob = self.zip([("custom_components/synthetic_helper/large.py", "x" * 4096)])
        for name, limit in (
            ("MAX_FILES", 1),
            ("MAX_FILE_BYTES", 1024),
            ("MAX_EXTRACT_BYTES", 1024),
        ):
            with patch("hahapent.downloads." + name, limit):
                with self.assertRaises(ManagerError):
                    self.extract(blob)
            self.assertEqual(list(self.stage.iterdir()), [])
        with self.assertRaisesRegex(ManagerError, "invalid_download_limit"):
            Downloader().download(URL, max_bytes=MAX_ARTIFACT_BYTES + 1)

    def test_case_aliased_required_manifest_is_rejected_cleanly(self):
        output = io.BytesIO()
        with zipfile.ZipFile(io.BytesIO(artifact())) as original:
            with zipfile.ZipFile(output, "w") as archive:
                for item in original.infolist():
                    archive.writestr(
                        item.filename.replace("manifest.json", "MANIFEST.JSON"), original.read(item)
                    )
        with self.assertRaisesRegex(ManagerError, "missing_manifest"):
            self.extract(output.getvalue())
        self.assertEqual(list(self.stage.iterdir()), [])

    def test_deeply_nested_manifest_rejected_without_uncaught_recursion(self):
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w") as archive:
            archive.writestr(
                "custom_components/synthetic_helper/manifest.json", "[" * 2000 + "0" + "]" * 2000
            )
            archive.writestr("custom_components/synthetic_helper/__init__.py", "")
        with self.assertRaisesRegex(ManagerError, "invalid_archive"):
            self.extract(output.getvalue())

    def test_duplicate_manifest_json_keys_are_rejected(self):
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w") as archive:
            archive.writestr(
                "custom_components/synthetic_helper/manifest.json",
                '{"domain":"synthetic_helper","version":"1.2.3","version":"9.9.9"}',
            )
            archive.writestr("custom_components/synthetic_helper/__init__.py", "")
        with self.assertRaisesRegex(ManagerError, "invalid_archive"):
            self.extract(output.getvalue())


if __name__ == "__main__":
    unittest.main()
