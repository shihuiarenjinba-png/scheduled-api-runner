"""Fail-closed MSIX package-version configuration for the Scheduled API Runner draft."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

CONFIG_PATH = Path(__file__).with_name("msix-version.json")
_COMPONENT = r"(?:0|[1-9][0-9]*)"
_MSIX_VERSION_RE = re.compile(rf"({_COMPONENT})\.({_COMPONENT})\.({_COMPONENT})\.({_COMPONENT})\Z")
_INTERNAL_VERSION_RE = re.compile(rf"({_COMPONENT})\.({_COMPONENT})\.({_COMPONENT})\Z")
_MAX_COMPONENT = 65535


def _parse_components(value: Any, pattern: re.Pattern[str], label: str, count: int) -> tuple[int, ...]:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} is missing; configure it explicitly. No version fallback is allowed.")
    match = pattern.fullmatch(value)
    if match is None:
        raise ValueError(f"{label} must contain exactly {count} canonical decimal components.")
    parts: list[int] = []
    for component in match.groups():
        if len(component) > 5:
            raise ValueError(f"{label} component exceeds the maximum value {_MAX_COMPONENT}.")
        number = int(component, 10)
        if number > _MAX_COMPONENT:
            raise ValueError(f"{label} component exceeds the maximum value {_MAX_COMPONENT}.")
        parts.append(number)
    return tuple(parts)


def validate_msix_package_version(
    value: Any,
    *,
    package_format: str = "msix",
    package_kind: str = "packaged_classic_desktop",
) -> str:
    """Validate the exact package format and its Store-specific four-part version."""
    if package_format != "msix":
        raise ValueError(f"Unsupported package_format {package_format!r}; this builder supports only 'msix'.")
    if package_kind != "packaged_classic_desktop":
        raise ValueError(
            f"Unsupported package_kind {package_kind!r}; this builder supports only 'packaged_classic_desktop'."
        )
    parts = _parse_components(value, _MSIX_VERSION_RE, "msix_package_version", 4)
    if parts[0] < 1:
        raise ValueError(
            "MSIX Store package major version must be at least 1; the legacy 0.x.x.0 value is not a valid Store candidate."
        )
    if parts[3] != 0:
        raise ValueError(
            "The fourth MSIX package version component must be 0 for Store submission; it is reserved for Store use."
        )
    return value


def validate_version_config(config: Any) -> dict[str, Any]:
    if not isinstance(config, dict):
        raise ValueError("MSIX version configuration must be a JSON object.")
    if config.get("schema_version") != 1:
        raise ValueError("MSIX version configuration schema_version must be 1.")
    if config.get("package_format") != "msix":
        raise ValueError("package_format must be explicitly set to 'msix'.")
    if config.get("package_kind") != "packaged_classic_desktop":
        raise ValueError("package_kind must be explicitly set to 'packaged_classic_desktop'.")
    if "internal_app_version" not in config or "internal_app_version_status" not in config:
        raise ValueError(
            "Internal app version and MSIX package version must be separate explicit fields; do not infer one from the other."
        )
    internal_version = config["internal_app_version"]
    internal_status = config["internal_app_version_status"]
    if internal_version is None:
        if internal_status != "NOT_DEFINED_IN_SOURCE":
            raise ValueError(
                "internal_app_version is null only when internal_app_version_status is NOT_DEFINED_IN_SOURCE."
            )
    else:
        _parse_components(internal_version, _INTERNAL_VERSION_RE, "internal_app_version", 3)
        if internal_status not in {"DEFINED_IN_PROJECT_METADATA", "DEFINED_IN_SOURCE"}:
            raise ValueError(
                "A defined internal_app_version requires status DEFINED_IN_PROJECT_METADATA or DEFINED_IN_SOURCE."
            )
    if "msix_package_version" not in config:
        raise ValueError("msix_package_version is missing; refusing to infer it from internal_app_version.")
    validate_msix_package_version(
        config["msix_package_version"],
        package_format=config.get("package_format"),
        package_kind=config.get("package_kind"),
    )
    if not config.get("msix_package_version_status"):
        raise ValueError("msix_package_version_status is required.")
    if config.get("store_submission_allowed") is not False:
        raise ValueError("This draft builder requires store_submission_allowed=false.")
    if not isinstance(config.get("store_version_history_verified"), bool):
        raise ValueError("store_version_history_verified must be an explicit boolean.")
    if config["store_version_history_verified"] and not config.get("previous_store_accepted_version"):
        raise ValueError(
            "A verified Store version history requires previous_store_accepted_version to be recorded."
        )
    return config


def load_msix_version_config(path: str | Path = CONFIG_PATH) -> dict[str, Any]:
    config_path = Path(path)
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"MSIX version configuration is missing: {config_path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"MSIX version configuration is invalid JSON: {exc}") from exc
    return validate_version_config(config)


def resolve_msix_package_version(config: Any) -> str:
    """Return only the explicit package version; internal app version never supplies a fallback."""
    validated = validate_version_config(config)
    return validate_msix_package_version(
        validated["msix_package_version"],
        package_format=validated["package_format"],
        package_kind=validated["package_kind"],
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="print the validated version record as JSON")
    args = parser.parse_args(argv)
    try:
        config = load_msix_version_config()
        package_version = resolve_msix_package_version(config)
    except ValueError as exc:
        print(f"MSIX version configuration error: {exc}", file=sys.stderr)
        return 2
    if args.json:
        result = {
            "internal_app_version": config["internal_app_version"],
            "msix_package_version": package_version,
            "msix_package_version_status": config["msix_package_version_status"],
            "package_format": config["package_format"],
            "package_kind": config["package_kind"],
            "previous_store_accepted_version": config["previous_store_accepted_version"],
            "store_version_history_verified": config["store_version_history_verified"],
            "store_submission_allowed": config["store_submission_allowed"],
        }
        print(json.dumps(result, ensure_ascii=False))
    else:
        print(package_version)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
