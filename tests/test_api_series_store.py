"""Regression tests for the daily API JSON -> history CSV operation."""
from __future__ import annotations

import csv
from datetime import datetime
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from api_series_store import SeriesError, update_series, validate_writer
from guided_config import add_daily_csv_output, make_get_job
from scheduled_api_runner import RunnerError, ScheduledRunner


NOW = datetime.fromisoformat("2026-10-18T09:01:00+09:00")
SETTINGS = {"path": "sales.csv",
            "fields": "sales = data.sales\norders = data.orders",
            "date_path": "data.date", "on_duplicate": "skip"}
DOCUMENT = {"data": {"date": "2026-10-18", "sales": 385000, "orders": 125}}


def read_csv(path: Path):
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


class CsvUpdateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_new_file_appends_today_numeric_values(self):
        out = update_series(self.root, SETTINGS, DOCUMENT, NOW)
        self.assertEqual(out["status"], "created_file")
        rows = read_csv(self.root / "sales.csv")
        self.assertEqual(rows, [{"date": "2026-10-18", "sales": "385000", "orders": "125"}])

    def test_existing_file_preserved_then_today_added_and_backup_created(self):
        original = (b"date,sales,orders\r\n2026-10-17,250000,100\r\n")
        target = self.root / "sales.csv"
        target.write_bytes(original)
        out = update_series(self.root, SETTINGS, DOCUMENT, NOW)
        self.assertEqual(out["status"], "appended_date")
        self.assertEqual(len(read_csv(target)), 2)
        backups = list(self.root.glob(".sales.csv.backup-*"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_bytes(), original)

    def test_duplicate_date_skips_without_file_change_or_new_backup(self):
        update_series(self.root, SETTINGS, DOCUMENT, NOW)
        target = self.root / "sales.csv"
        before = target.read_bytes()
        out = update_series(self.root, SETTINGS, {"data": {
            "date": "2026-10-18", "sales": 999, "orders": 1}}, NOW)
        self.assertEqual(out["status"], "skipped_existing_date")
        self.assertEqual(target.read_bytes(), before)
        self.assertFalse(list(self.root.glob(".sales.csv.backup-*")))

    def test_explicit_replace_only_changes_matching_date_and_creates_backup(self):
        target = self.root / "sales.csv"
        target.write_text("date,sales,orders\n2026-10-17,1,2\n2026-10-18,3,4\n",
                          encoding="utf-8")
        revised = {**SETTINGS, "on_duplicate": "replace"}
        result = update_series(self.root, revised, DOCUMENT, NOW)
        self.assertEqual(result["status"], "replaced_date")
        self.assertEqual(read_csv(target), [
            {"date": "2026-10-17", "sales": "1", "orders": "2"},
            {"date": "2026-10-18", "sales": "385000", "orders": "125"},
        ])
        self.assertEqual(len(list(self.root.glob(".sales.csv.backup-*"))), 1)

    def test_missing_api_value_is_not_silently_saved(self):
        target = self.root / "sales.csv"
        target.write_text("date,sales,orders\n2026-10-17,1,2\n", encoding="utf-8")
        before = target.read_bytes()
        with self.assertRaisesRegex(SeriesError, "required API value"):
            update_series(self.root, SETTINGS, {"data": {"date": "2026-10-18", "orders": 1}}, NOW)
        self.assertEqual(target.read_bytes(), before)

    def test_wrong_schema_never_modifies_historical_file(self):
        target = self.root / "sales.csv"
        original = b"date,price,quantity\n2026-10-17,3,5\n"
        target.write_bytes(original)
        with self.assertRaisesRegex(SeriesError, "columns do not match"):
            update_series(self.root, SETTINGS, DOCUMENT, NOW)
        self.assertEqual(target.read_bytes(), original)

    def test_stale_lock_fails_closed(self):
        lock = self.root / ".sales.csv.lock"
        lock.write_text("held by other writer")
        with self.assertRaisesRegex(SeriesError, "locked"):
            update_series(self.root, SETTINGS, DOCUMENT, NOW)
        self.assertTrue(lock.exists())
        self.assertFalse((self.root / "sales.csv").exists())

    def test_runtime_date_is_explicit_and_timezone_aware(self):
        cfg = {**SETTINGS, "date_path": "", "date_source": "run_local"}
        out = update_series(self.root, cfg, {"data": {"sales": 3, "orders": 4}}, NOW)
        self.assertEqual(out["date"], "2026-10-18")
        cfg.pop("date_source")
        with self.assertRaises(SeriesError):
            validate_writer(cfg, self.root)

    def test_validation_blocks_traversal_and_repeating_field(self):
        for bad in ("../outside.csv", "/tmp/absolute.csv", "data.json", ""):
            with self.subTest(path=bad), self.assertRaises(SeriesError):
                validate_writer({**SETTINGS, "path": bad}, self.root)
        with self.assertRaisesRegex(SeriesError, "one value"):
            validate_writer({**SETTINGS, "fields": "x = items[*].price"}, self.root)

    def test_value_starting_formula_is_sanitized_for_excel(self):
        cfg = {**SETTINGS, "fields": "sales = data.sales"}
        data = {"data": {"date": "2026-10-18", "sales": "=HYPERLINK(1)"}}
        update_series(self.root, cfg, data, NOW)
        self.assertEqual(read_csv(self.root / "sales.csv")[0]["sales"], "'=HYPERLINK(1)")

    def test_guided_config_wizard_can_create_csv_job_offline(self):
        base = make_get_job(root_dir=str(self.root), name="Daily Sales",
                            url="https://example.com/sales", daily_at="09:00")
        cfg = add_daily_csv_output(base, path="sales.csv",
                                   fields="sales = data.sales", date_path="data.date")
        self.assertEqual(cfg["jobs"][0]["csv_update"]["date_path"], "data.date")
        self.assertNotIn("csv_update", base["jobs"][0])
        self.assertFalse((self.root / "sales.csv").exists())

    def test_runner_scheduled_request_saves_json_after_success(self):
        base = make_get_job(root_dir=str(self.root), name="Daily Sales",
                            url="https://example.com/sales", daily_at="09:00")
        cfg = add_daily_csv_output(base, path="sales.csv",
                                   fields="sales = data.sales", date_path="data.date")
        runner = ScheduledRunner(cfg)
        class FakeResponse:
            status = 200
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def geturl(self): return "https://example.com/sales"
            def read(self, limit): return json.dumps(DOCUMENT).encode()
        class FakeOpener:
            def open(self, req, timeout): return FakeResponse()
        with patch("scheduled_api_runner.urllib.request.build_opener",
                   return_value=FakeOpener()), patch("sys.stdout", new_callable=io.StringIO):
            runner.run_all_once()
            runner.run_all_once()
        self.assertEqual(len(read_csv(self.root / "sales.csv")), 1)

    def test_daily_schedule_catches_up_once_after_configured_time(self):
        cfg = make_get_job(root_dir=str(self.root), name="Daily Sales",
                           url="https://example.com/sales", daily_at="09:00")
        runner = ScheduledRunner(cfg, dry_run=True)
        job = cfg["jobs"][0]
        self.assertIsNone(runner._schedule_key(job, datetime.fromisoformat(
            "2026-10-18T08:59:00+09:00")))
        at_time = runner._schedule_key(job, datetime.fromisoformat(
            "2026-10-18T09:00:00+09:00"))
        after = runner._schedule_key(job, datetime.fromisoformat(
            "2026-10-18T18:45:00+09:00"))
        self.assertEqual(at_time, after)

    def test_daily_schedule_invalid_non_padded_clock_rejected(self):
        cfg = make_get_job(root_dir=str(self.root), name="Daily Sales",
                           url="https://example.com/sales", daily_at="09:00")
        job = cfg["jobs"][0]
        job["schedule"]["at"] = "9:00"
        runner = ScheduledRunner(cfg, dry_run=True)
        with self.assertRaises(RunnerError):
            runner._schedule_key(job, NOW)

    def test_non_get_writer_rejected_without_side_effects(self):
        cfg = make_get_job(root_dir=str(self.root), name="Write",
                           url="https://example.com/write", daily_at="09:00")
        cfg["jobs"][0]["request"]["method"] = "POST"
        cfg["jobs"][0]["csv_update"] = SETTINGS
        with self.assertRaisesRegex(RunnerError, "read-only GET"):
            ScheduledRunner(cfg, dry_run=True)
        self.assertFalse((self.root / "sales.csv").exists())


if __name__ == "__main__":
    unittest.main()
