"""Run inside the actual App image with --network none; only synthetic requests."""

from __future__ import annotations

import http.client
import importlib.metadata
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path


def request(method: str, path: str, *, forged: bool = False) -> int:
    connection = http.client.HTTPConnection("127.0.0.1", 8099, timeout=2)
    headers = {"Content-Type": "application/json"}
    if forged:
        headers.update(
            {
                "X-Ingress-Path": "/api/hassio_ingress/synthetic",
                "X-Remote-User-Id": "synthetic-administrator",
                "X-Remote-User-Name": "synthetic-administrator",
                "X-Forwarded-For": "172.30.32.2",
            }
        )
    try:
        connection.request(method, path, body=b"{}" if method == "POST" else None, headers=headers)
        response = connection.getresponse()
        response.read(65536)
        return response.status
    finally:
        connection.close()


def main() -> None:
    import hahapent.engine
    import hahapent.server
    import jsonschema
    import websocket

    assert all((hahapent.engine, hahapent.server, jsonschema, websocket))
    assert sys.version_info[:2] == (3, 13), "wrong_app_python"
    assert importlib.metadata.version("jsonschema") == "4.25.1"
    assert importlib.metadata.version("websocket-client") == "1.9.0"
    assert Path("/app/schemas/catalog-v1.schema.json").is_file()
    assert Path("/app/hahapent.json").is_file()
    assert Path("/app/test-catalog.json").is_file()
    with tempfile.TemporaryDirectory(prefix="hahapent-image-smoke-") as temporary:
        root = Path(temporary)
        (root / "data").mkdir()
        (root / "homeassistant/custom_components").mkdir(parents=True)
        environment = dict(os.environ)
        environment.pop("SUPERVISOR_TOKEN", None)
        environment.update(
            {
                "HAHAPENT_DATA_DIR": str(root / "data"),
                "HAHAPENT_CONFIG_DIR": str(root / "homeassistant"),
            }
        )
        process = subprocess.Popen(
            [sys.executable, "-m", "hahapent.server"],
            env=environment,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            deadline = time.monotonic() + 15
            while True:
                assert process.poll() is None, "app_process_exited"
                try:
                    status = request("GET", "/")
                    break
                except (OSError, http.client.HTTPException):
                    if time.monotonic() >= deadline:
                        raise AssertionError("app_server_not_ready") from None
                    time.sleep(0.1)
            assert status == 403, "direct_index_access_not_rejected"
            assert request("GET", "/api/status", forged=True) == 403
            assert request("POST", "/api/install", forged=True) == 403
            assert list((root / "homeassistant/custom_components").iterdir()) == []
            print(
                json.dumps(
                    {
                        "status": "PASS",
                        "runtime": sys.version.split()[0],
                        "imports": "PASS",
                        "http_direct_access": "REJECTED",
                        "http_forged_ingress": "REJECTED",
                    }
                )
            )
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


if __name__ == "__main__":
    main()
