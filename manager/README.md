# Suite Manager scaffold

This directory reserves the Manager's place in the single HAHAPent repository.
Task 001 does not provide an App manifest, executable Manager, container image,
or installable release.

[Task 002](../tasks/002-suite-manager.md) will implement the Manager after its
entry conditions are met. A Supervisor-managed Home Assistant App with Ingress
is the proposed packaging, conditional on the verified installation supporting
it. Home Assistant documents Apps as containerized applications managed through
Supervisor and Ingress as access through the Home Assistant UI.
([Apps](https://developers.home-assistant.io/docs/apps/),
[Ingress](https://developers.home-assistant.io/docs/apps/presentation/#ingress))

Manager responsibilities will be catalog display, explicitly trusted sources,
compatibility checks, install/update/remove operations, ownership records, and
rollback. It must preserve unrelated files and configuration. Runtime device
communication belongs in installed integrations, with no dependency on a running
Manager or Mac.
