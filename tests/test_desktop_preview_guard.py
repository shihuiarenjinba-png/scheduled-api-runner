"""Tk-independent tests for user-confirmed API preview transitions."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from desktop_app import ScheduledApiDesktop


class PreviewGuardTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "jobs.json"
        self.config = {"allow_hosts": ["example.com"], "jobs": [{
            "name": "export", "request": {"method": "POST", "url": "https://example.com/api"},
            "schedule": {"type": "interval", "seconds": 60},
        }]}
        self.path.write_text(json.dumps(self.config), encoding="utf-8")
        self.app = ScheduledApiDesktop.__new__(ScheduledApiDesktop)
        self.app.lang = "ja"
        self.app.config_path = Mock()
        self.app.config_path.get.return_value = str(self.path)
        self.app.config = dict(self.config)
        self.app.preview_revision = None
        self.app.root = None
        self.app._finish = Mock()

    def test_preview_revision_independent_of_json_key_order(self):
        rev = self.app._revision(self.config)
        reverse = {"jobs": self.config["jobs"], "allow_hosts": ["example.com"]}
        self.assertEqual(rev, self.app._revision(reverse))

    def test_file_change_invalidates_preview(self):
        rev = self.app._revision(self.config)
        self.app._preview_complete(True, "OK", "completed", rev)
        self.assertEqual(self.app.preview_revision, rev)
        self.assertTrue(self.app._preview_ready())
        self.config["jobs"][0]["request"]["url"] = "https://example.com/changed"
        self.path.write_text(json.dumps(self.config), encoding="utf-8")
        self.app.config = dict(self.config)
        with patch("desktop_app.messagebox.showwarning") as warn:
            self.assertFalse(self.app._preview_ready())
            warn.assert_called_once()

    def test_change_during_preview_must_not_approve(self):
        rev = self.app._revision(self.config)
        self.config["jobs"][0]["request"]["method"] = "DELETE"
        self.path.write_text(json.dumps(self.config), encoding="utf-8")
        self.app._preview_complete(True, "OK", "complete", rev)
        self.assertIsNone(self.app.preview_revision)

    def test_failed_preview_cannot_grant_live_execution(self):
        self.app._preview_complete(False, "network error", "failed", "revision")
        self.assertIsNone(self.app.preview_revision)
        self.app._finish.assert_called_once()

    def test_other_config_path_invalidates_preview(self):
        rev = self.app._revision(self.config)
        self.app.preview_revision = rev
        second = self.path.with_name("other.json")
        second.write_text(json.dumps(self.config), encoding="utf-8")
        self.app.config_path.get.return_value = str(second)
        with patch("desktop_app.messagebox.showwarning"):
            self.assertFalse(self.app._preview_ready())

    def test_bundled_example_is_disabled_before_explicit_user_setup(self):
        root = Path(__file__).resolve().parents[1]
        build = (root / "build_windows.ps1").read_text(encoding="utf-8")
        self.assertIn('--add-data "jobs.example.json;."', build)
        sample = json.loads((root / "jobs.example.json").read_text(encoding="utf-8"))
        self.assertTrue(all(job.get("enabled") is False for job in sample["jobs"]))


if __name__ == "__main__":
    unittest.main()
