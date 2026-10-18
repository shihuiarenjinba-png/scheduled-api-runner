import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from xml.etree import ElementTree as ET

from win_task import TaskError, register, task_xml, unregister, validate_job


class TaskTests(unittest.TestCase):
    def test_xml_is_safe_and_non_elevated(self):
        xml = task_xml("09:30", r"C:\Python\python.exe", r"C:\app\runner.py",
                       r'C:\Data\a & "b".json', today="2026-10-18", username=r"WORK\alice")
        root = ET.fromstring(xml)
        ns = {"t": "http://schemas.microsoft.com/windows/2004/02/mit/task"}
        self.assertEqual(root.findtext(".//t:StartBoundary", namespaces=ns), "2026-10-18T09:30:00")
        self.assertEqual(root.findtext(".//t:LogonType", namespaces=ns), "InteractiveToken")
        self.assertEqual(root.findtext(".//t:RunLevel", namespaces=ns), "LeastPrivilege")
        self.assertIn("a &", root.findtext(".//t:Arguments", namespaces=ns))
        self.assertEqual(root.findtext(".//t:MultipleInstancesPolicy", namespaces=ns), "IgnoreNew")

    def test_reject_invalid_settings(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "job.json"
            path.write_text(json.dumps({"jobs": [{"name": "ok", "schedule":
                                {"type": "daily", "at": "99:00"}}]}), encoding="utf-8")
            with self.assertRaises(TaskError):
                validate_job(path)
        with self.assertRaises(TaskError):
            task_xml("09:70", "python", "runner", "job", username="alice")

    @patch("win_task.sys.platform", "linux")
    def test_no_os_changes_off_windows(self):
        with self.assertRaises(TaskError):
            register(Path("anything.json"))
        with self.assertRaises(TaskError):
            unregister(Path("anything.json"))


if __name__ == "__main__":
    unittest.main()
