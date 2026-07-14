from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from typing import Any

import pytest

from ygo_effect_dsl.engine.canonical import stable_digest
from ygo_effect_dsl.engine.failures import (
    FailureDisposition,
    RecoveryAction,
)
from ygo_effect_dsl.engine.interruption import (
    derive_ocgcore_interruption_validation,
)
from ygo_effect_dsl.experiment import load_experiment_document
from ygo_effect_dsl.external.ocgcore import (
    OcgcoreBootstrapError,
    verify_ocgcore,
    verify_ocgcore_assets,
)
from ygo_effect_dsl.prototype import (
    build_real_core_route,
    invoke_real_core_worker_process,
)
from ygo_effect_dsl.route_dsl import validate_route_document


EXPERIMENTS = Path(__file__).parents[1] / "examples" / "experiments"
EVIDENCE_PATH = (
    Path(__file__).parents[1]
    / "docs"
    / "interruption"
    / "evidence"
    / "real_core_negation_timing.json"
)
EXPERIMENT_PATHS = {
    "activation_negation": (
        EXPERIMENTS / "real_core_interruption_matrix_targetless.yaml"
    ),
    "effect_negation": (
        EXPERIMENTS / "real_core_interruption_effect_negation.yaml"
    ),
    "targeted_negation": (
        EXPERIMENTS / "real_core_interruption_matrix_field_multi_target.yaml"
    ),
    "missed_timing": (
        EXPERIMENTS / "real_core_interruption_missed_timing.yaml"
    ),
    "missed_timing_failure": (
        EXPERIMENTS
        / "real_core_interruption_missed_timing_path_failure.yaml"
    ),
}


@pytest.fixture(scope="module")
def routes() -> dict[str, dict[str, Any]]:
    try:
        verify_ocgcore()
        verify_ocgcore_assets()
    except (OcgcoreBootstrapError, OSError) as exc:
        pytest.skip(f"pinned local ocgcore runtime/assets are unavailable: {exc}")
    return {
        name: build_real_core_route(
            experiment=load_experiment_document(EXPERIMENT_PATHS[name])
        )
        for name in (
            "activation_negation",
            "effect_negation",
            "targeted_negation",
            "missed_timing",
        )
    }


def _validation(route: dict[str, Any]) -> dict[str, Any]:
    return route["presentation"]["interruption_validation_evidence"]


def _message_names(route: dict[str, Any]) -> list[str]:
    return [
        frame["message_name"]
        for batch in _validation(route)["lifecycle_batches"]
        for frame in batch["frames"]
    ]


def _self_cost(evidence: dict[str, Any]) -> dict[str, Any]:
    return next(
        move
        for move in evidence["moves"]
        if move["card_code"] == 14558127 and move["reason_cost"]
    )


def test_activation_and_effect_negation_are_controlled_core_variants(
    routes: dict[str, dict[str, Any]],
) -> None:
    activation = routes["activation_negation"]
    effect = routes["effect_negation"]
    activation_action = activation["replay"]["events"][5]["action"]
    effect_action = effect["replay"]["events"][5]["action"]

    assert activation_action == effect_action
    assert activation_action["source"] == {
        "controller": 1,
        "instance_id": None,
        "location": "hand",
        "owner": 1,
        "public_card_id": 14558127,
        "sequence": 0,
    }
    assert _self_cost(_validation(activation)) == _self_cost(
        _validation(effect)
    )
    assert _self_cost(_validation(effect))["current"]["location"] == 16
    assert "MSG_CHAIN_NEGATED" in _message_names(activation)
    assert "MSG_CHAIN_DISABLED" not in _message_names(activation)
    assert "MSG_CHAIN_DISABLED" in _message_names(effect)
    assert "MSG_CHAIN_NEGATED" not in _message_names(effect)
    assert _message_names(activation).count("MSG_CHAINED") == 2
    assert _message_names(effect).count("MSG_CHAINED") == 2
    assert activation["route_id"] != effect["route_id"]
    assert (
        activation["replay"]["events"][-1]["state_hash_after"]
        != effect["replay"]["events"][-1]["state_hash_after"]
    )


def test_targeted_multi_link_negation_retains_source_and_two_targets(
    routes: dict[str, dict[str, Any]],
) -> None:
    route = routes["targeted_negation"]
    activation = route["replay"]["events"][5]["action"]
    selection = route["replay"]["events"][6]["action"]

    assert activation["source"]["public_card_id"] == 10045474
    assert activation["source"]["location"] == "core_location_8"
    assert len(selection["selections"]) == 2
    assert {
        item["card_ref"]["public_card_id"]
        for item in selection["selections"]
    } == {23434538, 91800273}
    assert "MSG_CHAIN_DISABLED" in _message_names(route)
    assert _message_names(route).count("MSG_CHAINED") == 2
    assert not any(
        move["card_code"] == 10045474 and move["reason_cost"]
        for move in _validation(route)["moves"]
    )


def test_missed_timing_is_a_core_message_and_pass_only_request(
    routes: dict[str, dict[str, Any]],
) -> None:
    route = routes["missed_timing"]
    evidence = _validation(route)
    resolution_batch = next(
        batch
        for batch in evidence["lifecycle_batches"]
        if batch["event_step"] == 7
    )
    assert [frame["message_type"] for frame in resolution_batch["frames"]] == [
        72,
        50,
        73,
        72,
        120,
        73,
        74,
    ]
    assert evidence["missed_effects"] == [
        {
            "card_code": 91800273,
            "controller": 0,
            "event_step": 7,
            "frame_index": 4,
            "location": 16,
            "position": 5,
            "sequence": 0,
        }
    ]
    moved = next(
        move for move in evidence["moves"] if move["card_code"] == 91800273
    )
    assert moved["previous"]["location"] == 4
    assert moved["current"]["location"] == 16
    assert moved["reason_effect"] is True
    request_after_miss = next(
        request for request in evidence["requests"] if request["step"] == 8
    )
    assert request_after_miss["request_type"] == "select_chain"
    assert request_after_miss["player"] == 0
    assert request_after_miss["candidates"] == [
        {"candidate_id": "control:pass", "card_ref": None, "kind": "pass"}
    ]
    assert not any(
        action["source"] is not None
        and action["source"].get("public_card_id") == 91800273
        for action in evidence["actions"]
    )
    assert route["result"]["terminal_board"]["evaluation"]["field_count"] == 1


def test_route_validator_rejects_tampered_interruption_evidence(
    routes: dict[str, dict[str, Any]],
) -> None:
    tampered = deepcopy(routes["missed_timing"])
    tampered["presentation"]["interruption_validation_evidence"][
        "missed_effects"
    ][0]["card_code"] = 1

    assert "ocgcore_interruption_validation_evidence_mismatch" in {
        issue.code for issue in validate_route_document(tampered)
    }


def test_interruption_frame_parser_rejects_malformed_known_payload(
    routes: dict[str, dict[str, Any]],
) -> None:
    replay = deepcopy(routes["missed_timing"]["replay"])
    missed_frame = next(
        frame
        for event in replay["events"]
        for frame in event["core_output"]["frames"]
        if frame["message_type"] == 120
    )
    missed_frame["payload_hex"] = "00"

    with pytest.raises(ValueError, match="payload size must be 14"):
        derive_ocgcore_interruption_validation(replay)


def test_negation_timing_evidence_document_is_canonical(
    routes: dict[str, dict[str, Any]],
) -> None:
    evidence = json.loads(EVIDENCE_PATH.read_text(encoding="utf-8"))
    identity = {
        key: value for key, value in evidence.items() if key != "evidence_id"
    }

    assert evidence["schema_version"] == (
        "real-core-negation-timing-evidence-v1"
    )
    assert all(evidence["verification"].values())
    assert evidence["evidence_id"] == stable_digest(
        identity, prefix="negtimeev_"
    )
    for name, route in routes.items():
        assert evidence["routes"][name]["route_id"] == route["route_id"]


def test_missed_trigger_request_becomes_deterministic_path_failure() -> None:
    try:
        verify_ocgcore()
        verify_ocgcore_assets()
    except (OcgcoreBootstrapError, OSError) as exc:
        pytest.skip(f"pinned local ocgcore runtime/assets are unavailable: {exc}")
    experiment = load_experiment_document(
        EXPERIMENT_PATHS["missed_timing_failure"]
    )
    first = invoke_real_core_worker_process(experiment=experiment)
    second = invoke_real_core_worker_process(experiment=experiment)

    assert first.failure_record is not None
    assert second.failure_record is not None
    assert first.failure_record.to_dict() == second.failure_record.to_dict()
    assert first.stdout_digest == second.stdout_digest
    failure = first.failure_record
    assert failure.disposition == FailureDisposition.PATH_FAILURE
    assert failure.recovery == RecoveryAction.STOP_PATH
    assert failure.retryable is False
    actual_request = failure.context["request"]
    assert actual_request["request_type"] == "select_chain"
    assert actual_request["candidates"] == [
        {
            "candidate_id": "control:pass",
            "card_ref": None,
            "effect_ref": None,
            "kind": "pass",
            "label": "Pass",
            "payload": {
                "action_kind": "PASS",
                "response_codec": "int32",
                "response_value": -1,
            },
        }
    ]
    assert failure.context["step"]["request_type"] == "select_effect_yes_no"


@pytest.mark.parametrize("name", ["effect_negation", "missed_timing"])
def test_fresh_worker_route_identity_is_deterministic(
    routes: dict[str, dict[str, Any]], name: str
) -> None:
    replayed = build_real_core_route(
        experiment=load_experiment_document(EXPERIMENT_PATHS[name])
    )

    assert replayed["route_id"] == routes[name]["route_id"]
    assert replayed["replay"] == routes[name]["replay"]
