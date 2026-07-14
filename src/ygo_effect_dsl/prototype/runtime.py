from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Mapping

import yaml

from ygo_effect_dsl.engine.action import Action, Selection, aggregate_replay_events
from ygo_effect_dsl.engine.bridge import DecisionResponse, validate_decision_response
from ygo_effect_dsl.engine.canonical import canonical_json, stable_digest
from ygo_effect_dsl.engine.replay import (
    ReplayEventV03a,
    ReplayHistoryV03a,
    assert_complete_io_trace,
    build_scripted_output_trace,
)
from ygo_effect_dsl.experiment import assert_valid_experiment
from ygo_effect_dsl.prototype.evaluation import PrototypeEvaluation, PrototypePathEvaluator
from ygo_effect_dsl.prototype.scripted_core import ScriptedCoreSession
from ygo_effect_dsl.route_dsl import assert_valid_route_document


@dataclass(frozen=True)
class PrototypeVerificationResult:
    route_id: str
    event_count: int
    final_state_hash: str


@dataclass(frozen=True)
class _EvaluatedCheckpoint:
    document: dict[str, Any]
    evaluation: PrototypeEvaluation
    can_stop: bool
    stop_reason: str


def load_prototype_scenario(path: str | Path) -> dict[str, Any]:
    source = Path(path)
    try:
        payload = yaml.safe_load(source.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ValueError(f"invalid prototype scenario serialization: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError("prototype scenario root must be a mapping")
    return payload


def dump_route_document(document: Mapping[str, Any], path: str | Path) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.suffix.lower() == ".json":
        text = json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    else:
        text = yaml.safe_dump(dict(document), allow_unicode=True, sort_keys=False)
    destination.write_text(text, encoding="utf-8")


def build_prototype_route(scenario: Mapping[str, Any]) -> dict[str, Any]:
    session = ScriptedCoreSession(scenario)
    experiment = deepcopy(dict(scenario["experiment"]))
    assert_valid_experiment(experiment)
    evaluator_config = _nested_mapping(experiment, "evaluator", "config")
    success_config = _nested_mapping(experiment, "success_predicate", "config")
    evaluator = PrototypePathEvaluator(evaluator_config, success_config)
    experiment["prototype"] = {
        "adapter": "scripted-core",
        "scenario_id": session.scenario_id,
        "requires_validation": True,
    }
    experiment["evaluator"]["config_hash"] = evaluator.config_hash
    experiment["success_predicate"]["config_hash"] = evaluator.config_hash

    events: list[ReplayEventV03a] = []
    checkpoints: list[_EvaluatedCheckpoint] = []
    while (request := session.next_request()) is not None:
        selected_ids = session.selected_candidate_ids
        response = DecisionResponse(
            request_id=request.request_id,
            request_signature=request.request_signature,
            selected_candidate_ids=selected_ids,
            payload={"selected_candidate_ids": list(selected_ids)},
        )
        validate_decision_response(request, response)
        candidates = {candidate.candidate_id: candidate for candidate in request.candidates}
        selected_candidates = [candidates[candidate_id] for candidate_id in selected_ids]
        action_kinds = {str(candidate.payload["action_kind"]) for candidate in selected_candidates}
        if len(action_kinds) != 1:
            raise ValueError("one prototype response cannot mix multiple Action kinds")
        action = Action(
            kind=next(iter(action_kinds)),
            player=request.player,
            selections=tuple(
                Selection(
                    candidate_id=candidate.candidate_id,
                    order=index if request.constraints.ordered else None,
                    value=deepcopy(candidate.payload.get("value")),
                    payload_ref="candidate.payload",
                )
                for index, candidate in enumerate(selected_candidates)
            ),
            request_signature=request.request_signature,
        )
        transition = session.apply(action)
        step = len(events)
        raw_turn = transition.state_before.get("turn")
        turn = (
            raw_turn
            if isinstance(raw_turn, int) and not isinstance(raw_turn, bool) and raw_turn >= 1
            else None
        )
        raw_chain = transition.state_before.get("chain")
        chain_index = len(raw_chain) if isinstance(raw_chain, (list, tuple)) else None
        turn_action_index = (
            sum(1 for event in events if event.turn == turn) if turn is not None else None
        )
        next_request = session.next_request()
        response_payload = response.to_dict()
        events.append(
            ReplayEventV03a(
                step=step,
                request_signature=request.request_signature,
                action=action,
                node_id=f"node_{step}",
                request=request.to_dict(),
                core_input_ref=stable_digest(response_payload, prefix="input_"),
                core_response=response_payload,
                core_output=build_scripted_output_trace(
                    state_hash=transition.state_hash_after,
                    request_signature=(
                        next_request.request_signature
                        if next_request is not None
                        else None
                    ),
                ),
                state_hash_before=transition.state_hash_before,
                state_hash_after=transition.state_hash_after,
                turn=turn,
                turn_action_index=turn_action_index,
                chain_index=chain_index,
            )
        )
        evaluation = evaluator.evaluate(transition.state_after)
        state = transition.state_after
        checkpoints.append(
            _EvaluatedCheckpoint(
                document={
                    "step": step,
                    "state_hash": transition.state_hash_after,
                    "turn": state.get("turn"),
                    "phase": state.get("phase"),
                    "board_summary": deepcopy(state),
                    "evaluation": deepcopy(evaluation.vector),
                },
                evaluation=evaluation,
                can_stop=transition.can_stop,
                stop_reason=transition.stop_reason if transition.can_stop else "not_legal_stop",
            )
        )

    if not checkpoints:
        raise ValueError("prototype scenario produced no checkpoints")
    legal_checkpoints = [checkpoint for checkpoint in checkpoints if checkpoint.can_stop]
    if not legal_checkpoints:
        raise ValueError("prototype scenario produced no legal stop checkpoint")
    peak = legal_checkpoints[0]
    for candidate in legal_checkpoints[1:]:
        if _is_better_peak(candidate, peak):
            peak = candidate
    terminal = checkpoints[-1]
    initial_core_output = build_scripted_output_trace(
        state_hash=events[0].state_hash_before,
        request_signature=events[0].request_signature,
    )

    replay = ReplayHistoryV03a(
        initial_snapshot=session.initial_snapshot,
        version_metadata=session.version_metadata,
        seeds=session.seeds,
        events=tuple(events),
        strict_versions=True,
        initial_core_output=initial_core_output,
    ).to_dict()
    assert_complete_io_trace(replay)
    presentation = {
        "action_aggregation": aggregate_replay_events(replay["events"]).to_dict(),
        "validation": {"status": "provisional", "issue": 92},
    }
    route_identity = {
        "experiment": experiment,
        "replay": replay,
        "peak_state_hash": peak.document["state_hash"],
        "terminal_state_hash": terminal.document["state_hash"],
    }
    document = {
        "dsl": "ygo-route",
        "schema_version": "0.1",
        "route_id": stable_digest(route_identity, prefix="route_"),
        "status": "complete",
        "experiment": experiment,
        "replay": replay,
        "presentation": presentation,
        "checkpoints": [checkpoint.document for checkpoint in checkpoints],
        "result": {
            "success": peak.evaluation.success,
            "peak_board": _board_result(peak),
            "terminal_board": _board_result(terminal),
        },
        "interruptions": [],
        "lineage": {"parent_route_id": None, "fork_step": None},
    }
    assert_valid_route_document(document)
    return document


def verify_prototype_route(
    scenario: Mapping[str, Any],
    route_document: Mapping[str, Any],
) -> PrototypeVerificationResult:
    assert_valid_route_document(route_document)
    expected = build_prototype_route(scenario)
    if canonical_json(route_document) != canonical_json(expected):
        raise ValueError("Route DSL does not match a fresh deterministic replay of the prototype scenario")
    events = expected["replay"]["events"]
    return PrototypeVerificationResult(
        route_id=str(expected["route_id"]),
        event_count=len(events),
        final_state_hash=str(events[-1]["state_hash_after"]),
    )


def _nested_mapping(root: Mapping[str, Any], parent: str, child: str) -> dict[str, Any]:
    parent_value = root.get(parent)
    if not isinstance(parent_value, Mapping):
        raise ValueError(f"experiment.{parent} must be a mapping")
    child_value = parent_value.get(child)
    if not isinstance(child_value, Mapping):
        raise ValueError(f"experiment.{parent}.{child} must be a mapping")
    return dict(child_value)


def _is_better_peak(candidate: _EvaluatedCheckpoint, current: _EvaluatedCheckpoint) -> bool:
    candidate_key = (
        candidate.evaluation.success,
        candidate.evaluation.total_score,
        candidate.evaluation.tie_vector,
    )
    current_key = (
        current.evaluation.success,
        current.evaluation.total_score,
        current.evaluation.tie_vector,
    )
    if candidate_key != current_key:
        return candidate_key > current_key
    candidate_step = int(candidate.document["step"])
    current_step = int(current.document["step"])
    if candidate_step != current_step:
        return candidate_step < current_step
    return str(candidate.document["state_hash"]) < str(current.document["state_hash"])


def _board_result(checkpoint: _EvaluatedCheckpoint) -> dict[str, Any]:
    return {
        "checkpoint_step": checkpoint.document["step"],
        "state_hash": checkpoint.document["state_hash"],
        "score": checkpoint.evaluation.total_score,
        "evaluation": deepcopy(checkpoint.evaluation.vector),
        "success": checkpoint.evaluation.success,
        "stop_reason": checkpoint.stop_reason,
    }
