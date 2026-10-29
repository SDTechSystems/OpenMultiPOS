import importlib.util
import subprocess
import tempfile
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "windows_package", Path(__file__).resolve().parents[1] / "scripts/build-windows-client.py"
)
package = importlib.util.module_from_spec(spec)
spec.loader.exec_module(package)


class WindowsPackageSourcesTests(unittest.TestCase):
    def test_untracked_connection_and_symlink_cannot_enter_public_sources(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            subprocess.run(["git", "init", "--quiet", str(root)], check=True)
            windows = root / "windows"
            windows.mkdir()
            source = windows / "Client.cs"
            source.write_text("// fictional public source\n")
            private = windows / "connection.txt"
            private.write_text("https://private-server.example.invalid/omp\n")
            subprocess.run(["git", "add", "windows/Client.cs"], cwd=root, check=True)
            self.assertEqual(list(package.public_windows_sources(root)), [source])
            source.unlink()
            source.symlink_to(private)
            with self.assertRaises(ValueError):
                list(package.public_windows_sources(root))
