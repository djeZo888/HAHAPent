# Install and use

In Home Assistant, open **Settings → Apps → App store → Repositories**, add
`https://github.com/djeZo888/HAHAPent`, and install **HAHAPent Suite Manager**.
Start it and select **Open Web UI**. Administrator access is required; no separate
account or LAN management port is provided. Keep protection mode enabled.

Search the catalog and review the source, version, compatibility, dependencies,
documentation, and restart requirement before choosing **Install** or **Update**.
There are no automatic module updates. Installing files does not create a native
Home Assistant configuration entry. After any required Core restart, use
**Settings → Devices & services → Add integration** to configure the integration.

Adding an extra public GitHub source requires explicit trust in its publisher.
Adding or removing a source changes catalog availability only. Previously installed
entries remain in the registry when a source is removed or offline. Checksums
verify downloaded bytes; they do not establish whether a publisher is trustworthy.

The normal catalog initially has no production integrations. For the device-free
acceptance fixture, open **Sources** and enable **Show test integrations**. This
reveals the separate test catalog without installing anything. Disable it after
acceptance cleanup; it is not the aquarium integration.

# Remove and recover

Remove an integration's native configuration entry in **Settings → Devices &
services** first. Then confirm **Uninstall** in HAHAPent. The Manager removes only
its owned code and never edits Home Assistant's `.storage`. It refuses Core, HACS,
manual, or externally modified ownership conflicts.

Updates and removal retain recovery code in the App's persistent `/data`. Use
**Roll back** to select the previous owned code version. Code rollback cannot undo
Home Assistant configuration migrations, user configuration, or device settings.
Apply the displayed Core restart requirement before checking the running version.

If the App restarts during a change, its persistent transaction journal is used
to recover a consistent filesystem state. If Home Assistant cannot start after
installing code, use your existing protected Terminal & SSH recovery channel and
the [recovery runbook](../docs/test-dev-runbook.md). Preserve the Manager's registry,
transaction journal, and code backup; do not overwrite `.storage` or unrelated
integrations. Keep an independently verified Home Assistant backup before changes.

The App mounts Home Assistant configuration at `/homeassistant`, which is distinct
from other Apps' `/config` mounts. Settings, ownership records, transactions, and
code backups live in `/data` and survive App restarts. Home Assistant App backups
use a cold backup so these files are captured while the Manager is stopped.

# Limits

Version 0.1.1 supports amd64, explicit individual module changes, and declared
dependency checks. It has no dependency solver or automatic module updates.
Integrations run independently in Home Assistant after installation. The Manager
does not update Home Assistant, firmware, or infrastructure. License selection
is pending. See [Task 002 evidence](../tasks/002-suite-manager.md) for tested behavior.
