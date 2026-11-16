import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("store_handoff_generator", ROOT / "store" / "generate_store_handoff.py")
MOD = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MOD)


class StoreHandoffGeneratorTests(unittest.TestCase):
    def setUp(self):
        self.profile = json.loads((ROOT / "store" / "STORE_HANDOFF_PROFILE_20261116.json").read_text(encoding="utf-8"))
        identity = self.profile["identity"]
        self.report = {
            "source_commit": "a" * 40,
            "msix_sha256": "b" * 64,
            "source_exe_sha256": "c" * 64,
            "unpacked_exe_sha256": "c" * 64,
            "manifest_identity_verified": True,
            "makeappx_pack_unpack": "PASS",
            "signed": False,
            "store_submission_approved": False,
            "sale_approved": False,
            "store_id": identity["store_id"],
            "identity_name": identity["name"],
            "identity_publisher": identity["publisher"],
            "msix_version": identity["version"],
            "msix_file": "candidate_1.0.0.0_x64.msix",
        }

    def test_generated_handoff_binds_exact_package_and_stays_hold(self):
        result = MOD.build_handoff(self.profile, self.report, artifact_run_id=123)
        self.assertEqual(result["product"]["source_sha"], "a" * 40)
        self.assertEqual(result["package"]["package_sha256"], "b" * 64)
        self.assertEqual(result["security"]["package_sha256"], "b" * 64)
        self.assertEqual(result["package"]["artifact_run_id"], 123)
        self.assertFalse(result["identity"]["live_partner_center_reverified"])
        self.assertFalse(result["approvals"]["owner_approved_for_draft"])
        self.assertFalse(result["qa"]["local_final_pass"])

    def test_identity_mismatch_is_rejected(self):
        self.report["store_id"] = "WRONG"
        with self.assertRaises(MOD.HandoffGenerationError):
            MOD.build_handoff(self.profile, self.report)

    def test_sales_approval_in_build_report_is_rejected(self):
        self.report["sale_approved"] = True
        with self.assertRaises(MOD.HandoffGenerationError):
            MOD.build_handoff(self.profile, self.report)


if __name__ == "__main__":
    unittest.main()
