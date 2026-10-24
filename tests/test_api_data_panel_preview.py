import unittest

from api_data_panel import build_offline_preview


class OfflineApiPreviewTests(unittest.TestCase):
    def test_preview_is_explicitly_offline_and_does_not_claim_success(self):
        preview = build_offline_preview({
            "name": "Sales demo",
            "url": "https://api.example.invalid/v1/sales",
            "fields": "sales = data.sales\norders = data.orders",
            "header_name": "X-API-Key",
        })

        self.assertEqual(preview["https_host"], "api.example.invalid")
        self.assertEqual(preview["network_request"], "not sent / 通信なし")
        self.assertFalse(preview["retrieval_guaranteed"])
        self.assertEqual(preview["fields"][0], {
            "label": "sales", "json_path": "data.sales",
        })
        self.assertNotIn("secret", str(preview).lower())


if __name__ == "__main__":
    unittest.main()

