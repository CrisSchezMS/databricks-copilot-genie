import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch


SPEC = importlib.util.spec_from_file_location("workspace", Path(__file__).parents[1] / "tools" / "workspace.py")
workspace = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(workspace)


class FakeAPI:
    def __init__(self):
        self.objects = {}
        self.writes = []

    def user(self):
        return "demo@example.com"

    def read(self, remote):
        return self.objects.get(remote)

    def write(self, remote, content, language, overwrite):
        if not overwrite and remote in self.objects:
            raise RuntimeError("exists")
        self.objects[remote] = content
        self.writes.append((remote, language, overwrite))


class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.api = FakeAPI()
        self.name = "sql/example"
        self.remote = workspace.remote_path(self.api, self.name)
        self.first = b"-- Databricks notebook source\nSELECT 1\n"
        self.second = b"-- Databricks notebook source\nSELECT 2\n"

    def test_create_and_update_require_matching_revision(self):
        first_hash = workspace.put(self.api, self.remote, self.name, self.first, "absent")
        with self.assertRaises(RuntimeError):
            workspace.put(self.api, self.remote, self.name, self.second, "absent")
        self.api.objects[self.remote] = b"another remote editor"
        with self.assertRaises(RuntimeError):
            workspace.put(self.api, self.remote, self.name, self.second, first_hash)
        self.assertEqual(self.api.objects[self.remote], b"another remote editor")
        self.api.objects[self.remote] = self.first
        self.assertEqual(workspace.put(self.api, self.remote, self.name, self.second, first_hash), workspace.digest(self.second))

    def test_name_and_header_validation(self):
        for name in ("sql/../escape", "/sql/a", "other/a", "sql/a.py"):
            with self.assertRaises(ValueError):
                workspace.remote_path(self.api, name)
        with self.assertRaises(ValueError):
            workspace.put(self.api, self.remote, self.name, b"SELECT 1", "absent")
        self.assertFalse(self.api.writes)

    def test_export_requires_approved_current_revision_and_clean_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "databricks" / "sql").mkdir(parents=True)
            self.api.objects[self.remote] = self.first
            with self.assertRaises(RuntimeError):
                workspace.export_approved(self.api, self.remote, self.name, "wrong", root)
            clean = subprocess.CompletedProcess([], 0, stdout="", stderr="")
            dirty = subprocess.CompletedProcess([], 0, stdout=" M databricks/sql/example.sql\n", stderr="")
            with patch.object(workspace.subprocess, "run", return_value=dirty):
                with self.assertRaises(RuntimeError):
                    workspace.export_approved(self.api, self.remote, self.name, workspace.digest(self.first), root)
            with patch.object(workspace.subprocess, "run", return_value=clean):
                target = workspace.export_approved(self.api, self.remote, self.name, workspace.digest(self.first), root)
            self.assertEqual((root / target).read_bytes(), self.first)

    def test_sql_failure_is_not_reported_as_success(self):
        class Failed:
            def request(self, method, path, body=None):
                return {"statement_id": "id", "status": {"state": "FAILED"}}

        with self.assertRaises(RuntimeError):
            workspace.run_sql(Failed(), "123abc", "SELECT 1")


if __name__ == "__main__":
    unittest.main()
