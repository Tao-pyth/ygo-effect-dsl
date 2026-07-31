from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from ygo_effect_dsl import __version__
from ygo_effect_dsl.engine.canonical import stable_digest, to_canonical_data
from ygo_effect_dsl.external.asset_setup import external_asset_setup_guidance


V1_EXTERNAL_ASSET_SETUP_SCHEMA_VERSION = "v1-external-asset-setup-v1"


def _contains_all(text: str, values: tuple[str, ...]) -> list[str]:
    return [value for value in values if value not in text]


def evaluate_v1_external_asset_setup(repo_root: str | Path) -> dict[str, Any]:
    root = Path(repo_root)
    checks = [
        _document_check(
            root / "docs" / "adr" / "0020_v1_external_asset_setup.md",
            evidence="docs/adr/0020_v1_external_asset_setup.md",
        ),
        _diagnostic_source_check(
            root / "src" / "ygo_effect_dsl" / "external" / "asset_setup.py",
            evidence="src/ygo_effect_dsl/external/asset_setup.py",
        ),
        _desktop_bridge_check(
            root,
        ),
        _test_coverage_check(
            root / "tests" / "test_external_asset_setup.py",
            evidence="tests/test_external_asset_setup.py",
        ),
        _allowlist_check(
            root / "docs" / "release" / "evidence" / "v1_0_0_asset_allowlist.json",
            evidence="docs/release/evidence/v1_0_0_asset_allowlist.json",
        ),
    ]
    rejection_reasons = sorted(
        f"{check['id']}:{check['reason']}" for check in checks if not check["passed"]
    )
    identity = to_canonical_data(
        {
            "checks": checks,
            "dependent_features": {
                "card_names": "blocked_until_card_assets_verified",
                "deck_card_options": "blocked_until_card_assets_verified",
                "search_jobs": "blocked_until_core_and_card_assets_verified",
            },
            "guidance": external_asset_setup_guidance(),
            "issue": 358,
            "package_version": __version__,
            "passed": not rejection_reasons,
            "rejection_reasons": rejection_reasons,
            "schema_version": V1_EXTERNAL_ASSET_SETUP_SCHEMA_VERSION,
        }
    )
    return {
        **identity,
        "evidence_id": stable_digest(identity, prefix="v1externalassetsetup_"),
    }


def _document_check(path: Path, *, evidence: str) -> dict[str, Any]:
    check = _check("first_run_policy_documented", evidence)
    if not path.exists():
        check["reason"] = "missing_document"
        return check
    text = path.read_text(encoding="utf-8")
    missing = _contains_all(
        text,
        (
            "first-run UX",
            "external-asset-setup-status",
            "ocgcore-bootstrap",
            "ocgcore-assets-bootstrap",
            "ocgcore-verify",
            "ocgcore-assets-verify",
            "SHA-256",
            "fail closed",
            "does not bundle ocgcore",
            "CardScripts",
            "BabelCDB",
        ),
    )
    if missing:
        check["missing_terms"] = missing
        check["reason"] = "required_terms_missing"
        return check
    check["passed"] = True
    check["reason"] = "verified"
    return check


def _diagnostic_source_check(path: Path, *, evidence: str) -> dict[str, Any]:
    check = _check("cli_status_reports_setup_guidance", evidence)
    if not path.exists():
        check["reason"] = "missing_source"
        return check
    text = path.read_text(encoding="utf-8")
    missing = _contains_all(
        text,
        (
            "external_asset_setup_guidance",
            "describe_external_asset_setup",
            "verify_ocgcore",
            "verify_ocgcore_assets",
            "dependent_features",
            "silent_download_at_runtime",
            "scrape_card_data",
        ),
    )
    if missing:
        check["missing_terms"] = missing
        check["reason"] = "required_terms_missing"
        return check
    check["passed"] = True
    check["reason"] = "verified"
    return check


def _desktop_bridge_check(root: Path) -> dict[str, Any]:
    check = _check(
        "desktop_diagnostics_block_dependent_features",
        "src/ygo_effect_dsl/desktop/service.py",
    )
    service = (root / "src" / "ygo_effect_dsl" / "desktop" / "service.py").read_text(
        encoding="utf-8"
    )
    bridge = (root / "src" / "ygo_effect_dsl" / "desktop" / "static" / "bridge.js").read_text(
        encoding="utf-8"
    )
    contract = (
        root / "src" / "ygo_effect_dsl" / "resources" / "desktop-bridge-v1.json"
    ).read_text(encoding="utf-8")
    combined = "\n".join((service, bridge, contract))
    missing = _contains_all(
        combined,
        (
            "system.external_asset_status",
            "external_assets",
            "card_presentation_source_unavailable",
            "search_job_queue",
            "verified_external_asset_setup_status",
        ),
    )
    if missing:
        check["missing_terms"] = missing
        check["reason"] = "required_terms_missing"
        return check
    check["passed"] = True
    check["reason"] = "verified"
    return check


def _test_coverage_check(path: Path, *, evidence: str) -> dict[str, Any]:
    check = _check("tests_cover_missing_and_invalid_assets", evidence)
    if not path.exists():
        check["reason"] = "missing_tests"
        return check
    text = path.read_text(encoding="utf-8")
    missing = _contains_all(
        text,
        (
            "test_external_asset_status_blocks_features_when_cache_is_missing",
            "test_external_asset_status_reports_ready_after_verified_runtime_and_assets",
            "test_desktop_describe_exposes_external_asset_setup_status",
            "test_v1_external_asset_setup_evidence_passes_current_contract",
            "runtime_integrity_mismatch",
            "card_presentation_source_unavailable",
        ),
    )
    if missing:
        check["missing_terms"] = missing
        check["reason"] = "required_terms_missing"
        return check
    check["passed"] = True
    check["reason"] = "verified"
    return check


def _allowlist_check(path: Path, *, evidence: str) -> dict[str, Any]:
    check = _check("release_artifacts_do_not_bundle_external_assets", evidence)
    if not path.exists():
        check["reason"] = "missing_allowlist"
        return check
    document = json.loads(path.read_text(encoding="utf-8"))
    if document.get("schema_version") != "v1-asset-allowlist-v1":
        check["reason"] = "schema_version_mismatch"
        return check
    if document.get("release_artifact_allowed_third_party_payloads") != []:
        check["reason"] = "third_party_payloads_allowed"
        return check
    rows = document.get("external_local_only_assets")
    if not isinstance(rows, list) or not rows:
        check["reason"] = "external_assets_not_inventoried"
        return check
    included = [row.get("artifact_id") for row in rows if row.get("include_in_release") is not False]
    if included:
        check["included_assets"] = sorted(str(item) for item in included)
        check["reason"] = "external_asset_marked_for_release"
        return check
    check["passed"] = True
    check["reason"] = "verified"
    return check


def _check(check_id: str, evidence: str) -> dict[str, Any]:
    return {
        "evidence": evidence,
        "id": check_id,
        "passed": False,
        "reason": "not_evaluated",
    }


def validate_v1_external_asset_setup(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("v1 external asset setup evidence must be an object")
    document = to_canonical_data(value)
    if not isinstance(document, dict):
        raise ValueError("v1 external asset setup evidence must be an object")
    if document.get("schema_version") != V1_EXTERNAL_ASSET_SETUP_SCHEMA_VERSION:
        raise ValueError("unsupported v1 external asset setup schema_version")
    identity = {key: document[key] for key in document if key != "evidence_id"}
    expected = stable_digest(identity, prefix="v1externalassetsetup_")
    if document.get("evidence_id") != expected:
        raise ValueError("v1 external asset setup evidence_id mismatch")
    checks = document.get("checks")
    if not isinstance(checks, list) or not checks:
        raise ValueError("v1 external asset setup checks must be a list")
    expected_rejections = sorted(
        f"{check['id']}:{check['reason']}" for check in checks if not check["passed"]
    )
    if document.get("rejection_reasons") != expected_rejections:
        raise ValueError("v1 external asset setup rejections are inconsistent")
    if document.get("passed") is not (not expected_rejections):
        raise ValueError("v1 external asset setup passed is inconsistent")
    return document


def read_v1_external_asset_setup(path: str | Path) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    return validate_v1_external_asset_setup(value)


def write_v1_external_asset_setup(
    repo_root: str | Path,
    *,
    output_path: str | Path,
) -> dict[str, Any]:
    document = evaluate_v1_external_asset_setup(repo_root)
    validate_v1_external_asset_setup(document)
    Path(output_path).write_text(
        json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return document
