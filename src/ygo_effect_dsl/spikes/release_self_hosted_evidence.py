from __future__ import annotations

from collections.abc import Mapping
import hashlib
import json
from pathlib import Path
from typing import Any

from ygo_effect_dsl.engine.canonical import stable_digest, to_canonical_data
from ygo_effect_dsl.io_atomic import atomic_write_text
from ygo_effect_dsl.spikes.parallel_search_release_gate import (
    read_parallel_search_release_gate,
    read_parallel_search_release_records,
)
from ygo_effect_dsl.spikes.research_dashboard_release_gate import (
    read_research_dashboard_release_gate,
    validate_research_dashboard_qualification,
)


RELEASE_SELF_HOSTED_EVIDENCE_SCHEMA_VERSION = "release-self-hosted-evidence-v1"
RELEASE_SELF_HOSTED_EVIDENCE_AUDIT_SCHEMA_VERSION = (
    "release-self-hosted-evidence-audit-v1"
)
RELEASE_SELF_HOSTED_EVIDENCE_VERIFICATION_SCHEMA_VERSION = (
    "release-self-hosted-evidence-verification-v1"
)
ALLOWED_RELEASE_SELF_HOSTED_ARTIFACTS = frozenset(
    {
        "parallel_search_gate.json",
        "parallel_search_records.json",
        "research_dashboard_gate.json",
        "research_dashboard_qualification.json",
        "summary.json",
    }
)
ADOPTED_RELEASE_SELF_HOSTED_ARTIFACTS = frozenset(
    ALLOWED_RELEASE_SELF_HOSTED_ARTIFACTS - {"summary.json"}
)


def _read_json_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path.name} must contain a JSON object")
    return value


def _validate_summary(summary: Mapping[str, Any]) -> dict[str, Any]:
    normalized = to_canonical_data(summary)
    if not isinstance(normalized, dict):
        raise ValueError("release self-hosted summary must be an object")
    if normalized.get("schema_version") != RELEASE_SELF_HOSTED_EVIDENCE_SCHEMA_VERSION:
        raise ValueError("unsupported release self-hosted summary schema_version")
    status = normalized.get("status")
    if status not in {"success", "failure", "cancelled", "skipped"}:
        raise ValueError("release self-hosted summary status is invalid")
    commit = normalized.get("commit")
    if not isinstance(commit, str) or not commit:
        raise ValueError("release self-hosted summary commit is invalid")
    run_id = normalized.get("run_id")
    if not isinstance(run_id, str) or not run_id:
        raise ValueError("release self-hosted summary run_id is invalid")
    for key in ("parallel_search", "research_dashboard"):
        value = normalized.get(key)
        if value not in {"true", "false"}:
            raise ValueError(f"release self-hosted summary {key} flag is invalid")
    return normalized


def _validate_audit_summary(summary: Any) -> dict[str, Any]:
    normalized = to_canonical_data(summary)
    if not isinstance(normalized, dict):
        raise ValueError("release self-hosted audit summary must be an object")
    status = normalized.get("status")
    if status not in {"success", "failure", "cancelled", "skipped"}:
        raise ValueError("release self-hosted audit summary status is invalid")
    commit = normalized.get("commit")
    if not isinstance(commit, str) or not commit:
        raise ValueError("release self-hosted audit summary commit is invalid")
    run_id = normalized.get("run_id")
    if not isinstance(run_id, str) or not run_id:
        raise ValueError("release self-hosted audit summary run_id is invalid")
    for key in ("parallel_search", "research_dashboard"):
        value = normalized.get(key)
        if value not in {"true", "false"}:
            raise ValueError(f"release self-hosted audit summary {key} flag is invalid")
    return normalized


def _validate_branch_audit(name: str, value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    normalized = to_canonical_data(value)
    if not isinstance(normalized, dict):
        raise ValueError(f"release self-hosted audit {name} branch must be an object")
    if name == "parallel-search":
        expected_keys = {
            "gate_evidence_id",
            "passed",
            "record_count",
            "records_evidence_id",
        }
        gate_prefix = "parsearchgate_"
        source_id_key = "records_evidence_id"
        source_prefix = "parsearchrecords_"
        count_key = "record_count"
    elif name == "research-dashboard":
        expected_keys = {
            "gate_evidence_id",
            "passed",
            "qualification_evidence_id",
            "required_check_count",
        }
        gate_prefix = "researchdashgate_"
        source_id_key = "qualification_evidence_id"
        source_prefix = "researchdashqual_"
        count_key = "required_check_count"
    else:
        raise ValueError(f"release self-hosted audit {name} branch name is invalid")
    if set(normalized) != expected_keys:
        raise ValueError(f"release self-hosted audit {name} branch keys are invalid")
    gate_evidence_id = normalized.get("gate_evidence_id")
    if (
        not isinstance(gate_evidence_id, str)
        or not gate_evidence_id.startswith(gate_prefix)
    ):
        raise ValueError(f"release self-hosted audit {name} gate_evidence_id is invalid")
    if normalized.get("passed") not in {True, False}:
        raise ValueError(f"release self-hosted audit {name} passed flag is invalid")
    source_evidence_id = normalized.get(source_id_key)
    if (
        not isinstance(source_evidence_id, str)
        or not source_evidence_id.startswith(source_prefix)
    ):
        raise ValueError(
            f"release self-hosted audit {name} source evidence_id is invalid"
        )
    count = normalized.get(count_key)
    if not isinstance(count, int) or count < 0:
        raise ValueError(f"release self-hosted audit {name} count is invalid")
    if normalized["passed"] is True and count < 1:
        raise ValueError(
            f"release self-hosted audit {name} passed branch count is invalid"
        )
    return normalized


def _validate_release_self_hosted_evidence_audit(
    audit: Mapping[str, Any],
) -> dict[str, Any]:
    normalized = to_canonical_data(audit)
    if not isinstance(normalized, dict):
        raise ValueError("release self-hosted evidence audit must be an object")
    if normalized.get("schema_version") != RELEASE_SELF_HOSTED_EVIDENCE_AUDIT_SCHEMA_VERSION:
        raise ValueError("unsupported release self-hosted evidence audit schema_version")
    evidence_id = normalized.get("evidence_id")
    if not isinstance(evidence_id, str) or not evidence_id.startswith(
        "releaseevidenceaudit_"
    ):
        raise ValueError("release self-hosted evidence audit evidence_id is invalid")
    identity = dict(normalized)
    identity.pop("evidence_id", None)
    if stable_digest(identity, prefix="releaseevidenceaudit_") != evidence_id:
        raise ValueError("release self-hosted evidence audit evidence_id mismatch")
    artifact_files = _validate_artifact_file_list(
        normalized.get("artifact_files"),
        name="artifact_files",
        allowed=ADOPTED_RELEASE_SELF_HOSTED_ARTIFACTS,
    )
    source_artifact_files = _validate_artifact_file_list(
        normalized.get("source_artifact_files"),
        name="source_artifact_files",
        allowed=ALLOWED_RELEASE_SELF_HOSTED_ARTIFACTS,
    )
    if "summary.json" not in source_artifact_files:
        raise ValueError(
            "release self-hosted evidence audit source_artifact_files must include "
            "summary.json"
        )
    if any(item not in source_artifact_files for item in artifact_files):
        raise ValueError(
            "release self-hosted evidence audit source_artifact_files does not "
            "cover artifact_files"
        )
    summary = _validate_audit_summary(normalized.get("summary"))
    parallel = _validate_branch_audit(
        "parallel-search",
        normalized.get("parallel_search"),
    )
    research = _validate_branch_audit(
        "research-dashboard",
        normalized.get("research_dashboard"),
    )
    if parallel is not None and summary["parallel_search"] != "true":
        raise ValueError(
            "release self-hosted evidence audit parallel-search branch contradicts "
            "summary"
        )
    if research is not None and summary["research_dashboard"] != "true":
        raise ValueError(
            "release self-hosted evidence audit research-dashboard branch contradicts "
            "summary"
        )
    return {
        **normalized,
        "artifact_files": artifact_files,
        "parallel_search": parallel,
        "research_dashboard": research,
        "source_artifact_files": source_artifact_files,
        "summary": summary,
    }


def _validate_artifact_file_list(
    value: Any,
    *,
    name: str,
    allowed: frozenset[str],
) -> list[str]:
    if (
        not isinstance(value, list)
        or any(not isinstance(item, str) or not item for item in value)
        or value != sorted(value)
        or len(value) != len(set(value))
        or any(item not in allowed for item in value)
    ):
        raise ValueError(f"release self-hosted evidence audit {name} is invalid")
    return value


def _validate_verification_requirements(value: Any) -> dict[str, Any]:
    normalized = to_canonical_data(value)
    if not isinstance(normalized, dict):
        raise ValueError("release self-hosted evidence verification requirements invalid")
    expected_keys = {
        "expected_commit",
        "expected_run_id",
        "require_parallel_search",
        "require_research_dashboard",
    }
    if set(normalized) != expected_keys:
        raise ValueError(
            "release self-hosted evidence verification requirements keys invalid"
        )
    for key in ("expected_commit", "expected_run_id"):
        current = normalized[key]
        if current is not None and (not isinstance(current, str) or not current):
            raise ValueError(
                f"release self-hosted evidence verification {key} invalid"
            )
    for key in ("require_parallel_search", "require_research_dashboard"):
        if normalized[key] not in {True, False}:
            raise ValueError(
                f"release self-hosted evidence verification {key} invalid"
            )
    return normalized


def _validate_verification_file_list(value: Any) -> list[str]:
    allowed = ADOPTED_RELEASE_SELF_HOSTED_ARTIFACTS | {
        "release_self_hosted_evidence_audit.json"
    }
    if (
        not isinstance(value, list)
        or any(not isinstance(item, str) or not item for item in value)
        or value != sorted(value)
        or len(value) != len(set(value))
        or any(item not in allowed for item in value)
        or "release_self_hosted_evidence_audit.json" not in value
    ):
        raise ValueError(
            "release self-hosted evidence verification verified_files invalid"
        )
    return value


def _validate_verification_file_sha256(
    value: Any,
    *,
    verified_files: list[str],
) -> dict[str, str]:
    normalized = to_canonical_data(value)
    if not isinstance(normalized, dict):
        raise ValueError(
            "release self-hosted evidence verification verified_file_sha256 invalid"
        )
    if set(normalized) != set(verified_files):
        raise ValueError(
            "release self-hosted evidence verification verified_file_sha256 keys invalid"
        )
    for filename, digest in normalized.items():
        if (
            not isinstance(filename, str)
            or not isinstance(digest, str)
            or len(digest) != 64
            or any(char not in "0123456789abcdef" for char in digest)
        ):
            raise ValueError(
                "release self-hosted evidence verification verified_file_sha256 "
                "digest invalid"
            )
    return {key: normalized[key] for key in sorted(normalized)}


def _validate_no_unexpected_artifacts(root: Path) -> list[str]:
    unexpected_directories = sorted(item.name for item in root.iterdir() if item.is_dir())
    if unexpected_directories:
        raise ValueError(
            "release self-hosted artifact directory contains unexpected directories: "
            f"{unexpected_directories}"
        )
    unexpected = sorted(
        item.name
        for item in root.iterdir()
        if item.is_file() and item.name not in ALLOWED_RELEASE_SELF_HOSTED_ARTIFACTS
    )
    if unexpected:
        raise ValueError(
            "release self-hosted artifact directory contains unexpected files: "
            f"{unexpected}"
        )
    return sorted(
        item.name
        for item in root.iterdir()
        if item.is_file() and item.name in ALLOWED_RELEASE_SELF_HOSTED_ARTIFACTS
    )


def _content_addressed_audit_document(identity: Mapping[str, Any]) -> dict[str, Any]:
    document = to_canonical_data(identity)
    if not isinstance(document, dict):
        raise ValueError("release self-hosted evidence audit identity is invalid")
    return {
        **document,
        "evidence_id": stable_digest(document, prefix="releaseevidenceaudit_"),
    }


def _parallel_search_audit(root: Path, *, require_passed: bool) -> dict[str, Any]:
    records_path = root / "parallel_search_records.json"
    gate_path = root / "parallel_search_gate.json"
    if not records_path.exists() or not gate_path.exists():
        raise ValueError("parallel-search evidence requires records and gate JSON")
    records = read_parallel_search_release_records(records_path)
    gate = read_parallel_search_release_gate(gate_path)
    bundle = gate.get("record_bundle")
    if (
        not isinstance(bundle, Mapping)
        or bundle.get("evidence_id") != records.get("evidence_id")
        or bundle.get("record_count") != len(records.get("records", ()))
    ):
        raise ValueError("parallel-search gate does not match records bundle")
    if require_passed and gate.get("passed") is not True:
        raise ValueError("parallel-search release gate did not pass")
    return {
        "gate_evidence_id": gate["evidence_id"],
        "passed": gate["passed"],
        "record_count": len(records["records"]),
        "records_evidence_id": records["evidence_id"],
    }


def _research_dashboard_audit(root: Path, *, require_passed: bool) -> dict[str, Any]:
    qualification_path = root / "research_dashboard_qualification.json"
    gate_path = root / "research_dashboard_gate.json"
    if not qualification_path.exists() or not gate_path.exists():
        raise ValueError("research-dashboard evidence requires qualification and gate JSON")
    qualification = validate_research_dashboard_qualification(
        _read_json_object(qualification_path)
    )
    gate = read_research_dashboard_release_gate(gate_path)
    manual_checks = gate.get("manual_checks")
    if not isinstance(manual_checks, list) or len(manual_checks) != 1:
        raise ValueError("research-dashboard gate manual check is invalid")
    manual = manual_checks[0]
    manual_evidence = manual.get("evidence")
    if (
        not isinstance(manual_evidence, Mapping)
        or manual_evidence.get("evidence_id") != qualification.get("evidence_id")
        or manual.get("passed") != qualification.get("passed")
    ):
        raise ValueError("research-dashboard gate does not match qualification")
    if require_passed and gate.get("passed") is not True:
        raise ValueError("research-dashboard release gate did not pass")
    return {
        "gate_evidence_id": gate["evidence_id"],
        "passed": gate["passed"],
        "qualification_evidence_id": qualification["evidence_id"],
        "required_check_count": len(qualification["checks"]),
    }


def _reject_unadopted_passing_branch_evidence(
    root: Path,
    audit: Mapping[str, Any],
) -> None:
    if audit.get("parallel_search") is None and (
        root / "parallel_search_records.json"
    ).exists() and (root / "parallel_search_gate.json").exists():
        try:
            parallel = _parallel_search_audit(root, require_passed=False)
        except ValueError as exc:
            raise ValueError(
                "unadopted parallel-search evidence is invalid"
            ) from exc
        if parallel["passed"] is True:
            raise ValueError(
                "unadopted passing parallel-search evidence is not recorded in audit"
            )
    if audit.get("research_dashboard") is None and (
        root / "research_dashboard_qualification.json"
    ).exists() and (root / "research_dashboard_gate.json").exists():
        try:
            research = _research_dashboard_audit(root, require_passed=False)
        except ValueError as exc:
            raise ValueError(
                "unadopted research-dashboard evidence is invalid"
            ) from exc
        if research["passed"] is True:
            raise ValueError(
                "unadopted passing research-dashboard evidence is not recorded in audit"
            )


def audit_release_self_hosted_evidence(
    artifact_dir: str | Path,
    *,
    expected_commit: str | None = None,
    expected_run_id: str | None = None,
    require_parallel_search: bool = False,
    require_research_dashboard: bool = False,
) -> dict[str, Any]:
    root = Path(artifact_dir)
    if not root.is_dir():
        raise ValueError("release self-hosted artifact_dir must be a directory")
    files = _validate_no_unexpected_artifacts(root)
    summary_path = root / "summary.json"
    if not summary_path.exists():
        raise ValueError("release self-hosted artifact summary.json is required")
    summary = _validate_summary(_read_json_object(summary_path))
    if expected_commit is not None and summary.get("commit") != expected_commit:
        raise ValueError("release self-hosted summary commit does not match expected")
    if expected_run_id is not None and summary.get("run_id") != expected_run_id:
        raise ValueError("release self-hosted summary run_id does not match expected")
    if (require_parallel_search or require_research_dashboard) and (
        summary.get("status") != "success"
    ):
        raise ValueError("release self-hosted workflow summary did not succeed")
    if require_parallel_search and summary.get("parallel_search") != "true":
        raise ValueError("release self-hosted summary did not run parallel-search branch")
    if require_research_dashboard and summary.get("research_dashboard") != "true":
        raise ValueError(
            "release self-hosted summary did not run research-dashboard branch"
        )
    parallel = None
    if require_parallel_search or summary.get("parallel_search") == "true":
        parallel = _parallel_search_audit(root, require_passed=require_parallel_search)
    research = None
    if require_research_dashboard or summary.get("research_dashboard") == "true":
        research = _research_dashboard_audit(
            root,
            require_passed=require_research_dashboard,
        )
    identity = {
        "artifact_files": sorted(item for item in files if item != "summary.json"),
        "parallel_search": parallel,
        "research_dashboard": research,
        "schema_version": RELEASE_SELF_HOSTED_EVIDENCE_AUDIT_SCHEMA_VERSION,
        "source_artifact_files": files,
        "summary": {
            "commit": summary["commit"],
            "parallel_search": summary["parallel_search"],
            "research_dashboard": summary["research_dashboard"],
            "run_id": summary["run_id"],
            "status": summary["status"],
        },
    }
    return _content_addressed_audit_document(identity)


def write_release_self_hosted_evidence_audit(
    artifact_dir: str | Path,
    *,
    expected_commit: str | None = None,
    expected_run_id: str | None = None,
    output_path: str | Path,
    require_parallel_search: bool = False,
    require_research_dashboard: bool = False,
) -> dict[str, Any]:
    document = audit_release_self_hosted_evidence(
        artifact_dir,
        expected_commit=expected_commit,
        expected_run_id=expected_run_id,
        require_parallel_search=require_parallel_search,
        require_research_dashboard=require_research_dashboard,
    )
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(destination, json.dumps(document, indent=2, sort_keys=True) + "\n")
    return document


def _copy_json_artifact(source: Path, destination: Path) -> None:
    value = _read_json_object(source)
    destination.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(
        destination,
        json.dumps(value, indent=2, sort_keys=True) + "\n",
    )


def _selected_adoption_audit(
    audit: Mapping[str, Any],
    *,
    adopt_parallel_search: bool,
    adopt_research_dashboard: bool,
    existing_audit: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    artifact_files: list[str] = []
    parallel = None
    if adopt_parallel_search:
        parallel = audit["parallel_search"]
        artifact_files.extend(["parallel_search_gate.json", "parallel_search_records.json"])
    elif existing_audit is not None and existing_audit.get("parallel_search") is not None:
        if existing_audit["summary"] != audit["summary"]:
            raise ValueError(
                "existing adopted parallel-search evidence uses a different "
                "workflow identity"
            )
        parallel = existing_audit["parallel_search"]
        artifact_files.extend(["parallel_search_gate.json", "parallel_search_records.json"])
    research = None
    if adopt_research_dashboard:
        research = audit["research_dashboard"]
        artifact_files.extend(
            ["research_dashboard_gate.json", "research_dashboard_qualification.json"]
        )
    elif (
        existing_audit is not None
        and existing_audit.get("research_dashboard") is not None
    ):
        if existing_audit["summary"] != audit["summary"]:
            raise ValueError(
                "existing adopted research-dashboard evidence uses a different "
                "workflow identity"
            )
        research = existing_audit["research_dashboard"]
        artifact_files.extend(
            ["research_dashboard_gate.json", "research_dashboard_qualification.json"]
        )
    identity = {
        "artifact_files": sorted(artifact_files),
        "parallel_search": parallel,
        "research_dashboard": research,
        "schema_version": RELEASE_SELF_HOSTED_EVIDENCE_AUDIT_SCHEMA_VERSION,
        "source_artifact_files": audit["source_artifact_files"],
        "summary": audit["summary"],
    }
    return _content_addressed_audit_document(identity)


def adopt_release_self_hosted_evidence(
    artifact_dir: str | Path,
    *,
    expected_commit: str | None = None,
    expected_run_id: str | None = None,
    output_dir: str | Path,
    adopt_parallel_search: bool = False,
    adopt_research_dashboard: bool = False,
) -> dict[str, Any]:
    if not adopt_parallel_search and not adopt_research_dashboard:
        raise ValueError("at least one release self-hosted evidence branch must be adopted")
    audit = audit_release_self_hosted_evidence(
        artifact_dir,
        expected_commit=expected_commit,
        expected_run_id=expected_run_id,
        require_parallel_search=adopt_parallel_search,
        require_research_dashboard=adopt_research_dashboard,
    )
    root = Path(artifact_dir)
    destination = Path(output_dir)
    audit_path = destination / "release_self_hosted_evidence_audit.json"
    existing_audit = None
    if audit_path.exists():
        verify_adopted_release_self_hosted_evidence(
            destination,
            expected_commit=None,
            expected_run_id=None,
            require_parallel_search=False,
            require_research_dashboard=False,
        )
        existing_audit = _validate_release_self_hosted_evidence_audit(
            _read_json_object(audit_path)
        )
    adopted_audit = _selected_adoption_audit(
        audit,
        adopt_parallel_search=adopt_parallel_search,
        adopt_research_dashboard=adopt_research_dashboard,
        existing_audit=existing_audit,
    )
    _reject_unadopted_passing_branch_evidence(destination, adopted_audit)
    copied: list[str] = []
    if adopt_parallel_search:
        for name in ("parallel_search_records.json", "parallel_search_gate.json"):
            _copy_json_artifact(root / name, destination / name)
            copied.append(name)
    if adopt_research_dashboard:
        for name in ("research_dashboard_qualification.json", "research_dashboard_gate.json"):
            _copy_json_artifact(root / name, destination / name)
            copied.append(name)
    atomic_write_text(
        audit_path,
        json.dumps(adopted_audit, indent=2, sort_keys=True) + "\n",
    )
    copied.append(audit_path.name)
    verification = verify_adopted_release_self_hosted_evidence(
        destination,
        expected_commit=expected_commit,
        expected_run_id=expected_run_id,
        require_parallel_search=adopt_parallel_search,
        require_research_dashboard=adopt_research_dashboard,
    )
    return {
        **adopted_audit,
        "adoption_verification": {
            "evidence_id": verification["evidence_id"],
            "requirements": verification["requirements"],
            "verified_file_sha256": verification["verified_file_sha256"],
            "verified_files": verification["verified_files"],
        },
        "adopted_files": copied,
    }


def verify_adopted_release_self_hosted_evidence(
    evidence_dir: str | Path,
    *,
    expected_commit: str | None = None,
    expected_run_id: str | None = None,
    require_parallel_search: bool = False,
    require_research_dashboard: bool = False,
) -> dict[str, Any]:
    root = Path(evidence_dir)
    if not root.is_dir():
        raise ValueError("release self-hosted evidence_dir must be a directory")
    audit_path = root / "release_self_hosted_evidence_audit.json"
    if not audit_path.exists():
        raise ValueError("release self-hosted adopted evidence audit is required")
    audit = _validate_release_self_hosted_evidence_audit(_read_json_object(audit_path))
    summary = audit["summary"]
    if expected_commit is not None and summary.get("commit") != expected_commit:
        raise ValueError("release self-hosted audit commit does not match expected")
    if expected_run_id is not None and summary.get("run_id") != expected_run_id:
        raise ValueError("release self-hosted audit run_id does not match expected")

    verified_files = [audit_path.name]
    parallel = None
    if audit.get("parallel_search") is not None:
        parallel = _parallel_search_audit(
            root,
            require_passed=require_parallel_search,
        )
        if parallel != audit["parallel_search"]:
            raise ValueError("adopted parallel-search evidence does not match audit")
        verified_files.extend(["parallel_search_gate.json", "parallel_search_records.json"])
    elif require_parallel_search:
        raise ValueError(
            "adopted release evidence does not include parallel-search branch"
        )

    research = None
    if audit.get("research_dashboard") is not None:
        research = _research_dashboard_audit(
            root,
            require_passed=require_research_dashboard,
        )
        if research != audit["research_dashboard"]:
            raise ValueError("adopted research-dashboard evidence does not match audit")
        verified_files.extend(
            ["research_dashboard_gate.json", "research_dashboard_qualification.json"]
        )
    elif require_research_dashboard:
        raise ValueError(
            "adopted release evidence does not include research-dashboard branch"
        )

    verified_artifacts = sorted(
        name for name in verified_files if name != audit_path.name
    )
    if verified_artifacts != audit["artifact_files"]:
        raise ValueError("adopted release evidence files do not match audit")
    _reject_unadopted_passing_branch_evidence(root, audit)
    verified_file_sha256 = {
        name: hashlib.sha256((root / name).read_bytes()).hexdigest()
        for name in sorted(verified_files)
    }

    identity = {
        "audit_evidence_id": audit["evidence_id"],
        "parallel_search": parallel,
        "requirements": {
            "expected_commit": expected_commit,
            "expected_run_id": expected_run_id,
            "require_parallel_search": require_parallel_search,
            "require_research_dashboard": require_research_dashboard,
        },
        "research_dashboard": research,
        "schema_version": RELEASE_SELF_HOSTED_EVIDENCE_VERIFICATION_SCHEMA_VERSION,
        "summary": summary,
        "verified_file_sha256": verified_file_sha256,
        "verified_files": sorted(verified_files),
    }
    document = to_canonical_data(identity)
    return {
        **document,
        "evidence_id": stable_digest(document, prefix="releaseevidenceverify_"),
    }


def read_adopted_release_self_hosted_evidence_verification(
    path: str | Path,
    *,
    evidence_dir: str | Path | None = None,
) -> dict[str, Any]:
    verification_path = Path(path)
    normalized = to_canonical_data(_read_json_object(verification_path))
    if not isinstance(normalized, dict):
        raise ValueError("release self-hosted evidence verification must be an object")
    if (
        normalized.get("schema_version")
        != RELEASE_SELF_HOSTED_EVIDENCE_VERIFICATION_SCHEMA_VERSION
    ):
        raise ValueError(
            "unsupported release self-hosted evidence verification schema_version"
        )
    expected_keys = {
        "audit_evidence_id",
        "evidence_id",
        "parallel_search",
        "requirements",
        "research_dashboard",
        "schema_version",
        "summary",
        "verified_file_sha256",
        "verified_files",
    }
    if set(normalized) != expected_keys:
        raise ValueError("release self-hosted evidence verification keys invalid")
    evidence_id = normalized.get("evidence_id")
    if not isinstance(evidence_id, str) or not evidence_id.startswith(
        "releaseevidenceverify_"
    ):
        raise ValueError("release self-hosted evidence verification evidence_id invalid")
    identity = dict(normalized)
    identity.pop("evidence_id", None)
    if stable_digest(identity, prefix="releaseevidenceverify_") != evidence_id:
        raise ValueError(
            "release self-hosted evidence verification evidence_id mismatch"
        )
    audit_evidence_id = normalized.get("audit_evidence_id")
    if not isinstance(audit_evidence_id, str) or not audit_evidence_id.startswith(
        "releaseevidenceaudit_"
    ):
        raise ValueError(
            "release self-hosted evidence verification audit_evidence_id invalid"
        )
    summary = _validate_audit_summary(normalized.get("summary"))
    requirements = _validate_verification_requirements(normalized.get("requirements"))
    parallel = _validate_branch_audit(
        "parallel-search",
        normalized.get("parallel_search"),
    )
    research = _validate_branch_audit(
        "research-dashboard",
        normalized.get("research_dashboard"),
    )
    if parallel is not None and summary["parallel_search"] != "true":
        raise ValueError(
            "release self-hosted evidence verification parallel-search branch "
            "contradicts summary"
        )
    if research is not None and summary["research_dashboard"] != "true":
        raise ValueError(
            "release self-hosted evidence verification research-dashboard branch "
            "contradicts summary"
        )
    if requirements["require_parallel_search"]:
        if parallel is None:
            raise ValueError(
                "release self-hosted evidence verification requires parallel-search"
            )
        if parallel["passed"] is not True:
            raise ValueError(
                "release self-hosted evidence verification parallel-search did not pass"
            )
    if requirements["require_research_dashboard"]:
        if research is None:
            raise ValueError(
                "release self-hosted evidence verification requires research-dashboard"
            )
        if research["passed"] is not True:
            raise ValueError(
                "release self-hosted evidence verification research-dashboard did not pass"
            )
    verified_files = _validate_verification_file_list(normalized.get("verified_files"))
    expected_verified_files = ["release_self_hosted_evidence_audit.json"]
    if parallel is not None:
        expected_verified_files.extend(
            ["parallel_search_gate.json", "parallel_search_records.json"]
        )
    if research is not None:
        expected_verified_files.extend(
            ["research_dashboard_gate.json", "research_dashboard_qualification.json"]
        )
    if verified_files != sorted(expected_verified_files):
        raise ValueError(
            "release self-hosted evidence verification verified_files do not match "
            "branch witnesses"
        )
    verified_file_sha256 = _validate_verification_file_sha256(
        normalized.get("verified_file_sha256"),
        verified_files=verified_files,
    )
    if evidence_dir is not None:
        root = Path(evidence_dir)
        for name, digest in verified_file_sha256.items():
            file_path = root / name
            if not file_path.is_file():
                raise ValueError(
                    "release self-hosted evidence verification verified file missing"
                )
            if hashlib.sha256(file_path.read_bytes()).hexdigest() != digest:
                raise ValueError(
                    "release self-hosted evidence verification file sha256 mismatch"
                )
        current = verify_adopted_release_self_hosted_evidence(
            root,
            expected_commit=requirements["expected_commit"],
            expected_run_id=requirements["expected_run_id"],
            require_parallel_search=requirements["require_parallel_search"],
            require_research_dashboard=requirements["require_research_dashboard"],
        )
        if current["evidence_id"] != evidence_id:
            raise ValueError(
                "release self-hosted evidence verification does not match adopted "
                "evidence"
            )
    return {
        **normalized,
        "parallel_search": parallel,
        "requirements": requirements,
        "research_dashboard": research,
        "summary": summary,
        "verified_file_sha256": verified_file_sha256,
        "verified_files": verified_files,
    }


def write_adopted_release_self_hosted_evidence_verification(
    evidence_dir: str | Path,
    *,
    expected_commit: str | None = None,
    expected_run_id: str | None = None,
    output_path: str | Path,
    require_parallel_search: bool = False,
    require_research_dashboard: bool = False,
) -> dict[str, Any]:
    document = verify_adopted_release_self_hosted_evidence(
        evidence_dir,
        expected_commit=expected_commit,
        expected_run_id=expected_run_id,
        require_parallel_search=require_parallel_search,
        require_research_dashboard=require_research_dashboard,
    )
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(destination, json.dumps(document, indent=2, sort_keys=True) + "\n")
    return document
