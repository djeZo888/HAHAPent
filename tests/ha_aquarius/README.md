# Native Home Assistant tests

These tests load the distributable Aquarius integration in actual Home Assistant
2026.9.1 using the pinned `pytest-homeassistant-custom-component` fixtures. They
exercise native configuration flows, device/entity registries, services,
coordinator failures, cancellation, and setup/reload/unload. Most tests mock only
the lamp client. `test_loopback_integration.py` joins actual HA, the actual client
and parser, and a synthetic TCP lamp, including C/D wire mapping and ignored-write
echoes. All replies and targets are synthetic; no lamp or HA credentials are
needed and no physical behavior is validated here.

Version 0.2.0 ships one independently hardware-validated profile. Most action
tests temporarily enable fictional profiles inside their fixture scope. A
separate loopback test manufactures the shipped profile and exercises actual
release admission, read-only setup/poll/reload, and explicit services. This is
still synthetic evidence. The unvalidated-profile regression uses an empty
allowlist and verifies that all six Number controls and both mode choices raise
a clear read-only error without any client command. Shutdown and unknown starting
modes remain readable but cannot admit commands.

Use Python 3.14.7 and the dedicated dependency lock from the repository root:

```sh
python3.14 -m venv /private/tmp/hahapent-ha-tests
/private/tmp/hahapent-ha-tests/bin/python -m pip install -r requirements-ha-test.txt
/private/tmp/hahapent-ha-tests/bin/python -m pytest tests/ha_aquarius -v --disable-socket --allow-unix-socket
```

The repository `pyproject.toml` sets `asyncio_mode = "auto"` and fixture loop scope
to `function`, so the ordinary command correctly awaits the HA fixtures and
tests. TCP sockets are disabled by default. The simulator tests use
`pytest.mark.allow_hosts(["127.0.0.1"])` plus a scoped `socket_enabled` fixture
(required by HA's own socket-creation guard), immediately applying
`socket_allow_hosts(["127.0.0.1"])` before any network action. This permits only
local-loopback connections. Unix sockets remain enabled for the asyncio event
loop. The same command and pinned Python/dependencies run in the dedicated
public CI job.

Keep this directory without `__init__.py`: the existing Python 3.9/3.13
`unittest discover` suite must not import these HA/Python 3.14-only tests.
Pure protocol and synthetic loopback TCP tests remain in the standard unit
suite and test different behavior. A passing native test run is synthetic
evidence, not actual lamp validation.
