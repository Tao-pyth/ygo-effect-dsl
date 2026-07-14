from __future__ import annotations

from pathlib import Path
import json

import pytest

from ygo_effect_dsl.engine.evaluation import (
    RESOURCE_CONSUMPTION_METRIC,
    build_route_resource_consumption,
)
from ygo_effect_dsl.route_dsl import load_route_document, normalize_and_explain_routes
from ygo_effect_dsl.spikes.resource_consumption_evidence import (
    build_resource_consumption_evidence,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
PROTOTYPE_DIR = REPO_ROOT / "examples" / "prototype"
EVIDENCE = (
    REPO_ROOT
    / "docs"
    / "evaluation"
    / "evidence"
    / "resource_consumption.json"
)


def _route(name: str) -> dict[str, object]:
    return load_route_document(PROTOTYPE_DIR / name)


def test_representative_routes_have_golden_resource_vectors() -> None:
    base = build_route_resource_consumption(
        _route("real_core_effect_veiler.route.yaml")
    )
    with_cost = build_route_resource_consumption(
        _route("real_core_action_aggregation.route.yaml")
    )

    assert base["schema_version"] == "route-resource-consumption-v1"
    assert base["metric"] == RESOURCE_CONSUMPTION_METRIC
    assert base["players"]["0"]["dimensions"] == {
        "banished_net_increase": 0,
        "deck_net_decrease": 0,
        "explicit_cost_cards": 0,
        "extra_deck_net_decrease": 0,
        "graveyard_net_increase": 0,
        "hand_net_decrease": 1,
        "life_point_loss": 0,
        "monster_zone_net_decrease": 0,
        "normal_summon_uses": 1,
        "special_summon_actions": 0,
        "spell_trap_zone_net_decrease": 0,
    }
    assert with_cost["players"]["0"]["dimensions"] == {
        "banished_net_increase": 0,
        "deck_net_decrease": 0,
        "explicit_cost_cards": 1,
        "extra_deck_net_decrease": 0,
        "graveyard_net_increase": 1,
        "hand_net_decrease": 2,
        "life_point_loss": 0,
        "monster_zone_net_decrease": 0,
        "normal_summon_uses": 1,
        "special_summon_actions": 0,
        "spell_trap_zone_net_decrease": 0,
    }
    assert base["scalar"]["total"] == 2.0
    assert with_cost["scalar"]["total"] == 3.0
    assert len(with_cost["explicit_cost_evidence"]["records"]) == 1


def test_resource_weights_are_versioned_and_recalculable() -> None:
    route = _route("real_core_action_aggregation.route.yaml")
    default = build_route_resource_consumption(route)
    weighted = build_route_resource_consumption(
        route,
        config={
            "weights": {
                "extra_deck_net_decrease": 1,
                "hand_net_decrease": 2,
                "life_point_loss": 0.001,
                "normal_summon_uses": 0.5,
            }
        },
    )

    assert weighted["scalar"]["total"] == 4.5
    assert weighted["config_hash"] != default["config_hash"]
    assert weighted["resource_report_id"] != default["resource_report_id"]

    with pytest.raises(ValueError, match="must contain exactly"):
        build_route_resource_consumption(route, config={"weights": {}})


def test_route_normalization_recalculates_resource_ranking() -> None:
    base = _route("real_core_effect_veiler.route.yaml")
    with_cost = _route("real_core_action_aggregation.route.yaml")

    report = normalize_and_explain_routes([with_cost, base])

    assert report["resource_metric"] == RESOURCE_CONSUMPTION_METRIC
    assert report["resource_measurement_mode"] == "recalculated_from_route"
    assert set(report["resource_reports"]) == {
        base["route_id"],
        with_cost["route_id"],
    }
    assert report["rankings"]["minimum_consumption"] == {
        "metric": RESOURCE_CONSUMPTION_METRIC,
        "route_ids": [base["route_id"]],
        "selection_rule": "minimum",
        "status": "available",
        "value": 2.0,
    }


def test_builtin_metric_cannot_be_relabelled_without_external_values() -> None:
    route = _route("real_core_effect_veiler.route.yaml")

    with pytest.raises(ValueError, match="cannot override"):
        normalize_and_explain_routes([route], resource_metric="custom_metric")


def test_fixed_resource_evidence_matches_fresh_route_recalculation() -> None:
    expected = json.loads(EVIDENCE.read_text(encoding="utf-8"))

    assert build_resource_consumption_evidence(repo_root=REPO_ROOT) == expected
    assert expected["calibration"] == {
        "follow_up_issue": 108,
        "status": "provisional_expert_weights",
        "validation_required": (
            "multi_deck_same_state_alternatives_and_blind_human_ranking"
        ),
    }
