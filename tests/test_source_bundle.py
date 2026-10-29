import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile

spec = importlib.util.spec_from_file_location(
    "sources", Path(__file__).resolve().parents[1] / "scripts/build-source-bundle.py"
)
sources = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sources)


class SourcesTests(unittest.TestCase):
    def test_bundle_verifies_exact_sources_and_excludes_logs(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder) / "input"
            ubuntu = root / "ubuntu/fixture"
            ubuntu.mkdir(parents=True)
            payload = ubuntu / "fixture.tar.gz"
            payload.write_bytes(b"fictional source archive")
            dsc = ubuntu / "fixture.dsc"
            dsc.write_text(
                "Source: fixture\nVersion: 1.0\nChecksums-Sha256:\n "
                + sources.digest(payload)
                + " "
                + str(payload.stat().st_size)
                + " fixture.tar.gz\n"
            )
            python = root / "python.tar.gz"
            python.write_bytes(b"fictional Python source")
            (root / "private.log").write_text("not for distribution")
            data = {
                "ubuntu-source-status.json": [
                    {"package": "fixture", "version": "1.0", "complete": True}
                ],
                "recovery-status.json": {"results": []},
                "python-runtime-source-status.json": {
                    "results": [
                        {
                            "kind": "python",
                            "name": "fixture",
                            "version": "1.0",
                            "state": "complete",
                            "downloads": [
                                {
                                    "file": "python.tar.gz",
                                    "size": python.stat().st_size,
                                    "sha256": sources.digest(python),
                                }
                            ],
                        }
                    ]
                },
                "manifests/bench-packages.json": [{"name": "fixture", "version": "1.0"}],
                "manifests/tools-packages.json": [],
            }
            for name, value in data.items():
                path = root / name
                path.parent.mkdir(exist_ok=True)
                path.write_text(json.dumps(value))
            output = Path(folder) / "release"
            sources.build(root, output)
            with ZipFile(output / "Sources-01.zip") as archive:
                self.assertEqual(
                    set(archive.namelist()),
                    {
                        "ubuntu/fixture/fixture.dsc",
                        "ubuntu/fixture/fixture.tar.gz",
                        "python.tar.gz",
                    },
                )
            payload.write_bytes(b"changed archive")
            with self.assertRaises(ValueError):
                sources.collect(root)
            with self.assertRaises(ValueError):
                sources.dsc_files(root, "fixture", "2.0")

    def test_sources_cannot_escape_through_paths_or_links(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "file").write_text("fictitious")
            (root / "link").symlink_to(root / "file")
            for name in ("../file", str(root / "file"), "link"):
                with self.assertRaises(ValueError):
                    sources.local_file(root, name)
