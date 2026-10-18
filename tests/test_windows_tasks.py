"""Offline tests for opt-in SHA-pinned Windows daily API scheduling."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, Mock

from guided_config import make_get_job, add_daily_csv_output
from scheduler_windows_tasks import (
    WindowsTaskError, build_register_command, register_task, run_locked_config,
    task_name, unregister_task, validate_dated_get_config,
)


class WindowsDailyApiTaskTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.config = add_daily_csv_output(
            make_get_job(root_dir=str(self.root), name="Daily sales",
                         url="https://example.com/sales", daily_at="09:00"),
            path="daily.csv", fields="sales = data.sales", date_path="data.date")
        self.file = self.root / "daily.json"
        self.file.write_text(json.dumps(self.config), encoding="utf-8")
        self.checksum = hashlib.sha256(self.file.read_bytes()).hexdigest()

    def test_get_csv_daily_job_is_only_accepted_auto_schedule(self):
        self.assertEqual(validate_dated_get_config(self.config), "09:00")
        for method in ("POST", "PATCH", "PUT", "DELETE"):
            altered = json.loads(json.dumps(self.config))
            altered["jobs"][0]["request"]["method"] = method
            with self.subTest(method=method), self.assertRaises(WindowsTaskError):
                validate_dated_get_config(altered)
        multi = json.loads(json.dumps(self.config))
        multi["jobs"].append(dict(multi["jobs"][0]))
        with self.assertRaises(WindowsTaskError):
            validate_dated_get_config(multi)

    def test_register_task_uses_create_without_force_and_pins_sha(self):
        with patch("scheduler_windows_tasks._is_windows", return_value=True), \
             patch("scheduler_windows_tasks._command", return_value="app.exe --run-locked"), \
             patch("scheduler_windows_tasks._execute") as execute:
            result = register_task(self.file, expected_sha256=self.checksum)
        self.assertEqual(result, task_name(self.file))
        args = execute.call_args.args[0]
        self.assertIn("/Create", args)
        self.assertIn("/IT", args)
        self.assertIn("/ST", args)
        self.assertIn("09:00", args)
        self.assertNotIn("/F", args)

    def test_mutated_config_is_rejected_before_task_creation(self):
        self.file.write_text(json.dumps({**self.config, "poll_seconds": 999}),
                             encoding="utf-8")
        with patch("scheduler_windows_tasks._is_windows", return_value=True), \
             patch("scheduler_windows_tasks._execute") as execute:
            with self.assertRaisesRegex(WindowsTaskError, "changed after approval"):
                register_task(self.file, expected_sha256=self.checksum)
            execute.assert_not_called()

    def test_headless_run_checks_saved_sha_before_network(self):
        self.file.write_text(json.dumps({**self.config, "jobs": []}), encoding="utf-8")
        with patch("scheduled_api_runner.ScheduledRunner") as runner:
            with self.assertRaisesRegex(WindowsTaskError, "changed"):
                run_locked_config(self.file, self.checksum)
            runner.assert_not_called()

    def test_locked_daily_run_uses_one_due_pass(self):
        with patch("scheduled_api_runner.ScheduledRunner") as runner:
            runner.return_value.run_due.return_value = 0
            self.assertEqual(run_locked_config(self.file, self.checksum), 0)
            runner.return_value.run_due.assert_called_once_with()
            runner.return_value.run_all_once.assert_not_called()
            runner.return_value.run_due.return_value = 1
            self.assertEqual(run_locked_config(self.file, self.checksum), 1)

    def test_unregister_only_deletes_hashed_task_not_customer_files(self):
        with patch("scheduler_windows_tasks._is_windows", return_value=True), \
             patch("scheduler_windows_tasks._execute") as execute:
            name = unregister_task(self.file)
        self.assertEqual(name, task_name(self.file))
        self.assertEqual(execute.call_args.args[0],
                         ["schtasks", "/Delete", "/TN", name, "/F"])
        self.assertTrue(self.file.is_file())

    def test_short_command_template_has_no_task_overwrite_switch(self):
        with patch("scheduler_windows_tasks._command", return_value="runner.exe /example"):
            cmd = build_register_command(self.file, self.file.read_bytes())
        self.assertEqual(cmd[0:2], ["schtasks", "/Create"])
        self.assertNotIn("/F", cmd)


if __name__ == "__main__":
    unittest.main()
