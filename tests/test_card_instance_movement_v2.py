from __future__ import annotations

import json
from pathlib import Path

import pytest

from ygo_effect_dsl.engine.canonical import stable_digest
from ygo_effect_dsl.external.ocgcore import (
    OcgcoreBootstrapError,
    verify_ocgcore,
    verify_ocgcore_assets,
)
from ygo_effect_dsl.spikes.card_instance_v2_movement_evidence import (
    MOVEMENT_EVIDENCE_SCHEMA_VERSION,
    build_card_instance_v2_movement_evidence,
)


EVIDENCE = (
    Path(__file__).parents[1]
    / "docs"
    / "ocgcore"
    / "evidence"
    / "card_instance_movement_v2.json"
)


def test_checked_movement_evidence_covers_issue_boundaries() -> None:
    evidence = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    evidence_id = evidence.pop("evidence_id")
    provenance = evidence["run"]["provenance"]
    movement_kinds = {
        item["movement_kind"] for item in provenance["movement_transitions"]
    }
    shuffle_kinds = {
        item["mutation"] for item in provenance["shuffle_boundaries"]
    }

    assert evidence_id == stable_digest(evidence, prefix="cardmoveev_")
    assert evidence["schema_version"] == MOVEMENT_EVIDENCE_SCHEMA_VERSION
    assert all(evidence["checks"].values())
    assert {"draw", "search", "salvage", "control_change"}.issubset(
        movement_kinds
    )
    assert {"shuffle_deck", "shuffle_hand", "shuffle_set_card"}.issubset(
        shuffle_kinds
    )
    assert any(
        item["after"]["location"] == 0x10
        for item in provenance["movement_transitions"]
    )
    assert any(
        item["after"]["location"] == 0x20
        for item in provenance["movement_transitions"]
    )


def test_movement_evidence_matches_fresh_workers() -> None:
    try:
        verify_ocgcore()
        verify_ocgcore_assets()
    except (OcgcoreBootstrapError, OSError) as exc:
        pytest.skip(f"pinned local ocgcore runtime/assets are unavailable: {exc}")

    expected = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    assert build_card_instance_v2_movement_evidence() == expected
