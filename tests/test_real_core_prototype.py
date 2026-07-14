from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from ygo_effect_dsl.external.ocgcore import (
    OcgcoreBootstrapError,
    verify_ocgcore,
    verify_ocgcore_assets,
)
from ygo_effect_dsl.engine.canonical import stable_digest
from ygo_effect_dsl.engine.failures import (
    FailureDisposition,
    FailureRecordError,
    RecoveryAction,
)
from ygo_effect_dsl.engine.interruption import (
    build_interruption_comparison,
    resolve_interruption_target,
)
from ygo_effect_dsl.experiment import load_experiment_document
from ygo_effect_dsl.prototype import (
    build_real_core_route,
    run_real_core_parallel_stress,
    verify_real_core_route,
)
from ygo_effect_dsl.route_dsl import (
    assert_valid_route_document,
    load_route_document,
    validate_route_document,
)


ROUTE = (
    Path(__file__).parents[1]
    / "examples"
    / "prototype"
    / "real_core_effect_veiler.route.yaml"
)
INTERRUPTED_ROUTE = (
    Path(__file__).parents[1]
    / "examples"
    / "prototype"
    / "real_core_effect_veiler_interrupted.route.yaml"
)
SAMPLED_EXPERIMENT = (
    Path(__file__).parents[1]
    / "examples"
    / "experiments"
    / "real_core_effect_veiler_sampled.yaml"
)
TEMPORARY_ATK_ROUTE = (
    Path(__file__).parents[1]
    / "examples"
    / "prototype"
    / "real_core_temporary_atk.route.yaml"
)
ACTION_AGGREGATION_ROUTE = (
    Path(__file__).parents[1]
    / "examples"
    / "prototype"
    / "real_core_action_aggregation.route.yaml"
)


def test_checked_real_core_route_records_validated_and_pending_contracts() -> None:
    route = load_route_document(ROUTE)
    assert_valid_route_document(route)

    prototype = route["experiment"]["prototype"]
    assert prototype["adapter"] == "ocgcore-v11"
    assert "requires_validation" not in prototype
    assert prototype["pending_validation"] == []
    assert "end_phase_durability" in prototype["validated_contracts"]
    assert "pluggable_evaluator_registry" in prototype["validated_contracts"]
    assert "score_breakdown_persistence" in prototype["validated_contracts"]
    assert "configured_interruption_execution" in prototype["validated_contracts"]
    assert "sampled_interruption_manifest" in prototype["validated_contracts"]
    assert "ocgcore_temporary_effect_observation" in prototype["validated_contracts"]
    assert route["experiment"]["evaluator"]["id"] == "real_core_board_count"
    assert route["experiment"]["evaluator"]["version"] == "1"
    assert route["experiment"]["evaluator"]["config"][
        "missing_value_policy"
    ] == "error"
    assert len(route["replay"]["events"]) > 6
    assert route["replay"]["manifest"]["reproducible"] is True
    assert route["replay"]["manifest"]["missing_requirements"] == []
    policy_id = route["experiment"]["information_policy"]["policy_id"]
    assert route["experiment"]["schema_version"] == "0.3b"
    assert route["replay"]["information_policy_id"] == policy_id
    assert route["replay"]["manifest"]["initial_conditions"][
        "information_policy_id"
    ] == policy_id
    assert route["information_audit"]["policy"]["policy_id"] == policy_id
    assert len(route["information_audit"]["accesses"]) == 4
    assert route["information_audit"]["leak_count"] == 0
    assert all(event["action_id"] for event in route["replay"]["events"])
    assert all(event["request_signature"] for event in route["replay"]["events"])
    assert all(event["state_hash_after"] for event in route["replay"]["events"])
    aggregation = route["presentation"]["action_aggregation"]
    assert len(aggregation["groups"]) == len(route["replay"]["events"])
    assert len(aggregation["links"]) == len(route["replay"]["events"])
    assert route["presentation"]["validation"] == {
        "method": "ocgcore-lifecycle-v2",
        "status": "validated",
    }
    assert len(route["replay"]["random_events"]) == 2
    assert {event["outcome"]["player"] for event in route["replay"]["random_events"]} == {
        0,
        1,
    }
    assert all(
        event["after_response_step"] is None
        and event["kind"] == "shuffle_hand"
        and event["outcome"]["codes"] == [97268402]
        for event in route["replay"]["random_events"]
    )
    assert any(
        event["action"]["kind"] == "END_TURN"
        for event in route["replay"]["events"]
    )
    assert route["result"]["peak_board"]["stop_reason"] == (
        "core_end_turn_available"
    )
    durability = route["result"]["durability"]
    assert durability["before"]["turn"] == 1
    assert durability["after"]["turn"] == 2
    assert durability["after"]["phase"] == "main1"
    assert durability["success_retained"] is True
    score_comparison = durability["delta"]["score_breakdown"]
    assert score_comparison["schema_version"] == "score-comparison-v1"
    assert score_comparison["total_score_delta"] == 0
    assert all(term["contribution_delta"] == 0 for term in score_comparison["terms"])
    evaluation_result = route["checkpoints"][5]["evaluation_result"]
    assert evaluation_result["schema_version"] == "evaluation-result-v1"
    assert evaluation_result["total_score"] == route["checkpoints"][5]["score"]
    assert evaluation_result["score_breakdown"]["schema_version"] == (
        "score-breakdown-v1"
    )
    assert evaluation_result["score_breakdown"]["missing_metrics"] == []
    temporary = route["result"]["evaluation_explanation"]["temporary_effects"]
    assert temporary["values"]["field_count"] == {
        "durable": 1,
        "excluded_temporary": 0,
        "raw": 1,
    }
    assert temporary["overvaluation_prevention"]["applied"] is False
    assert temporary["components"][0]["permanence"] == "persistent"
    assert route["result"]["terminal_board"]["turn"] == 2
    assert route["result"]["diagnostics"] == []


def test_checked_route_matches_fresh_real_core_worker() -> None:
    try:
        verify_ocgcore()
        verify_ocgcore_assets()
    except (OcgcoreBootstrapError, OSError) as exc:
        pytest.skip(f"pinned local ocgcore runtime/assets are unavailable: {exc}")

    route = load_route_document(ROUTE)
    result = verify_real_core_route(route)
    assert result.event_count == len(route["replay"]["events"])
    assert result.route_id == route["route_id"]
    assert result.final_state_hash == route["result"]["terminal_board"]["state_hash"]


def test_checked_scripted_interruption_forks_at_the_real_response_opportunity() -> None:
    base = load_route_document(ROUTE)
    interrupted = load_route_document(INTERRUPTED_ROUTE)
    assert_valid_route_document(base)
    assert_valid_route_document(interrupted)

    record = interrupted["interruptions"][0]
    resolution = resolve_interruption_target(base["replay"], record["target"])
    comparison = build_interruption_comparison(base, interrupted)

    assert interrupted["lineage"] == {
        "fork_step": 5,
        "parent_route_id": base["route_id"],
    }
    assert resolution.replay_step == 5
    assert [event["action_id"] for event in base["replay"]["events"][:5]] == [
        event["action_id"] for event in interrupted["replay"]["events"][:5]
    ]
    assert base["replay"]["events"][5]["action"]["kind"] == "PASS"
    assert interrupted["replay"]["events"][5]["action"]["kind"] == "ACTIVATE_EFFECT"
    assert interrupted["replay"]["events"][6]["action"]["kind"] == "SELECT_CARD"
    assert interrupted["replay"]["events"][5]["action"]["source"][
        "public_card_id"
    ] == 97268402
    assert record["status"] == "applied_by_core"
    assert comparison["recovery"]["status"] == "goal_only"
    assert comparison["metrics"]["route_length"]["delta"] == 5
    observation = interrupted["result"]["temporary_modifier_observation"]
    assert observation["modifier_kind"] == "effect_disabled"
    assert observation["boundary_evidence"] == "observed_expired"
    assert observation["transition"]["active_delta"] == 1
    assert observation["transition"]["expired_delta"] == 0
    temporary = interrupted["result"]["evaluation_explanation"][
        "temporary_effects"
    ]
    assert temporary["values"]["effect_disabled"]["durable"] == 0
    assert temporary["values"]["effect_disabled"]["excluded_temporary"] == 1
    assert base["route_id"] != interrupted["route_id"]
    assert stable_digest(base["replay"], prefix="replay_") != stable_digest(
        interrupted["replay"], prefix="replay_"
    )

    tampered = deepcopy(interrupted)
    tampered["interruptions"][0]["activation_step"] = 6
    assert "interruption_activation_step_mismatch" in {
        issue.code for issue in validate_route_document(tampered)
    }


def test_sampled_interruption_persists_seed_and_replays_fresh() -> None:
    try:
        verify_ocgcore()
        verify_ocgcore_assets()
    except (OcgcoreBootstrapError, OSError) as exc:
        pytest.skip(f"pinned local ocgcore runtime/assets are unavailable: {exc}")
    experiment = load_experiment_document(SAMPLED_EXPERIMENT)

    route = build_real_core_route(experiment=experiment)
    result = verify_real_core_route(route)
    sampling = route["replay"]["manifest"]["randomness"][
        "interruption_sampling"
    ]

    assert result.route_id == route["route_id"]
    assert sampling["schema_version"] == "interruption-sampling-v1"
    assert sampling["sampler_id"] == "stable-digest-mod-v1"
    assert sampling["seed"] == 20260713
    assert sampling["selected_definition_id"] == (
        "effect_veiler_after_first_normal_summon"
    )
    assert route["interruptions"][0]["sampling"] == sampling


def test_unsupported_interruption_definition_fails_with_yaml_path() -> None:
    experiment = load_experiment_document(SAMPLED_EXPERIMENT)
    invalid = deepcopy(experiment)
    invalid["interruption"]["definitions"][0]["interruption_type"] = (
        "unsupported_fixture"
    )

    with pytest.raises(
        FailureRecordError,
        match=r"\$\.interruption\.definitions\[0\]\.interruption_type",
    ) as captured:
        build_real_core_route(experiment=invalid)

    assert captured.value.failure.disposition == (
        FailureDisposition.EXPERIMENT_FAILURE
    )
    assert captured.value.failure.recovery == RecoveryAction.ABORT_EXPERIMENT
    assert captured.value.failure.retryable is False


def test_real_core_parallel_stress_smoke_is_pool_independent() -> None:
    try:
        verify_ocgcore()
        verify_ocgcore_assets()
    except (OcgcoreBootstrapError, OSError) as exc:
        pytest.skip(f"pinned local ocgcore runtime/assets are unavailable: {exc}")

    report = run_real_core_parallel_stress(
        pool_sizes=(1, 2),
        task_count=2,
        include_failure_injection=False,
    )

    assert all(report["verification"].values())
    assert len(report["pool_runs"][0]["semantic_routes"]) == 2


def test_temporary_attack_fixture_observes_end_phase_expiration() -> None:
    try:
        verify_ocgcore()
        verify_ocgcore_assets()
    except (OcgcoreBootstrapError, OSError) as exc:
        pytest.skip(f"pinned local ocgcore runtime/assets are unavailable: {exc}")
    route = load_route_document(TEMPORARY_ATK_ROUTE)

    result = verify_real_core_route(route)
    observation = route["result"]["temporary_modifier_observation"]
    temporary = route["result"]["evaluation_explanation"]["temporary_effects"]

    assert result.route_id == route["route_id"]
    assert observation["modifier_kind"] == "attack_delta"
    assert observation["points"]["baseline"]["value"] == 0
    assert observation["points"]["active"]["value"] == 500
    assert observation["points"]["expired"]["value"] == 0
    assert observation["expiration"]["boundary"] == "end_of_turn"
    assert observation["expiration"]["turn"] == 1
    assert temporary["values"]["attack"] == {
        "durable": 0,
        "excluded_temporary": 500,
        "raw": 500,
    }


def test_action_aggregation_fixture_derives_core_lifecycle_roles() -> None:
    route = load_route_document(ACTION_AGGREGATION_ROUTE)
    assert_valid_route_document(route)

    presentation = route["presentation"]
    group = next(
        group
        for group in presentation["action_aggregation"]["groups"]
        if group["atomic_steps"] == [4, 5, 6, 7]
    )
    assert [part["role"] for part in group["parts"]] == [
        "primary",
        "cost",
        "target",
        "option",
    ]
    evidence = presentation["action_aggregation_evidence"]
    assert [item["evidence"]["basis"] for item in evidence["role_evidence"]] == [
        "action_kind",
        "selected_card_reason_cost_move",
        "select_hint_target",
        "selection_message_type",
    ]
    assert evidence["group_boundaries"][0]["end_message_type"] == 71

    tampered = deepcopy(route)
    tampered_group = next(
        group
        for group in tampered["presentation"]["action_aggregation"]["groups"]
        if group["atomic_steps"] == [4, 5, 6, 7]
    )
    tampered_group["parts"][1]["role"] = "target"
    assert "ocgcore_action_aggregation_mismatch" in {
        issue.code for issue in validate_route_document(tampered)
    }


def test_action_aggregation_fixture_matches_fresh_real_core_worker() -> None:
    try:
        verify_ocgcore()
        verify_ocgcore_assets()
    except (OcgcoreBootstrapError, OSError) as exc:
        pytest.skip(f"pinned local ocgcore runtime/assets are unavailable: {exc}")

    route = load_route_document(ACTION_AGGREGATION_ROUTE)
    result = verify_real_core_route(route)

    assert result.route_id == route["route_id"]
    assert result.event_count == 14
