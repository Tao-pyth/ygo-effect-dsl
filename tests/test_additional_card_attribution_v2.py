from __future__ import annotations

import json
from pathlib import Path

import pytest

from ygo_effect_dsl.engine.canonical import stable_digest
from ygo_effect_dsl.engine.interruption.attribution import _candidate_instances_v2
from ygo_effect_dsl.external.ocgcore import (
    OcgcoreBootstrapError,
    verify_ocgcore,
    verify_ocgcore_assets,
)
from ygo_effect_dsl.spikes.card_instance_v2_evidence import (
    CARD_INSTANCE_V2_EVIDENCE_SCHEMA_VERSION,
    build_card_instance_v2_evidence,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = REPO_ROOT / "docs" / "ocgcore" / "evidence" / "card_instance_route_v2.json"
GOLDEN = REPO_ROOT / "tests" / "golden" / "additional_card_attribution_v2.json"


def _candidate_route(route_id: str) -> dict[str, object]:
    cards = [
        ("corecard_base", 111),
        ("corecard_same_a", 222),
        ("corecard_same_b", 222),
    ]
    return {
        "route_id": route_id,
        "replay": {
            "initial_snapshot": {
                "zones": [
                    {
                        "cards": [
                            {
                                "fields": [
                                    {"name": "code", "value": code}
                                ],
                                "owner": 0,
                                "persistent_instance_id": instance_id,
                                "slot": sequence,
                            }
                            for sequence, (instance_id, code) in enumerate(cards)
                        ],
                        "controller": 0,
                        "location": 2,
                    }
                ]
            },
            "events": [
                {
                    "action": {
                        "action_id": f"act_{index}",
                        "kind": "SELECT_CARD",
                        "selections": [
                            {
                                "card_ref": {
                                    "instance_id": instance_id,
                                    "public_card_id": 222,
                                }
                            }
                        ],
                        "source": None,
                    },
                    "step": index,
                }
                for index, instance_id in enumerate(
                    ("corecard_same_a", "corecard_same_b")
                )
            ],
        },
    }


def test_v2_candidate_builder_distinguishes_duplicate_same_code_cards() -> None:
    instances = _candidate_instances_v2(
        [111],
        [111, 222, 222],
        perspective=0,
        control_route=_candidate_route("route_control"),
        interrupted_route=_candidate_route("route_interrupted"),
    )

    assert [item["instance_id"] for item in instances] == [
        "corecard_same_a",
        "corecard_same_b",
    ]
    assert all(len(item["usage_evidence"]) == 1 for item in instances)


def test_checked_v2_evidence_and_attribution_golden_are_canonical() -> None:
    evidence = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    evidence_id = evidence.pop("evidence_id")
    golden = json.loads(GOLDEN.read_text(encoding="utf-8"))

    assert evidence_id == stable_digest(evidence, prefix="cardv2ev_")
    assert evidence["schema_version"] == CARD_INSTANCE_V2_EVIDENCE_SCHEMA_VERSION
    assert all(evidence["checks"].values())
    assert evidence["attribution"] == golden
    assert golden["schema_version"] == "additional-card-attribution-v2"
    assert golden["instance_identity_scope"]["duplicate_same_code_policy"] == (
        "compare_persistent_instance_id"
    )


def test_v2_evidence_matches_fresh_workers() -> None:
    try:
        verify_ocgcore()
        verify_ocgcore_assets()
    except (OcgcoreBootstrapError, OSError) as exc:
        pytest.skip(f"pinned local ocgcore runtime/assets are unavailable: {exc}")

    expected = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    assert build_card_instance_v2_evidence() == expected
