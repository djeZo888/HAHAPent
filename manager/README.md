# HAHAPent Suite Manager

An administrator-only Home Assistant App for choosing, installing, updating,
removing, and recovering independently versioned integrations. Its interface
opens through Home Assistant Ingress. Installed integrations run directly in
Home Assistant and keep working while this App and the developer computer are off.

The initial App targets **amd64** and requires Home Assistant **2026.9.1 or later**.
The Task 002 evidence identifies the exact release tested.
It publishes no LAN port, keeps protection mode enabled, and uses only the
Home Assistant API permission. Its writable Home Assistant configuration mount
is explicitly `/homeassistant`; manager settings and recovery files persist in
`/data`. Source trust and administrator checks apply to direct API requests too.

Use the App store repository URL
`https://github.com/djeZo888/HAHAPent`, install **HAHAPent Suite Manager**, start it,
and choose **Open Web UI**. Read [DOCS.md](DOCS.md) before managing code. Update
the Manager itself through the normal Home Assistant App update mechanism.

The ordinary built-in catalog initially contains no production integrations.
The separately published device-free test catalog is for acceptance testing only.
Task 003's aquarium integration is not included. License selection remains pending.

See the [release evidence](../tasks/002-suite-manager.md) for exactly what was
verified on the approved test environment and any remaining limitations.
