"""Guided first-run forms: no network, no Tk display, no existing config edits."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from guided_config import GuidedConfigError, https_host, save_new_config

from guided_config import make_get_job
from desktop_app import ScheduledApiDesktop


class GuidedApiSetupTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def make(self, **overrides):
        data = {"root_dir": str(self.root), "name": "Morning check",
                "url": "https://example.com/status", "daily_at": "09:00"}
        return make_get_job(**{**data, **overrides})

    def test_first_run_is_get_only_and_explicit(self):
        data = self.make()
        self.assertEqual(data["allow_hosts"], ["example.com"])
        self.assertEqual(data["jobs"][0]["request"]["method"], "GET")
        self.assertEqual(data["jobs"][0]["schedule"], {"type": "daily", "at": "09:00"})
        self.assertEqual(data["jobs"][0]["retries"], 0)
        self.assertTrue(data["jobs"][0]["enabled"])

    def test_https_url_must_not_be_local_ip_or_embed_secret(self):
        for url in ("http://example.com", "https://user:pass@example.com",
                    "https://localhost/api", "https://127.0.0.1",
                    "https://192.168.1.1", "https://example.com:444/api",
                    "https://example.com/#secret", "https://bad host/path"):
            with self.subTest(url=url), self.assertRaises(GuidedConfigError):
                https_host(url)

    def test_invalid_daily_time_and_name_refused(self):
        for time in ("24:00", "9:00", "09:99", "never"):
            with self.subTest(time=time), self.assertRaises(GuidedConfigError):
                self.make(daily_at=time)
        for name in ("", " ", "a\nsecret", "x"*90):
            with self.subTest(name=name), self.assertRaises(GuidedConfigError):
                self.make(name=name)

    def test_existing_json_remains_identical_after_save_attempt(self):
        target = self.root / "existing.json"
        target.write_text("valuable", encoding="utf-8")
        with self.assertRaises(FileExistsError):
            save_new_config(target, self.make())
        self.assertEqual(target.read_text(encoding="utf-8"), "valuable")

    def test_new_json_can_be_loaded_by_real_runner_offline(self):
        from scheduled_api_runner import ScheduledRunner
        target = self.root / "new.json"
        save_new_config(target, self.make())
        raw = json.loads(target.read_text(encoding="utf-8"))
        with patch("scheduled_api_runner.urllib.request.build_opener") as opener:
            runner = ScheduledRunner(raw, dry_run=True)
            runner.run_all_once()
        opener.assert_not_called()
        self.assertFalse((self.root / ".state").exists())

    def test_gui_wizard_saves_without_executing_requests(self):
        app = ScheduledApiDesktop.__new__(ScheduledApiDesktop)
        app._once_running = False
        app.monitor_thread = None
        app.root = None
        app.lang = "ja"
        app.t = lambda ja,en: ja
        app.guide_root = Mock(get=Mock(return_value=str(self.root)))
        app.guide_name = Mock(get=Mock(return_value="Status"))
        app.guide_url = Mock(get=Mock(return_value="https://example.com/"))
        app.guide_at = Mock(get=Mock(return_value="09:00"))
        app.config_path = Mock()
        app.notebook = Mock()
        app.advanced_tab = "advanced"
        app.status = Mock()
        app._load_config = Mock(return_value=True)
        app.preview_revision = "previous"
        out = self.root / "wizard.json"
        with patch("desktop_app.filedialog.asksaveasfilename", return_value=str(out)), \
             patch("desktop_app.ScheduledRunner") as runner:
            app._create_guided_config()
            runner.assert_not_called()
        self.assertTrue(out.is_file())
        self.assertEqual(json.loads(out.read_text(encoding="utf-8"))["jobs"][0]["request"]["method"], "GET")
        self.assertIsNone(app.preview_revision)
        app._load_config.assert_called_once_with(True)


if __name__ == "__main__":
    unittest.main()
