from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from ygo_effect_dsl.engine.canonical import stable_digest, to_canonical_data
from ygo_effect_dsl.engine.failures import (
    FailureDisposition,
    RecoveryAction,
)
from ygo_effect_dsl.experiment import load_experiment_document
from ygo_effect_dsl.prototype import (
    build_real_core_route,
    invoke_real_core_worker_process,
)
from ygo_effect_dsl.route_dsl import validate_route_document


INTERRUPTION_NEGATION_TIMING_EVIDENCE_SCHEMA_VERSION = (
    "real-core-negation-timing-evidence-v1"
)
_REPOSITORY_ROOT = Path(__file__).parents[3]
_EXPERIMENTS = _REPOSITORY_ROOT / "examples" / "experiments"
_PATHS = {
    "activation_negation": (
        _EXPERIMENTS / "real_core_interruption_matrix_targetless.yaml"
    ),
    "effect_negation": (
        _EXPERIMENTS / "real_core_interruption_effect_negation.yaml"
    ),
    "targeted_negation": (
        _EXPERIMENTS
        / "real_core_interruption_matrix_field_multi_target.yaml"
    ),
    "missed_timing": (
        _EXPERIMENTS / "real_core_interruption_missed_timing.yaml"
    ),
    "missed_timing_failure": (
        _EXPERIMENTS
        / "real_core_interruption_missed_timing_path_failure.yaml"
    ),
}


def _validation(route: Mapping[str, Any]) -> Mapping[str, Any]:
    return route["presentation"]["interruption_validation_evidence"]


def _messages(route: Mapping[str, Any]) -> list[str]:
    return [
        str(frame["message_name"])
        for batch in _validation(route)["lifecycle_batches"]
        for frame in batch["frames"]
        if frame["message_type"] in {75, 76, 120}
    ]


def _cost_move(route: Mapping[str, Any]) -> Mapping[str, Any] | None:
    return next(
        (
            move
            for move in _validation(route)["moves"]
            if move["card_code"] == 14558127 and move["reason_cost"]
        ),
        None,
    )


def _route_summary(route: Mapping[str, Any]) -> dict[str, Any]:
    replay = route["replay"]
    evidence = _validation(route)
    return to_canonical_data(
        {
            "event_count": len(replay["events"]),
            "final_state_hash": replay["events"][-1]["state_hash_after"],
            "interruption_validation_evidence_id": evidence["evidence_id"],
            "messages": _messages(route),
            "missed_effects": evidence["missed_effects"],
            "replay_id": stable_digest(replay, prefix="replay_"),
            "route_id": route["route_id"],
            "terminal_board": route["result"]["terminal_board"],
        }
    )


def build_interruption_negation_timing_evidence() -> dict[str, Any]:
    routes = {
        name: build_real_core_route(
            experiment=load_experiment_document(_PATHS[name])
        )
        for name in (
            "activation_negation",
            "effect_negation",
            "targeted_negation",
            "missed_timing",
        )
    }
    replays = {
        name: build_real_core_route(
            experiment=load_experiment_document(_PATHS[name])
        )
        for name in ("effect_negation", "missed_timing")
    }
    failure_experiment = load_experiment_document(
        _PATHS["missed_timing_failure"]
    )
    failure_runs = [
        invoke_real_core_worker_process(experiment=failure_experiment)
        for _ in range(2)
    ]
    failure_records = [run.failure_record for run in failure_runs]
    if any(record is None for record in failure_records):
        raise AssertionError("missed timing negative fixture unexpectedly succeeded")
    first_failure = failure_records[0]
    second_failure = failure_records[1]
    assert first_failure is not None
    assert second_failure is not None

    activation = routes["activation_negation"]
    effect = routes["effect_negation"]
    targeted = routes["targeted_negation"]
    missed = routes["missed_timing"]
    missed_validation = _validation(missed)
    request_after_miss = next(
        request
        for request in missed_validation["requests"]
        if request["step"] == 8
    )
    targeted_selection = targeted["replay"]["events"][6]["action"]
    verification = {
        "activation_and_effect_cost_equal": (
            _cost_move(activation) == _cost_move(effect)
            and _cost_move(activation) is not None
        ),
        "activation_and_effect_request_action_equal": (
            activation["replay"]["events"][5]["request_signature"]
            == effect["replay"]["events"][5]["request_signature"]
            and activation["replay"]["events"][5]["action"]
            == effect["replay"]["events"][5]["action"]
        ),
        "activation_negation_observed": (
            _messages(activation) == ["MSG_CHAIN_NEGATED"]
        ),
        "effect_negation_observed": (
            _messages(effect) == ["MSG_CHAIN_DISABLED"]
        ),
        "fresh_worker_replay_deterministic": all(
            replays[name]["route_id"] == routes[name]["route_id"]
            and replays[name]["replay"] == routes[name]["replay"]
            for name in replays
        ),
        "missed_effect_observed": (
            _messages(missed) == ["MSG_MISSED_EFFECT"]
            and missed_validation["missed_effects"][0]["card_code"]
            == 91800273
        ),
        "missed_request_is_pass_only": (
            request_after_miss["request_type"] == "select_chain"
            and [
                candidate["candidate_id"]
                for candidate in request_after_miss["candidates"]
            ]
            == ["control:pass"]
        ),
        "negative_failure_deterministic": (
            first_failure.to_dict() == second_failure.to_dict()
            and failure_runs[0].stdout_digest
            == failure_runs[1].stdout_digest
        ),
        "negative_failure_is_path_stop": (
            first_failure.disposition == FailureDisposition.PATH_FAILURE
            and first_failure.recovery == RecoveryAction.STOP_PATH
            and first_failure.retryable is False
        ),
        "routes_validate": all(
            not validate_route_document(route) for route in routes.values()
        ),
        "targeted_multi_link_observed": (
            len(targeted_selection["selections"]) == 2
            and _messages(targeted) == ["MSG_CHAIN_DISABLED"]
        ),
    }
    failed = sorted(key for key, value in verification.items() if value is not True)
    if failed:
        raise AssertionError(f"negation/timing evidence failed checks: {failed}")

    identity = to_canonical_data(
        {
            "failure": {
                "failure_record": first_failure.to_dict(),
                "stdout_digest": failure_runs[0].stdout_digest,
            },
            "routes": {
                name: _route_summary(route) for name, route in routes.items()
            },
            "schema_version": (
                INTERRUPTION_NEGATION_TIMING_EVIDENCE_SCHEMA_VERSION
            ),
            "verification": verification,
        }
    )
    return {
        **identity,
        "evidence_id": stable_digest(identity, prefix="negtimeev_"),
    }


def dump_interruption_negation_timing_evidence(
    path: str | Path,
) -> dict[str, Any]:
    report = build_interruption_negation_timing_evidence()
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
        / "real_core_negation_timing.json"
    )
    result = dump_interruption_negation_timing_evidence(default_output)
    print(f"wrote {default_output} evidence_id={result['evidence_id']}")
