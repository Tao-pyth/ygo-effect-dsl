from __future__ import annotations

import json
from pathlib import Path

from ygo_effect_dsl.external.licensing import load_distribution_policy


REPO_ROOT = Path(__file__).resolve().parents[1]
APPROVAL_DOC = REPO_ROOT / "docs" / "legal" / "20_project_license_approval.md"
APPROVAL_STATUS = (
    REPO_ROOT / "docs" / "release" / "evidence" / "project_license_approval_status.json"
)
PYPROJECT = REPO_ROOT / "pyproject.toml"


def _approval_status() -> dict:
    return json.loads(APPROVAL_STATUS.read_text(encoding="utf-8"))


def test_project_license_approval_status_matches_current_noassertion_state() -> None:
    status = _approval_status()
    policy = load_distribution_policy()
    pyproject = PYPROJECT.read_text(encoding="utf-8")

    assert status["schema_version"] == "project-license-approval-status-v1"
    assert status["approval_state"] == "missing"
    assert status["blocking_issues"] == [91, 169]
    assert status["project_license"] == {"spdx": "NOASSERTION", "license_file": None}
    assert status["package_metadata"] == {
        "license_classifiers": [],
        "license_expression": "NOASSERTION",
        "license_files": [],
    }
    assert status["public_distribution"] == "blocked"
    assert status["distribution_policy"] == {
        "legal_review_required": True,
        "policy_id": policy.policy_id,
        "project_release_status": policy.data["project"]["release_status"],
    }
    assert not (REPO_ROOT / "LICENSE").exists()
    assert "\nlicense" not in pyproject
    assert "License ::" not in pyproject


def test_project_license_approval_record_lists_required_approval_evidence() -> None:
    status = _approval_status()
    document = APPROVAL_DOC.read_text(encoding="utf-8")

    required = status["required_before_approval"]
    assert len(required) == 7
    assert "owner-approved root project license identifier and LICENSE text" in required
    assert "explicit BabelCDB redistribution license or written permission" in required
    assert "legal review link or approval record" in required[-1]

    assert "Status: Approval required" in document
    assert "project.release_status" in document
    assert "Adding a root `LICENSE` without updating package metadata" in document
    for reference in status["evidence_refs"]:
        assert reference in document or Path(reference).exists()
