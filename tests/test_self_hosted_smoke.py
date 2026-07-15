from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest

from ygo_effect_dsl.engine.canonical import stable_digest
from ygo_effect_dsl.external.self_hosted_smoke import (
    SELF_HOSTED_SMOKE_SCHEMA_VERSION,
    build_success_summary,
)


ROOT = Path(__file__).parents[1]


def _reports() -> tuple[dict, dict, dict]:
    route_id = "route_" + "1" * 64
    binary = "2" * 64
    search = {
        "status": "complete",
        "run_id": "searchrun_fixture",
        "best_route": {"route_id": route_id},
    }
    replay = {
        "status": "verified",
        "verification_id": "replayverify_fixture",
        "route": {"route_id": route_id},
        "replay": {"terminal_state_hash": "state_fixture"},
        "runtime": {
            "asset_lock_id": "assets_fixture",
            "core_api": "11.0",
            "core_binary_sha256": binary,
            "core_lock_id": "core_fixture",
        },
    }
    lua = {
        "status": "smoke_only",
        "qualification_id": "luaqualification_fixture",
        "runtime": {"binary_sha256": binary, "lock_id": "core_fixture"},
    }
    return search, replay, lua


def test_success_summary_is_sanitized_and_content_addressed() -> None:
    summary = build_success_summary(
        *_reports(), commit="a" * 40, workflow_run_id="123"
    )
    evidence_id = summary.pop("evidence_id")
    assert summary["schema_version"] == SELF_HOSTED_SMOKE_SCHEMA_VERSION
    assert summary["status"] == "success"
    assert evidence_id == stable_digest(summary, prefix="realcoresmoke_")
    raw = json.dumps(summary)
    assert "opening_hand" not in raw
    assert "deck_sha256" not in raw
    assert "path" not in raw


def test_success_summary_rejects_replay_divergence() -> None:
    search, replay, lua = _reports()
    changed = deepcopy(replay)
    changed["route"]["route_id"] = "route_other"
    with pytest.raises(ValueError, match="Route IDs differ"):
        build_success_summary(
            search, changed, lua, commit="a" * 40, workflow_run_id="123"
        )


@pytest.mark.parametrize(
    "filename, workflow_run_id",
    [
        ("self_hosted_smoke_local.json", "local-20260715"),
        ("self_hosted_smoke_workflow.json", "29380688844"),
    ],
)
def test_checked_smoke_evidence_is_content_addressed(
    filename: str, workflow_run_id: str
) -> None:
    evidence = json.loads(
        (ROOT / "docs/ocgcore/evidence" / filename).read_text(encoding="utf-8")
    )
    evidence_id = evidence.pop("evidence_id")
    assert evidence["schema_version"] == SELF_HOSTED_SMOKE_SCHEMA_VERSION
    assert evidence["status"] == "success"
    assert evidence["workflow_run_id"] == workflow_run_id
    assert evidence_id == stable_digest(evidence, prefix="realcoresmoke_")
