import csv
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from daily_csv_store import DailyStoreError, update_daily_csv

CFG={'target_file':'history.csv','date_column':'date','columns': {'amount':'data.amount','symbol':'data.symbol'}}
TODAY=datetime(2026,10,18,tzinfo=timezone.utc)
PAYLOAD={'data':{'amount':42,'symbol':'ABC'}}

class DailyStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        (self.root/'history.csv').write_text('date,amount,symbol\n2026-10-17,17,OLD\n',encoding='utf-8')
    def run_update(self,config=None,payload=None):
        return update_daily_csv(self.root,PAYLOAD if payload is None else payload,CFG if config is None else config,recorded_at=TODAY)
    def test_append_preserves_prior_row(self):
        r=self.run_update(); self.assertEqual(r['status'],'APPENDED_DATE')
        with (self.root/'history.csv').open(newline='',encoding='utf-8') as f: rows=list(csv.DictReader(f))
        self.assertEqual(len(rows),2);self.assertEqual(rows[0]['amount'],'17');self.assertEqual(rows[1]['amount'],'42')
        self.assertTrue(Path(r['backup']).exists())
    def test_duplicate_default_does_not_change(self):
        self.run_update(); old=(self.root/'history.csv').read_bytes()
        with self.assertRaisesRegex(DailyStoreError,'already exists'):self.run_update()
        self.assertEqual(old,(self.root/'history.csv').read_bytes())
    def test_duplicate_skip(self):
        self.run_update();r=self.run_update({**CFG,'duplicate_policy':'skip'});self.assertEqual(r['status'],'SKIPPED_EXISTING_DATE')
    def test_duplicate_replace(self):
        self.run_update(); payload={'data':{'amount':99,'symbol':'ABC'}}
        r=self.run_update({**CFG,'duplicate_policy':'replace'},payload);self.assertEqual(r['status'],'REPLACED_DATE')
        self.assertIn(',99,',(self.root/'history.csv').read_text())
    def test_wrong_schema_keeps_original(self):
        original=(self.root/'history.csv').read_bytes()
        with self.assertRaisesRegex(DailyStoreError,'headers'): self.run_update({**CFG,'columns':{'foo':'data.amount'}})
        self.assertEqual(original,(self.root/'history.csv').read_bytes())
    def test_missing_field_no_guess(self):
        with self.assertRaisesRegex(DailyStoreError,'missing'):self.run_update({**CFG,'columns':{'amount':'data.amunt'}})
    def test_injection_rejected(self):
        with self.assertRaisesRegex(DailyStoreError,'formula'):self.run_update(payload={'data':{'amount':42,'symbol':'=HYPERLINK("x")'}})
    def test_negative_numeric_allowed(self):
        self.run_update(payload={'data':{'amount':-5.8,'symbol':'ABC'}})
        self.assertIn(',-5.8,',(self.root/'history.csv').read_text())
    def test_path_escape(self):
        with self.assertRaisesRegex(DailyStoreError,'beneath'):self.run_update({**CFG,'target_file':'../outside.csv'})
    def test_existing_file_required(self):
        (self.root/'history.csv').unlink()
        with self.assertRaisesRegex(DailyStoreError,'missing'):self.run_update()
    def test_create_requires_explicit_optin(self):
        (self.root/'history.csv').unlink()
        self.run_update({**CFG,'create_if_missing':True})
        self.assertIn('2026-10-18',(self.root/'history.csv').read_text())
    def test_lock_no_write(self):
        lock=self.root/'history.csv.update.lock';lock.write_text('other')
        old=(self.root/'history.csv').read_bytes()
        with self.assertRaisesRegex(DailyStoreError,'update is running'):self.run_update()
        self.assertEqual(old,(self.root/'history.csv').read_bytes());self.assertTrue(lock.exists())
    def test_date_field(self):
        cfg={**CFG,'date_field':'date'}
        self.run_update(cfg, {'date':'2026-10-19',**PAYLOAD})
        self.assertIn('2026-10-19',(self.root/'history.csv').read_text())
    def test_invalid_date(self):
        with self.assertRaisesRegex(DailyStoreError,'Date'): self.run_update({**CFG,'date_field':'date'}, {'date':'2026-02-30',**PAYLOAD})
    def test_bad_existing_row(self):
        (self.root/'history.csv').write_text('date,amount,symbol\n2026-10-17,17,OLD,extra\n')
        with self.assertRaisesRegex(DailyStoreError,'Malformed'):self.run_update()

if __name__=='__main__':unittest.main()
