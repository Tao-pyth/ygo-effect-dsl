from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from ygo_effect_dsl import __version__
from ygo_effect_dsl.engine.canonical import stable_digest, to_canonical_data


V1_SECURITY_THREAT_MODEL_SCHEMA_VERSION = "v1-security-threat-model-v1"

REQUIRED_THREAT_ROWS = (
    "untrusted_ydk_yaml_input",
    "lua_script_path",
    "unsafe_lua_library_option",
    "sqlite_cdb",
    "native_dll",
    "worker_ipc",
    "artifact_import_export",
    "desktop_bridge",
    "github_actions_supply_chain",
)


def _contains_all(text: str, values: tuple[str, ...]) -> list[str]:
    return [value for value in values if value not in text]


def _check(check_id: str, evidence: str) -> dict[str, Any]:
    return {
        "evidence": evidence,
        "id": check_id,
        "passed": False,
        "reason": "not_evaluated",
    }


def _threat_model_doc_check(path: Path, *, evidence: str) -> dict[str, Any]:
    check = _check("v1_threat_model_documents_required_boundaries", evidence)
    if not path.exists():
        check["reason"] = "missing_threat_model"
        return check
    missing = _contains_all(
        path.read_text(encoding="utf-8"),
        (
            "untrusted YDK",
            "YAML",
            "Lua path inputs",
            "SQLite/CDB",
            "native DLL",
            "worker IPC",
            "artifact import/export",
            "GitHub Actions supply chain",
            "trust boundaries",
            "Abuse case",
            "Impact",
            "Mitigation",
            "Residual risk",
            "critical or high risk is a release blocker",
            "dependency",
            "action pinning",
            "vulnerability triage",
            "update cadence",
            "emergency patch",
            "path traversal",
            "resource exhaustion",
            "malformed native payload",
            "unsafe Lua libraries disabled",
            "arbitrary script root",
        ),
    )
    if missing:
        check["missing_terms"] = missing
        check["reason"] = "threat_model_terms_missing"
        return check
    check["passed"] = True
    check["reason"] = "verified"
    return check


def _negative_security_tests_check(root: Path) -> dict[str, Any]:
    check = _check(
        "negative_security_tests_cover_paths_resources_and_native_payloads",
        "tests/test_ocgcore_lifecycle.py;tests/test_ocgcore_lua_qualification.py;tests/test_ocgcore_isolation_spike.py;tests/test_release_audit.py;tests/test_job_recovery.py;src/ygo_effect_dsl/storage/jobs.py",
    )
    paths = (
        root / "tests" / "test_ocgcore_lifecycle.py",
        root / "tests" / "test_ocgcore_lua_qualification.py",
        root / "tests" / "test_ocgcore_isolation_spike.py",
        root / "tests" / "test_release_audit.py",
        root / "tests" / "test_job_recovery.py",
        root / "src" / "ygo_effect_dsl" / "storage" / "jobs.py",
    )
    if any(not path.exists() for path in paths):
        check["reason"] = "missing_security_tests"
        return check
    text = "\n".join(path.read_text(encoding="utf-8") for path in paths)
    missing = _contains_all(
        text,
        (
            "test_filesystem_script_resolution_is_canonical_and_fail_closed",
            "test_card_script_resolution_rejects_ambiguous_directory_matches",
            "../secret.lua",
            "symbolic link",
            "oversized.lua",
            "unsafe Lua libraries",
            "test_ipc_frame_rejects_wrong_schema_and_oversized_payload",
            "test_release_audit_rejects_unsafe_and_link_members",
            "test_release_audit_rejects_oversized_members_without_allowlist",
            "traversal-free",
            "checkpoint payload exceeds the 1 MiB limit",
        ),
    )
    if missing:
        check["missing_terms"] = missing
        check["reason"] = "negative_test_terms_missing"
        return check
    check["passed"] = True
    check["reason"] = "verified"
    return check


def _bridge_and_lua_policy_check(root: Path) -> dict[str, Any]:
    check = _check(
        "unsafe_lua_and_arbitrary_script_roots_remain_disabled",
        "src/ygo_effect_dsl/engine/bridge/ocgcore/types.py;src/ygo_effect_dsl/engine/bridge/ocgcore/providers.py;docs/bridge/20_ocgcore_lifecycle.md;docs/ocgcore/evidence/lua_load_qualification.json",
    )
    paths = (
        root / "src" / "ygo_effect_dsl" / "engine" / "bridge" / "ocgcore" / "types.py",
        root / "src" / "ygo_effect_dsl" / "engine" / "bridge" / "ocgcore" / "providers.py",
        root / "docs" / "bridge" / "20_ocgcore_lifecycle.md",
        root / "docs" / "ocgcore" / "evidence" / "lua_load_qualification.json",
    )
    if any(not path.exists() for path in paths):
        check["reason"] = "missing_bridge_policy_evidence"
        return check
    text = "\n".join(path.read_text(encoding="utf-8") for path in paths)
    missing = _contains_all(
        text,
        (
            "enable_unsafe_libraries",
            "unsafe Lua libraries are disabled by the bridge contract",
            "enableUnsafeLibraries",
            "false",
            "path_traversal",
            "strict_filesystem_resolver",
            "runtime_network_access",
            "CardScripts profile",
        ),
    )
    if missing:
        check["missing_terms"] = missing
        check["reason"] = "bridge_policy_terms_missing"
        return check
    check["passed"] = True
    check["reason"] = "verified"
    return check


def _dependency_and_supply_chain_check(root: Path) -> dict[str, Any]:
    check = _check(
        "dependency_update_and_github_actions_supply_chain_policy_current",
        "pyproject.toml;.github/workflows;docs/adr/0023_v1_gated_release.md;docs/release/evidence/v1_0_0_gated_release.json",
    )
    paths = (
        root / "pyproject.toml",
        root / "docs" / "adr" / "0023_v1_gated_release.md",
        root / "docs" / "release" / "evidence" / "v1_0_0_gated_release.json",
    )
    if any(not path.exists() for path in paths) or not (root / ".github" / "workflows").exists():
        check["reason"] = "missing_dependency_policy_evidence"
        return check
    workflows = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted((root / ".github" / "workflows").glob("*.yml"))
    )
    text = "\n".join(path.read_text(encoding="utf-8") for path in paths) + workflows
    missing = _contains_all(
        text,
        (
            "PyYAML>=6.0",
            "pyarrow==25.0.0",
            "pywebview==6.2.1",
            "actions/checkout@v7",
            "actions/setup-python@v6",
            "actions/upload-artifact@v7",
            "github_actions_runtime_and_pinning_policy_current",
            "protected environment",
            "dry_run",
        ),
    )
    forbidden = [
        value
        for value in (
            "actions/checkout@v3",
            "actions/checkout@v4",
            "actions/setup-python@v4",
            "actions/upload-artifact@v3",
            "actions/upload-artifact@v4",
        )
        if value in workflows
    ]
    if forbidden:
        check["forbidden_terms"] = forbidden
        check["reason"] = "deprecated_action_reference"
        return check
    if missing:
        check["missing_terms"] = missing
        check["reason"] = "dependency_policy_terms_missing"
        return check
    check["passed"] = True
    check["reason"] = "verified"
    return check


def _test_coverage_check(path: Path, *, evidence: str) -> dict[str, Any]:
    check = _check("tests_cover_v1_security_threat_model_gate", evidence)
    if not path.exists():
        check["reason"] = "missing_tests"
        return check
    missing = _contains_all(
        path.read_text(encoding="utf-8"),
        (
            "test_v1_security_threat_model_evidence_passes_current_contract",
            "test_committed_v1_security_threat_model_matches_current_checkout",
            "test_v1_security_threat_model_cli_writes_evidence",
            "test_v1_security_threat_model_blocks_unmitigated_critical_or_high_risk",
        ),
    )
    if missing:
        check["missing_terms"] = missing
        check["reason"] = "required_tests_missing"
        return check
    check["passed"] = True
    check["reason"] = "verified"
    return check


def evaluate_v1_security_threat_model(repo_root: str | Path) -> dict[str, Any]:
    root = Path(repo_root)
    checks = [
        _threat_model_doc_check(
            root / "docs" / "security" / "10_v1_threat_model_dependency_policy.md",
            evidence="docs/security/10_v1_threat_model_dependency_policy.md",
        ),
        _negative_security_tests_check(root),
        _bridge_and_lua_policy_check(root),
        _dependency_and_supply_chain_check(root),
        _test_coverage_check(
            root / "tests" / "test_security_threat_model_release_gate.py",
            evidence="tests/test_security_threat_model_release_gate.py",
        ),
    ]
    rejection_reasons = sorted(
        f"{check['id']}:{check['reason']}" for check in checks if not check["passed"]
    )
    threat_rows = [
        {
            "id": row,
            "release_blocker_if_unmitigated": row in {
                "lua_script_path",
                "unsafe_lua_library_option",
                "native_dll",
                "worker_ipc",
                "github_actions_supply_chain",
            },
            "residual_risk": "medium" if row in {"sqlite_cdb", "native_dll", "github_actions_supply_chain"} else "low",
            "status": "mitigated" if not rejection_reasons else "blocked",
        }
        for row in REQUIRED_THREAT_ROWS
    ]
    unmitigated_blockers = [
        row["id"]
        for row in threat_rows
        if row["release_blocker_if_unmitigated"] and row["status"] != "mitigated"
    ]
    identity = to_canonical_data(
        {
            "checks": checks,
            "issue": 177,
            "package_version": __version__,
            "passed": not rejection_reasons and not unmitigated_blockers,
            "policy": {
                "critical_high_unmitigated_release_blocker": True,
                "dependency_update_cadence": "before_each_release_and_monthly_security_review",
                "emergency_patch_scope": "narrow_dependency_action_asset_or_workflow_fix",
                "unsafe_lua_default": False,
                "arbitrary_script_root_default": False,
            },
            "rejection_reasons": rejection_reasons
            + [f"unmitigated_release_blocker:{row}" for row in unmitigated_blockers],
            "schema_version": V1_SECURITY_THREAT_MODEL_SCHEMA_VERSION,
            "threat_rows": threat_rows,
        }
    )
    return {
        **identity,
        "evidence_id": stable_digest(identity, prefix="v1securitythreat_"),
    }


def validate_v1_security_threat_model(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("v1 security threat model evidence must be an object")
    document = to_canonical_data(value)
    if not isinstance(document, dict):
        raise ValueError("v1 security threat model evidence must be an object")
    if document.get("schema_version") != V1_SECURITY_THREAT_MODEL_SCHEMA_VERSION:
        raise ValueError("unsupported v1 security threat model schema_version")
    identity = {key: document[key] for key in document if key != "evidence_id"}
    expected = stable_digest(identity, prefix="v1securitythreat_")
    if document.get("evidence_id") != expected:
        raise ValueError("v1 security threat model evidence_id mismatch")
    checks = document.get("checks")
    if not isinstance(checks, list) or not checks:
        raise ValueError("v1 security threat model checks must be a list")
    rows = document.get("threat_rows")
    if not isinstance(rows, list):
        raise ValueError("v1 security threat model rows must be a list")
    observed_rows = tuple(row.get("id") for row in rows if isinstance(row, Mapping))
    if observed_rows != REQUIRED_THREAT_ROWS:
        raise ValueError("v1 security threat model rows are inconsistent")
    expected_rejections = sorted(
        f"{check['id']}:{check['reason']}" for check in checks if not check["passed"]
    )
    expected_rejections.extend(
        f"unmitigated_release_blocker:{row['id']}"
        for row in rows
        if row.get("release_blocker_if_unmitigated") is True
        and row.get("status") != "mitigated"
    )
    if document.get("rejection_reasons") != expected_rejections:
        raise ValueError("v1 security threat model rejections are inconsistent")
    if document.get("passed") is not (not expected_rejections):
        raise ValueError("v1 security threat model passed is inconsistent")
    return document


def read_v1_security_threat_model(path: str | Path) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    return validate_v1_security_threat_model(value)


def write_v1_security_threat_model(
    repo_root: str | Path,
    *,
    output_path: str | Path,
) -> dict[str, Any]:
    document = evaluate_v1_security_threat_model(repo_root)
    validate_v1_security_threat_model(document)
    Path(output_path).write_text(
        json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return document
