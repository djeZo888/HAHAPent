# Suite Manager installation

Use Home Assistant's Supervisor-managed App store on an amd64 system running
Home Assistant 2026.9.1 or later. The task report identifies the exact tested release.
Manager updates use the normal App-store update action. The historical 0.1.0 →
0.1.1 live update preserved settings, ownership records and code backups in
`/data`. Manager 0.1.2 adds built-in catalog refresh; its current deployment
evidence is tracked in Task 003.
Add `https://github.com/djeZo888/HAHAPent` as an App repository, install **HAHAPent
Suite Manager**, start it, and open its Ingress interface as an administrator.
There is no LAN port, owner-token option, or developer-computer dependency.

Keep protection mode enabled. The only additional mount is Home Assistant's
configuration directory, explicitly writable at `/homeassistant`; persistent
manager state uses the App's existing `/data` volume. The only API permission is
`homeassistant_api`. The App's normal HA update mechanism updates the Manager;
individual integrations are chosen separately in its interface.

Before changing live integration code, retain a current independently readable
backup and review integration-specific startup/restart effects. Follow the
[test-dev runbook](test-dev-runbook.md) when executing this project's acceptance
tests. No physical controls are part of the device-free fixture.

Read the [App usage and recovery guide](../manager/DOCS.md),
[JSON contract](catalog.md), and [Task 002 evidence](../tasks/002-suite-manager.md).
The repository catalog includes the read-only Aquarius prerelease candidate.
Manager 0.1.2's **Refresh** action retrieves canonical built-in metadata securely,
with a validated persistent last-known-good cache and bundled bootstrap fallback.
Refresh updates metadata only; select each integration version and action
explicitly. Catalog source status shows freshness or refresh failure. Manager
0.1.1 requires the App update first because its refresh covers extra sources only.
See [Task 003](../tasks/003-led-integration.md) for actual release and acceptance
status; a published candidate is not proof of live control validation.
The acceptance-test catalog is separate and requires an explicit test action.

# Reproducible App source build

Supervisor builds `manager/` as its complete Docker context. Root schemas and the
normal catalog are canonical; regenerate their committed build-context copies
with `python tooling/sync_manager_bundle.py` and verify with `--check`. CI rejects
drift. Runtime does not fetch remote schemas or read files outside its App context.

The Dockerfile uses official
`python:3.13.15-slim-bookworm@sha256:ed86c82274b3c69b52fb5820f358f0bd7df0b603332063cb5c6e32bd220c3e6e`.
On 2026-09-08, Docker Hub's registry returned the amd64 child manifest
`sha256:2f2e5a876c71a6757f55ec57f2add0225ddaf01c802a33fcc29073943f94d907`
with Python `3.13.15`; the explicit version tag resolved to the same child.
Dependencies and Linux amd64 wheel hashes are pinned in `manager/requirements.txt`.
The build uses no implicit `BUILD_FROM`, unpinned package, or package source build.
These pins reproduce selected inputs; they do not promise identical Docker image
metadata across different Docker builders.

Public CI builds `linux/amd64`, checks imports and security failures through the
actual HTTP server, and runs synthetic engine changes inside that image without
network access. It separately runs the bootstrap-compatible Python matrix. It
does not contain test-dev credentials or prove a live HA deployment.

References: [App configuration](https://developers.home-assistant.io/docs/apps/configuration/),
[Ingress requirements](https://developers.home-assistant.io/docs/apps/presentation/#ingress),
[official Python image](https://hub.docker.com/_/python).
