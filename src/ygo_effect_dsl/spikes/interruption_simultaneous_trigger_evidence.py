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


INTERRUPTION_SIMULTANEOUS_TRIGGER_EVIDENCE_SCHEMA_VERSION = (
    "real-core-simultaneous-trigger-evidence-v1"
)
_REPOSITORY_ROOT = Path(__file__).parents[3]
_EXPERIMENTS = _REPOSITORY_ROOT / "examples" / "experiments"
_CONTROL_EXPERIMENT = (
    _EXPERIMENTS / "real_core_interruption_simultaneous_trigger.yaml"
)
_SELECT_FIRST_EXPERIMENT = (
    _EXPERIMENTS / "real_core_interruption_simultaneous_trigger_select_first.yaml"
)
_SOURCE_CARD_CODE = 91800273
_SECOND_CARD_CODE = 10045474
_TRIGGER_STEP = 4


def _validation(route: Mapping[str, Any]) -> Mapping[str, Any]:
    return route["presentation"]["interruption_validation_evidence"]


def _trigger_event(route: Mapping[str, Any]) -> Mapping[str, Any]:
    event = route["replay"]["events"][_TRIGGER_STEP]
    if event["request"]["request_type"] != "select_chain":
        raise AssertionError("simultaneous trigger request step changed")
    return event


def _candidate_order(route: Mapping[str, Any]) -> list[dict[str, Any]]:
    request = _trigger_event(route)["request"]
    return [
        {
            "candidate_id": candidate["candidate_id"],
            "card_code": (
                candidate.get("card_ref") or {}
            ).get("public_card_id"),
            "kind": candidate["kind"],
        }
        for candidate in request["candidates"]
    ]


def _route_summary(route: Mapping[str, Any]) -> dict[str, Any]:
    replay = route["replay"]
    event = _trigger_event(route)
    return to_canonical_data(
        {
            "candidate_order": _candidate_order(route),
            "event_count": len(replay["events"]),
            "final_state_hash": replay["events"][-1]["state_hash_after"],
            "interruption_validation_evidence_id": _validation(route)[
                "evidence_id"
            ],
            "replay_id": stable_digest(replay, prefix="replay_"),
            "route_id": route["route_id"],
            "selected_action": event["action"],
            "state_hash_before": event["state_hash_before"],
            "terminal_board": route["result"]["terminal_board"],
            "trigger_step": event["step"],
        }
    )


def build_interruption_simultaneous_trigger_evidence() -> dict[str, Any]:
    control_experiment = load_experiment_document(_CONTROL_EXPERIMENT)
    selected_experiment = load_experiment_document(_SELECT_FIRST_EXPERIMENT)
    control = build_real_core_route(experiment=control_experiment)
    selected = build_real_core_route(experiment=selected_experiment)
    selected_replay = build_real_core_route(experiment=selected_experiment)
    request = _trigger_event(control)["request"]
    policy = InterruptionValidationPolicy().register_verified(
        "simultaneous_trigger"
    )
    taxonomy = classify_interruption_candidates(
        request,
        source_card_code=_SOURCE_CARD_CODE,
        source_player=0,
        source_zone="field",
        policy=policy,
        expected_candidate_ids=("chain:0",),
        validation_categories=("simultaneous_trigger",),
    )
    unregistered_taxonomy = classify_interruption_candidates(
        request,
        source_card_code=_SOURCE_CARD_CODE,
        source_player=0,
        source_zone="field",
        expected_candidate_ids=("chain:0",),
        validation_categories=("simultaneous_trigger",),
    )
    missing_taxonomy = classify_interruption_candidates(
        request,
        source_card_code=_SOURCE_CARD_CODE,
        source_player=0,
        source_zone="field",
        policy=policy,
        expected_candidate_ids=("chain:missing",),
        validation_categories=("simultaneous_trigger",),
    )
    ambiguous_request = deepcopy(request)
    ambiguous_request["candidates"] = [
        ambiguous_request["candidates"][0],
        ambiguous_request["candidates"][0],
        ambiguous_request["candidates"][2],
    ]
    ambiguous_taxonomy = classify_interruption_candidates(
        ambiguous_request,
        source_card_code=_SOURCE_CARD_CODE,
        source_player=0,
        source_zone="field",
        policy=policy,
        validation_categories=("simultaneous_trigger",),
    )
    selected_event = _trigger_event(selected)
    followup_event = selected["replay"]["events"][_TRIGGER_STEP + 1]
    verification = {
        "candidate_disappearance_fails_closed": (
            missing_taxonomy.status == "path_failure"
            and missing_taxonomy.diagnostics[0].code
            == "candidate_disappeared"
        ),
        "candidate_order_exposed_by_core": _candidate_order(control)
        == [
            {
                "candidate_id": "chain:0",
                "card_code": _SOURCE_CARD_CODE,
                "kind": "effect",
            },
            {
                "candidate_id": "chain:1",
                "card_code": _SECOND_CARD_CODE,
                "kind": "effect",
            },
            {
                "candidate_id": "control:pass",
                "card_code": None,
                "kind": "pass",
            },
        ],
        "fresh_real_core_selected_replay_two_repetitions": (
            selected_replay["route_id"] == selected["route_id"]
            and selected_replay["replay"] == selected["replay"]
        ),
        "selected_occurrence_replayed": (
            selected_event["action"]["kind"] == "ACTIVATE_EFFECT"
            and selected_event["action"]["selections"][0]["candidate_id"]
            == "chain:0"
            and followup_event["request"]["candidates"][0]["candidate_id"]
            == "chain:0"
            and followup_event["request"]["candidates"][0]["card_ref"][
                "public_card_id"
            ]
            == _SECOND_CARD_CODE
        ),
        "simultaneous_taxonomy_registered_fixture_only": (
            taxonomy.supported
            and taxonomy.candidates[0].validation_categories
            == ("simultaneous_trigger",)
            and unregistered_taxonomy.status == "unsupported_category"
            and unregistered_taxonomy.diagnostics[0].code
            == "unverified_fixture_category"
        ),
        "routes_validate": all(
            not validate_route_document(route) for route in (control, selected)
        ),
        "unsupported_or_ambiguous_candidate_shapes_fail_closed": (
            ambiguous_taxonomy.status == "configuration_failure"
            and ambiguous_taxonomy.diagnostics[0].code
            == "ambiguous_candidate_identity"
        ),
    }
    failed = sorted(key for key, value in verification.items() if value is not True)
    if failed:
        raise AssertionError(
            f"simultaneous-trigger evidence failed checks: {failed}"
        )

    identity = to_canonical_data(
        {
            "category": {
                "default_runtime_policy": "fail_closed",
                "registered_fixture_category": "simultaneous_trigger",
                "scope": "pinned_real_core_fixture_only",
                "ordering_authority": "ocgcore_decision_request_candidate_order",
            },
            "routes": {
                "control": _route_summary(control),
                "select_first": _route_summary(selected),
            },
            "schema_version": (
                INTERRUPTION_SIMULTANEOUS_TRIGGER_EVIDENCE_SCHEMA_VERSION
            ),
            "taxonomy": {
                "ambiguous_shape": ambiguous_taxonomy.to_dict(),
                "candidate_missing": missing_taxonomy.to_dict(),
                "registered": taxonomy.to_dict(),
                "unregistered": unregistered_taxonomy.to_dict(),
            },
            "verification": verification,
        }
    )
    return {
        **identity,
        "evidence_id": stable_digest(identity, prefix="simtrigev_"),
    }


def dump_interruption_simultaneous_trigger_evidence(
    path: str | Path,
) -> dict[str, Any]:
    report = build_interruption_simultaneous_trigger_evidence()
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
        / "real_core_simultaneous_trigger.json"
    )
    result = dump_interruption_simultaneous_trigger_evidence(default_output)
    print(f"wrote {default_output} evidence_id={result['evidence_id']}")
