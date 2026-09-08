# Integration package template

Copy this layout into a new independently versioned `modules/<module-id>/`
directory only after that module's task is authorized:

```text
modules/<module-id>/
  README.md
  custom_components/<integration_domain>/
    manifest.json
    __init__.py
    config_flow.py
    strings.json
    translations/en.json
    <platform>.py
```

Start with [manifest.example.json](manifest.example.json), replacing example
identity and documentation with the actual module. Home Assistant owns this
manifest's format; never add HAHAPent `schema_version` or catalog fields to it.
Implement setup, unload, and configuration through Home Assistant's native APIs.
The installed integration must run independently of the Manager and developer
computer. Declare every runtime dependency; never include an install script.

Use [module.example.json](module.example.json) as the module entry in the versioned
catalog. Replace every example URL, commit and digest. Keep the module version,
packaged HA manifest version, archive filename, and release metadata aligned.
Fill the tested Home Assistant compatibility range and minimum Manager semantics;
do not copy the fixture's range as proof of support. Leave license status pending
until the owner selects a license; do not invent a license URL.

Build an archive whose only root is `custom_components/<integration_domain>/`.
Include ordinary files only, with stable order, timestamps and permissions.
Publish a versioned GitHub release asset, calculate SHA-256 from those exact bytes,
and record the published source commit in catalog provenance. Do not point a
module install at a moving branch or rely on an external schema URL.

Before publishing, test archive safety, identity/version agreement, declared
dependencies, native config flow, reload/restart behavior, uninstall safety and
code rollback. A code rollback cannot reverse a configuration migration. Preserve
unrelated integrations and user configuration. See
[integration packaging](../../docs/integration-packaging.md) for the release steps.

This template contains no aquarium or LED implementation. Task 003 awaits its
separate authorization and device details.
