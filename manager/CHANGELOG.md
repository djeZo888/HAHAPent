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
