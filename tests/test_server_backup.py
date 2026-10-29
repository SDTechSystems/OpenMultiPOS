import fcntl
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from server import first_run


class ServerBackupTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        self.addCleanup(patch.stopall)
        patch.object(first_run, "STATE", self.root).start()
        self.run = patch.object(first_run, "run").start()
        self.app = patch.object(first_run, "app").start()
        self.active = patch.object(first_run.subprocess, "run").start()
        self.active.return_value.returncode = 3

    def test_refuses_uninstalled_active_and_other_controller(self):
        with self.assertRaises(ValueError):
            first_run.backup_site(self.root, {})
        self.active.return_value.returncode = 0
        with self.assertRaises(ValueError):
            first_run.backup_site(self.root, {"installed": True})
        self.run.assert_not_called()
        with (self.root / "server.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with self.assertRaises(BlockingIOError):
                first_run.backup_site(self.root, {"installed": True})
        self.app.assert_not_called()

    def test_drill_credentials_stay_on_stdin_and_cleanup_runs_on_failure(self):
        self.app.side_effect = RuntimeError("fictional drill failure")
        with self.assertRaises(RuntimeError):
            first_run.backup_site(self.root, {"installed": True}, check=True)
        payload = self.app.call_args.args[2]
        self.assertTrue(payload["check"])
        self.assertNotIn(payload["password"], repr([c.args for c in self.run.call_args_list]))
        sql = [c.kwargs.get("input", "") for c in self.run.call_args_list]
        self.assertIn("CREATE USER", sql[1])
        self.assertTrue(any("DROP USER" in statement for statement in sql))
        self.assertEqual(self.run.call_args.args[:2], ("systemctl", "stop"))
        compile(first_run.BACKUP, "<backup>", "exec")

    def test_backup_needs_no_privileged_database_account(self):
        first_run.backup_site(self.root, {"installed": True})
        self.assertFalse(self.app.call_args.args[2]["check"])
        self.assertFalse(any(c.args[0] == "mariadb" for c in self.run.call_args_list))
        self.assertEqual(self.run.call_args.args[:2], ("systemctl", "stop"))
