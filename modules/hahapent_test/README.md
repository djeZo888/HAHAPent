# Device-free lifecycle fixture

This integration is exclusively for Suite Manager acceptance tests. It is absent
from the normal catalog. Versions A (`0.1.0`) and B (`0.2.0`) are separate,
deterministically built release assets. Both create the same native configuration
entry and one diagnostic sensor, **HAHAPent test installed version**. Its state is
the loaded code's version. No devices, network requests, service calls, polling,
or physical controls are involved.

Use Home Assistant's **Settings → Devices & services → Add integration** flow to
configure it after installation and the required Core restart. Remove its native
configuration entry before uninstalling its code through the Manager. The fixture
keeps working with the Manager and developer computer stopped. Config-entry format
version `1` stays identical between A and B, so this specific rollback needs no
configuration migration. Other integrations may differ.

Build with `python tooling/build_fixture.py --output-dir build/fixtures --revision
<published-source-commit> --release-tag test-fixtures-v1`. The builder writes two
ZIPs and `test-catalog.json` for that immutable fixture release. The same ZIP bytes
can also accompany the final Manager `v0.1.0` release. Each ZIP contains only
`custom_components/hahapent_test/`. The committed source describes version A; the
builder changes only `manifest.json` and `const.py` for version B. The source
revision goes into catalog provenance, not into the ZIP bytes.

License selection is pending; no license grant or license URL is asserted.
