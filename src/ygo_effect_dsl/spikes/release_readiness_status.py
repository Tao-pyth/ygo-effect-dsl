from __future__ import annotations

from collections.abc import Mapping
import json
from pathlib import Path
from typing import Any, Callable

from ygo_effect_dsl.engine.canonical import stable_digest, to_canonical_data
from ygo_effect_dsl.io_atomic import atomic_write_text
from ygo_effect_dsl.spikes.japanese_i18n_release_gate import (
    read_japanese_i18n_release_gate,
)
from ygo_effect_dsl.spikes.parallel_search_release_gate import (
    read_parallel_search_release_gate,
)
from ygo_effect_dsl.spikes.release_self_hosted_evidence import (
    verify_adopted_release_self_hosted_evidence,
)
from ygo_effect_dsl.spikes.research_dashboard_release_gate import (
    read_research_dashboard_release_gate,
)
from ygo_effect_dsl.test_profile_plan import read_pytest_profile_release_gate


RELEASE_READINESS_STATUS_SCHEMA_VERSION = "release-readiness-status-v1"
_STAGE_ORDER = ("0.5.1", "0.6.0", "0.7.0", "0.8.0")
_STAGE_GATE_FILES = {
    "0.5.1": "pytest_profile_gate.json",
    "0.6.0": "parallel_search_gate.json",
    "0.7.0": "research_dashboard_gate.json",
    "0.8.0": "japanese_i18n_gate.json",
}
_STAGE_GATE_PREFIXES = {
    "0.5.1": "pytestprofilegate_",
    "0.6.0": "parsearchgate_",
    "0.7.0": "researchdashgate_",
    "0.8.0": "japanesei18ngate_",
}
_STAGE_REQUIRED_VERIFIED_FILES = {
    "0.6.0": {"parallel_search_gate.json", "parallel_search_records.json"},
    "0.7.0": {
        "research_dashboard_gate.json",
        "research_dashboard_qualification.json",
    },
}


def _gate_stage(
    *,
    evidence_dir: Path,
    gate_filename: str,
    reader: Callable[[Path], Mapping[str, Any]],
    stage: str,
) -> dict[str, Any]:
    gate_path = evidence_dir / gate_filename
    try:
        gate = reader(gate_path)
    except (OSError, ValueError) as exc:
        return {
            "gate": {
                "error": str(exc),
                "file": gate_filename,
                "valid": False,
            },
            "ready": False,
            "rejection_reasons": [f"{stage}:gate-invalid"],
            "stage": stage,
        }
    rejection_reasons = [str(reason) for reason in gate.get("rejection_reasons", ())]
    gate_passed = gate.get("passed") is True
    if not gate_passed and not rejection_reasons:
        rejection_reasons = [f"{stage}:gate-failed"]
    return {
        "gate": {
            "evidence_id": gate["evidence_id"],
            "file": gate_filename,
            "passed": gate_passed,
            "valid": True,
        },
        "ready": gate_passed,
        "rejection_reasons": rejection_reasons,
        "stage": stage,
    }


def _self_hosted_stage(
    *,
    evidence_dir: Path,
    gate_filename: str,
    reader: Callable[[Path], Mapping[str, Any]],
    require_parallel_search: bool,
    require_research_dashboard: bool,
    stage: str,
) -> dict[str, Any]:
    stage_status = _gate_stage(
        evidence_dir=evidence_dir,
        gate_filename=gate_filename,
        reader=reader,
        stage=stage,
    )
    gate_passed = stage_status["gate"].get("passed") is True
    try:
        verification = verify_adopted_release_self_hosted_evidence(
            evidence_dir,
            require_parallel_search=require_parallel_search,
            require_research_dashboard=require_research_dashboard,
        )
    except ValueError as exc:
        adoption = {
            "error": str(exc),
            "passed": False,
            "verification_evidence_id": None,
        }
    else:
        branch = (
            verification["parallel_search"]
            if require_parallel_search
            else verification["research_dashboard"]
        )
        adoption = {
            "audit_evidence_id": verification["audit_evidence_id"],
            "passed": branch is not None and branch.get("passed") is True,
            "verification_evidence_id": verification["evidence_id"],
            "verified_files": verification["verified_files"],
        }
    rejection_reasons = list(stage_status["rejection_reasons"])
    if not adoption["passed"]:
        rejection_reasons.append(f"{stage}:self-hosted-adoption-missing-or-invalid")
    ready = gate_passed and adoption["passed"]
    return {
        **stage_status,
        "adopted_self_hosted_evidence": adoption,
        "ready": ready,
        "rejection_reasons": sorted(set(rejection_reasons)),
    }


def build_release_readiness_status(evidence_dir: str | Path) -> dict[str, Any]:
    root = Path(evidence_dir)
    stages = [
        _gate_stage(
            evidence_dir=root,
            gate_filename="pytest_profile_gate.json",
            reader=read_pytest_profile_release_gate,
            stage="0.5.1",
        ),
        _self_hosted_stage(
            evidence_dir=root,
            gate_filename="parallel_search_gate.json",
            reader=read_parallel_search_release_gate,
            require_parallel_search=True,
            require_research_dashboard=False,
            stage="0.6.0",
        ),
        _self_hosted_stage(
            evidence_dir=root,
            gate_filename="research_dashboard_gate.json",
            reader=read_research_dashboard_release_gate,
            require_parallel_search=False,
            require_research_dashboard=True,
            stage="0.7.0",
        ),
        _gate_stage(
            evidence_dir=root,
            gate_filename="japanese_i18n_gate.json",
            reader=read_japanese_i18n_release_gate,
            stage="0.8.0",
        ),
    ]
    ready_versions = [stage["stage"] for stage in stages if stage["ready"] is True]
    incomplete_versions = [
        stage["stage"] for stage in stages if stage["ready"] is not True
    ]
    identity = to_canonical_data(
        {
            "evidence_dir_name": root.name,
            "incomplete_versions": incomplete_versions,
            "passed": not incomplete_versions,
            "ready_versions": ready_versions,
            "schema_version": RELEASE_READINESS_STATUS_SCHEMA_VERSION,
            "stages": stages,
        }
    )
    if not isinstance(identity, dict):
        raise ValueError("release readiness status identity is invalid")
    return {
        **identity,
        "evidence_id": stable_digest(identity, prefix="releasereadiness_"),
    }


def _validate_gate_witness(stage: str, value: Any) -> bool:
    if not isinstance(value, Mapping):
        raise ValueError("release readiness status stage gate is invalid")
    gate = to_canonical_data(value)
    if not isinstance(gate, dict):
        raise ValueError("release readiness status stage gate is invalid")
    if gate.get("file") != _STAGE_GATE_FILES[stage]:
        raise ValueError("release readiness status stage gate file is invalid")
    valid = gate.get("valid")
    if valid is True:
        if set(gate) != {"evidence_id", "file", "passed", "valid"}:
            raise ValueError("release readiness status valid gate keys are invalid")
        evidence_id = gate.get("evidence_id")
        if (
            not isinstance(evidence_id, str)
            or not evidence_id.startswith(_STAGE_GATE_PREFIXES[stage])
        ):
            raise ValueError("release readiness status stage gate evidence_id invalid")
        if gate.get("passed") not in {True, False}:
            raise ValueError("release readiness status stage gate passed invalid")
        return gate["passed"]
    if valid is False:
        if set(gate) != {"error", "file", "valid"}:
            raise ValueError("release readiness status invalid gate keys are invalid")
        if not isinstance(gate.get("error"), str) or not gate["error"]:
            raise ValueError("release readiness status invalid gate error is invalid")
        return False
    raise ValueError("release readiness status stage gate valid flag is invalid")


def _validate_adoption_witness(stage: str, value: Any) -> bool:
    if not isinstance(value, Mapping):
        raise ValueError("release readiness status self-hosted adoption is invalid")
    adoption = to_canonical_data(value)
    if not isinstance(adoption, dict):
        raise ValueError("release readiness status self-hosted adoption is invalid")
    passed = adoption.get("passed")
    if passed not in {True, False}:
        raise ValueError("release readiness status self-hosted adoption passed invalid")
    if passed is False:
        if set(adoption) != {"error", "passed", "verification_evidence_id"}:
            raise ValueError(
                "release readiness status failed self-hosted adoption keys invalid"
            )
        if not isinstance(adoption.get("error"), str) or not adoption["error"]:
            raise ValueError(
                "release readiness status failed self-hosted adoption error invalid"
            )
        if adoption.get("verification_evidence_id") is not None:
            raise ValueError(
                "release readiness status failed self-hosted verification_id invalid"
            )
        return False
    if set(adoption) != {
        "audit_evidence_id",
        "passed",
        "verification_evidence_id",
        "verified_files",
    }:
        raise ValueError(
            "release readiness status passed self-hosted adoption keys invalid"
        )
    audit_evidence_id = adoption.get("audit_evidence_id")
    if not isinstance(audit_evidence_id, str) or not audit_evidence_id.startswith(
        "releaseevidenceaudit_"
    ):
        raise ValueError("release readiness status self-hosted audit_evidence_id invalid")
    verification_evidence_id = adoption.get("verification_evidence_id")
    if (
        not isinstance(verification_evidence_id, str)
        or not verification_evidence_id.startswith("releaseevidenceverify_")
    ):
        raise ValueError(
            "release readiness status self-hosted verification_evidence_id invalid"
        )
    verified_files = adoption.get("verified_files")
    if (
        not isinstance(verified_files, list)
        or verified_files != sorted(verified_files)
        or len(verified_files) != len(set(verified_files))
        or any(not isinstance(item, str) or not item for item in verified_files)
    ):
        raise ValueError("release readiness status self-hosted verified_files invalid")
    expected = {
        "release_self_hosted_evidence_audit.json",
        *_STAGE_REQUIRED_VERIFIED_FILES[stage],
    }
    if not expected.issubset(set(verified_files)):
        raise ValueError(
            "release readiness status self-hosted verified_files missing branch files"
        )
    return True


def validate_release_readiness_status(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("release readiness status must be an object")
    document = to_canonical_data(value)
    if not isinstance(document, dict):
        raise ValueError("release readiness status must be an object")
    if set(document) != {
        "evidence_dir_name",
        "evidence_id",
        "incomplete_versions",
        "passed",
        "ready_versions",
        "schema_version",
        "stages",
    }:
        raise ValueError("release readiness status keys are invalid")
    if document.get("schema_version") != RELEASE_READINESS_STATUS_SCHEMA_VERSION:
        raise ValueError("unsupported release readiness status schema_version")
    if not isinstance(document.get("evidence_dir_name"), str) or not document[
        "evidence_dir_name"
    ]:
        raise ValueError("release readiness status evidence_dir_name is invalid")
    evidence_id = document.get("evidence_id")
    if not isinstance(evidence_id, str) or not evidence_id.startswith(
        "releasereadiness_"
    ):
        raise ValueError("release readiness status evidence_id is invalid")
    identity = dict(document)
    identity.pop("evidence_id", None)
    if evidence_id != stable_digest(identity, prefix="releasereadiness_"):
        raise ValueError("release readiness status evidence_id mismatch")
    stages = document.get("stages")
    if not isinstance(stages, list) or [item.get("stage") for item in stages] != list(
        _STAGE_ORDER
    ):
        raise ValueError("release readiness status stages are invalid")
    ready_versions: list[str] = []
    incomplete_versions: list[str] = []
    for item in stages:
        if not isinstance(item, Mapping):
            raise ValueError("release readiness status stage is invalid")
        stage = item["stage"]
        expected_keys = {"gate", "ready", "rejection_reasons", "stage"}
        if stage in {"0.6.0", "0.7.0"}:
            expected_keys.add("adopted_self_hosted_evidence")
        if set(item) != expected_keys:
            raise ValueError("release readiness status stage keys are invalid")
        if item.get("ready") is True:
            ready_versions.append(item["stage"])
        elif item.get("ready") is False:
            incomplete_versions.append(item["stage"])
        else:
            raise ValueError("release readiness status stage ready flag is invalid")
        gate_passed = _validate_gate_witness(stage, item.get("gate"))
        rejection_reasons = item.get("rejection_reasons")
        if not isinstance(rejection_reasons, list) or any(
            not isinstance(reason, str) for reason in rejection_reasons
        ):
            raise ValueError(
                "release readiness status stage rejection_reasons are invalid"
            )
        expected_ready = gate_passed
        if item["stage"] in {"0.6.0", "0.7.0"}:
            adoption_passed = _validate_adoption_witness(
                stage,
                item.get("adopted_self_hosted_evidence"),
            )
            expected_ready = gate_passed and adoption_passed
        if item["ready"] != expected_ready:
            raise ValueError("release readiness status stage ready is inconsistent")
        if expected_ready and rejection_reasons:
            raise ValueError("ready release readiness stage must not have rejections")
        if not expected_ready and not rejection_reasons:
            raise ValueError("incomplete release readiness stage must have rejections")
    if document.get("ready_versions") != ready_versions:
        raise ValueError("release readiness status ready_versions are inconsistent")
    if document.get("incomplete_versions") != incomplete_versions:
        raise ValueError(
            "release readiness status incomplete_versions are inconsistent"
        )
    if document.get("passed") != (not incomplete_versions):
        raise ValueError("release readiness status passed is inconsistent")
    return document


def read_release_readiness_status(
    path: str | Path,
    *,
    evidence_dir: str | Path | None = None,
) -> dict[str, Any]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError("release readiness status is invalid JSON") from exc
    document = validate_release_readiness_status(value)
    if evidence_dir is not None:
        current = build_release_readiness_status(evidence_dir)
        if current["evidence_id"] != document["evidence_id"]:
            raise ValueError(
                "release readiness status does not match current evidence directory"
            )
    return document


def write_release_readiness_status(
    evidence_dir: str | Path,
    *,
    output_path: str | Path,
) -> dict[str, Any]:
    document = build_release_readiness_status(evidence_dir)
    validate_release_readiness_status(document)
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(destination, json.dumps(document, indent=2, sort_keys=True) + "\n")
    return document
