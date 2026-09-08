# Architecture

## Boundaries

HAHAPent uses one source repository for the Suite Manager, built-in modules,
catalog contract, tooling, and task evidence. The Manager and each module have
independent versions and release artifacts. A suite version must not force every
module to update.

Task 001 established access and repository boundaries. Task 002 implements the
Manager's catalog, installation, update, removal, and recovery paths. Its
device-free fixture exercises the native integration lifecycle; aquarium device
communication remains outside the authorized scope.

## Runtime

The Manager is a Supervisor-managed App with Ingress, an explicit digest-pinned
Python 3.13 image, and an amd64 build target. Its configuration maps Home
Assistant's configuration directory to `/homeassistant` and uses `/data` for
persistent manager state. It exposes no LAN port, retains protection mode, and
requests only `homeassistant_api`. The Supervisor-provided credential accesses
the internal Core proxy; workstation credentials never enter the App.

Normal App updates preserve `/data`. Version 0.1.1 handles Supervisor stop
gracefully; the App's 30-second shutdown window accommodates its bounded drain.
Hosted image checks and the live 0.1.0-to-0.1.1 App update are recorded separately
in the Task 002 evidence.

Every management request must arrive from the trusted Ingress gateway and identify
an administrator verified through Home Assistant. Mutations also require the
expected same-origin request headers. Forwarded peer headers and sidebar
visibility cannot establish authorization. See
[Ingress requirements](https://developers.home-assistant.io/docs/apps/presentation/#ingress)
and the implemented App configuration in `manager/config.yaml`.

Installed custom integrations run in Home Assistant. Their device communication
and normal operation must not depend on the Manager, an external repository
being reachable, or the development Mac staying on. The Manager manages files
and lifecycle metadata; it is not a runtime device bridge.

## Catalog and trust

The versioned catalog contract is shared by the built-in source and optional
extra sources. Each entry identifies a module, its version and origin,
compatibility limits, a release artifact, integrity information, and the
expected integration domain. Unknown schema versions and invalid entries must
fail closed. Exact fields are defined by the checked-in contract, not by this
overview.

Adding an extra source requires explicit user trust. Catalog metadata must not
silently add another trusted origin. Matching names from different origins must
remain distinguishable. Source changes, origin conflicts, incompatible releases,
invalid paths, and artifact validation failures must block the affected
operation before installed files change.

Downloads use bounded HTTPS requests with certificate verification and restricted
GitHub release-asset redirects. The engine checks the digest before extraction,
rejects unsafe paths, links and identity mismatches, and stages the selected
integration before replacement. Package-supplied install scripts are never run.
Checksums verify bytes; they do not establish publisher trust.

The released catalog remains `schema_version: 1` and safely reads the original
empty draft. Settings and installed-state documents have independent v1 schemas;
module and Manager software versions are separate. Unknown optional extension
data is retained without changing required semantics. Unsupported future schemas
are rejected without overwriting stored data. The canonical root schemas and
normal catalog have committed copies in the App build context; a sync tool and
drift check keep them aligned. Runtime uses bundled schemas only.

## Ownership and recovery

Manager ownership is recorded per installation. A pre-existing integration with
the same domain is not owned merely because a catalog entry matches it. Never
overwrite or remove Core-, HACS-, or manually managed integrations. Preserve
unrelated files and user configuration on every lifecycle path.

The persistent registry records installed ownership independently of catalog
availability. Operations are serialized and use staged code, a transaction
journal, filesystem swaps, and prior-code backups. Recovery handles interrupted
operations; removal is blocked while native HA configuration entries remain.
The Manager does not edit `.storage` or delete user configuration.

After uninstall, the installed record and owned integration directory are gone,
while a removed-code recovery record and private backup remain. The recovery
section may retain a conservative restart reminder; this describes the removed
code operation and does not imply installed code or a native configuration entry.
Restoring that retained code requires an explicit recovery action.

The interface distinguishes files installed, restart pending, and configured or
loaded state. Rollback restores code, not HA configuration migrations or device
settings. Necessary test-dev Core restarts follow the current backup and startup
safety gate in the runbook; the Manager does not restart Core automatically.
The real Ingress acceptance exercised A installation and native setup, B update,
A rollback, configured-removal blocking, native entry removal, and code uninstall.
The version sensor remained loaded with the Manager stopped. Exact restart,
cleanup, backup, and release evidence is recorded in
[Task 002](../tasks/002-suite-manager.md), separately from synthetic tests.

## Private operational data

The protected bootstrap profile selects the exact repository and test-dev host.
Private credentials and targets live under `~/.config/hahapent/`; operational
state lives under `~/.local/state/hahapent/`; backups live under
`~/.local/share/hahapent/backups/`. No home configuration or operational dump is
a source artifact. See [access and secrets](access-and-secrets.md).

The architecture decisions are recorded in
[ADR 0001](decisions/0001-single-repository-and-runtime-boundaries.md) and
[ADR 0002](decisions/0002-manager-packaging.md).
