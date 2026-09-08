# Independently versioned integration packages

The Manager and built-in integrations share this repository but have independent
software versions. A native integration lives in `modules/<module-id>/` and is
published as a versioned ZIP containing only
`custom_components/<integration_domain>/`. Home Assistant loads its native
manifest and config flow; no Manager process or Mac is needed at runtime.

The catalog records the module's identity/domain/version, tested HA range,
minimum Manager version and required semantics, dependencies, documentation,
provenance commit, versioned release-asset URL, SHA-256, and restart requirements.
Checksums verify bytes, not trust. Extra sources need explicit trust and must bind
their metadata and artifacts to the approved public GitHub repository. See the
[JSON contract](catalog.md) for draft-v1 compatibility and extension rules.

1. Implement the native integration and test it independently. Begin from the
   [small template](../templates/integration/README.md) when the next module's
   task is authorized. Keep credentials and runtime configuration out of source.
2. Choose the module version and keep it identical in its manifest, source
   metadata, catalog and artifact filename. Declare dependencies. Code rollback
   does not reverse HA configuration migrations or device settings.
3. Commit the reviewed source, then build deterministic ZIP bytes from that exact
   published revision. Include ordinary files with stable paths and permissions;
   never include links, scripts to run during installation, caches or state.
4. Publish immutable versioned release assets and the catalog. Record SHA-256
   from the exact uploaded bytes. Verify the public download and provenance.
5. Verify install/configure/update/recovery/removal with the native HA lifecycle.
   Preserve unrelated code and configuration; do not claim an untested HA range.

## Generic module builder

Build a reviewed and published source commit with:

```sh
python tooling/build_module.py --domain aquarius_plant_led \
  --revision <full-source-commit> --output-dir <new-output-directory>
```

The builder reads ordinary native integration files directly from Git objects,
not the working tree. It ignores local Git replacement refs and rejects unsafe paths, executables,
private/non-native files, invalid manifests and unsupported dependencies; fixed
timestamps, ordering, permissions and stored ZIP entries make bytes reproducible.
The emitted metadata records exact provenance and SHA-256; publication and catalog
updates remain separate reviewed steps. A prerelease candidate must clearly state
its limits in the release, catalog description and module documentation.

Manager 0.1.1 embeds the built-in catalog. Publishing root `hahapent.json` and its
canonical build-context copy does not update an already installed App image.
Refreshing or adding the same source cannot bypass that limitation. An App
packaging update or a supported remote-catalog feature requires authorization;
do not patch installed containers or directly copy acceptance integrations.

# Device-free acceptance assets

`modules/hahapent_test/` is excluded from the normal catalog. Its version A is
`0.1.0`; B is `0.2.0`. Both create one diagnostic version sensor and no devices,
network requests, service calls or polling. Their native config-entry format is
unchanged, making this fixture suitable for the A → B → A code lifecycle.

Build with:

```sh
python tooling/build_fixture.py --output-dir build/fixtures \
  --revision <published-source-commit> --release-tag test-fixtures-v1
```

The builder emits `hahapent-test-0.1.0.zip`, `hahapent-test-0.2.0.zip`, and
`test-catalog.json`. ZIP entries are sorted and stored without compression, have
fixed timestamps and ordinary `0644` file modes, and exclude Python bytecode.
Only the manifest and code-version constant change between A and B. Build output
does not include private files. The catalog pins the source commit and release
URLs; its compatibility is conservatively limited to HA 2026.9.1 until further
releases are tested.

The immutable `test-fixtures-v1` release allows testing the Manager before its
final release is cut. The final Manager `v0.1.1` release may attach the same fixture
ZIP bytes; `--release-tag v0.1.1` generates corresponding catalog URLs without
changing artifact bytes. Never move a tested release tag to hide subsequent fixes.
Actual published commits, asset digests and live evidence belong in
[Task 002](../tasks/002-suite-manager.md).

License selection remains pending for project code. The catalog supports
`{"status":"pending"}` and does not invent a license expression or URL.

Home Assistant references: [integration manifest](https://developers.home-assistant.io/docs/creating_integration_manifest/),
[native config flow](https://developers.home-assistant.io/docs/core/integration/config_flow/),
[sensor entity](https://developers.home-assistant.io/docs/core/entity/sensor/).
