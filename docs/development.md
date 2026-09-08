# Development

## Local setup

Use Python 3.9 or newer in an isolated `.venv`. Keep the environment and caches
out of Git. Dependency versions are pinned in the repository's development
requirements. Public CI runs only synthetic inputs and must not need a private
profile, real credentials, or access to Home Assistant.

Create the local environment from the repository root:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
```

Run these checks after installing the pinned development requirements:

```sh
.venv/bin/python -m unittest discover -s tests
.venv/bin/python tooling/validate_catalog.py
.venv/bin/ruff check .
```

The catalog validator checks local metadata against the checked-in schema. It
does not download artifacts, prove repository trust, or install modules.

## Live access command

```sh
.venv/bin/python tooling/check_access.py
.venv/bin/python tooling/check_access.py --ssh
```

This is a separate live operation for the coordinator, using the protected
profile's exact test-dev target and credential-file reference. It is not a CI
check. Read [access and secrets](access-and-secrets.md) and follow
[the runbook](test-dev-runbook.md) before using it. Its observed API results do
not establish every administrative capability.

`--ssh` adds read-only checks with the dedicated key and pinned host key. Only
`--file-probe` explicitly enables a unique non-executable marker round trip and
cleanup in a new project directory under the configuration mount. The flag
implies SSH; it never installs an integration or calls a device service.
An absent `custom_components` directory with a writable parent is reported as
`AVAILABLE_NOT_EXERCISED`; creating that directory is deferred to Task 002.
Reports describe checks in that invocation; historical Git/API writes and the
backup are documented separately in the task evidence report.

## Git checkpoints

Preserve an existing repository's history, branch protections, and merge policy.
After establishing `main`, use a task branch. Stage explicit paths, inspect the
staged diff, and run synthetic checks before each push. Only the coordinator
may merge or push.

```sh
.venv/bin/python tooling/check_secrets.py --staged
.venv/bin/python tooling/check_secrets.py --history
.venv/bin/python tooling/check_secrets.py --outgoing origin/main
```

Use `--outgoing origin/main` only after the base ref exists and is the verified
remote base; use the history scan for the initial push with no remote base.
Inspect all outgoing commits, not only the working tree. CI uses
`--no-private-values` so public validation never reads local credentials.

The private-value scan supplements public pattern checks on the coordinator's
machine. Never weaken it to publish a known secret. A clean scan does not replace
manual review for household information or operational data.

After each push, independently verify the actual remote commit and the completed
CI conclusion for that commit. Queued or running CI is not a passing result.
Never force-push or rewrite shared history.

## Task 001 verification record

Evidence updated 2026-09-08T21:47:51+02:00 (Europe/Ljubljana). The tested
implementation checkpoint and completed hosted runs are linked below. The full sanitized
access and repository report belongs in
[Task 001](../tasks/001-access-and-repository.md); private reports remain under
`~/.local/state/hahapent/`.

| Check | Result | Meaning |
| --- | --- | --- |
| Unit tests | `PASS` | 88 synthetic tests; Python 3.9.6 |
| Catalog validation | `PASS` | Empty draft catalog and schema; offline metadata only |
| Ruff | `PASS` | Repository Python lint |
| Staged/outgoing secret checks | `PASS` | Exact private values plus patterns, paths, history and messages; repeated before each push |
| Remote commit verification | `PASS` | Initial privacy checkpoint and source commit `ecbfaeb` independently matched remote heads |
| Completed CI | `PASS` | [Push run](https://github.com/djeZo888/HAHAPent/actions/runs/34270701339) and [PR run](https://github.com/djeZo888/HAHAPent/actions/runs/34270756867); Python 3.9 and 3.13 |

Use `PASS`, `FAIL`, `BLOCKED`, `NOT_TESTED`,
`AVAILABLE_NOT_EXERCISED`, and `NOT_REQUIRED` as defined in
[access and secrets](access-and-secrets.md). Do not turn a read-only result into
a claim that writes, restores, restarts, or device operations were exercised.
