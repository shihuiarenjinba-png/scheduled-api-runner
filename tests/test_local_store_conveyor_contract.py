from pathlib import Path
import unittest


class LocalStoreConveyorContractTests(unittest.TestCase):
    def test_github_ci_is_primary_and_local_is_exact_artifact_confirmation(self):
        root = Path(__file__).resolve().parents[1]
        text = (
            root / "store" / "LOCAL_FINAL_QA_AND_STORE_HANDOFF_20261116.md"
        ).read_text(encoding="utf-8")

        for required in (
            "GitHub CI is the primary test environment",
            "store-product-handoff.json",
            "run_store_preupload_readiness.ps1",
            "READY_FOR_MSIX_UPLOAD_APPROVAL",
            "Do not rebuild",
            "authorized non-production HTTPS GET",
            "Task Scheduler"
        ):
            self.assertIn(required, text)

        self.assertNotIn("Run `python -m unittest discover -s tests -v`.", text)


if __name__ == "__main__":
    unittest.main()
