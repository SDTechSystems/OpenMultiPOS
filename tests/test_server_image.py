import json
import tempfile
import unittest
from pathlib import Path

from server.image_contract import BENCH, validate


class ImageContractTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        (self.root / "etc").mkdir()
        (self.root / "etc/openmultipos-build-environment").write_text("clean build")
        (self.root / "etc/shadow").write_text(
            "root:!:0:0:99999:7:::\nopenmultipos:!:0:0:99999:7:::\n"
        )
        self.sites = self.root / BENCH / "sites"
        self.sites.mkdir(parents=True)
        self.config = self.sites / "common_site_config.json"
        self.config.write_text('{"redis_cache":"redis://127.0.0.1:13000"}')

    def test_clean_runtime_has_no_site_or_reusable_credentials(self):
        self.assertEqual(validate(self.root)["site_count"], 0)
        (self.sites / "omp.localhost").mkdir()
        with self.assertRaisesRegex(ValueError, "sitio"):
            validate(self.root)

    def test_reusable_secrets_and_config_links_are_rejected(self):
        for config in (
            {"db_password": "fictional"},
            {"redis_cache": "redis://:fictional@localhost"},
        ):
            self.config.write_text(json.dumps(config))
            with self.assertRaises(ValueError):
                validate(self.root)
        self.config.unlink()
        self.config.symlink_to(self.root / "etc/shadow")
        with self.assertRaisesRegex(ValueError, "enlace"):
            validate(self.root)

    def test_application_schema_and_linux_password_are_rejected(self):
        schema = self.root / "var/lib/mysql/fictional_application"
        schema.mkdir(parents=True)
        with self.assertRaisesRegex(ValueError, "base de datos"):
            validate(self.root)
        schema.rmdir()
        (self.root / "etc/shadow").write_text("root:$fictional-hash:0:0:99999:7:::\n")
        with self.assertRaisesRegex(ValueError, "contraseña"):
            validate(self.root)

    def test_private_installation_and_retained_attempts_are_rejected(self):
        for relative in (
            "var/lib/openmultipos",
            str(BENCH.parent / "incomplete"),
            str(BENCH.parent / "redis-queue"),
            "root/.ssh",
        ):
            folder = self.root / relative
            folder.mkdir(parents=True)
            marker = folder / "fictional-private-state"
            marker.write_text("do not distribute")
            with self.assertRaises(ValueError):
                validate(self.root)
            marker.unlink()
