"""Conservative publication guard. Never print matched values or file contents.

This catches common mistakes; manual privacy review remains mandatory. It cannot
identify every real name, confidential SKU, price or customer in arbitrary text.
"""

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import PurePosixPath

PRIVATE_DIRS = {
    "private",
    "local-data",
    "business-data",
    "attachments",
    "exports",
    "backups",
    "recovery",
    "screenshots",
    "photos",
    "test-results",
}
PRIVATE_SUFFIXES = {
    ".pem",
    ".key",
    ".pfx",
    ".p12",
    ".sqlite",
    ".sqlite3",
    ".db",
    ".dump",
    ".sql",
    ".gz",
    ".tgz",
    ".tar",
    ".7z",
    ".bak",
    ".csv",
    ".xlsx",
    ".xls",
    ".pdf",
    ".png",
    ".jpg",
    ".jpeg",
    ".pbm",
    ".zip",
    ".rar",
    ".log",
}
PATTERNS = {
    "private-key": re.compile(r"-----BEGIN (?:[A-Z ]+ )?PRIVATE KEY-----"),
    "credential-token": re.compile(
        r"\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,}|AKIA[A-Z0-9]{16}|sk_live_[A-Za-z0-9]{16,})\b"
    ),
    "local-user-path": re.compile(
        r"[A-Za-z]:[\\/]+Users[\\/]+[A-Za-z0-9_~.-]+|/mnt/[a-z]/Users/[A-Za-z0-9_~.-]+|/home/[A-Za-z0-9_.-]+/"
    ),
}
EMAIL = re.compile(r"\b[A-Z0-9._%+-]+@([A-Z0-9.-]+\.[A-Z]{2,})\b", re.IGNORECASE)


MANIFEST = "open_multi_pos/public/manual/manifest.json"
MANUAL_PREFIX = "open_multi_pos/public/manual/screenshots/"
MANUAL_SECTIONS = {
    "product-form",
    "receipt-preview",
    "returns",
    "imports",
    "costs",
    "warranties",
    "valuation",
    "home",
    "sales",
    "inventory",
    "purchases",
    "finances",
    "customers",
    "businesses",
    "team",
    "settings",
    "help",
}


def reviewed_images(data: bytes) -> dict[str, str]:
    """Exact generated images only; this manifest still requires visual privacy review."""
    try:
        manifest = json.loads(data)
        if (
            manifest.get("source") != "scripts/workspace-smoke.cjs"
            or manifest.get("data") != "fictional-only"
        ):
            return {}
        return {
            path: sha
            for path, sha in manifest["images"].items()
            if path in {MANUAL_PREFIX + name + ".png" for name in MANUAL_SECTIONS}
            and isinstance(sha, str)
            and re.fullmatch(r"[a-f0-9]{64}", sha)
        }
    except (ValueError, KeyError, TypeError, AttributeError):
        return {}


def violations(path: str, data: bytes, reviewed: dict[str, str] | None = None) -> list[str]:
    if (
        reviewed
        and path in reviewed
        and path in {MANUAL_PREFIX + name + ".png" for name in MANUAL_SECTIONS}
        and data.startswith(b"\x89PNG\r\n\x1a\n")
        and hashlib.sha256(data).hexdigest() == reviewed[path]
    ):
        return []
    file = PurePosixPath(path)
    issues = []
    if (
        PRIVATE_DIRS.intersection(part.lower() for part in file.parts)
        or file.suffix.lower() in PRIVATE_SUFFIXES
        or file.name.lower().startswith(".env")
        and not file.name.lower().endswith(".example")
        or "project_brief" in file.name.lower()
        or file.name.lower() == "connection.txt"
    ):
        issues.append("private-file-type-or-location")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return issues + ["unreviewed-binary"]
    for category, pattern in PATTERNS.items():
        if pattern.search(text):
            issues.append(category)
    for match in EMAIL.finditer(text):
        domain = match[1].lower()
        if not (
            domain in {"example.com", "example.net", "example.org", "users.noreply.github.com"}
            or domain.endswith((".invalid", ".test", ".example"))
        ):
            issues.append("non-example-email")
            break
    return issues


def main():
    parser = argparse.ArgumentParser(description="Check tracked source before publication")
    parser.add_argument("--staged", action="store_true", help="Inspect the complete Git index")
    args = parser.parse_args()
    command = (
        ["git", "ls-files", "-z"]
        if args.staged
        else ["git", "ls-tree", "-r", "--name-only", "-z", "HEAD"]
    )
    names = subprocess.check_output(command).decode().split("\0")

    def read(name):
        return subprocess.check_output(
            ["git", "show", f":{name}" if args.staged else f"HEAD:{name}"]
        )

    reviewed = reviewed_images(read(MANIFEST)) if MANIFEST in names else {}
    failures = []
    count = 0
    for name in filter(None, names):
        count += 1
        if args.staged:
            data = subprocess.check_output(["git", "show", f":{name}"])
        else:
            data = subprocess.check_output(["git", "show", f"HEAD:{name}"])
        issues = violations(name, data, reviewed)
        if issues:
            failures.append((name, issues))
    if failures:
        for name, issues in failures:
            print(f"BLOCKED {name}: {', '.join(issues)}")
        print(
            "Do not publish. Review locally; never paste sensitive values into an issue or CI log."
        )
        raise SystemExit(1)
    print(f"PASS: {count} tracked files checked; no blocked private assets or recognized patterns.")


if __name__ == "__main__":
    main()
