import copy
import json
import sys
import tempfile
from pathlib import Path
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
STORE = ROOT / "store"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from store.msix_version import (  # noqa: E402
    load_msix_version_config,
    resolve_msix_package_version,
    validate_msix_package_version,
)

NS = "http://schemas.microsoft.com/appx/manifest/foundation/windows10"
UAP10 = "http://schemas.microsoft.com/appx/manifest/uap/windows10/10"


class StoreIdentityDraftTests(unittest.TestCase):
    def test_canonical_identity_is_single_source_and_manifest_matches(self):
        identity_paths = sorted(STORE.glob("*identity*.json"))
        self.assertEqual([path.name for path in identity_paths], ["partner-center-identity.json"])
        identity = json.loads(identity_paths[0].read_text(encoding="utf-8"))
        self.assertEqual(identity["schema_version"], 1)
        self.assertEqual(identity["store_id"], "9PND0HG61XD6")
        self.assertEqual(identity["identity_name"], "OkinawaDesktopTools.ScheduledAPIRunner")
        self.assertEqual(identity["publisher"], "CN=46263F21-A700-41DB-8C9B-114C22FB82FC")
        self.assertEqual(identity["publisher_display_name"], "Okinawa Desktop Tools")
        self.assertEqual(
            identity["package_family_name"],
            "OkinawaDesktopTools.ScheduledAPIRunner_j8yefg9jgfh58",
        )
        self.assertIn("2026-10-18", identity["evidence"])
        self.assertIs(identity["partner_center_rechecked"], False)
        self.assertIs(identity["submission_allowed"], False)

        version_config = load_msix_version_config()
        package_version = resolve_msix_package_version(version_config)
        template = (STORE / "AppxManifest.template.xml").read_text(encoding="utf-8")
        for key, value in {
            "__PACKAGE_IDENTITY_NAME__": identity["identity_name"],
            "__PUBLISHER__": identity["publisher"],
            "__PUBLISHER_DISPLAY_NAME__": identity["publisher_display_name"],
            "__VERSION__": package_version,
        }.items():
            template = template.replace(key, value)
        root = ET.fromstring(template)
        package_identity = root.find(f".//{{{NS}}}Identity")
        app = root.find(f".//{{{NS}}}Application")
        self.assertEqual(package_identity.attrib["Name"], identity["identity_name"])
        self.assertEqual(package_identity.attrib["Publisher"], identity["publisher"])
        self.assertEqual(package_identity.attrib["Version"], "1.0.0.0")
        self.assertEqual(app.attrib["Executable"], "ScheduledApiRunner.exe")
        self.assertEqual(app.attrib[f"{{{UAP10}}}RuntimeBehavior"], "packagedClassicApp")
        self.assertIsNotNone(root.find(".//{*}Capability[@Name='runFullTrust']"))

    def test_msix_version_requires_four_components_and_store_constraints(self):
        for value in ("1.0.0.0", "1.2.3.0", "65535.65535.65535.0"):
            with self.subTest(valid=value):
                self.assertEqual(validate_msix_package_version(value), value)
        invalid_values = (
            None,
            "",
            "0.1.0.0",
            "1.0.0.1",
            "1.0.0",
            "1.-1.0.0",
            "01.0.0.0",
            "1.65536.0.0",
            "1.0.0.0.0",
        )
        for value in invalid_values:
            with self.subTest(invalid=value):
                with self.assertRaises(ValueError):
                    validate_msix_package_version(value)

    def test_package_format_and_kind_are_checked(self):
        with self.assertRaisesRegex(ValueError, "package_format"):
            validate_msix_package_version("1.0.0.0", package_format="msixbundle")
        with self.assertRaisesRegex(ValueError, "package_kind"):
            validate_msix_package_version("1.0.0.0", package_kind="uwp")

    def test_internal_app_version_does_not_drive_package_version(self):
        config = load_msix_version_config()
        expected = resolve_msix_package_version(config)
        self.assertIsNone(config["internal_app_version"])
        self.assertEqual(config["internal_app_version_status"], "NOT_DEFINED_IN_SOURCE")
        changed = copy.deepcopy(config)
        changed["internal_app_version"] = "0.2.0"
        changed["internal_app_version_status"] = "DEFINED_IN_PROJECT_METADATA"
        self.assertEqual(resolve_msix_package_version(changed), expected)
        self.assertEqual(expected, "1.0.0.0")

    def test_missing_or_unapproved_version_settings_fail_closed(self):
        config = load_msix_version_config()
        missing_version = copy.deepcopy(config)
        missing_version.pop("msix_package_version")
        with self.assertRaisesRegex(ValueError, "msix_package_version"):
            resolve_msix_package_version(missing_version)
        allowed = copy.deepcopy(config)
        allowed["store_submission_allowed"] = True
        with self.assertRaisesRegex(ValueError, "store_submission_allowed"):
            resolve_msix_package_version(allowed)
        wrong_history = copy.deepcopy(config)
        wrong_history["store_version_history_verified"] = True
        with self.assertRaisesRegex(ValueError, "previous_store_accepted_version"):
            resolve_msix_package_version(wrong_history)

    def test_missing_version_file_has_clear_error(self):
        with tempfile.TemporaryDirectory() as temp:
            missing = Path(temp) / "missing.json"
            with self.assertRaisesRegex(ValueError, "configuration is missing"):
                load_msix_version_config(missing)

    def test_builder_remains_a_non_sales_draft(self):
        builder = (STORE / "build_msix_draft.ps1").read_text(encoding="utf-8")
        self.assertIn("partner-center-identity.json", builder)
        self.assertIn("msix_version.py", builder)
        self.assertIn("store_submission_approved = $false", builder)
        self.assertIn("public_release_approved = $false", builder)
        self.assertIn("sale_approved = $false", builder)
        self.assertNotIn("initial_msix_version", builder)
        workflow = (ROOT / ".github" / "workflows" / "windows-desktop.yml").read_text(encoding="utf-8")
        self.assertIn("store/build_msix_draft.ps1", workflow)
        self.assertIn("ScheduledApiRunner-Store-MSIX-UNSIGNED-DRAFT", workflow)
        self.assertIn("source_commit = $sourceCommit", builder)
        self.assertIn("git -C $repoRoot rev-parse HEAD", builder)
        build_script = (ROOT / "build_windows.ps1").read_text(encoding="utf-8")
        self.assertIn("source_commit = $sourceCommit", build_script)
        self.assertIn("git -C $PSScriptRoot rev-parse HEAD", build_script)


    def test_source_commit_powershell_blocks_are_complete(self):
        # Detect the 2026-10-24 regression: a missing regex terminator
        # followed by a second concatenated copy of the builder script.
        for relative in ("build_windows.ps1", "store/build_msix_draft.ps1"):
            with self.subTest(script=relative):
                script = (ROOT / relative).read_text(encoding="utf-8")
                guard = "if ($LASTEXITCODE -ne 0 -or $sourceCommit -notmatch '^[0-9a-fA-F]{40}$') {"
                self.assertEqual(script.count(guard), 1)
                self.assertEqual(script.count("$sourceCommit = (& git -C "), 1)
                self.assertEqual(script.count("source_commit = $sourceCommit"), 1)
                self.assertNotIn("40}$identity", script)
                self.assertNotIn("40}$stamp", script)
                self.assertEqual(script.count("Unable to resolve exact source commit"), 1)
                if relative.startswith("store/"):
                    self.assertEqual(script.count("function Assert-Manifest("), 1)



    def test_windows_workflow_verifies_unsigned_msix_evidence(self):
        workflow = (ROOT / ".github" / "workflows" / "windows-desktop.yml").read_text(encoding="utf-8")
        for required in (
            "MSIX source commit mismatch",
            "MSIX SHA-256 mismatch",
            "EXE roundtrip SHA-256 mismatch",
            "MSIX checksum file mismatch",
            "MSIX candidate unexpectedly marked approved",
        ):
            with self.subTest(required=required):
                self.assertIn(required, workflow)

if __name__ == "__main__":
    unittest.main()
