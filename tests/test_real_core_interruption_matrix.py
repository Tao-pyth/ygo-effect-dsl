from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest

from ygo_effect_dsl.external.ocgcore import (
    OcgcoreBootstrapError,
    verify_ocgcore,
    verify_ocgcore_assets,
)
from ygo_effect_dsl.engine.bridge.ocgcore.decision_corpus import (
    build_decision_shape_corpus,
)
from ygo_effect_dsl.experiment import load_experiment_document
from ygo_effect_dsl.prototype import (
    build_real_core_route,
    invoke_real_core_worker_process,
)
from ygo_effect_dsl.route_dsl import load_route_document, validate_route_document


EXPERIMENTS = Path(__file__).parents[1] / "examples" / "experiments"
ACTION_AGGREGATION_ROUTE = (
    Path(__file__).parents[1]
    / "examples"
    / "prototype"
    / "real_core_action_aggregation.route.yaml"
)
MATRIX_EXPERIMENTS = {
    name: EXPERIMENTS / f"real_core_interruption_matrix_{name}.yaml"
    for name in ("control", "cost", "field_multi_target", "targetless")
}


@pytest.fixture(scope="module")
def matrix_routes() -> dict[str, dict[str, Any]]:
    try:
        verify_ocgcore()
        verify_ocgcore_assets()
    except (OcgcoreBootstrapError, OSError) as exc:
        pytest.skip(f"pinned local ocgcore runtime/assets are unavailable: {exc}")
    return {
        name: build_real_core_route(
            experiment=load_experiment_document(path)
        )
        for name, path in MATRIX_EXPERIMENTS.items()
    }


def test_matrix_exposes_three_interruption_shapes_from_one_core_opportunity(
    matrix_routes: dict[str, dict[str, Any]],
) -> None:
    control = matrix_routes["control"]
    variants = {
        name: matrix_routes[name]
        for name in ("targetless", "cost", "field_multi_target")
    }

    assert control["route_id"] == (
        "route_7b90389762bd8ef5d86254c3657a3bb7fe765cb37ff12c4286563d7f810d7ff5"
    )
    assert control["replay"]["events"][5]["action"]["kind"] == "PASS"
    assert {
        candidate["card_ref"]["public_card_id"]
        for candidate in control["replay"]["events"][5]["request"]["candidates"]
        if candidate["kind"] == "effect"
    } == {10045474, 14558127, 27204311}
    for route in variants.values():
        assert route["lineage"] == {
            "fork_step": 5,
            "parent_route_id": control["route_id"],
        }
        assert route["replay"]["events"][5]["action"]["kind"] == (
            "ACTIVATE_EFFECT"
        )
        assert route["route_id"] != control["route_id"]


def test_matrix_persists_targetless_cost_and_multi_target_response_roles(
    matrix_routes: dict[str, dict[str, Any]],
) -> None:
    targetless = matrix_routes["targetless"]["interruptions"][0]
    cost = matrix_routes["cost"]["interruptions"][0]
    multi_target = matrix_routes["field_multi_target"]["interruptions"][0]

    assert targetless["response_steps"] == []
    assert "target_selection_step" not in targetless
    assert cost["response_steps"] == [
        {
            "action_step": 6,
            "candidate_ids": ["card:1"],
            "response_index": 0,
            "role": "cost",
        }
    ]
    assert "target_selection_step" not in cost
    assert multi_target["response_steps"] == [
        {
            "action_step": 6,
            "candidate_ids": ["card:0", "card:1"],
            "response_index": 0,
            "role": "target",
        }
    ]
    assert multi_target["target_selection_step"] == 6
    assert len(
        matrix_routes["field_multi_target"]["replay"]["events"][6][
            "action"
        ]["selections"]
    ) == 2
    assert len(
        {
            interruption["candidate_policy_id"]
            for interruption in (targetless, cost, multi_target)
        }
    ) == 3


def test_matrix_covers_hand_and_field_activation_sources(
    matrix_routes: dict[str, dict[str, Any]],
) -> None:
    expected = {
        "targetless": (14558127, "hand"),
        "cost": (27204311, "hand"),
        "field_multi_target": (10045474, "core_location_8"),
    }
    for name, (card_code, location) in expected.items():
        activation = matrix_routes[name]["replay"]["events"][5]["action"]
        assert activation["source"]["public_card_id"] == card_code
        assert activation["source"]["location"] == location


def test_matrix_completes_machine_readable_interruption_shape_coverage(
    matrix_routes: dict[str, dict[str, Any]],
) -> None:
    corpus = build_decision_shape_corpus(
        [load_route_document(ACTION_AGGREGATION_ROUTE), *matrix_routes.values()]
    )

    assert set(corpus["coverage"]["categories"]) >= {
        "cost",
        "field_source",
        "hand_source",
        "multi_target",
        "targetless",
    }
    assert corpus["coverage"]["missing_required_categories"] == []
    assert corpus["coverage"]["shape_coverage_status"] == "complete"


def test_matrix_promotes_negated_and_disabled_chain_edges_to_real_core(
    matrix_routes: dict[str, dict[str, Any]],
) -> None:
    negated = matrix_routes["targetless"]["presentation"][
        "action_aggregation_evidence"
    ]
    disabled = matrix_routes["field_multi_target"]["presentation"][
        "action_aggregation_evidence"
    ]
    negated_names = [
        item["message_name"] for item in negated["chain_lifecycle"]
    ]
    disabled_names = [
        item["message_name"] for item in disabled["chain_lifecycle"]
    ]

    assert negated_names.count("MSG_CHAINED") == 2
    assert "MSG_CHAIN_NEGATED" in negated_names
    assert disabled_names.count("MSG_CHAINED") == 2
    assert "MSG_CHAIN_DISABLED" in disabled_names
    assert len(negated["group_boundaries"]) == 2
    assert len(disabled["group_boundaries"]) == 2


def test_explicit_response_evidence_is_validated_against_replay(
    matrix_routes: dict[str, dict[str, Any]],
) -> None:
    tampered = deepcopy(matrix_routes["cost"])
    tampered["interruptions"][0]["response_steps"][0]["candidate_ids"] = [
        "card:tampered"
    ]

    assert "interruption_response_candidates_mismatch" in {
        issue.code for issue in validate_route_document(tampered)
    }


@pytest.mark.parametrize(
    ("field", "value", "expected_code"),
    [
        ("interruption_id", "tampered", "interruption_definition_mismatch"),
        ("source_card_code", 99999999, "interruption_definition_mismatch"),
        (
            "candidate_policy_id",
            "intpolicy_tampered",
            "interruption_candidate_policy_mismatch",
        ),
        (
            "sampling",
            {"sample_id": "intsample_tampered"},
            "interruption_sampling_evidence_mismatch",
        ),
    ],
)
def test_interruption_record_is_linked_to_experiment_definition(
    matrix_routes: dict[str, dict[str, Any]],
    field: str,
    value: object,
    expected_code: str,
) -> None:
    tampered = deepcopy(matrix_routes["targetless"])
    tampered["interruptions"][0][field] = value

    assert expected_code in {
        issue.code for issue in validate_route_document(tampered)
    }


def test_matrix_route_identity_is_deterministic(
    matrix_routes: dict[str, dict[str, Any]],
) -> None:
    experiment = load_experiment_document(MATRIX_EXPERIMENTS["targetless"])
    replayed = build_real_core_route(experiment=experiment)

    assert replayed["route_id"] == matrix_routes["targetless"]["route_id"]
    assert replayed["replay"] == matrix_routes["targetless"]["replay"]


def test_worker_preserves_path_and_experiment_failure_dispositions(
    matrix_routes: dict[str, dict[str, Any]],
) -> None:
    del matrix_routes
    experiment = load_experiment_document(MATRIX_EXPERIMENTS["targetless"])
    runtime_mismatch = deepcopy(experiment)
    runtime_definition = runtime_mismatch["interruption"]["definitions"][0]
    runtime_definition["source_card_code"] = 99999999
    runtime_definition["candidate_policy"]["activation"]["selector"][
        "card_ref"
    ]["public_card_id"] = 99999999

    runtime_result = invoke_real_core_worker_process(experiment=runtime_mismatch)
    assert runtime_result.failure_record is not None
    assert runtime_result.failure_record.disposition.value == "path_failure"
    assert runtime_result.failure_record.recovery.value == "stop_path"
    assert runtime_result.failure_record.context["request"]["request_type"] == (
        "select_chain"
    )
    assert runtime_result.failure_record.context["step"]["role"] == "activation"

    invalid_configuration = deepcopy(experiment)
    invalid_configuration["interruption"]["definitions"][0][
        "candidate_policy"
    ]["activation"]["selection_count"] = 0
    configuration_result = invoke_real_core_worker_process(
        experiment=invalid_configuration
    )
    assert configuration_result.failure_record is not None
    assert configuration_result.failure_record.disposition.value == (
        "experiment_failure"
    )
    assert configuration_result.failure_record.recovery.value == "abort_experiment"
    assert "request" not in configuration_result.failure_record.context
