# Built-in modules

This directory contains independently packaged and independently versioned
HAHAPent modules. [Aquarius Plant LED](aquarius_plant_led/README.md) is a
read-only candidate pending successful bounded hardware controls and an installed
catalog delivery decision. The device-free `hahapent_test` fixture is distributed
separately from the normal catalog for Manager acceptance tests.

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

The first device integration is recorded in [Task 003](../tasks/003-led-integration.md).
Its static evidence, synthetic checks, actual readback and failed bounded control
test are distinguished; no optical validation or production installation is claimed.
