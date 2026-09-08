# ADR 0002: Supervisor-managed Manager App

Status: accepted by the revised Task 002 assignment.

Task 001 verified Home Assistant OS, Supervisor and amd64 test-dev access. Build
the initial Manager in `manager/` as a Supervisor-managed App with an Ingress UI.
Install through the actual repository/App-store path. The revised Task 002
assignment replaces the earlier prohibition on an installable manifest.

Use an explicit digest-pinned base image and reproducible published source;
Supervisor no longer provides the obsolete implicit BUILD_FROM fallback. Test
the actual amd64 runtime/image and advertise only supported architectures.
Map `homeassistant_config` explicitly to a dedicated path. Persist settings,
registry, backups and transaction journal under `/data`. Keep protection enabled,
minimum permissions and no exposed LAN port. Authenticate every management
request through a verified trusted Ingress boundary plus administrator identity.
Use supported Supervisor-provided credentials, never workstation credentials.

Installed integrations operate independently of the Manager or development Mac.
Manager updates follow HA's normal App mechanism; modules have their own versions.

References: [App configuration](https://developers.home-assistant.io/docs/apps/configuration/)
and [Ingress](https://developers.home-assistant.io/docs/apps/presentation/#ingress).
