# ADR 0002: Conditional Home Assistant App packaging

Status: proposed; requires verified installation support and Task 002 approval.

## Decision

Use a Supervisor-managed Home Assistant App with an Ingress UI for the future
Manager if the approved test-dev installation supports that deployment path.
Do not create an installable App manifest or deploy Manager in Task 001.

Home Assistant documents Apps as containers configured through Supervisor.
Ingress exposes an App UI through Home Assistant and has specific gateway-access
requirements. Home Assistant Container does not include Apps.
([Apps](https://developers.home-assistant.io/docs/apps/),
[Ingress](https://developers.home-assistant.io/docs/apps/presentation/#ingress),
[Installation types](https://www.home-assistant.io/installation/#about-installation-types))

## Consequences

Task 001 must record installation type and access capabilities from actual
evidence. If the required path is unavailable, report that constraint before
selecting another architecture. Do not infer support from a hostname, a token,
or the presence of a Supervisor permission flag.

Task 002 must choose the smallest required privileges, retain App protection,
restrict Ingress access, and avoid an additional public management port. An App
container session is not host or hypervisor administration. Installed modules
must remain independent of Manager availability.
