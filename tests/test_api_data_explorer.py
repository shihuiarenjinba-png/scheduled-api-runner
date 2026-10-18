"""Offline regression coverage for field extraction, response boundaries and exports."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from zipfile import ZipFile
from xml.etree import ElementTree as ET

from api_data_explorer import (
    ExplorerError, extract_rows, fetch_json, fingerprint, load_template,
    parse_fields, save_raw_json, save_template, save_text, save_xlsx, suggest_fields,
    validate_sources, validate_url,
)


class JsonExplorerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.sources = [
            {"name": "Sales", "url": "https://example.com/orders?from=2026-10-01",
             "fields": "Name = items[*].name\nRevenue = items[*].revenue\nTotal = total",
             "header_name": "X-API-Key"},
            {"name": "Inventory", "url": "https://api.example.com/stock",
             "fields": "Stock = data.remaining", "header_name": ""},
        ]

    def test_path_extraction_multiple_records_numbers_and_text(self):
        data = {"items": [{"name": "Book", "revenue": 1020},
                          {"name": "Pen", "revenue": 300}], "total": 1320}
        fields, rows = extract_rows(data, self.sources[0]["fields"])
        self.assertEqual(fields, ["Name", "Revenue", "Total"])
        self.assertEqual(rows, [{"Name": "Book", "Revenue": 1020, "Total": 1320},
                                {"Name": "Pen", "Revenue": 300, "Total": 1320}])
        self.assertIsInstance(rows[0]["Revenue"], int)

    def test_root_array_and_missing_fields_are_safe(self):
        fields, rows = extract_rows([{"name": "first"}, {"name": "second"}],
                                    "Item = $[*].name\nPrice = $[*].price")
        self.assertEqual(fields, ["Item", "Price"])
        self.assertEqual(rows, [{"Item": "first", "Price": ""},
                                {"Item": "second", "Price": ""}])

    def test_nested_index_and_unicode_keys(self):
        fields, rows = extract_rows({"値": [{"金額": 15.25}]},
                                    "数値 = 値[0].金額")
        self.assertEqual(rows, [{"数値": 15.25}])

    def test_suggest_fields_from_sample_and_reuse(self):
        sample = {"orders": [{"id": 1, "amount": 15.5}],
                  "created_at": "2026-10-18", "other": [{"name": "skip"}]}
        suggestions = suggest_fields(sample)
        self.assertIn("orders[*].id = orders[*].id", suggestions)
        self.assertIn("orders[*].amount = orders[*].amount", suggestions)
        self.assertIn("created_at = created_at", suggestions)
        self.assertNotIn("other[*].name = other[*].name", suggestions)
        fields, rows = extract_rows(sample, "\n".join(suggestions))
        self.assertEqual(rows[0]["orders[*].amount"], 15.5)

    def test_reject_mixed_repeating_arrays_and_invalid_selectors(self):
        for text in ["Price = a[*].p\nName = b[*].n",
                     "Broken = a[bad].value", "a..b", "a[0]name"]:
            with self.subTest(text=text), self.assertRaises(ExplorerError):
                parse_fields(text)

    def test_reject_unsafe_urls_and_sensitive_query_values(self):
        bad = ["http://example.com/data", "https://127.0.0.1/",
               "https://localhost/", "https://site.local/",
               "https://example.com:8443/x", "https://user:pass@example.com/",
               "https://example.com/?api_key=sensitive",
               "https://example.com/#token", "https://example.com/\nheader"]
        for url in bad:
            with self.subTest(url=url), self.assertRaises(ExplorerError):
                validate_url(url)

    def test_preview_hash_and_template_are_secret_free(self):
        clean = validate_sources(self.sources)
        before = fingerprint(clean)
        changed = [dict(s) for s in clean]
        changed[0]["fields"] = "Status = success"
        self.assertNotEqual(before, fingerprint(changed))
        out = self.root / "sources.json"
        save_template(out, clean)
        self.assertEqual(load_template(out), clean)
        self.assertNotIn("super-secret", out.read_text())
        with self.assertRaises(FileExistsError):
            save_template(out, clean)

    def test_reject_private_dns_before_any_http_request(self):
        with patch("api_data_explorer.socket.getaddrinfo",
                   return_value=[(2, 1, 6, "", ("127.0.0.1", 443))]), \
             patch("api_data_explorer._PinnedHTTPS") as conn:
            with self.assertRaisesRegex(ExplorerError, "non-public"):
                fetch_json("https://example.com/data")
            conn.assert_not_called()

    def test_json_fetch_is_get_once_with_header_and_no_redirect(self):
        class Response:
            status = 200
            def read(self, limit):
                return b'{"items":[{"name":"hello"}]}'
        class Connection:
            def __init__(self):
                self.calls = []
            def request(self, method, path, headers):
                self.calls.append((method, path, headers))
            def getresponse(self):
                return Response()
            def close(self):
                pass
        connection = Connection()
        with patch("api_data_explorer.socket.getaddrinfo",
                   return_value=[(2, 1, 6, "", ("8.8.8.8", 443))]), \
             patch("api_data_explorer._PinnedHTTPS", return_value=connection):
            result = fetch_json("https://example.com/data?p=1", "X-API-Key", "secret")
        self.assertEqual(result["items"][0]["name"], "hello")
        self.assertEqual(len(connection.calls), 1)
        self.assertEqual(connection.calls[0][0], "GET")
        self.assertEqual(connection.calls[0][1], "/data?p=1")
        self.assertEqual(connection.calls[0][2]["X-API-Key"], "secret")

    def test_spreadsheet_is_typed_and_text_is_never_a_formula(self):
        result = [{"name": "Sales", "fields": ["Name", "Revenue", "Text"],
                   "rows": [{"Name": "Book", "Revenue": 21.5, "Text": "=1+1"},
                            {"Name": "Pen", "Revenue": 3, "Text": "日本語"}],
                   "raw": {"some": "data"}}]
        xlsx = self.root / "table.xlsx"
        save_xlsx(xlsx, result)
        with ZipFile(xlsx) as archive:
            xml = archive.read("xl/worksheets/sheet1.xml")
            ET.fromstring(xml)
            self.assertIn(b't="n"', xml)
            self.assertIn(b't="inlineStr"', xml)
            self.assertNotIn(b"<f>", xml)
            self.assertIn(b"21.5", xml)
            self.assertIn(b"=1+1", xml)
        text = self.root / "strings.txt"
        save_text(text, result)
        self.assertIn("=1+1", text.read_text(encoding="utf-8"))
        raw = self.root / "original.json"
        save_raw_json(raw, result)
        self.assertEqual(json.loads(raw.read_text(encoding="utf-8"))[0]["response"],
                         {"some": "data"})
        with self.assertRaises(FileExistsError):
            save_xlsx(xlsx, result)
        with ZipFile(xlsx) as archive:
            self.assertIsNotNone(archive.getinfo("xl/workbook.xml"))

    def test_template_rejects_raw_secret_in_url(self):
        changed = [dict(self.sources[0])]
        changed[0]["url"] = "https://example.com/?token=private"
        with self.assertRaises(ExplorerError):
            validate_sources(changed)


if __name__ == "__main__":
    unittest.main()
