import io
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from server.first_run import RETIRE, setup


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.home = Path(self.directory.name)
        self.name = "_omp_" + "a" * 24
        self.site = self.home / ".local/share/openmultipos/bench/sites/omp.localhost"
        self.site.mkdir(parents=True)
        self.payload = dict(
            db_name=self.name,
            db_password="fictional",
            root_password="fictional",
            socket="/fictional.sock",
        )
        (self.site / "site_config.json").write_text(json.dumps(self.payload))
        self.archive = self.home / ".local/share/openmultipos/incomplete" / self.name
        self.tables = []
        self.count = 0
        self.queries = []

    def retire(self):
        fixture = self

        class Cursor:
            def execute(self, sql, args=None):
                fixture.queries.append(sql)

            def fetchall(self):
                return [(name,) for name in fixture.tables]

            def fetchone(self):
                return (fixture.count,)

        connection = types.SimpleNamespace(cursor=lambda: Cursor(), close=lambda: None)
        with (
            patch.object(Path, "home", return_value=self.home),
            patch.object(sys, "stdin", io.StringIO(json.dumps(self.payload))),
            patch.dict(
                sys.modules, MySQLdb=types.SimpleNamespace(connect=lambda **kwargs: connection)
            ),
        ):
            exec(compile(RETIRE, "<bootstrap recovery>", "exec"), {})

    def test_owned_partial_site_is_preserved_and_retry_is_idempotent(self):
        self.retire()
        self.assertFalse(self.site.exists())
        self.assertTrue((self.archive / "site_config.json").is_file())
        self.retire()
        self.assertTrue(all(query.startswith("SELECT") for query in self.queries))

    def test_personal_accounts_and_business_records_are_refused(self):
        for table in ("tabUser", "tabCompany", "tabSales Invoice", "tabItem"):
            self.tables, self.count = [table], 1
            with self.assertRaises(ValueError):
                self.retire()
            self.assertTrue(self.site.is_dir())
            self.assertFalse(self.archive.exists())

    def test_foreign_config_uploads_and_symlinks_are_refused(self):
        self.payload["db_password"] = "different"
        with self.assertRaises(ValueError):
            self.retire()
        self.payload["db_password"] = "fictional"
        files = self.site / "private/files"
        files.mkdir(parents=True)
        (files / "fictional.txt").write_text("preserve this file")
        with self.assertRaises(ValueError):
            self.retire()
        self.assertTrue((files / "fictional.txt").is_file())

    def test_linked_site_is_not_moved(self):
        saved = self.home / "saved"
        self.site.rename(saved)
        self.site.symlink_to(saved, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "enlaces"):
            self.retire()
        self.assertTrue((saved / "site_config.json").is_file())

    def test_completed_site_cannot_enter_recovery(self):
        with self.assertRaisesRegex(ValueError, "ya está instalado"):
            setup(self.home, {"installed": True}, "", recover=True)
