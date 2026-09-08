# Third-party runtime notices

HAHAPent's own license selection is pending. This statement does not replace or
change the licenses of bundled dependencies. Their installed wheel metadata and
license files remain in the image, along with the official Python/Debian image's
existing notices. No license field is invented for HAHAPent.

| Distribution | Pinned version | Upstream license |
| --- | --- | --- |
| websocket-client | 1.9.0 | Apache-2.0 |
| jsonschema | 4.25.1 | MIT |
| attrs | 26.1.0 | MIT |
| jsonschema-specifications | 2025.9.1 | MIT |
| referencing | 0.36.2 | MIT |
| rpds-py | 0.27.1 | MIT |
| typing-extensions | 4.16.0 | PSF-2.0 |

Versions, wheel digests, and license identifiers were checked against the
version-specific [PyPI JSON metadata](https://docs.pypi.org/api/json/) on
2026-09-08. The runtime lock uses the Python 3.13 manylinux x86_64 wheel for rpds-py.
The base is the [official Python image](https://hub.docker.com/_/python), derived
from Debian Bookworm; Python and operating-system components retain their own
licenses and notices.
