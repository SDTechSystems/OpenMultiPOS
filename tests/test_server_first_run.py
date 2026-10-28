import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from server import first_run


class FirstRunTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.home = self.root / "account"
        self.state_path = self.root / "state"
        self.state_path.mkdir()
        self.addCleanup(patch.stopall)
        patch.object(first_run, "STATE", self.state_path).start()
        patch.object(first_run, "configurations", return_value={}).start()
        self.app = patch.object(first_run, "app").start()
        self.run = patch.object(first_run, "run").start()

    def test_installed_replay_never_resets_a_password_or_recreates_site(self):
        first_run.setup(self.home, {"installed": True}, "")
        self.app.assert_not_called()
        self.run.assert_not_called()

    def test_an_existing_unclaimed_site_is_preserved(self):
        site = self.home / ".local/share/openmultipos/bench/sites" / first_run.SITE
        site.mkdir(parents=True)
        with self.assertRaisesRegex(ValueError, "sin registro"):
            first_run.setup(self.home, {}, "Fictional-password-only")
        self.assertTrue(site.is_dir())
        self.run.assert_not_called()
        self.app.assert_not_called()

    def test_intent_is_private_and_survives_failure_without_claiming_success(self):
        self.app.side_effect = RuntimeError("fictional interrupted preparation")
        state = {}
        with self.assertRaises(RuntimeError):
            first_run.setup(self.home, state, "Fictional-password-only")
        saved = json.loads((self.state_path / "bootstrap.json").read_text())
        self.assertEqual(saved["db_name"], state["db_name"])
        self.assertNotIn("installed", saved)
        self.assertNotIn("Fictional-password-only", json.dumps(saved))
        self.assertEqual((self.state_path / "bootstrap.json").stat().st_mode & 0o777, 0o600)

    def test_native_install_failure_removes_temporary_database_account(self):
        self.app.side_effect = [None, RuntimeError("fictional native failure")]
        state = {}
        with self.assertRaises(RuntimeError):
            first_run.setup(self.home, state, "Fictional-password-only")
        self.assertNotIn("installed", state)
        self.assertTrue(
            any("DROP USER" in call.kwargs.get("input", "") for call in self.run.call_args_list)
        )

    def test_recovery_rotation_is_durable_if_the_new_install_fails(self):
        state = {"db_name": "_omp_" + "a" * 24, "db_password": "fictional"}
        previous = dict(state)
        self.app.side_effect = [None, None, RuntimeError("fictional new install failure")]
        with self.assertRaises(RuntimeError):
            first_run.setup(self.home, state, "Fictional-password-only", recover=True)
        saved = json.loads((self.state_path / "bootstrap.json").read_text())
        self.assertEqual(saved["previous"], [previous])
        self.assertNotEqual(saved["db_name"], previous["db_name"])
        self.assertNotIn("retiring", saved)
        self.assertNotIn("installed", saved)

    def test_bootstrap_passwords_are_input_only_and_temporary_account_is_removed(self):
        state = {}
        first_run.setup(self.home, state, "Fictional-password-only")
        self.assertTrue(state["installed"])
        native = self.app.call_args_list[1]
        self.assertEqual(native.args[2]["admin_password"], "Fictional-password-only")
        for call in self.run.call_args_list:
            self.assertNotIn("Fictional-password-only", str(call.args))
        sql = [call.kwargs.get("input", "") for call in self.run.call_args_list]
        self.assertTrue(any("DROP USER" in command for command in sql))
        self.assertNotIn("admin_password", (self.state_path / "bootstrap.json").read_text())


class RuntimeConfigurationTests(unittest.TestCase):
    def test_internal_services_use_private_sockets_and_proxy_binds_loopback(self):
        configs = first_run.configurations(Path("/srv/account"))
        self.assertIn("skip-networking", configs["/etc/mysql/mariadb.conf.d/99-openmultipos.cnf"])
        nginx = configs["/etc/nginx/nginx.conf"]
        self.assertIn("listen 127.0.0.1:8089", nginx)
        self.assertNotIn("listen 0.0.0.0", nginx)
        for name in ("cache", "queue"):
            unit = configs[f"/etc/systemd/system/omp-{name}.service"]
            self.assertIn("--port 0 --unixsocket", unit)
            self.assertIn("RuntimeDirectoryMode=0700", unit)
        self.assertIn("--appendonly yes", configs["/etc/systemd/system/omp-queue.service"])
        self.assertIn("socketio_uds", first_run.PREPARE)
