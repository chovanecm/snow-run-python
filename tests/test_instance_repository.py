# tests/test_instance_repository.py
import io
import json
import os
import sys
import tempfile
import types
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest.mock import patch

keyring_stub = types.SimpleNamespace(
    get_password=lambda *a, **kw: None,
    set_password=lambda *a, **kw: None,
    delete_password=lambda *a, **kw: None,
)
sys.modules.setdefault("keyring", keyring_stub)

from snow_cli.instance_repository import InstanceRepository


class LoadJsonTests(unittest.TestCase):
    def test_returns_empty_dict_when_file_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = InstanceRepository(snow_dir=Path(tmp) / ".snow-run")
            self.assertEqual(repo._load_json(), {})

    def test_returns_data_for_valid_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            snow_dir = Path(tmp) / ".snow-run"
            snow_dir.mkdir()
            (snow_dir / "config.json").write_text(
                '{"default_instance": "dev.service-now.com"}'
            )
            repo = InstanceRepository(snow_dir=snow_dir)
            self.assertEqual(repo._load_json()["default_instance"], "dev.service-now.com")

    def test_returns_empty_dict_and_warns_for_corrupted_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            snow_dir = Path(tmp) / ".snow-run"
            snow_dir.mkdir()
            (snow_dir / "config.json").write_text("{ not valid json }")
            repo = InstanceRepository(snow_dir=snow_dir)
            buf = io.StringIO()
            with redirect_stderr(buf):
                result = repo._load_json()
            self.assertEqual(result, {})
            self.assertIn("Warning", buf.getvalue())


class PathHelperTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = InstanceRepository(snow_dir=Path(self._tmp.name) / ".snow-run")

    def tearDown(self):
        self._tmp.cleanup()

    def test_cookie_file_for_returns_expected_path(self):
        expected = self.repo.snow_dir / "tmp" / "dev.service-now.com" / "cookies.txt"
        self.assertEqual(self.repo.cookie_file_for("dev.service-now.com"), expected)

    def test_tmp_dir_for_returns_expected_path(self):
        expected = self.repo.snow_dir / "tmp" / "dev.service-now.com"
        self.assertEqual(self.repo.tmp_dir_for("dev.service-now.com"), expected)


class InstanceRepositoryCrudTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = InstanceRepository(snow_dir=Path(self._tmp.name) / ".snow-run")

    def tearDown(self):
        self._tmp.cleanup()

    def _write_config(self, data: dict):
        self.repo.snow_dir.mkdir(parents=True, exist_ok=True)
        (self.repo.snow_dir / "config.json").write_text(json.dumps(data))

    def test_save_persists_instance_and_user_to_file(self):
        self.repo.save("dev.service-now.com", "admin", "pass123")
        data = self.repo._load_json()
        self.assertIn("dev.service-now.com", data["instances"])
        self.assertEqual(data["instances"]["dev.service-now.com"]["user"], "admin")

    def test_save_sets_default_when_no_existing_default(self):
        self.repo.save("dev.service-now.com", "admin", "pass123")
        self.assertEqual(self.repo.get_default(), "dev.service-now.com")

    def test_save_does_not_overwrite_existing_default(self):
        self.repo.save("dev1.service-now.com", "admin", "pass1")
        self.repo.save("dev2.service-now.com", "admin", "pass2")
        self.assertEqual(self.repo.get_default(), "dev1.service-now.com")

    def test_save_with_set_default_true_changes_default(self):
        self.repo.save("dev1.service-now.com", "admin", "pass1")
        self.repo.save("dev2.service-now.com", "admin", "pass2", set_default=True)
        self.assertEqual(self.repo.get_default(), "dev2.service-now.com")

    def test_save_stores_password_in_file_when_keyring_unavailable(self):
        failing_keyring = types.SimpleNamespace(
            get_password=lambda *a, **kw: None,
            set_password=lambda *a, **kw: (_ for _ in ()).throw(Exception("no keyring")),
            delete_password=lambda *a, **kw: None,
        )
        with patch.dict(sys.modules, {"keyring": failing_keyring}):
            import importlib
            import snow_cli.instance_repository as ir_mod
            importlib.reload(ir_mod)
            repo = ir_mod.InstanceRepository(snow_dir=Path(self._tmp.name) / ".snow-run-kr")
            repo.save("dev.service-now.com", "admin", "pass123")
            data = repo._load_json()
        importlib.reload(ir_mod)  # restore module state
        self.assertEqual(data["instances"]["dev.service-now.com"].get("password"), "pass123")
        self.assertFalse(data["instances"]["dev.service-now.com"]["keyring"])

    def test_list_all_returns_all_instances(self):
        self.repo.save("dev1.service-now.com", "admin", "pass1")
        self.repo.save("dev2.service-now.com", "admin", "pass2")
        instances = self.repo.list_all()
        self.assertIn("dev1.service-now.com", instances)
        self.assertIn("dev2.service-now.com", instances)

    def test_list_all_returns_empty_dict_when_no_config(self):
        self.assertEqual(self.repo.list_all(), {})

    def test_get_default_returns_none_when_no_config(self):
        self.assertIsNone(self.repo.get_default())

    def test_set_default_changes_default(self):
        self.repo.save("dev1.service-now.com", "admin", "pass1")
        self.repo.save("dev2.service-now.com", "admin", "pass2")
        self.repo.set_default("dev2.service-now.com")
        self.assertEqual(self.repo.get_default(), "dev2.service-now.com")

    def test_set_default_raises_for_unknown_instance(self):
        with self.assertRaises(ValueError):
            self.repo.set_default("unknown.service-now.com")

    def test_remove_deletes_instance(self):
        self.repo.save("dev.service-now.com", "admin", "pass")
        self.repo.remove("dev.service-now.com")
        self.assertNotIn("dev.service-now.com", self.repo.list_all())

    def test_remove_rotates_default_to_next_instance(self):
        self.repo.save("dev1.service-now.com", "admin", "pass1")
        self.repo.save("dev2.service-now.com", "admin", "pass2")
        self.repo.remove("dev1.service-now.com")
        self.assertEqual(self.repo.get_default(), "dev2.service-now.com")

    def test_remove_sets_default_to_none_when_last_instance_removed(self):
        self.repo.save("dev.service-now.com", "admin", "pass")
        self.repo.remove("dev.service-now.com")
        self.assertIsNone(self.repo.get_default())

    def test_remove_is_noop_for_nonexistent_instance(self):
        self.repo.save("dev.service-now.com", "admin", "pass")
        self.repo.remove("other.service-now.com")  # must not raise
        self.assertIn("dev.service-now.com", self.repo.list_all())
