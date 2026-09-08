"""Fixed Task 001 SSH checks; no general command execution interface.
Absent custom_components with a writable parent means AVAILABLE_NOT_EXERCISED:
future creation is available by access predicates, but no package is created.
"""

from __future__ import annotations

import os
import re
import selectors
import subprocess
import time
from pathlib import Path

from tooling.access import Profile, read_private_file

CHECKS = tuple(
    "ssh_session app_container_root ha_cli configuration_directory "
    "custom_components_directory core_info supervisor_info file_probe file_probe_cleanup".split()
)
TIMEOUT = 30
MAX_OUTPUT = 4096
STATUSES = frozenset("PASS FAIL BLOCKED NOT_REQUIRED AVAILABLE_NOT_EXERCISED".split())

READ_ONLY_SCRIPT = r"""set -u
exec 2>/dev/null
printf 'ssh_session=PASS\n'
if [ "$(id -u)" = 0 ]; then
  printf 'app_container_root=PASS\n'
else
  printf 'app_container_root=FAIL\n'
fi
if command -v ha >/dev/null; then printf 'ha_cli=PASS\n'; else printf 'ha_cli=FAIL\n'; fi
resolved=$(readlink -f /config) || resolved=
if [ -n "$resolved" ] && [ "$resolved" != / ] && [ -d "$resolved" ]; then
  printf 'configuration_directory=PASS\n'
else
  printf 'configuration_directory=FAIL\n'
fi
components="$resolved/custom_components"
if [ -n "$resolved" ] && [ "$resolved" != / ] &&
   [ -d "$components" ] && [ ! -L "$components" ] &&
   [ -r "$components" ] && [ -w "$components" ] && [ -x "$components" ]; then
  printf 'custom_components_directory=PASS\n'
elif [ -n "$resolved" ] && [ "$resolved" != / ] && [ -d "$resolved" ] && [ -w "$resolved" ] &&
     [ ! -e "$components" ] && [ ! -L "$components" ]; then
  printf 'custom_components_directory=AVAILABLE_NOT_EXERCISED\n'
else
  printf 'custom_components_directory=FAIL\n'
fi
if ha core info >/dev/null 2>&1; then printf 'core_info=PASS\n'; else
  printf 'core_info=FAIL\n'; fi
if ha supervisor info >/dev/null 2>&1; then printf 'supervisor_info=PASS\n'; else
  printf 'supervisor_info=FAIL\n'; fi
"""
PROBE_SCRIPT = r"""probe_dir=
cleanup() {
  trap - EXIT HUP INT TERM
  if [ -n "$probe_dir" ]; then
    if rm -f -- "$probe_dir/marker" && rmdir -- "$probe_dir"; then
      printf 'file_probe_cleanup=PASS\n'
    else
      printf 'file_probe_cleanup=FAIL\n'
    fi
  fi
}
trap cleanup EXIT
trap 'exit 1' HUP INT TERM
umask 077
if [ -z "$resolved" ] || [ "$resolved" = / ] || [ ! -d "$resolved" ]; then
  printf 'file_probe=BLOCKED\nfile_probe_cleanup=NOT_REQUIRED\n'
elif probe_dir=$(mktemp -d "$resolved/.hahapent-task001.XXXXXXXXXX"); then
  if printf 'HAHAPent Task 001 synthetic access marker\n' > "$probe_dir/marker" &&
     printf 'HAHAPent Task 001 synthetic access marker\n' | cmp -s - "$probe_dir/marker" &&
     [ ! -x "$probe_dir/marker" ]; then
    printf 'file_probe=PASS\n'
  else
    printf 'file_probe=FAIL\n'
  fi
else
  printf 'file_probe=FAIL\nfile_probe_cleanup=NOT_REQUIRED\n'
fi
"""


def _private_ssh_path(path: Path) -> Path:
    root = (Path.home() / ".config/hahapent").resolve()
    resolved = Path(path).resolve()
    if (
        root not in resolved.parents
        or not re.fullmatch(r"[A-Za-z0-9_./-]+", str(resolved))
        or Path(path).is_symlink()
    ):
        raise ValueError("private SSH path rejected")
    read_private_file(path)
    return resolved


def _run(args: list[str], script: bytes) -> bytes:
    """Read at most MAX_OUTPUT bytes and enforce a total subprocess deadline."""
    process = subprocess.Popen(
        args, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=0
    )
    deadline = time.monotonic() + TIMEOUT
    output = bytearray()
    try:
        pending = memoryview(script)
        os.set_blocking(process.stdin.fileno(), False)
        os.set_blocking(process.stdout.fileno(), False)
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdin, selectors.EVENT_WRITE)
            selector.register(process.stdout, selectors.EVENT_READ)
            while selector.get_map():
                remaining = deadline - time.monotonic()
                events = selector.select(max(0, remaining))
                if remaining <= 0 or not events:
                    raise TimeoutError
                for selected, _event in events:
                    stream = selected.fileobj
                    if stream is process.stdin:
                        pending = pending[os.write(stream.fileno(), pending) :]
                        if not pending:
                            selector.unregister(stream)
                            stream.close()
                    else:
                        chunk = os.read(stream.fileno(), MAX_OUTPUT + 1 - len(output))
                        output.extend(chunk)
                        if len(output) > MAX_OUTPUT:
                            raise ValueError("SSH output limit exceeded")
                        if not chunk:
                            selector.unregister(stream)
        if process.wait(timeout=max(0.001, deadline - time.monotonic())) != 0:
            raise ValueError("SSH failed")
        return bytes(output)
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=2)
        for stream in (process.stdin, process.stdout):
            if stream and not stream.closed:
                stream.close()


def check_ssh(profile: Profile, *, file_probe: bool = False) -> dict[str, str]:
    """Only fixed statuses leave this function, including on subprocess failure."""
    result = dict.fromkeys(CHECKS, "BLOCKED")
    if not file_probe:
        result.update(file_probe="NOT_REQUIRED", file_probe_cleanup="NOT_REQUIRED")
    try:
        if not isinstance(profile, Profile) or not isinstance(file_probe, bool):
            raise ValueError("invalid SSH request")
        profile.__post_init__()
        key = _private_ssh_path(profile.ha_ssh_key)
        known_hosts = _private_ssh_path(profile.ha_ssh_known_hosts)
        options = (
            "BatchMode=yes",
            "IdentitiesOnly=yes",
            "StrictHostKeyChecking=yes",
            "IdentityAgent=none",
            "GlobalKnownHostsFile=/dev/null",
            f"UserKnownHostsFile={known_hosts}",
            "UpdateHostKeys=no",
            "VerifyHostKeyDNS=no",
            "ForwardAgent=no",
            "ForwardX11=no",
            "ClearAllForwardings=yes",
            "PermitLocalCommand=no",
            "ProxyCommand=none",
            "ProxyJump=none",
            "ConnectTimeout=10",
        )
        args = ["/usr/bin/ssh", "-F", "/dev/null", "-T"]
        for option in options:
            args.extend(("-o", option))
        args.extend(("-i", str(key), "-p", str(profile.ha_ssh_port)))
        args.extend(("--", f"root@{profile.ha_host}", "sh -s"))
        script = READ_ONLY_SCRIPT
        script += (
            PROBE_SCRIPT
            if file_probe
            else ("printf 'file_probe=NOT_REQUIRED\\nfile_probe_cleanup=NOT_REQUIRED\\n'\n")
        )
        output = _run(args, script.encode("ascii")).decode("ascii")
        parsed = {}
        for line in output.splitlines():
            name, separator, status = line.partition("=")
            if not separator or name not in CHECKS or name in parsed or status not in STATUSES:
                raise ValueError("unexpected SSH output")
            parsed[name] = status
        if set(parsed) != set(CHECKS):
            raise ValueError("incomplete SSH output")
        if not file_probe and (
            parsed["file_probe"] != "NOT_REQUIRED" or parsed["file_probe_cleanup"] != "NOT_REQUIRED"
        ):
            raise ValueError("unrequested probe result")
        return parsed
    except Exception:
        # A missing cleanup acknowledgement is BLOCKED, never inferred successful.
        return result
