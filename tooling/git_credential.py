"""A Git-only credential helper restricted to the selected HTTPS repository.

Configure Git credential.useHttpPath=true and invoke this script via a helper
shell command setting HAHAPENT_GIT_CREDENTIAL_HELPER=1. The helper additionally
checks for a Git ancestor process and non-terminal protocol pipes. Its secret
output is exclusively Git's credential protocol; never run it as a display tool.
Store/erase are no-ops: the protected credential file remains the sole source.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Any

# A canonical absolute script path also works when Git runs in another worktree.
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tooling.access import EXPECTED_REPOSITORY, AccessError, load_private_profile  # noqa: E402


def _git_invocation() -> bool:
    if (
        os.environ.get("HAHAPENT_GIT_CREDENTIAL_HELPER") != "1"
        or sys.stdin.isatty()
        or sys.stdout.isatty()
    ):
        return False
    pid = os.getppid()
    for _ in range(5):
        if pid <= 1:
            return False
        try:
            result = subprocess.run(
                ["ps", "-p", str(pid), "-o", "ppid=", "-o", "comm="],
                check=True,
                capture_output=True,
                text=True,
                timeout=2,
            )
            parent, executable = result.stdout.strip().split(None, 1)
            if Path(executable).name in {"git", "git-remote-https", "git-remote-http"}:
                return True
            pid = int(parent)
        except Exception:
            return False
    return False


def _request_matches(request: str, repository: str = EXPECTED_REPOSITORY) -> bool:
    """Match only the pinned target; discard documented Git challenge metadata.

    Git 2.46+ can advertise capability[] and include repeated wwwauth[] headers.
    These fields are informational: this helper always returns its own basic
    username/password pair and never reflects a challenge or inherited username.
    See https://git-scm.com/docs/git-credential#_inputoutput_format.
    """
    records: dict[str, str] = {}
    if len(request) > 8192 or "\r" in request or "\x00" in request:
        return False
    for line in request.split("\n"):
        if not line:
            continue
        key, separator, value = line.partition("=")
        if not separator:
            return False
        if key in {"capability[]", "wwwauth[]"}:
            continue
        if key in records or key not in {"protocol", "host", "path", "username"}:
            return False
        records[key] = value
    return (
        records.get("protocol") == "https"
        and records.get("host") == "github.com"
        and records.get("path") in {repository, repository + ".git"}
    )


def main(argv: Any = None) -> int:
    arguments = sys.argv[1:] if argv is None else argv
    if arguments in (["store"], ["erase"]):
        return 0
    if arguments != ["get"] or not _git_invocation():
        print("git_invocation_required", file=sys.stderr)
        return 1
    try:
        if not _request_matches(sys.stdin.read(8193)):
            return 0
        profile = load_private_profile()
        token = profile.credentials.github_token
        if any(character in token for character in ("\r", "\n", "\x00")):
            raise AccessError("credentials_invalid")
        sys.stdout.write("username=x-access-token\npassword=" + token + "\n\n")
        sys.stdout.flush()
        return 0
    except Exception:
        print("credential_unavailable", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
