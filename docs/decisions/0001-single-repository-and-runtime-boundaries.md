# ADR 0001: One repository, independent module lifecycles

Status: accepted for Task 001 scaffolding.

## Decision

Keep Manager, built-in module source, catalog contract, tooling, and public task
evidence in one repository. Version and release the Manager and each module
independently. Optional external repositories use the same versioned catalog
contract and require explicit trust.

Installed integrations must work while Manager and the development Mac are off.
Manager is responsible for installation lifecycle, not ongoing device transport.

## Consequences

An install record identifies the module, version, source origin, owned files,
and rollback state. Detect conflicts with Core, HACS, manual installations, and
other sources before any mutation. Do not adopt, overwrite, or remove an
unowned integration. Preserve unrelated files and user configuration.

Task 001 defines and tests the contract using synthetic data. The operational
installer and rollback behavior belong to Task 002. License selection is still
pending and is not resolved by this decision.
