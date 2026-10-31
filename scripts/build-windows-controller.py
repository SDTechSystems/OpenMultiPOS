"""Build the Windows server controller candidate without an image or private data."""

import argparse
import hashlib
import json
import shutil
import subprocess
from pathlib import Path


def build(destination, manual):
    repo = Path(__file__).resolve().parents[1]
    destination.mkdir(parents=True, exist_ok=False)
    executable = destination / "OpenMultiPOS-Server-Control.exe"
    subprocess.run(
        [
            "mcs",
            "-target:winexe",
            "-platform:x64",
            "-sdk:4.8",
            "-optimize+",
            "-r:System.Windows.Forms",
            "-r:System.Drawing",
            "-r:System.Web.Extensions",
            "-out:" + str(executable),
            str(repo / "windows/Server.cs"),
        ],
        check=True,
    )
    subprocess.run(["mono", str(executable), "--self-test"], check=True)
    shutil.copyfile(manual, destination / "Manual.html")
    shutil.copyfile(repo / "LICENSE", destination / "LICENSE")
    source = destination / "source"
    source.mkdir()
    for path in (repo / "windows/Server.cs", repo / "server/first_run.py", Path(__file__)):
        shutil.copyfile(path, source / path.name)
    info = {
        "version": "0.1.0",
        "scope": "server controller candidate; clean server image not included",
        "signed": False,
        "windows_gui_acceptance": "pending",
        "protocol": 1,
    }
    (destination / "build-info.json").write_text(json.dumps(info, indent=2) + "\n")
    (destination / "SHA256SUMS.txt").write_text(
        "\n".join(
            hashlib.sha256(path.read_bytes()).hexdigest() + "  " + path.name
            for path in (executable, destination / "Manual.html", destination / "LICENSE")
        )
        + "\n"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--manual", required=True, type=Path)
    options = parser.parse_args()
    build(options.output, options.manual)
