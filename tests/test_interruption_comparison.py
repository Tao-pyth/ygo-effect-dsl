from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest
import yaml

from ygo_effect_dsl.engine.interruption import (
    InterruptionTarget,
    build_interruption_comparison,
)
from ygo_effect_dsl.route_dsl import load_route_document, validate_route_document


REPO_ROOT = Path(__file__).resolve().parents[1]
BASE = yaml.safe_load(
    (REPO_ROOT / "examples" / "route_dsl" / "minimal_route.yaml").read_text(
        encoding="utf-8"
    )
)


def _route(
    route_id: str,
    actions: tuple[tuple[str, str], ...],
    *,
    score: int | float,
    evaluation: dict[str, int | float],
    success: bool = True,
    hand_count: int = 0,
) -> dict[str, object]:
    document = deepcopy(BASE)
    template = deepcopy(document["replay"]["events"][0])
    events = []
    state_before = "state_start"
    for step, (kind, state_after) in enumerate(actions):
        event = deepcopy(template)
        request_signature = f"req_{route_id}_{step}"
        event["step"] = step
        event["request_signature"] = request_signature
        event["action"]["action_id"] = f"act_{route_id}_{step}_{kind.lower()}"
        event["action"]["kind"] = kind
        event["action"]["request_signature"] = request_signature
        event["state_hash_before"] = state_before
        event["state_hash_after"] = state_after
        events.append(event)
        state_before = state_after
    document["route_id"] = route_id
    document["replay"]["events"] = events
    document["result"]["success"] = success
    checkpoint = document["checkpoints"][0]
    checkpoint["step"] = len(events) - 1
    checkpoint["state_hash"] = actions[-1][1]
    checkpoint["evaluation"] = deepcopy(evaluation)
    checkpoint["board_summary"]["player_0"]["hand_count"] = hand_count
    for name in ("peak_board", "terminal_board"):
        board = document["result"][name]
        board["checkpoint_step"] = len(events) - 1
        board["state_hash"] = actions[-1][1]
        board["score"] = score
        board["evaluation"] = deepcopy(evaluation)
    assert validate_route_document(document) == ()
    return document


def _interrupted_child(
    base: dict[str, object],
    child: dict[str, object],
    *,
    fork_step: int,
) -> dict[str, object]:
    target = InterruptionTarget.from_replay_event(base["replay"]["events"][fork_step])
    child["replay"]["events"][:fork_step] = deepcopy(
        base["replay"]["events"][:fork_step]
    )
    child["lineage"] = {
        "parent_route_id": base["route_id"],
        "fork_step": fork_step,
    }
    child["interruptions"] = [
        {
            "at_step": fork_step,
            "interruption_id": "ash_blossom_at_fork",
            "target": target.to_dict(),
        }
    ]
    child["experiment"]["interruption"] = {
        "mode": "scripted",
        "definitions": [
            {"id": "ash_blossom_at_fork", "target": target.to_dict()}
        ],
    }
    assert validate_route_document(child) == ()
    return child


def test_comparison_saves_score_evaluation_resources_length_and_rejoin() -> None:
    base = _route(
        "route_base",
        (
            ("NORMAL_SUMMON", "state_common"),
            ("PASS", "state_rejoin"),
            ("END_TURN", "state_base_peak"),
        ),
        score=10,
        evaluation={"follow_up": 3, "interruptions": 2, "resource_balance": 5},
        hand_count=3,
    )
    child = _route(
        "route_child",
        (
            ("NORMAL_SUMMON", "state_common"),
            ("DECLINE", "state_disrupted"),
            ("PASS", "state_rejoin"),
            ("END_TURN", "state_child_peak"),
        ),
        score=6,
        evaluation={"follow_up": 1, "interruptions": 1, "resource_balance": 2},
        hand_count=1,
    )
    child = _interrupted_child(base, child, fork_step=1)

    report = build_interruption_comparison(
        base,
        child,
        additional_card_evidence=[
            {"card_id": "89631139", "evidence": {"source": "caller_fixture"}}
        ],
    )

    assert report["schema_version"] == "interruption-comparison-v1"
    assert report["metrics"]["score"]["delta"] == -4
    assert report["metrics"]["evaluation"]["metrics"]["interruptions"]["delta"] == -1
    assert report["metrics"]["evaluation"]["metrics"]["follow_up"]["delta"] == -2
    assert report["metrics"]["resources"]["metrics"]["hand"]["delta"] == -2
    assert report["metrics"]["route_length"]["delta"] == 1
    assert report["metrics"]["additional_cards"]["cards"][0]["card_id"] == "89631139"
    assert report["recovery"]["status"] == "original_route_rejoined"
    assert report["recovery"]["rejoin"] == {
        "base_step": 1,
        "recovery_step": 2,
        "state_id": "state_rejoin",
    }
    assert report["comparison_id"].startswith("intcompare_")


def test_original_peak_recovery_is_distinct_from_goal_only() -> None:
    base = _route(
        "route_base",
        (("PASS", "state_common"), ("END_TURN", "state_peak")),
        score=5,
        evaluation={"interruptions": 1},
    )
    child = _route(
        "route_child",
        (
            ("DECLINE", "state_disrupted"),
            ("PASS", "state_common"),
            ("END_TURN", "state_peak"),
        ),
        score=5,
        evaluation={"interruptions": 1},
    )
    child = _interrupted_child(base, child, fork_step=0)

    report = build_interruption_comparison(base, child)

    assert report["recovery"]["status"] == "original_target_reached"
    assert report["recovery"]["original_target_reached"] is True
    assert report["metrics"]["additional_cards"]["status"] == (
        "unavailable_not_attributed"
    )
    assert report["metrics"]["additional_cards"]["verification_issue"] == 100


def test_goal_only_and_not_recovered_are_reported_separately() -> None:
    base = _route(
        "route_base",
        (("PASS", "state_base"),),
        score=5,
        evaluation={"interruptions": 1},
    )
    goal_child = _interrupted_child(
        base,
        _route(
            "route_goal_child",
            (("DECLINE", "state_other"),),
            score=3,
            evaluation={"interruptions": 0},
            success=True,
        ),
        fork_step=0,
    )
    failed_child = _interrupted_child(
        base,
        _route(
            "route_failed_child",
            (("DECLINE", "state_failed"),),
            score=0,
            evaluation={"interruptions": 0},
            success=False,
        ),
        fork_step=0,
    )

    assert build_interruption_comparison(base, goal_child)["recovery"]["status"] == (
        "goal_only"
    )
    assert build_interruption_comparison(base, failed_child)["recovery"]["status"] == (
        "not_recovered"
    )


def test_evaluator_and_success_predicate_changes_disable_invalid_deltas() -> None:
    base = _route(
        "route_base",
        (("PASS", "state_base"),),
        score=5,
        evaluation={"interruptions": 1},
    )
    child = _route(
        "route_child",
        (("DECLINE", "state_other"),),
        score=999,
        evaluation={"interruptions": 999},
    )
    child["experiment"]["evaluator"]["version"] = "2"
    child["experiment"]["success_predicate"]["version"] = "2"
    child = _interrupted_child(base, child, fork_step=0)

    report = build_interruption_comparison(base, child)

    assert report["metrics"]["score"]["delta"] is None
    assert report["metrics"]["evaluation"]["status"] == (
        "unavailable_incomparable_evaluator_contexts"
    )
    assert report["metrics"]["goal"]["status"] == (
        "unavailable_incomparable_success_predicates"
    )
    assert report["recovery"]["status"] == "goal_incomparable"


def test_invalid_lineage_prefix_or_target_is_rejected() -> None:
    base = _route(
        "route_base",
        (("PASS", "state_common"), ("END_TURN", "state_peak")),
        score=5,
        evaluation={"interruptions": 1},
    )
    child = _interrupted_child(
        base,
        _route(
            "route_child",
            (("PASS", "state_common"), ("DECLINE", "state_other")),
            score=1,
            evaluation={"interruptions": 0},
        ),
        fork_step=1,
    )
    wrong_parent = deepcopy(child)
    wrong_parent["lineage"]["parent_route_id"] = "route_other"
    bad_target = deepcopy(child)
    bad_target["interruptions"][0]["target"]["target_id"] = "inttarget_tampered"

    with pytest.raises(ValueError, match="lineage must reference"):
        build_interruption_comparison(base, wrong_parent)
    with pytest.raises(ValueError, match="target_id or fields"):
        build_interruption_comparison(base, bad_target)


def test_real_core_evaluation_result_produces_score_breakdown_delta() -> None:
    base = load_route_document(
        REPO_ROOT
        / "examples"
        / "prototype"
        / "real_core_effect_veiler.route.yaml"
    )
    child = deepcopy(base)
    child["route_id"] = "route_real_core_comparison_child"
    child = _interrupted_child(base, child, fork_step=0)

    report = build_interruption_comparison(base, child)

    assert report["metrics"]["score_breakdown"]["total_score_delta"] == 0
    assert report["metrics"]["resources"]["metrics"]["monster_zone"]["delta"] == 0
    assert report["interruption"]["target_resolution"]["replay_step"] == 0


def test_same_exact_target_state_rejects_stale_evaluation() -> None:
    base = _route(
        "route_base",
        (("PASS", "state_peak"),),
        score=5,
        evaluation={"interruptions": 1},
    )
    child = _interrupted_child(
        base,
        _route(
            "route_child",
            (("DECLINE", "state_peak"),),
            score=4,
            evaluation={"interruptions": 0},
        ),
        fork_step=0,
    )

    with pytest.raises(ValueError, match="identical evaluation"):
        build_interruption_comparison(base, child)
