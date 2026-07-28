from __future__ import annotations

import pytest

from ygo_effect_dsl.engine.evaluation import (
    RouteRankingPolicy,
    build_route_randomness_summary,
    rank_route_candidates,
)


def _route(route_id: str, random_events: list[dict[str, object]] | None) -> dict[str, object]:
    route: dict[str, object] = {"route_id": route_id}
    if random_events is not None:
        route["replay"] = {"random_events": random_events}
    return route


def test_route_randomness_summary_distinguishes_deterministic_stochastic_unknown() -> None:
    deterministic = build_route_randomness_summary(_route("route_a", []))
    stochastic = build_route_randomness_summary(
        _route(
            "route_b",
            [
                {
                    "after_response_step": 2,
                    "kind": "toss_coin",
                    "outcome": {"results": [1]},
                    "random_event_id": "rng_1",
                }
            ],
        )
    )
    unknown = build_route_randomness_summary(_route("route_c", None))

    assert deterministic["schema_version"] == "route-randomness-summary-v1"
    assert deterministic["reliability_class"] == "deterministic"
    assert deterministic["gameplay_random_event_count"] == 0
    assert stochastic["reliability_class"] == "stochastic"
    assert stochastic["gameplay_random_event_count"] == 1
    assert stochastic["random_events"][0]["outcome_observed"] is True
    assert unknown["reliability_class"] == "unknown"
    assert unknown["evidence_completeness"] == "missing_replay_random_events"


def test_route_ranking_orders_by_success_score_reliability_and_tiebreakers() -> None:
    deterministic = build_route_randomness_summary(_route("route_b", []))
    stochastic = build_route_randomness_summary(
        _route(
            "route_a",
            [
                {
                    "kind": "shuffle_deck",
                    "outcome": {"zone_order": []},
                    "random_event_id": "rng_shuffle",
                }
            ],
        )
    )
    unknown = build_route_randomness_summary(_route("route_c", None))

    ranking = rank_route_candidates(
        [
            {
                "action_count": 3,
                "peak_score": 12,
                "randomness_summary": unknown,
                "route_id": "route_c",
                "success": True,
                "terminal_composite_score": 10,
            },
            {
                "action_count": 2,
                "peak_score": 9,
                "randomness_summary": stochastic,
                "route_id": "route_a",
                "success": True,
                "terminal_composite_score": 10,
            },
            {
                "action_count": 9,
                "peak_score": 8,
                "randomness_summary": deterministic,
                "route_id": "route_b",
                "success": True,
                "terminal_composite_score": 10,
            },
            {
                "action_count": 1,
                "peak_score": 99,
                "randomness_summary": deterministic,
                "route_id": "route_failed",
                "success": False,
                "terminal_composite_score": 100,
            },
        ]
    )

    assert ranking["schema_version"] == "route-ranking-v1"
    assert ranking["best_route_id"] == "route_b"
    assert [route["route_id"] for route in ranking["ranked_routes"]] == [
        "route_b",
        "route_a",
        "route_c",
        "route_failed",
    ]
    assert ranking["ranked_routes"][0]["gameplay_reliability"] == "deterministic"
    assert ranking["ranked_routes"][1]["gameplay_random_event_count"] == 1


def test_route_ranking_can_require_deterministic_with_recorded_exclusions() -> None:
    policy = RouteRankingPolicy(require_deterministic=True)
    ranking = rank_route_candidates(
        [
            {
                "action_count": 1,
                "gameplay_random_event_count": 0,
                "gameplay_reliability": "deterministic",
                "peak_score": 3,
                "route_id": "stable",
                "success": True,
                "terminal_composite_score": 3,
            },
            {
                "action_count": 1,
                "gameplay_random_event_count": 1,
                "gameplay_reliability": "stochastic",
                "peak_score": 30,
                "route_id": "coin",
                "success": True,
                "terminal_composite_score": 30,
            },
        ],
        policy=policy,
    )

    assert ranking["best_route_id"] == "stable"
    assert ranking["policy"]["require_deterministic"] is True
    assert [route["route_id"] for route in ranking["excluded_routes"]] == ["coin"]
    assert (
        ranking["excluded_routes"][0]["exclusion_reason"]
        == "requires_deterministic_gameplay"
    )


def test_route_ranking_rejects_duplicate_route_ids() -> None:
    candidate = {
        "action_count": 1,
        "gameplay_random_event_count": 0,
        "gameplay_reliability": "deterministic",
        "peak_score": 1,
        "route_id": "dup",
        "success": True,
        "terminal_composite_score": 1,
    }

    with pytest.raises(ValueError, match="route_id must be unique"):
        rank_route_candidates([candidate, candidate])
