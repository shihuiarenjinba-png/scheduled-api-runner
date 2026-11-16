#!/usr/bin/env python3
"""Generate a fail-closed store-product-handoff/2 from exact MSIX CI evidence.

This module never calls Partner Center and never grants upload/certification/publish
approval. It binds immutable source/package evidence to a product profile so the
same bytes can be downloaded and verified on the local Windows QA machine.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

HEX40 = re.compile(r"^[0-9a-fA-F]{40}$")
HEX64 = re.compile(r"^[0-9a-fA-F]{64}$")


class HandoffGenerationError(ValueError):
    pass


def _obj(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise HandoffGenerationError(f"{label} must be an object")
    return value


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise HandoffGenerationError(f"{label} must be a non-empty string")
    return value.strip()


def _hex(value: Any, label: str, pattern: re.Pattern[str]) -> str:
    text = _text(value, label).lower()
    if not pattern.fullmatch(text):
        raise HandoffGenerationError(f"{label} has invalid format")
    return text


def build_handoff(profile: dict[str, Any], report: dict[str, Any], *, artifact_run_id: int | None = None) -> dict[str, Any]:
    profile = _obj(profile, "profile")
    report = _obj(report, "report")
    if profile.get("schema_version") != "store-handoff-profile/1":
        raise HandoffGenerationError("unsupported profile schema")

    product = _obj(profile.get("product"), "profile.product")
    identity = _obj(profile.get("identity"), "profile.identity")
    commercial = _obj(profile.get("commercial"), "profile.commercial")
    distribution = _obj(profile.get("distribution"), "profile.distribution")

    source_sha = _hex(report.get("source_commit"), "report.source_commit", HEX40)
    package_sha = _hex(report.get("msix_sha256"), "report.msix_sha256", HEX64)
    exe_sha = _hex(report.get("source_exe_sha256"), "report.source_exe_sha256", HEX64)
    unpacked_exe_sha = _hex(report.get("unpacked_exe_sha256"), "report.unpacked_exe_sha256", HEX64)
    if exe_sha != unpacked_exe_sha:
        raise HandoffGenerationError("EXE roundtrip SHA mismatch")

    if report.get("manifest_identity_verified") is not True or report.get("makeappx_pack_unpack") != "PASS":
        raise HandoffGenerationError("MSIX engineering validation is not PASS")
    for forbidden in ("signed", "store_submission_approved", "sale_approved"):
        if report.get(forbidden) is not False:
            raise HandoffGenerationError(f"report.{forbidden} must remain false")

    expected = {
        "store_id": _text(identity.get("store_id"), "profile.identity.store_id"),
        "identity_name": _text(identity.get("name"), "profile.identity.name"),
        "identity_publisher": _text(identity.get("publisher"), "profile.identity.publisher"),
        "msix_version": _text(identity.get("version"), "profile.identity.version"),
    }
    for key, value in expected.items():
        if report.get(key) != value:
            raise HandoffGenerationError(f"report/profile mismatch: {key}")

    package_file = _text(report.get("msix_file"), "report.msix_file")
    if Path(package_file).suffix.lower() != ".msix":
        raise HandoffGenerationError("expected .msix package")

    model = _text(commercial.get("model"), "profile.commercial.model")
    trial = _text(commercial.get("free_trial"), "profile.commercial.free_trial")
    if model == "free" and trial != "none":
        raise HandoffGenerationError("free product cannot carry a paid-product trial")

    run_id = artifact_run_id if artifact_run_id is not None else 0
    if run_id < 0:
        raise HandoffGenerationError("artifact_run_id cannot be negative")

    handoff = {
        "schema_version": "store-product-handoff/2",
        "product": {
            "id": _text(product.get("id"), "profile.product.id"),
            "type": _text(product.get("type"), "profile.product.type"),
            "name": _text(product.get("name"), "profile.product.name"),
            "edition": _text(product.get("edition"), "profile.product.edition"),
            "summary": _text(product.get("summary"), "profile.product.summary"),
            "submission_kind": _text(product.get("submission_kind"), "profile.product.submission_kind"),
            "submission_route": _text(product.get("submission_route"), "profile.product.submission_route"),
            "repository": _text(product.get("repository"), "profile.product.repository"),
            "source_ref": _text(product.get("source_ref"), "profile.product.source_ref"),
            "source_sha": source_sha,
            "market_preset": str(product.get("market_preset") or ""),
        },
        "package": {
            "artifact_run_id": run_id,
            "windows_artifact_id": None,
            "msix_artifact_id": None,
            "package_type": "msix",
            "file_name": package_file,
            "package_sha256": package_sha,
            "exe_sha256": exe_sha,
            "unsigned_engineering_candidate": True,
        },
        "identity": {
            "store_id": expected["store_id"],
            "name": expected["identity_name"],
            "publisher": expected["identity_publisher"],
            "version": expected["msix_version"],
            "architecture": _text(identity.get("architecture"), "profile.identity.architecture"),
            "package_family_name": str(identity.get("package_family_name") or ""),
            "package_sid": str(identity.get("package_sid") or ""),
            "live_partner_center_reverified": False,
            "accepted_version_history_verified": False,
            "version_history_state": "UNKNOWN",
            "version_conflict": None,
        },
        "commercial": {
            "model": model,
            "strategy": str(commercial.get("strategy") or ""),
            "currency": _text(commercial.get("currency"), "profile.commercial.currency"),
            "exact_partner_center_price_value": None,
            "price_confirmed": False,
            "approved_by": None,
            "free_trial": trial,
            "trial_confirmed": trial == "none",
            "trial_approved_by": None,
            "publishing_hold": "manual_publish",
        },
        "distribution": {
            "audience": _text(distribution.get("audience"), "profile.distribution.audience"),
            "known_user_group": None,
            "public_release_approved": False,
        },
        "assets": {
            "jp_en_listing_candidate_present": True,
            "owner_visual_approval": False,
            "final_public_release_screenshots": False,
            "final_icon_approved": False,
        },
        "security": {
            "package_sha256": package_sha,
            "owner_confirmation_complete": False,
            "fields": profile.get("security_fields"),
        },
        "approvals": {
            "owner_approved_for_draft": False,
            "certification_submit_approved": False,
            "publish_approved": False,
            "initial_submission_start_approved": False,
        },
        "qa": {
            "github_exact_head_ci_pass": True,
            "local_final_pass": False,
            "store_signed_install_pass": False,
        },
        "release_holds": list(profile.get("release_holds") or []),
        "notes": [
            "Generated from exact CI MSIX validation evidence.",
            "Local Windows QA must use these exact package bytes; rebuilding creates a different candidate.",
            "Live Partner Center identity/submission state, security answers, assets, and external writes remain separate gates.",
        ],
    }
    return handoff


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", required=True)
    parser.add_argument("--report", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--artifact-run-id", type=int, default=0)
    args = parser.parse_args()

    profile = json.loads(Path(args.profile).read_text(encoding="utf-8-sig"))
    report = json.loads(Path(args.report).read_text(encoding="utf-8-sig"))
    handoff = build_handoff(profile, report, artifact_run_id=args.artifact_run_id)
    Path(args.output).write_text(json.dumps(handoff, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"STORE_HANDOFF_GENERATED source={handoff['product']['source_sha']} package={handoff['package']['package_sha256']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
