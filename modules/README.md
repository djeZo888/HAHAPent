# Built-in modules

This directory will contain independently installable and independently
versioned HAHAPent modules. It contains no released integrations in Task 001.
Catalog fixtures are synthetic validation data, not installable modules.

Each future module must declare its identity, version, origin, compatibility,
artifact integrity information, and lifecycle requirements using the versioned
catalog contract. Home Assistant custom integrations also require an integration
manifest and their own version.
([Integration manifest](https://developers.home-assistant.io/docs/creating_integration_manifest/))

Installation ownership must remain explicit. A matching domain found in Core,
HACS, or an existing manual installation is a conflict to report, not permission
to replace it. Removal must leave unrelated files and user configuration intact.

An installed module must keep operating with the Manager and development Mac
off. Additional source repositories are optional, require explicit trust, and
must obey the same contract and ownership rules as built-in modules.

The first planned device integration is recorded in
[Task 003](../tasks/003-led-integration.md). Its device protocol and supported
functions are not yet established.
