"""Run read-only checks and emit only an allowlisted, credential-free report."""

from __future__ import annotations

import argparse
import json
import os
import stat
import sys
from pathlib import Path
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tooling.access import (  # noqa: E402
    STATUS_VALUES,
    AccessError,
    _outside_worktrees,
    check_access,
    load_private_profile,
)


def write_report(report: dict[str, Any], destination: Path) -> None:
    """Create a new report only under the dedicated private state directory."""
    descriptor = None
    try:
        requested_root = Path.home() / ".local/state/hahapent"
        if requested_root.is_symlink():
            raise AccessError("report_path_rejected")
        root = requested_root.resolve()
        destination = destination.expanduser()
        if any(parent.is_symlink() for parent in (destination, *destination.parents)):
            raise AccessError("report_path_rejected")
        resolved = destination.resolve()
        if root not in resolved.parents or destination.is_symlink():
            raise AccessError("report_path_rejected")
        _outside_worktrees(resolved, ())
        # Only create/tighten this application's own directories, never ~/.local.
        directories = [root]
        directories.extend(reversed([p for p in resolved.parent.parents if root in p.parents]))
        if resolved.parent != root:
            directories.append(resolved.parent)
        for directory in dict.fromkeys(directories):
            if directory.is_symlink():
                raise AccessError("report_path_rejected")
            directory.mkdir(mode=0o700, parents=True, exist_ok=True)
            info = directory.stat()
            if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
                raise AccessError("report_path_rejected")
        descriptor = os.open(resolved, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            descriptor = None
            json.dump(report, output, indent=2, sort_keys=True)
            output.write("\n")
    except AccessError:
        raise
    except Exception:
        raise AccessError("report_path_rejected") from None
    finally:
        if descriptor is not None:
            os.close(descriptor)


def main(argv: Any = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", type=Path, help="Owner-only private bootstrap profile")
    parser.add_argument("--report", type=Path, help="New file under ~/.local/state/hahapent/")
    parser.add_argument("--ssh", action="store_true", help="Also verify the configured SSH channel")
    parser.add_argument(
        "--file-probe",
        action="store_true",
        help="Create/read/delete an isolated test file in approved /config (implies --ssh)",
    )
    arguments = parser.parse_args(argv)
    try:
        profile = load_private_profile(arguments.profile)
        report = check_access(profile)
        if arguments.ssh or arguments.file_probe:
            from tooling.ssh_access import check_ssh

            ssh_report = check_ssh(profile, file_probe=arguments.file_probe)
            # Do not allow another check implementation to widen the report schema.
            report["ssh"] = {
                key: ssh_report.get(key) if ssh_report.get(key) in STATUS_VALUES else "BLOCKED"
                for key in (
                    "ssh_session",
                    "app_container_root",
                    "ha_cli",
                    "configuration_directory",
                    "custom_components_directory",
                    "core_info",
                    "supervisor_info",
                    "file_probe",
                    "file_probe_cleanup",
                )
            }
        if arguments.report:
            write_report(report, arguments.report)
        print(json.dumps(report, indent=2, sort_keys=True))
        statuses = [item["status"] for item in report["checks"].values()]
        statuses.extend(report.get("ssh", {}).values())
        return int(any(status in {"FAIL", "BLOCKED"} for status in statuses))
    except AccessError as error:
        print(json.dumps({"status": "BLOCKED", "reason": error.code}), file=sys.stderr)
        return 2
    except Exception:
        print('{"status": "BLOCKED", "reason": "request_failed"}', file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
