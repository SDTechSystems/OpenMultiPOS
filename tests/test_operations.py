"""Backup integrity and safe extraction contracts; real restoration is a separate drill."""

import io
import json
import tarfile
import tempfile
import unittest
from pathlib import Path

from open_multi_pos.operations import backup_lock, digest, private_root, safe_extract, verify_bundle


class RecoveryContracts(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(dir=Path.home(), prefix="omp-recovery-test-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def bundle(self):
        bundle = self.root / "copy"
        bundle.mkdir(mode=0o700)
        records = {}
        for name in ("database", "public", "private", "config", "snapshot"):
            path = bundle / name
            path.write_bytes(b"fictional fixture only")
            path.chmod(0o600)
            records[name] = {"name": name, "bytes": path.stat().st_size, "sha256": digest(path)}
        path = bundle / "manifest.json"
        path.write_text(json.dumps({"format": 1, "artifacts": records}))
        path.chmod(0o600)
        return bundle

    def test_verified_bundle_rejects_corruption_or_missing_files(self):
        bundle = self.bundle()
        self.assertEqual(verify_bundle(bundle)["format"], 1)
        (bundle / "database").write_bytes(b"altered")
        with self.assertRaises(ValueError):
            verify_bundle(bundle)
        (bundle / "database").unlink()
        with self.assertRaises(ValueError):
            verify_bundle(bundle)

    def test_bundle_rejects_public_permissions_and_links(self):
        bundle = self.bundle()
        (bundle / "config").chmod(0o644)
        with self.assertRaises(ValueError):
            verify_bundle(bundle)
        (bundle / "config").chmod(0o600)
        link = self.root / "alias"
        link.symlink_to(bundle)
        with self.assertRaises(ValueError):
            verify_bundle(link)

    def test_bundle_rejects_manifest_path_escape(self):
        bundle = self.bundle()
        path = bundle / "manifest.json"
        manifest = json.loads(path.read_text())
        manifest["artifacts"]["config"]["name"] = "../config"
        path.write_text(json.dumps(manifest))
        with self.assertRaises(ValueError):
            verify_bundle(bundle)

    def archive(self, name, *, symlink=False):
        path = self.root / "archive.tar"
        with tarfile.open(path, "w") as tar:
            member = tarfile.TarInfo(name)
            if symlink:
                member.type, member.linkname = tarfile.SYMTYPE, "/etc/passwd"
            else:
                member.size = 7
            tar.addfile(member, None if symlink else io.BytesIO(b"fixture"))
        return path

    def test_native_relative_and_absolute_prefix_archives(self):
        for prefix in ("", "home/test/bench/sites/"):
            target = self.root / ("restored" + str(len(prefix)))
            archive = self.archive(prefix + "demo.localhost/private/files/fixture.txt")
            safe_extract(archive, target, "private", "demo.localhost")
            self.assertEqual((target / "private/files/fixture.txt").read_bytes(), b"fixture")

    def test_archive_rejects_traversal_links_and_wrong_site(self):
        for name, link in (
            ("../demo.localhost/private/files/fixture.txt", False),
            ("demo.localhost/private/files/fixture.txt", True),
            ("other.localhost/private/files/fixture.txt", False),
        ):
            with self.subTest(name=name, link=link), self.assertRaises(ValueError):
                safe_extract(
                    self.archive(name, symlink=link),
                    self.root / "restored",
                    "private",
                    "demo.localhost",
                )

    def test_private_path_and_concurrent_backup_guard(self):
        root = private_root(self.root)
        with backup_lock(root), self.assertRaises(BlockingIOError), backup_lock(root):
            pass
        with self.assertRaises(ValueError):
            private_root(Path("/tmp/omp-public-copy"))
