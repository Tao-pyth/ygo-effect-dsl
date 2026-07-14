from __future__ import annotations

import pytest

from ygo_effect_dsl.engine.evaluation import (
    MissingValuePolicy,
    ScoreBreakdown,
    build_weighted_score_breakdown,
    compare_score_breakdowns,
)


def test_score_breakdown_records_weights_contributions_and_total() -> None:
    breakdown = build_weighted_score_breakdown(
        {"follow_up": 2, "interruptions": 1},
        {"follow_up": 3, "interruptions": 10},
    )
    payload = breakdown.to_dict()

    assert payload["schema_version"] == "score-breakdown-v1"
    assert payload["total_score"] == 16
    assert payload["missing_metrics"] == []
    assert payload["terms"] == [
        {
            "contribution": 6,
            "metric": "follow_up",
            "raw_value": 2,
            "resolution": "observed",
            "resolved_value": 2,
            "weight": 3,
        },
        {
            "contribution": 10,
            "metric": "interruptions",
            "raw_value": 1,
            "resolution": "observed",
            "resolved_value": 1,
            "weight": 10,
        },
    ]
    assert ScoreBreakdown.from_dict(payload) == breakdown


def test_score_breakdown_missing_value_policy_is_explicit() -> None:
    zero = build_weighted_score_breakdown(
        {"follow_up": None},
        {"follow_up": 3},
        missing_policy=MissingValuePolicy.ZERO,
    )
    configured = build_weighted_score_breakdown(
        {"follow_up": None},
        {"follow_up": 3},
        missing_policy=MissingValuePolicy.CONFIGURED_DEFAULT,
        defaults={"follow_up": 2},
    )

    assert zero.to_dict()["terms"][0]["resolution"] == "zero"
    assert zero.total_score == 0
    assert configured.to_dict()["terms"][0]["resolution"] == "configured_default"
    assert configured.total_score == 6
    with pytest.raises(ValueError, match="missing evaluation value"):
        build_weighted_score_breakdown(
            {"follow_up": None},
            {"follow_up": 3},
        )


def test_score_comparison_reports_each_contribution_delta() -> None:
    before = build_weighted_score_breakdown(
        {"follow_up": 2, "interruptions": 1},
        {"follow_up": 3, "interruptions": 10},
    )
    after = build_weighted_score_breakdown(
        {"follow_up": 1, "interruptions": 2},
        {"follow_up": 3, "interruptions": 10},
    )

    comparison = compare_score_breakdowns(before, after)

    assert comparison["schema_version"] == "score-comparison-v1"
    assert comparison["total_score_delta"] == 7
    assert {
        term["metric"]: term["contribution_delta"]
        for term in comparison["terms"]
    } == {"follow_up": -3, "interruptions": 10}


def test_score_breakdown_rejects_tampered_contribution() -> None:
    payload = build_weighted_score_breakdown(
        {"follow_up": 2}, {"follow_up": 3}
    ).to_dict()
    payload["terms"][0]["contribution"] = 999

    with pytest.raises(ValueError, match="does not match"):
        ScoreBreakdown.from_dict(payload)
