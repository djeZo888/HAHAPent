# Draft catalog contract

Task 001 establishes an **empty built-in catalog** and an offline validator.
There are no published modules or installable Manager App. The license decision
is pending. Passing validation establishes metadata shape and local consistency
only; it does not establish trust, download availability, artifact integrity,
license validity, compatibility in a running system, or safe installation.

## Files and versioning

- The root hahapent.json describes the built-in source and its modules.
- schemas/catalog-v1.schema.json uses JSON Schema Draft 2020-12.
- The catalog has schema_version 1 and status draft. This is an initial contract,
  subject to review before Task 002; it is not a frozen installer API.
- The root repository.yaml is the separate Home Assistant App repository
  descriptor. It does not serve as the HAHAPent module catalog.
- Manager code belongs directly in manager/. It is a scaffold with no App
  config.yaml, image declaration, Dockerfile, or install path in Task 001.

The Manager and built-in modules share one repository. Module versions are
independent SemVer values; a repository change does not imply a release of every
module. The module array currently has no entries. Synthetic fixtures are kept
under tests/fixtures/catalog/ and must never be promoted as release metadata.

## Reserved fields

Every object rejects additional properties. Unknown catalog versions fail
validation. A module must supply all metadata below when a real release is
eventually proposed.

| Field | Draft meaning |
| --- | --- |
| source.id | Stable source identity, paired with a repository URL; this text does not grant trust. |
| source.name / repository_url | Display name and HTTPS source repository. |
| module id | Stable lowercase module identity, unique within the source. The global identity is source id plus module id. |
| integration_domain | Home Assistant integration domain, unique within this catalog; future installation must also check the target environment. |
| version | Independent SemVer version, including optional prerelease/build metadata. |
| home_assistant | Inclusive min_version and optional exclusive max_version_exclusive, using stable year.month.patch releases. Bounds describe a claim, not verified compatibility. |
| dependencies | Exact source_id, module_id and version requirements. No version-range resolver is implemented. |
| artifact | HTTPS ZIP URL and lowercase SHA-256 of the future exact artifact bytes. |
| license | Declared license expression and HTTPS text URL. SPDX expression parsing and license review are not implemented. This does not choose the project's license. |
| provenance | HTTPS source repository, full lowercase 40-character Git revision, and relative source path without dot/traversal segments. |
| restart | Separate Home Assistant and Manager declarations: required, not_required, or unknown. Metadata never authorizes a restart. |

HTTPS metadata URLs must not contain embedded credentials, query strings,
fragments, malformed ports, whitespace, or backslashes. Public artifacts must not
depend on token-bearing download URLs. Validation performs no network requests.
Digest/revision syntax checks do not prove that the referenced bytes or revision
exist. ZIP extraction, path validation inside archives, digest verification,
signatures, release creation, installation and rollback are future work.

## Dependencies and trust

The validator rejects duplicate module ids and integration domains, duplicate
dependency identities, missing local dependencies, mismatched exact local
versions, self-dependencies and local cycles. Compatibility bounds must be
ordered. Dependency matching includes the source identity.

An external source reference receives syntax validation only. The offline
validator neither resolves nor authorizes it. Before future installation, an
operator must explicitly trust each extra source and bind its identity to the
selected repository; source declarations cannot self-authorize. Resolution must
then check dependency versions, cross-source cycles, and domain collisions across
the complete trusted set. That trust store and resolver are outside Task 001.

Future installation must preserve HACS, manual, and Core-managed integrations
and refuse conflicting ownership. Installed integrations must operate with both
Manager and the Mac off. These are requirements for subsequent tasks, not
capabilities demonstrated by this catalog.

## Local validation

From the repository root, after installing the development requirements:

    .venv/bin/python tooling/validate_catalog.py
    .venv/bin/python -m unittest discover -s tests -p 'test_catalog.py' -v

The CLI accepts one or more explicit JSON paths as positional arguments. It exits
0 for schema and local semantic success and 1 for invalid metadata or unreadable
JSON. Duplicate object keys and non-finite JSON numbers are rejected. Diagnostics
report rule names and field paths without echoing input values. The validator
uses the checked-in schema; a catalog's optional $schema does not cause a fetch.
Executed results are recorded in docs/development.md and
tasks/001-access-and-repository.md by the Task 001 coordinator.

## Official Home Assistant references

Reviewed on 2026-09-08:

- Home Assistant requires a repository.yaml at the Git repository root; name is
  required and url/maintainer are optional. This scaffold uses name and url.
  [Create an app repository](https://developers.home-assistant.io/docs/apps/repository/)
- An installable App uses config.yaml with required name, version, slug,
  description and arch fields. Supervisor searches recursively for config.yaml,
  so no placeholder App manifest is included in this scaffold.
  [App configuration](https://developers.home-assistant.io/docs/apps/configuration/)

These official documents define the App repository shape. The HAHAPent module
catalog above is a project-specific draft, not a Home Assistant-defined format.
