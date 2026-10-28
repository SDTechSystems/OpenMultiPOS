import tempfile
import unittest
from pathlib import Path

from server.seal_image import remove, replace


class SealTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)

    def test_cleanup_does_not_follow_links(self):
        value = self.root / "preserve"
        value.mkdir()
        (value / "file").write_text("fictional retained content")
        (self.root / "cache").symlink_to(value, target_is_directory=True)
        remove(self.root, "cache")
        self.assertTrue((value / "file").is_file())
        (self.root / "parent").symlink_to(value, target_is_directory=True)
        with self.assertRaises(ValueError):
            remove(self.root, "parent/file")
        for name in ("../preserve", str(value)):
            with self.assertRaises(ValueError):
                remove(self.root, name)

    def test_identity_replacement_does_not_write_symlink_target(self):
        original = self.root / "original"
        original.write_text("fictional identity")
        destination = self.root / "machine-id"
        destination.symlink_to(original)
        replace(destination, "")
        self.assertEqual(original.read_text(), "fictional identity")
        self.assertFalse(destination.is_symlink())
        self.assertEqual(destination.read_text(), "")
