from __future__ import annotations

import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
MATRIX_PATH = REPO_ROOT / "docs" / "release" / "evidence" / "v1_0_0_support_matrix.json"
DOC_PATH = REPO_ROOT / "docs" / "spec" / "v1.0.0" / "30_support_matrix.md"

EXPECTED_CATEGORIES = {
    "cli_api",
    "core_assets",
    "filesystem",
    "install_upgrade_rollback",
    "locale_ui",
    "os_architecture",
    "python_runtime",
    "schema_artifact",
}
EXPECTED_SUPPORT_LEVELS = {"supported", "maintenance", "experimental", "unsupported"}
EXPECTED_EVIDENCE_STATES = {"verified", "pending_issue", "rejected"}


def _matrix() -> dict:
    return json.loads(MATRIX_PATH.read_text(encoding="utf-8"))


def test_v1_support_matrix_is_complete_and_fail_closed() -> None:
    matrix = _matrix()

    assert matrix["schema_version"] == "v1-support-matrix-v1"
    assert set(matrix["status_vocabulary"]) == EXPECTED_SUPPORT_LEVELS
    assert matrix["default_policy"] == {
        "classification": "unsupported",
        "reason": (
            "Combinations not listed in this matrix are not part of the 1.0.0 stable "
            "claim."
        ),
    }
    assert matrix["issue"] == 168
    assert matrix["support_window"] == {
        "active": "Until 1.1.0 is released or 12 months after 1.0.0, whichever is later.",
        "security_only": "6 months after active support ends.",
        "release_notes_requirement": (
            "Publish concrete calendar dates in the final 1.0.0 release notes."
        ),
    }
    assert matrix["test_links"] == ["tests/test_v1_support_matrix.py"]

    rows = matrix["matrix"]
    assert isinstance(rows, list) and rows
    assert {row["category"] for row in rows} == EXPECTED_CATEGORIES
    assert len({row["id"] for row in rows}) == len(rows)

    support_levels = {row["support_level"] for row in rows}
    evidence_states = {row["evidence_state"] for row in rows}
    assert support_levels <= EXPECTED_SUPPORT_LEVELS
    assert evidence_states <= EXPECTED_EVIDENCE_STATES
    assert "experimental" in EXPECTED_SUPPORT_LEVELS
    assert any(row["support_level"] == "unsupported" for row in rows)
    assert any(row["evidence_state"] == "verified" for row in rows)
    assert any(row["evidence_state"] == "pending_issue" for row in rows)
    assert any(row["evidence_state"] == "rejected" for row in rows)

    for row in rows:
        assert set(row) >= {
            "category",
            "evidence_refs",
            "evidence_state",
            "id",
            "support_level",
            "user_claim",
        }
        assert row["category"] in EXPECTED_CATEGORIES
        assert row["support_level"] in EXPECTED_SUPPORT_LEVELS
        assert row["evidence_state"] in EXPECTED_EVIDENCE_STATES
        assert row["evidence_refs"]
        assert row["user_claim"]
        if row["support_level"] == "unsupported":
            assert row["evidence_state"] == "rejected"
            assert row.get("reason")
        else:
            assert row["evidence_state"] != "rejected"


def test_v1_support_matrix_names_required_boundaries() -> None:
    rows = {row["id"]: row for row in _matrix()["matrix"]}

    assert rows["windows-11-x64-desktop"]["support_level"] == "supported"
    assert rows["non-windows-or-non-x64-desktop"]["support_level"] == "unsupported"
    assert rows["ja-jp-utf8-desktop-ui"]["evidence_state"] == "verified"
    assert rows["cpython-313-x64"]["support_level"] == "supported"
    assert rows["cpython-310-312-x64"]["support_level"] == "maintenance"
    assert rows["ocgcore-api-11-user-acquired-assets"]["support_level"] == "supported"
    assert rows["bundled-third-party-card-assets"]["support_level"] == "unsupported"
    assert rows["public-rest-or-debug-bridge-api"]["support_level"] == "unsupported"
    assert rows["arbitrary-downgrade-or-silent-migration"]["support_level"] == (
        "unsupported"
    )


def test_v1_support_matrix_document_links_machine_evidence_and_test() -> None:
    text = DOC_PATH.read_text(encoding="utf-8")

    assert "docs/release/evidence/v1_0_0_support_matrix.json" in text
    assert "tests/test_v1_support_matrix.py" in text
    assert "ここにない OS、architecture、runtime、asset、schema、CLI/API" in text
    assert "`unsupported`" in text
    assert "`production-distribution-release-gate-v1`" in text
