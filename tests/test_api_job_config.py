import tempfile
import unittest
from pathlib import Path
from api_job_config import ConfigurationError, build_daily_job, parse_column_mapping

class ConfigurationTests(unittest.TestCase):
    def setUp(self):
        self.t=tempfile.TemporaryDirectory();self.addCleanup(self.t.cleanup)
        self.path=Path(self.t.name)/'daily.csv';self.path.write_text('date,value\n',encoding='utf-8')
    def config(self,**kwargs):
        return build_daily_job(**{'url':'https://api.example.com/v1','csv_path':str(self.path),'mapping':'value=data.today',**kwargs})
    def test_basic(self):
        c=self.config();self.assertEqual(c['jobs'][0]['persist']['columns'],{'value':'data.today'});self.assertEqual(c['allow_hosts'],['api.example.com'])
    def test_bearer_template(self):
        expected='Bearer ' + '$' + '{ENV:API_TOKEN}'
        self.assertEqual(self.config(token_env_name='API_TOKEN')['jobs'][0]['request']['headers']['Authorization'],expected)
    def test_no_secret_in_url(self):
        with self.assertRaises(ConfigurationError):build_daily_job(url='https://host/a?api_key=secret',csv_path=str(self.path),mapping='value=v')
    def test_non_https(self):
        with self.assertRaises(ConfigurationError):build_daily_job(url='http://api.example.com/',csv_path=str(self.path),mapping='value=v')
    def test_duplicate_columns(self):
        with self.assertRaises(ConfigurationError):parse_column_mapping('value=a\nvalue=b')
    def test_typo_no_guess(self):
        self.assertEqual(parse_column_mapping('amount=data.amout'),{'amount':'data.amout'})
    def test_reserved_date(self):
        with self.assertRaises(ConfigurationError):self.config(mapping='')
    def test_invalid_schedule(self):
        with self.assertRaises(ConfigurationError):self.config(at='25:99')
    def test_missing_output(self):
        self.path.unlink()
        with self.assertRaises(ConfigurationError):self.config()
    def test_invalid_token_name(self):
        with self.assertRaises(ConfigurationError):self.config(token_env_name='a$bad')

if __name__=='__main__':unittest.main()
