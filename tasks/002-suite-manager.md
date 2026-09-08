# Task 002: Suite Manager

Status: planned; not implemented or authorized by Task 001.

## Objective and entry conditions

Deliver an actually installable Manager with catalog display and safe
install/update/remove/rollback operations for independently versioned modules.
Review Task 001 evidence first, confirm the supported installation and access
path, resolve the release/license requirements, and agree a recovery plan before
live deployment.

The proposed packaging is a Supervisor-managed App with Ingress, conditional on
verified support. A README scaffold or catalog validator does not meet this
task's installability requirement.

## Required behavior

- Present built-in modules and explicitly trusted extra sources using the same
  versioned catalog contract; preserve origin identity and reject conflicts.
- Enforce compatibility and integrity checks before changing installed files.
  Reject malformed catalogs, unsupported schema versions, unsafe paths, corrupt
  archives, incomplete downloads, and incompatible releases.
- Stage and validate artifacts before applying them. Record ownership and
  previous versions so interrupted updates have a recoverable state.
- Install, update, remove, and roll back only Manager-owned modules. Preserve
  unrelated files, user configuration, and Core/HACS/manual installations.
- Explain reload/restart requirements before applying changes. Installed
  modules must run with Manager and the development Mac off.

## Validation and safety

First exercise the full lifecycle on device-free synthetic fixtures, including
failed downloads, corrupt bytes, traversal/link attacks, origin and domain
conflicts, incompatibility, interrupted updates, and rollback after failure.
Validate removal preserves unrelated files and configuration.

Before a later live change, take and verify the relevant backup and prepare a
concrete rollback. Existing KNX integrations and automations must be preserved.
Any Core restart needs a separately approved maintenance plan that considers
startup automations, availability, and recovery. Task 001 authorizes no such
restart. Do not intentionally control physical devices during Manager testing.

Acceptance requires a completed installation on the approved supported test-dev
path, exercised lifecycle outcomes, and sanitized evidence. Report unexercised
capabilities honestly; CI success alone does not prove live deployment.
