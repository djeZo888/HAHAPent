"""Exercise the installed App engine against local artifact bytes inside its image."""

from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

from hahapent.engine import Manager


class SyntheticHA:
    def core_version(self):
        return "2026.9.1"

    def is_core_domain(self, domain):
        return False

    def config_entries(self, domain):
        return []

    def domain_status(self, domain):
        return {"configured": False, "loaded": False, "loaded_version": None}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixtures", type=Path, default=Path("/fixtures"))
    arguments = parser.parse_args()
    catalog = json.loads((arguments.fixtures / "test-catalog.json").read_text())
    by_url = {
        module["artifact"]["url"]: (
            arguments.fixtures / module["artifact"]["url"].rsplit("/", 1)[1]
        ).read_bytes()
        for module in catalog["modules"]
    }

    def download(url, max_bytes):
        content = by_url[url]
        assert len(content) <= max_bytes
        return content

    with tempfile.TemporaryDirectory(prefix="hahapent-runtime-engine-") as temporary:
        root = Path(temporary).resolve()
        config = root / "homeassistant"
        config.mkdir()
        unrelated = config / "configuration.yaml"
        unrelated.write_text("# synthetic unrelated configuration\n")
        built_in = {
            **catalog,
            "source": {**catalog["source"], "id": "hahapent"},
            "modules": [],
        }

        def manager():
            return Manager(root / "data", config, SyntheticHA(), download, built_in, catalog)

        engine = manager()
        engine.set_test_mode(True)
        target = config / "custom_components/hahapent_test"
        engine.install("hahapent-test", "hahapent-test", "0.1.0")
        assert json.loads((target / "manifest.json").read_text())["version"] == "0.1.0"
        engine.install("hahapent-test", "hahapent-test", "0.2.0")
        assert json.loads((target / "manifest.json").read_text())["version"] == "0.2.0"
        engine = manager()
        assert engine.status()["installed"][0]["version"] == "0.2.0"
        engine.rollback("hahapent_test")
        assert json.loads((target / "manifest.json").read_text())["version"] == "0.1.0"
        engine.remove("hahapent_test", confirmed=True)
        assert not target.exists()
        assert unrelated.read_text() == "# synthetic unrelated configuration\n"
        assert manager().status()["installed"] == []
        print(
            json.dumps(
                {"status": "PASS", "runtime_engine_lifecycle": "PASS", "persistence": "PASS"}
            )
        )


if __name__ == "__main__":
    main()
