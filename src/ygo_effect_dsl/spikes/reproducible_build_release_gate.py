from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from ygo_effect_dsl import __version__
from ygo_effect_dsl.engine.canonical import stable_digest, to_canonical_data


V1_BUILD_PROVENANCE_SCHEMA_VERSION = "v1-build-provenance-v1"


def _contains_all(text: str, values: tuple[str, ...]) -> list[str]:
    return [value for value in values if value not in text]


def _check(check_id: str, evidence: str) -> dict[str, Any]:
    return {
        "evidence": evidence,
        "id": check_id,
        "passed": False,
        "reason": "not_evaluated",
    }


def _doc_policy_check(path: Path, *, evidence: str) -> dict[str, Any]:
    check = _check("fixed_build_environment_documented", evidence)
    if not path.exists():
        check["reason"] = "missing_policy_document"
        return check
    missing = _contains_all(
        path.read_text(encoding="utf-8"),
        (
            "SOURCE_DATE_EPOCH",
            ".build-env-primary",
            ".build-env-independent",
            "dependency lock",
            "compiler",
            "build command",
            "SHA-256",
            "attestation",
            "source commit",
            "wheel",
            "sdist",
            "Windows executable",
            "field-level differences",
        ),
    )
    if missing:
        check["missing_terms"] = missing
        check["reason"] = "required_terms_missing"
        return check
    check["passed"] = True
    check["reason"] = "verified"
    return check


def _workflow_check(root: Path) -> dict[str, Any]:
    check = _check(
        "ci_generates_checksums_and_provenance",
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
            "SOURCE_DATE_EPOCH",
            "build_provenance_manifest",
            "release-checksums.json",
            "windows-checksums.json",
            "build-provenance-ubuntu.json",
            "build-provenance-windows.json",
            "dist-primary",
            "dist-independent",
            ".build-env-primary",
            ".build-env-independent",
            "reproducible-build-comparison.json",
            "ygo-effect-dsl-win64-portable.zip",
        ),
    )
    if missing:
        check["missing_terms"] = missing
        check["reason"] = "workflow_provenance_missing"
        return check
    check["passed"] = True
    check["reason"] = "verified"
    return check


def _artifact_composition_check(path: Path, *, evidence: str) -> dict[str, Any]:
    check = _check("artifact_composition_covers_release_artifacts", evidence)
    if not path.exists():
        check["reason"] = "missing_artifact_composition"
        return check
    document = json.loads(path.read_text(encoding="utf-8"))
    if document.get("schema_version") != "v1-release-artifact-composition-v1":
        check["reason"] = "schema_version_mismatch"
        return check
    artifact_kinds = {
        artifact.get("artifact_kind")
        for artifact in document.get("artifacts", [])
        if isinstance(artifact, Mapping)
    }
    required_kinds = {"installer", "sdist", "wheel", "windows_executable"}
    missing_kinds = sorted(required_kinds - artifact_kinds)
    missing_refs: list[str] = []
    for artifact in document.get("artifacts", []):
        if not isinstance(artifact, Mapping):
            continue
        for key in ("asset_allowlist", "notice", "sbom"):
            if not artifact.get(key):
                missing_refs.append(f"{artifact.get('artifact_kind')}:{key}")
    if missing_kinds or missing_refs:
        check["missing_artifact_kinds"] = missing_kinds
        check["missing_refs"] = sorted(missing_refs)
        check["reason"] = "release_artifact_coverage_missing"
        return check
    check["passed"] = True
    check["reason"] = "verified"
    return check


def _manifest_writer_check(path: Path, *, evidence: str) -> dict[str, Any]:
    check = _check("manifest_writer_records_artifact_hashes_and_source", evidence)
    if not path.exists():
        check["reason"] = "missing_manifest_writer"
        return check
    missing = _contains_all(
        path.read_text(encoding="utf-8"),
        (
            "BUILD_PROVENANCE_MANIFEST_SCHEMA_VERSION",
            "sha256",
            "source_date_epoch",
            "github_sha",
            "manifest_id",
            "artifact-checksums-v1",
        ),
    )
    if missing:
        check["missing_terms"] = missing
        check["reason"] = "manifest_fields_missing"
        return check
    check["passed"] = True
    check["reason"] = "verified"
    return check


def _test_coverage_check(path: Path, *, evidence: str) -> dict[str, Any]:
    check = _check("tests_cover_reproducible_build_gate", evidence)
    if not path.exists():
        check["reason"] = "missing_tests"
        return check
    missing = _contains_all(
        path.read_text(encoding="utf-8"),
        (
            "test_build_provenance_manifest_writes_hashes_and_checksums",
            "test_v1_build_provenance_evidence_passes_current_contract",
            "test_committed_v1_build_provenance_matches_current_checkout",
            "test_v1_build_provenance_cli_writes_evidence",
        ),
    )
    if missing:
        check["missing_terms"] = missing
        check["reason"] = "required_tests_missing"
        return check
    check["passed"] = True
    check["reason"] = "verified"
    return check


def evaluate_v1_build_provenance(repo_root: str | Path) -> dict[str, Any]:
    root = Path(repo_root)
    checks = [
        _doc_policy_check(
            root / "docs" / "adr" / "0021_v1_build_provenance.md",
            evidence="docs/adr/0021_v1_build_provenance.md",
        ),
        _workflow_check(root),
        _artifact_composition_check(
            root / "docs" / "release" / "evidence" / "v1_0_0_release_artifact_composition.json",
            evidence="docs/release/evidence/v1_0_0_release_artifact_composition.json",
        ),
        _manifest_writer_check(
            root / "src" / "ygo_effect_dsl" / "spikes" / "build_provenance_manifest.py",
            evidence="src/ygo_effect_dsl/spikes/build_provenance_manifest.py",
        ),
        _test_coverage_check(
            root / "tests" / "test_reproducible_build_release_gate.py",
            evidence="tests/test_reproducible_build_release_gate.py",
        ),
    ]
    rejection_reasons = sorted(
        f"{check['id']}:{check['reason']}" for check in checks if not check["passed"]
    )
    identity = to_canonical_data(
        {
            "checks": checks,
            "issue": 171,
            "package_version": __version__,
            "passed": not rejection_reasons,
            "release_policy": {
                "artifact_kinds": [
                    "wheel",
                    "sdist",
                    "windows_executable",
                    "portable_zip",
                ],
                "checksum_publication": "sha256-json",
                "independent_environment_requirement": (
                    "Ubuntu wheel/sdist builds are produced twice in CI; Windows "
                    "exe/portable artifacts require provenance and release-time "
                    "attestation before publication."
                ),
                "non_reproducible_difference_policy": (
                    "hash differences must be analyzed and explained at field level"
                ),
                "source_traceability": ["source commit", "source tree", "SOURCE_DATE_EPOCH"],
            },
            "rejection_reasons": rejection_reasons,
            "schema_version": V1_BUILD_PROVENANCE_SCHEMA_VERSION,
        }
    )
    return {
        **identity,
        "evidence_id": stable_digest(identity, prefix="v1buildprov_"),
    }


def validate_v1_build_provenance(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("v1 build provenance evidence must be an object")
    document = to_canonical_data(value)
    if not isinstance(document, dict):
        raise ValueError("v1 build provenance evidence must be an object")
    if document.get("schema_version") != V1_BUILD_PROVENANCE_SCHEMA_VERSION:
        raise ValueError("unsupported v1 build provenance schema_version")
    identity = {key: document[key] for key in document if key != "evidence_id"}
    expected = stable_digest(identity, prefix="v1buildprov_")
    if document.get("evidence_id") != expected:
        raise ValueError("v1 build provenance evidence_id mismatch")
    checks = document.get("checks")
    if not isinstance(checks, list) or not checks:
        raise ValueError("v1 build provenance checks must be a list")
    expected_rejections = sorted(
        f"{check['id']}:{check['reason']}" for check in checks if not check["passed"]
    )
    if document.get("rejection_reasons") != expected_rejections:
        raise ValueError("v1 build provenance rejections are inconsistent")
    if document.get("passed") is not (not expected_rejections):
        raise ValueError("v1 build provenance passed is inconsistent")
    return document


def read_v1_build_provenance(path: str | Path) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    return validate_v1_build_provenance(value)


def write_v1_build_provenance(
    repo_root: str | Path,
    *,
    output_path: str | Path,
) -> dict[str, Any]:
    document = evaluate_v1_build_provenance(repo_root)
    validate_v1_build_provenance(document)
    Path(output_path).write_text(
        json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return document
