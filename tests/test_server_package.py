import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "server_package", Path(__file__).resolve().parents[1] / "scripts/build-windows-server.py"
)
package = importlib.util.module_from_spec(spec)
spec.loader.exec_module(package)


class PackageTests(unittest.TestCase):
    def test_image_must_match_clean_audit(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            image = root / "fixture.wsl"
            manifest = root / "manifest.json"
            audit = root / "audit.json"
            image.write_bytes(b"fictional clean image")
            checksum = package.digest(image)
            metadata = {"schema": 1, "sha256": checksum, "source_revision": "a" * 40}
            proof = {
                "sha256": checksum,
                "source_revision": "a" * 40,
                "sites": 0,
                "application_schemas": 0,
                "reusable_identity": False,
            }
            manifest.write_text(json.dumps(metadata))
            audit.write_text(json.dumps(proof))
            self.assertEqual(package.check_image(image, manifest, audit), metadata)
            for key, bad in (
                ("sites", 1),
                ("application_schemas", 1),
                ("reusable_identity", True),
                ("source_revision", "b" * 40),
            ):
                audit.write_text(json.dumps({**proof, key: bad}))
                with self.assertRaises(ValueError):
                    package.check_image(image, manifest, audit)
            for revision in (None, "", "a" * 39, "z" * 40):
                manifest.write_text(json.dumps({**metadata, "source_revision": revision}))
                audit.write_text(json.dumps({**proof, "source_revision": revision}))
                with self.assertRaises(ValueError):
                    package.check_image(image, manifest, audit)
            manifest.write_text(json.dumps(metadata))
            audit.write_text(json.dumps(proof))
            image.write_bytes(b"changed image")
            with self.assertRaises(ValueError):
                package.check_image(image, manifest, audit)
