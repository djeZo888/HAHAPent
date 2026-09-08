# 0.1.2

- Refresh the built-in catalog from the canonical GitHub repository using the
  existing secure downloader and source identity/schema/feature checks.
- Atomically retain validated metadata for App restarts, with the bundled catalog
  as bootstrap fallback. Invalid downloads or cache-write failures preserve the
  last usable catalog; unsafe or unknown cache formats are not overwritten.
- Show catalog origin, refresh timestamps and errors in Sources. Metadata refresh
  does not install code or restart HA; duplicate-source and ownership rules remain.

Synthetic validation and live deployment evidence are tracked separately in Task 003.
The module and frozen device-free fixture releases remain independently versioned.

# 0.1.1

- Shut down gracefully when Supervisor stops the App, avoiding an error state
  caused by the default SIGTERM exit behavior observed with the 0.1.0 candidate.
- Preserve settings, owned integration code, and the independent fixture releases
  when updating through Home Assistant's normal App store mechanism.

The Manager version advances independently. Fixture A remains 0.1.0, fixture B
remains 0.2.0, and their minimum Manager requirement remains 0.1.0. Published
fixture bytes, hashes, provenance, and the `test-fixtures-v1` tag are unchanged.
Current validation and release identifiers are recorded in Task 002.

# 0.1.0 candidate

- Introduce the Ingress Suite Manager for explicitly trusted integration sources.
- Track owned code, native configuration state, restart requirements, and recovery.
- Package the amd64 Python 3.13 runtime with pinned dependencies and bundled schemas.
- Publish device-free A/B artifacts separately from the normal integration catalog.

Live validation and release identifiers are recorded in the repository's Task 002
report. License selection remains pending.
