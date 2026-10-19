import importlib.util
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "public_guard", Path(__file__).resolve().parents[1] / "scripts/check-public-files.py"
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class PublicationPolicyTests(unittest.TestCase):
    def test_private_assets_are_blocked(self):
        for name in (
            "customers.csv",
            "photos/image.jpg",
            "private/config.json",
            "backup.sqlite3",
            "x.pem",
            ".env",
            "PROJECT_BRIEF.md",
        ):
            with self.subTest(name=name):
                self.assertTrue(module.violations(name, b"fictional"))

    def test_public_fictional_source_is_allowed(self):
        self.assertEqual(module.violations("config.env.example", b"contact@example.invalid"), [])
        self.assertEqual(module.violations("fixture.json", b'{"brand":"Demo","price":100}'), [])

    def test_content_patterns_are_blocked_without_real_secrets(self):
        examples = [
            "ghp_" + "A" * 36,
            "C:" + "/Users/" + "private-user/file",
            "person" + "@" + "provider.com",
        ]
        for text in examples:
            with self.subTest(kind="synthetic"):
                self.assertTrue(module.violations("fixture.txt", text.encode()))

    def test_opaque_binary_is_blocked(self):
        self.assertIn("unreviewed-binary", module.violations("asset.bin", bytes([255, 254])))
