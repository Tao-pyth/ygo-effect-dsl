from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from ygo_effect_dsl import __version__
from ygo_effect_dsl.engine.canonical import stable_digest, to_canonical_data


V1_UPGRADE_ROLLBACK_SCHEMA_VERSION = "v1-upgrade-rollback-v1"

REQUIRED_MATRIX_ROWS = (
    "clean_install",
    "0.5_to_1.0_upgrade",
    "1.0_patch_upgrade",
    "rollback",
    "uninstall_reinstall",
    "offline_runtime",
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


def _policy_doc_check(path: Path, *, evidence: str) -> dict[str, Any]:
    check = _check("upgrade_rollback_matrix_documented", evidence)
    if not path.exists():
        check["reason"] = "missing_policy_document"
        return check
    text = path.read_text(encoding="utf-8")
    missing = _contains_all(
        text,
        (
            "clean_install",
            "0.5_to_1.0_upgrade",
            "1.0_patch_upgrade",
            "rollback",
            "uninstall_reinstall",
            "offline_runtime",
            "editable install",
            "parent/worker subprocess",
            "user cache/config/evidence",
            "pre-migration backup",
            "explicit confirmation",
            "owned cache resolver",
        ),
    )
    if missing:
        check["missing_terms"] = missing
        check["reason"] = "required_terms_missing"
        return check
    check["passed"] = True
    check["reason"] = "verified"
    return check


def _portable_readme_check(path: Path, *, evidence: str) -> dict[str, Any]:
    check = _check("portable_package_has_manual_upgrade_and_rollback", evidence)
    if not path.exists():
        check["reason"] = "missing_readme"
        return check
    missing = _contains_all(
        path.read_text(encoding="utf-8"),
        (
            "Install",
            "Clean install",
            "Upgrade",
            "Patch upgrade",
            "Rollback",
            "Uninstall",
            "Reinstall",
            "Offline runtime",
            "User data, external assets, caches, logs, and evidence",
            "backup",
            "explicit confirmation",
            "No third-party card assets",
        ),
    )
    if missing:
        check["missing_terms"] = missing
        check["reason"] = "required_terms_missing"
        return check
    check["passed"] = True
    check["reason"] = "verified"
    return check


def _ci_smoke_check(root: Path) -> dict[str, Any]:
    check = _check(
        "ci_smokes_clean_wheel_and_windows_executable_without_editable_install",
        ".github/workflows/test.yml;.github/workflows/build-windows-exe.yml",
    )
    test_workflow = root / ".github" / "workflows" / "test.yml"
    windows_workflow = root / ".github" / "workflows" / "build-windows-exe.yml"
    if not test_workflow.exists() or not windows_workflow.exists():
        check["reason"] = "missing_workflow"
        return check
    combined = "\n".join(
        (
            test_workflow.read_text(encoding="utf-8"),
            windows_workflow.read_text(encoding="utf-8"),
        )
    )
    missing = _contains_all(
        combined,
        (
            "python -m venv .release-venv",
            ".release-venv/bin/python -m pip install dist-primary/*.whl",
            ".release-venv/bin/python -m ygo_effect_dsl --version",
            ".\\dist\\ygo-effect-dsl.exe --version",
            ".\\dist\\ygo-effect-dsl-desktop.exe --version",
            "Expand-Archive ygo-effect-dsl-win64-portable.zip",
            ".\\package_smoke\\ygo-effect-dsl-win64\\ygo-effect-dsl.exe --version",
            ".\\package_smoke\\ygo-effect-dsl-win64\\ygo-effect-dsl-desktop.exe --version",
        ),
    )
    if missing:
        check["missing_terms"] = missing
        check["reason"] = "workflow_smoke_missing"
        return check
    check["passed"] = True
    check["reason"] = "verified"
    return check


def _import_consistency_check(root: Path) -> dict[str, Any]:
    check = _check(
        "parent_worker_subprocess_import_source_consistency_tested",
        "src/ygo_effect_dsl/runtime_imports.py;tests/test_runtime_imports.py;src/ygo_effect_dsl/desktop/lifecycle.py",
    )
    paths = {
        "runtime": root / "src" / "ygo_effect_dsl" / "runtime_imports.py",
        "tests": root / "tests" / "test_runtime_imports.py",
        "lifecycle": root / "src" / "ygo_effect_dsl" / "desktop" / "lifecycle.py",
    }
    if any(not path.exists() for path in paths.values()):
        check["reason"] = "missing_source_or_tests"
        return check
    combined = "\n".join(path.read_text(encoding="utf-8") for path in paths.values())
    missing = _contains_all(
        combined,
        (
            "current_checkout_environment",
            "package_source_root",
            "test_child_python_imports_the_same_checkout",
            "sys.executable",
            "-m",
            "ygo_effect_dsl",
        ),
    )
    if missing:
        check["missing_terms"] = missing
        check["reason"] = "import_consistency_terms_missing"
        return check
    check["passed"] = True
    check["reason"] = "verified"
    return check


def _asset_policy_check(root: Path) -> dict[str, Any]:
    check = _check(
        "external_assets_remain_owned_cache_not_bundled",
        "docs/release/evidence/v1_0_0_asset_allowlist.json;packaging/windows-portable/README.txt",
    )
    allowlist_path = root / "docs" / "release" / "evidence" / "v1_0_0_asset_allowlist.json"
    readme_path = root / "packaging" / "windows-portable" / "README.txt"
    if not allowlist_path.exists() or not readme_path.exists():
        check["reason"] = "missing_asset_policy"
        return check
    allowlist = json.loads(allowlist_path.read_text(encoding="utf-8"))
    if allowlist.get("schema_version") != "v1-asset-allowlist-v1":
        check["reason"] = "schema_version_mismatch"
        return check
    if allowlist.get("release_artifact_allowed_third_party_payloads") != []:
        check["reason"] = "third_party_payloads_allowed"
        return check
    missing = _contains_all(
        readme_path.read_text(encoding="utf-8"),
        (
            "owned cache resolver",
            "No third-party card assets",
            "does not include ocgcore binaries",
            "does not include",
        ),
    )
    if missing:
        check["missing_terms"] = missing
        check["reason"] = "asset_guidance_missing"
        return check
    check["passed"] = True
    check["reason"] = "verified"
    return check


def evaluate_v1_upgrade_rollback(repo_root: str | Path) -> dict[str, Any]:
    root = Path(repo_root)
    checks = [
        _policy_doc_check(
            root / "docs" / "adr" / "0022_v1_upgrade_rollback.md",
            evidence="docs/adr/0022_v1_upgrade_rollback.md",
        ),
        _portable_readme_check(
            root / "packaging" / "windows-portable" / "README.txt",
            evidence="packaging/windows-portable/README.txt",
        ),
        _ci_smoke_check(root),
        _import_consistency_check(root),
        _asset_policy_check(root),
    ]
    rejection_reasons = sorted(
        f"{check['id']}:{check['reason']}" for check in checks if not check["passed"]
    )
    matrix = [
        {
            "id": row,
            "rollback_requires_backup": row in {"0.5_to_1.0_upgrade", "rollback"},
            "status": "verified" if not rejection_reasons else "blocked",
        }
        for row in REQUIRED_MATRIX_ROWS
    ]
    identity = to_canonical_data(
        {
            "checks": checks,
            "issue": 172,
            "matrix": matrix,
            "package_version": __version__,
            "passed": not rejection_reasons,
            "release_policy": {
                "automatic_update": False,
                "editable_install_dependency": False,
                "external_assets_bundled": False,
                "irreversible_migration_requires": [
                    "pre-migration backup",
                    "explicit confirmation",
                ],
                "upgrade_channel": "manual",
            },
            "rejection_reasons": rejection_reasons,
            "schema_version": V1_UPGRADE_ROLLBACK_SCHEMA_VERSION,
        }
    )
    return {
        **identity,
        "evidence_id": stable_digest(identity, prefix="v1upgraderollback_"),
    }


def validate_v1_upgrade_rollback(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("v1 upgrade rollback evidence must be an object")
    document = to_canonical_data(value)
    if not isinstance(document, dict):
        raise ValueError("v1 upgrade rollback evidence must be an object")
    if document.get("schema_version") != V1_UPGRADE_ROLLBACK_SCHEMA_VERSION:
        raise ValueError("unsupported v1 upgrade rollback schema_version")
    identity = {key: document[key] for key in document if key != "evidence_id"}
    expected = stable_digest(identity, prefix="v1upgraderollback_")
    if document.get("evidence_id") != expected:
        raise ValueError("v1 upgrade rollback evidence_id mismatch")
    checks = document.get("checks")
    if not isinstance(checks, list) or not checks:
        raise ValueError("v1 upgrade rollback checks must be a list")
    matrix = document.get("matrix")
    if not isinstance(matrix, list):
        raise ValueError("v1 upgrade rollback matrix must be a list")
    observed_rows = tuple(row.get("id") for row in matrix if isinstance(row, Mapping))
    if observed_rows != REQUIRED_MATRIX_ROWS:
        raise ValueError("v1 upgrade rollback matrix rows are inconsistent")
    expected_rejections = sorted(
        f"{check['id']}:{check['reason']}" for check in checks if not check["passed"]
    )
    if document.get("rejection_reasons") != expected_rejections:
        raise ValueError("v1 upgrade rollback rejections are inconsistent")
    if document.get("passed") is not (not expected_rejections):
        raise ValueError("v1 upgrade rollback passed is inconsistent")
    return document


def read_v1_upgrade_rollback(path: str | Path) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    return validate_v1_upgrade_rollback(value)


def write_v1_upgrade_rollback(
    repo_root: str | Path,
    *,
    output_path: str | Path,
) -> dict[str, Any]:
    document = evaluate_v1_upgrade_rollback(repo_root)
    validate_v1_upgrade_rollback(document)
    Path(output_path).write_text(
        json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return document
