from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any, Mapping

from ygo_effect_dsl.engine.canonical import stable_digest, to_canonical_data
from ygo_effect_dsl.engine.interruption import (
    InterruptionValidationPolicy,
    classify_interruption_candidates,
)
from ygo_effect_dsl.experiment import load_experiment_document
from ygo_effect_dsl.prototype import build_real_core_route
from ygo_effect_dsl.route_dsl import validate_route_document


INTERRUPTION_DAMAGE_STEP_EVIDENCE_SCHEMA_VERSION = (
    "real-core-damage-step-evidence-v1"
)
_REPOSITORY_ROOT = Path(__file__).parents[3]
_EXPERIMENT_PATH = (
    _REPOSITORY_ROOT
    / "examples"
    / "experiments"
    / "real_core_interruption_damage_step.yaml"
)
_SOURCE_CARD_CODE = 14558127
_ACTIVATION_STEP = 16


def _validation(route: Mapping[str, Any]) -> Mapping[str, Any]:
    return route["presentation"]["interruption_validation_evidence"]


def _activation_event(route: Mapping[str, Any]) -> Mapping[str, Any]:
    event = route["replay"]["events"][_ACTIVATION_STEP]
    action = event["action"]
    if action["kind"] != "ACTIVATE_EFFECT":
        raise AssertionError("damage-step fixture activation step changed")
    return event


def _activation_request(route: Mapping[str, Any]) -> Mapping[str, Any]:
    request = _activation_event(route)["request"]
    if request["request_type"] != "select_chain":
        raise AssertionError("damage-step activation is not a chain request")
    return request


def _cost_move(route: Mapping[str, Any]) -> Mapping[str, Any]:
    return next(
        move
        for move in _validation(route)["moves"]
        if move["card_code"] == _SOURCE_CARD_CODE and move["reason_cost"]
    )


def _route_summary(route: Mapping[str, Any]) -> dict[str, Any]:
    replay = route["replay"]
    activation = _activation_event(route)
    activation_action = activation["action"]
    activation_request = _activation_request(route)
    activation_candidates = [
        candidate["candidate_id"]
        for candidate in activation_request["candidates"]
    ]
    return to_canonical_data(
        {
            "activation": {
                "action_id": activation_action["action_id"],
                "action_occurrence_id": activation["action_occurrence_id"],
                "candidate_ids": activation_candidates,
                "player": activation_action["player"],
                "request_signature": activation["request_signature"],
                "source": activation_action["source"],
                "state_hash_before": activation["state_hash_before"],
                "step": activation["step"],
                "turn": activation["turn"],
                "turn_action_index": activation["turn_action_index"],
            },
            "event_count": len(replay["events"]),
            "final_state_hash": replay["events"][-1]["state_hash_after"],
            "interruption_validation_evidence_id": _validation(route)[
                "evidence_id"
            ],
            "replay_id": stable_digest(replay, prefix="replay_"),
            "route_id": route["route_id"],
            "terminal_board": route["result"]["terminal_board"],
        }
    )


def build_interruption_damage_step_evidence() -> dict[str, Any]:
    experiment = load_experiment_document(_EXPERIMENT_PATH)
    routes = [
        build_real_core_route(experiment=experiment),
        build_real_core_route(experiment=experiment),
    ]
    primary = routes[0]
    replayed = routes[1]
    request = _activation_request(primary)
    policy = InterruptionValidationPolicy().register_verified("damage_step")
    taxonomy = classify_interruption_candidates(
        request,
        source_card_code=_SOURCE_CARD_CODE,
        source_player=1,
        source_zone="hand",
        policy=policy,
        expected_candidate_ids=("chain:0",),
        validation_categories=("damage_step",),
    )
    unregistered_taxonomy = classify_interruption_candidates(
        request,
        source_card_code=_SOURCE_CARD_CODE,
        source_player=1,
        source_zone="hand",
        expected_candidate_ids=("chain:0",),
        validation_categories=("damage_step",),
    )
    ambiguous_request = deepcopy(request)
    ambiguous_request["candidates"] = [
        ambiguous_request["candidates"][0],
        ambiguous_request["candidates"][0],
    ]
    ambiguous_taxonomy = classify_interruption_candidates(
        ambiguous_request,
        source_card_code=_SOURCE_CARD_CODE,
        source_player=1,
        source_zone="hand",
        policy=policy,
        validation_categories=("damage_step",),
    )
    cost_move = _cost_move(primary)
    verification = {
        "activation_candidate_exposed_by_core": (
            [
                candidate["candidate_id"]
                for candidate in request["candidates"]
            ]
            == ["chain:0", "control:pass"]
            and request["candidates"][0]["card_ref"]["public_card_id"]
            == _SOURCE_CARD_CODE
        ),
        "activation_cost_moves_source_to_graveyard": (
            cost_move["previous"]["location"] == 2
            and cost_move["current"]["location"] == 16
            and cost_move["reason_cost"] is True
        ),
        "damage_step_taxonomy_registered_fixture_only": (
            taxonomy.supported
            and taxonomy.candidates[0].validation_categories == ("damage_step",)
            and unregistered_taxonomy.status == "unsupported_category"
            and unregistered_taxonomy.diagnostics[0].code
            == "unverified_fixture_category"
        ),
        "fresh_real_core_replay_two_repetitions": (
            replayed["route_id"] == primary["route_id"]
            and replayed["replay"] == primary["replay"]
        ),
        "no_python_effect_or_timing_inference": (
            experiment["interruption"]["definitions"][0][
                "validation_categories"
            ]
            == ["damage_step"]
            and taxonomy.candidates[0].candidate_id == "chain:0"
        ),
        "routes_validate": all(
            not validate_route_document(route) for route in routes
        ),
        "unsupported_or_ambiguous_candidate_shapes_fail_closed": (
            ambiguous_taxonomy.status == "configuration_failure"
            and ambiguous_taxonomy.diagnostics[0].code
            == "ambiguous_candidate_identity"
        ),
    }
    failed = sorted(key for key, value in verification.items() if value is not True)
    if failed:
        raise AssertionError(f"damage-step evidence failed checks: {failed}")

    identity = to_canonical_data(
        {
            "category": {
                "default_runtime_policy": "fail_closed",
                "registered_fixture_category": "damage_step",
                "scope": "pinned_real_core_fixture_only",
                "timing_authority": "fixture_lua_condition_and_ocgcore_decision_request",
            },
            "route": _route_summary(primary),
            "schema_version": (
                INTERRUPTION_DAMAGE_STEP_EVIDENCE_SCHEMA_VERSION
            ),
            "taxonomy": {
                "ambiguous_shape": ambiguous_taxonomy.to_dict(),
                "registered": taxonomy.to_dict(),
                "unregistered": unregistered_taxonomy.to_dict(),
            },
            "verification": verification,
        }
    )
    return {
        **identity,
        "evidence_id": stable_digest(identity, prefix="damagestepev_"),
    }


def dump_interruption_damage_step_evidence(path: str | Path) -> dict[str, Any]:
    report = build_interruption_damage_step_evidence()
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return report


if __name__ == "__main__":
    default_output = (
        _REPOSITORY_ROOT
        / "docs"
        / "interruption"
        / "evidence"
        / "real_core_damage_step.json"
    )
    result = dump_interruption_damage_step_evidence(default_output)
    print(f"wrote {default_output} evidence_id={result['evidence_id']}")
