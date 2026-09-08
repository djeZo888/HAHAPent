# Architecture

## Boundaries

HAHAPent uses one source repository for the Suite Manager, built-in modules,
catalog contract, tooling, and task evidence. The Manager and each module have
independent versions and release artifacts. A suite version must not force every
module to update.

Task 001 establishes these boundaries and validates synthetic catalog inputs.
It does not implement downloads, installation, updates, removal, rollback, or
device communication.

## Planned runtime

The Manager is proposed as a Supervisor-managed Home Assistant App with Ingress,
subject to confirming the approved test-dev installation supports Apps. Current
Home Assistant documentation distinguishes Home Assistant OS, which supports
Apps, from Home Assistant Container, which does not.
([Installation types](https://www.home-assistant.io/installation/#about-installation-types))

Ingress provides access to an App UI through Home Assistant. Task 002 must
implement the documented access restrictions and avoid exposing an additional
public management port. This design is proposed, not a tested deployment.
([Ingress requirements](https://developers.home-assistant.io/docs/apps/presentation/#ingress))

Installed custom integrations run in Home Assistant. Their device communication
and normal operation must not depend on the Manager, an external repository
being reachable, or the development Mac staying on. The Manager manages files
and lifecycle metadata; it is not a runtime device bridge.

## Catalog and trust

The versioned catalog contract is shared by the built-in source and optional
extra sources. Each future entry identifies a module, its version and origin,
compatibility limits, a release artifact, integrity information, and the
expected integration domain. Unknown schema versions and invalid entries must
fail closed. Exact fields are defined by the checked-in contract, not by this
overview.

Adding an extra source requires explicit user trust. Catalog metadata must not
silently add another trusted origin. Matching names from different origins must
remain distinguishable. Source changes, origin conflicts, incompatible releases,
invalid paths, and artifact validation failures must block the affected
operation before installed files change.

The later installer must validate downloaded bytes, extract into a staging
directory with path and link checks, then apply only a validated module. An
integrity field does not itself prove that an origin is trustworthy. These are
Task 002 requirements; Task 001 catalog validation is not an installer proof.

## Ownership and recovery

Manager ownership is recorded per installation. A pre-existing integration with
the same domain is not owned merely because a catalog entry matches it. Never
overwrite or remove Core-, HACS-, or manually managed integrations. Preserve
unrelated files and user configuration on every lifecycle path.

Task 002 must record the prior owned version and a usable rollback artifact
before updates, handle interrupted operations, and verify recovery using
device-free fixtures. Reload and restart requirements must be disclosed before
changes. Existing KNX integrations and automations make an approved maintenance
window and recovery plan necessary for any later Core restart.

## Private operational data

The protected bootstrap profile selects the exact repository and test-dev host.
Private credentials and targets live under `~/.config/hahapent/`; operational
state lives under `~/.local/state/hahapent/`; backups live under
`~/.local/share/hahapent/backups/`. No home configuration or operational dump is
a source artifact. See [access and secrets](access-and-secrets.md).

The architecture decisions are recorded in
[ADR 0001](decisions/0001-single-repository-and-runtime-boundaries.md) and
[ADR 0002](decisions/0002-manager-packaging.md).
