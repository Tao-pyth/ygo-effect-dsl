from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from typing import Any, Mapping, Sequence

from ygo_effect_dsl.engine.action import Action, ActionKind
from ygo_effect_dsl.engine.canonical import (
    canonical_json,
    stable_digest,
    to_canonical_data,
)
from ygo_effect_dsl.engine.search import (
    SearchBudget,
    SearchExecutor,
    SearchFrontier,
    SearchRouteSummary,
    strategy_from_experiment,
)
from ygo_effect_dsl.experiment.schema import load_experiment_document
from ygo_effect_dsl.experiment.scenario import preflight_scenario
from ygo_effect_dsl.io_atomic import atomic_write_text
from ygo_effect_dsl.prototype import (
    RealCoreFrontierAdapter,
    verify_general_search_route,
)
from ygo_effect_dsl.route_dsl import assert_valid_route_document


STRATEGY_INTERRUPTION_MATRIX_SCHEMA_VERSION = (
    "strategy-interruption-cross-validation-v1"
)
STRATEGY_INTERRUPTION_LINEAGE_SCHEMA_VERSION = (
    "strategy-interruption-lineage-v1"
)
STRATEGY_INTERRUPTION_PROFILE_IDS = ("short", "long", "grave_banish")
STRATEGY_MATRIX_IDS = (
    "random_search_v1",
    "beam_search_v1",
    "mcts_v1",
)


class StrategyInterruptionCrossValidationError(ValueError):
    pass


class _TreatmentFrontierAdapter:
    def __init__(
        self,
        delegate: RealCoreFrontierAdapter,
        *,
        source_card_code: int,
        treatment: str,
    ) -> None:
        if treatment not in {"baseline", "interrupted"}:
            raise ValueError("treatment must be baseline or interrupted")
        self.delegate = delegate
        self.source_card_code = source_card_code
        self.treatment = treatment

    def _specified_activation(self, action: Action) -> bool:
        if action.kind != ActionKind.ACTIVATE_EFFECT:
            return False
        card_refs = (
            *(selection.card_ref for selection in action.selections),
            action.source,
        )
        return any(
            card_ref is not None
            and card_ref.public_card_id == self.source_card_code
            for card_ref in card_refs
        )

    def replay(
        self,
        experiment: Mapping[str, Any],
        action_prefix: Sequence[Action],
    ) -> SearchFrontier:
        frontier = self.delegate.replay(experiment, action_prefix)
        if frontier.legal_stop and frontier.actions:
            return replace(frontier, actions=())
        specified_actions = tuple(
            action
            for action in frontier.actions
            if self._specified_activation(action)
        )
        already_interrupted = any(
            self._specified_activation(action) for action in action_prefix
        )
        if self.treatment == "baseline":
            filtered = tuple(
                action
                for action in frontier.actions
                if not self._specified_activation(action)
            )
            if filtered != frontier.actions:
                return replace(frontier, actions=filtered)
        elif specified_actions and not already_interrupted:
            return replace(frontier, actions=specified_actions)
        return frontier


def _mapping(value: Any, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise StrategyInterruptionCrossValidationError(f"{path} must be a mapping")
    return value


def _sequence(value: Any, path: str) -> Sequence[Any]:
    if not isinstance(value, Sequence) or isinstance(
        value, (str, bytes, bytearray)
    ):
        raise StrategyInterruptionCrossValidationError(
            f"{path} must be a sequence"
        )
    return value


def _string(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value:
        raise StrategyInterruptionCrossValidationError(
            f"{path} must be a non-empty string"
        )
    return value


def _integer(value: Any, path: str, *, minimum: int = 0) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < minimum:
        raise StrategyInterruptionCrossValidationError(
            f"{path} must be an integer >= {minimum}"
        )
    return value


def _request_identity(event: Mapping[str, Any], path: str) -> dict[str, Any]:
    request = _mapping(event.get("request"), f"{path}.request")
    candidates = [
        _mapping(candidate, f"{path}.request.candidates[{index}]")
        for index, candidate in enumerate(
            _sequence(request.get("candidates"), f"{path}.request.candidates")
        )
    ]
    candidate_ids = [
        _string(candidate.get("candidate_id"), f"{path}.candidate_id")
        for candidate in candidates
    ]
    if len(candidate_ids) != len(set(candidate_ids)):
        raise StrategyInterruptionCrossValidationError(
            f"{path}.request has duplicate candidate IDs"
        )
    return {
        "candidate_ids": candidate_ids,
        "constraints": to_canonical_data(request.get("constraints")),
        "player": request.get("player"),
        "request_signature": _string(
            event.get("request_signature"), f"{path}.request_signature"
        ),
        "request_type": _string(
            request.get("request_type"), f"{path}.request.request_type"
        ),
    }


def _action_identity(event: Mapping[str, Any], path: str) -> dict[str, Any]:
    action = _mapping(event.get("action"), f"{path}.action")
    selections = [
        _mapping(selection, f"{path}.action.selections[{index}]")
        for index, selection in enumerate(
            _sequence(action.get("selections"), f"{path}.action.selections")
        )
    ]
    return {
        "candidate_ids": [
            _string(selection.get("candidate_id"), f"{path}.candidate_id")
            for selection in selections
        ],
        "kind": _string(action.get("kind"), f"{path}.action.kind"),
        "request_signature": _string(
            action.get("request_signature"),
            f"{path}.action.request_signature",
        ),
    }


def _event_semantics(event: Mapping[str, Any], path: str) -> dict[str, Any]:
    return {
        "action": _action_identity(event, path),
        "chain_index": _integer(event.get("chain_index"), f"{path}.chain_index"),
        "core_response": to_canonical_data(event.get("core_response")),
        "request": _request_identity(event, path),
        "state_hash_after": _string(
            event.get("state_hash_after"), f"{path}.state_hash_after"
        ),
        "state_hash_before": _string(
            event.get("state_hash_before"), f"{path}.state_hash_before"
        ),
        "step": _integer(event.get("step"), f"{path}.step"),
        "turn": _integer(event.get("turn"), f"{path}.turn", minimum=1),
        "turn_action_index": _integer(
            event.get("turn_action_index"), f"{path}.turn_action_index"
        ),
    }


def _route_events(route: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    replay = _mapping(route.get("replay"), "route.replay")
    events = [
        _mapping(event, f"route.replay.events[{index}]")
        for index, event in enumerate(
            _sequence(replay.get("events"), "route.replay.events")
        )
    ]
    if not events:
        raise StrategyInterruptionCrossValidationError(
            "cross-validation Route must contain Replay events"
        )
    return events


def _route_trace(route: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    presentation = _mapping(route.get("presentation"), "route.presentation")
    return [
        _mapping(item, f"route.specified_interruption_trace[{index}]")
        for index, item in enumerate(
            _sequence(
                presentation.get("specified_interruption_trace", []),
                "route.presentation.specified_interruption_trace",
            )
        )
    ]


def build_route_semantic_observation(
    route: Mapping[str, Any],
    *,
    deck_sha256: str,
) -> dict[str, Any]:
    assert_valid_route_document(route)
    events = _route_events(route)
    result = _mapping(route.get("result"), "route.result")
    terminal = _mapping(result.get("terminal_board"), "route.result.terminal_board")
    event_semantics = [
        _event_semantics(event, f"route.replay.events[{index}]")
        for index, event in enumerate(events)
    ]
    identity = {
        "deck_sha256": _string(deck_sha256, "deck_sha256"),
        "events": event_semantics,
        "schema_version": "strategy-route-semantics-v1",
        "success": result.get("success"),
        "terminal": {
            "phase": terminal.get("phase"),
            "score": terminal.get("score"),
            "state_hash": terminal.get("state_hash"),
            "stop_reason": terminal.get("stop_reason"),
            "turn": terminal.get("turn"),
        },
    }
    return {
        "action_count": len(events),
        "event_semantic_ids": [
            stable_digest(event, prefix="strategyevent_")
            for event in event_semantics
        ],
        "route_id": _string(route.get("route_id"), "route.route_id"),
        "semantic_id": stable_digest(identity, prefix="strategyroute_"),
        "specified_interruption_count": len(_route_trace(route)),
        "terminal": identity["terminal"],
    }


def build_strategy_interruption_lineage(
    baseline_route: Mapping[str, Any],
    interrupted_route: Mapping[str, Any],
    *,
    deck_sha256: str,
) -> dict[str, Any]:
    baseline_events = _route_events(baseline_route)
    interrupted_events = _route_events(interrupted_route)
    trace = _route_trace(interrupted_route)
    if _route_trace(baseline_route):
        raise StrategyInterruptionCrossValidationError(
            "baseline Route must not contain an applied specified interruption"
        )
    if len(trace) != 1:
        raise StrategyInterruptionCrossValidationError(
            "interrupted Route must contain exactly one specified interruption"
        )
    activation = _mapping(trace[0].get("activation"), "trace.activation")
    fork_step = _integer(
        activation.get("action_step"), "trace.activation.action_step"
    )
    if fork_step >= len(baseline_events) or fork_step >= len(interrupted_events):
        raise StrategyInterruptionCrossValidationError(
            "interruption fork step is outside baseline/interrupted Replay"
        )
    baseline_prefix = [
        _event_semantics(event, f"baseline.events[{index}]")
        for index, event in enumerate(baseline_events[:fork_step])
    ]
    interrupted_prefix = [
        _event_semantics(event, f"interrupted.events[{index}]")
        for index, event in enumerate(interrupted_events[:fork_step])
    ]
    if baseline_prefix != interrupted_prefix:
        raise StrategyInterruptionCrossValidationError(
            "baseline/interrupted prefix diverged before the recorded fork"
        )
    baseline_fork = baseline_events[fork_step]
    interrupted_fork = interrupted_events[fork_step]
    baseline_request = _request_identity(baseline_fork, "baseline.fork")
    interrupted_request = _request_identity(interrupted_fork, "interrupted.fork")
    if baseline_request != interrupted_request:
        raise StrategyInterruptionCrossValidationError(
            "baseline/interrupted fork DecisionRequest does not match"
        )
    baseline_action = _action_identity(baseline_fork, "baseline.fork")
    interrupted_action = _action_identity(interrupted_fork, "interrupted.fork")
    activation_candidates = [
        _string(value, "trace.activation.candidate_ids[*]")
        for value in _sequence(
            activation.get("candidate_ids"), "trace.activation.candidate_ids"
        )
    ]
    if interrupted_action["kind"] != "ACTIVATE_EFFECT":
        raise StrategyInterruptionCrossValidationError(
            "interrupted fork Action must activate the specified effect"
        )
    if interrupted_action["candidate_ids"] != activation_candidates:
        raise StrategyInterruptionCrossValidationError(
            "interrupted fork Action does not match trace candidates"
        )
    if not set(activation_candidates).issubset(baseline_request["candidate_ids"]):
        raise StrategyInterruptionCrossValidationError(
            "specified activation candidate is absent from the baseline request"
        )
    if baseline_action == interrupted_action:
        raise StrategyInterruptionCrossValidationError(
            "baseline and interrupted fork Actions must diverge"
        )
    response_steps = [
        _mapping(value, f"trace.response_steps[{index}]")
        for index, value in enumerate(
            _sequence(trace[0].get("response_steps"), "trace.response_steps")
        )
    ]
    for response_index, response in enumerate(response_steps):
        action_step = _integer(
            response.get("action_step"),
            f"trace.response_steps[{response_index}].action_step",
        )
        expected_step = fork_step + response_index + 1
        if action_step != expected_step or action_step >= len(interrupted_events):
            raise StrategyInterruptionCrossValidationError(
                "specified response sequence is not contiguous"
            )
        action = _action_identity(
            interrupted_events[action_step], f"interrupted.events[{action_step}]"
        )
        expected_candidates = list(
            _sequence(
                response.get("candidate_ids"),
                f"trace.response_steps[{response_index}].candidate_ids",
            )
        )
        if action["candidate_ids"] != expected_candidates:
            raise StrategyInterruptionCrossValidationError(
                "specified response Action does not match trace candidates"
            )
    recovery_start = fork_step + len(response_steps) + 1
    if recovery_start >= len(interrupted_events):
        raise StrategyInterruptionCrossValidationError(
            "interrupted Route has no recovery tail after the specified response"
        )
    baseline_observation = build_route_semantic_observation(
        baseline_route, deck_sha256=deck_sha256
    )
    interrupted_observation = build_route_semantic_observation(
        interrupted_route, deck_sha256=deck_sha256
    )
    divergence_identity = {
        "baseline_action": baseline_action,
        "fork_request": baseline_request,
        "fork_step": fork_step,
        "interrupted_action": interrupted_action,
        "schema_version": "strategy-first-divergence-v1",
        "state_hash_before": baseline_fork.get("state_hash_before"),
    }
    recovery_semantics = [
        _event_semantics(event, f"interrupted.recovery[{index}]")
        for index, event in enumerate(interrupted_events[recovery_start:])
    ]
    recovery_event_semantic_ids = [
        stable_digest(event, prefix="strategyrecoveryevent_")
        for event in recovery_semantics
    ]
    identity = {
        "baseline_semantic_id": baseline_observation["semantic_id"],
        "divergence": divergence_identity,
        "interrupted_semantic_id": interrupted_observation["semantic_id"],
        "recovery_event_semantic_ids": recovery_event_semantic_ids,
        "schema_version": STRATEGY_INTERRUPTION_LINEAGE_SCHEMA_VERSION,
        "trace_id": trace[0].get("trace_id"),
    }
    return {
        **identity,
        "divergence_id": stable_digest(
            divergence_identity, prefix="strategydivergence_"
        ),
        "lineage_id": stable_digest(identity, prefix="strategylineage_"),
        "recovery_action_count": len(recovery_semantics),
        "status": "validated",
    }


def _strategy_experiment(
    base: Mapping[str, Any], strategy_id: str
) -> dict[str, Any]:
    experiment = deepcopy(dict(base))
    search = dict(_mapping(experiment.get("search"), "experiment.search"))
    shared = {
        "max_frontier_actions": int(
            _mapping(search.get("parameters", {}), "search.parameters").get(
                "max_frontier_actions", 128
            )
        ),
        "seed": 0,
        "termination": {},
    }
    search["budget"] = {"max_depth": 8, "max_nodes": 12, "max_replays": 12}
    search["strategy"] = strategy_id
    if strategy_id == "random_search_v1":
        search["parameters"] = shared
    elif strategy_id == "beam_search_v1":
        search["parameters"] = {**shared, "beam_width": 2}
    elif strategy_id == "mcts_v1":
        search["parameters"] = {
            **shared,
            "reward_ceiling": 100,
            "reward_floor": 0,
            "simulations": 5,
        }
    else:
        raise StrategyInterruptionCrossValidationError(
            f"unsupported matrix strategy {strategy_id!r}"
        )
    experiment["search"] = search
    return experiment


def _select_treatment_route(
    routes: Sequence[SearchRouteSummary], *, interrupted: bool
) -> SearchRouteSummary:
    matching = []
    for route in routes:
        trace_count = len(_route_trace(route.route_document))
        if (trace_count == 1) == interrupted:
            matching.append(route)
    if not matching:
        treatment = "interrupted" if interrupted else "baseline"
        raise StrategyInterruptionCrossValidationError(
            f"SearchRun produced no {treatment} legal Route"
        )
    return min(matching, key=lambda route: (route.action_count, route.action_ids))


def run_strategy_interruption_cross_validation(
    experiments: Mapping[str, str | Path],
    *,
    external_root: str | Path | None = None,
    worker_timeout: float = 30.0,
    max_retries: int = 1,
) -> dict[str, Any]:
    if tuple(experiments) != STRATEGY_INTERRUPTION_PROFILE_IDS:
        raise StrategyInterruptionCrossValidationError(
            "experiments must be ordered short, long, grave_banish"
        )
    profiles = []
    for profile_id in STRATEGY_INTERRUPTION_PROFILE_IDS:
        experiment_path = Path(experiments[profile_id]).resolve()
        base = load_experiment_document(experiment_path)
        if base.get("schema_version") != "0.4":
            raise StrategyInterruptionCrossValidationError(
                f"{profile_id} requires Experiment 0.4"
            )
        interruption = _mapping(
            base.get("interruption"), f"{profile_id}.interruption"
        )
        definitions = _sequence(
            interruption.get("definitions"), f"{profile_id}.interruption.definitions"
        )
        if interruption.get("mode") != "specified" or len(definitions) != 1:
            raise StrategyInterruptionCrossValidationError(
                f"{profile_id} requires one specified interruption definition"
            )
        definition = _mapping(definitions[0], f"{profile_id}.interruption.definitions[0]")
        source_card_code = _integer(
            definition.get("source_card_code"),
            f"{profile_id}.interruption.definitions[0].source_card_code",
            minimum=1,
        )
        preflight = preflight_scenario(
            base,
            experiment_path=experiment_path,
            external_root=external_root,
        )
        if not preflight.ok or preflight.manifest is None:
            raise StrategyInterruptionCrossValidationError(
                f"{profile_id} scenario preflight failed: {canonical_json(preflight.to_dict())}"
            )
        strategy_runs = []
        for strategy_id in STRATEGY_MATRIX_IDS:
            experiment = _strategy_experiment(base, strategy_id)
            treatment_results: dict[
                str, tuple[Any, SearchRouteSummary, Any, dict[str, Any]]
            ] = {}
            for treatment, interrupted_expected in (
                ("baseline", False),
                ("interrupted", True),
            ):
                adapter = _TreatmentFrontierAdapter(
                    RealCoreFrontierAdapter(
                        external_root=external_root,
                        experiment_path=experiment_path,
                        timeout_seconds=worker_timeout,
                        max_retries=max_retries,
                    ),
                    source_card_code=source_card_code,
                    treatment=treatment,
                )
                result = SearchExecutor(
                    adapter,
                    strategy_from_experiment(experiment),
                    SearchBudget.from_experiment(experiment),
                ).run(experiment)
                try:
                    route = _select_treatment_route(
                        result.routes, interrupted=interrupted_expected
                    )
                except StrategyInterruptionCrossValidationError as exc:
                    raise StrategyInterruptionCrossValidationError(
                        f"{profile_id}/{strategy_id}/{treatment}: {exc}"
                    ) from exc
                verification = verify_general_search_route(
                    route.route_document,
                    external_root=external_root,
                    experiment_path=experiment_path,
                    timeout_seconds=worker_timeout,
                )
                observation = build_route_semantic_observation(
                    route.route_document,
                    deck_sha256=preflight.manifest.deck_sha256,
                )
                treatment_results[treatment] = (
                    result,
                    route,
                    verification,
                    observation,
                )
            baseline_result, baseline, baseline_verification, baseline_observation = (
                treatment_results["baseline"]
            )
            (
                interrupted_result,
                interrupted,
                interrupted_verification,
                interrupted_observation,
            ) = treatment_results["interrupted"]
            lineage = build_strategy_interruption_lineage(
                baseline.route_document,
                interrupted.route_document,
                deck_sha256=preflight.manifest.deck_sha256,
            )
            strategy_runs.append(
                {
                    "baseline": {
                        **baseline_observation,
                        "fresh_replay_event_count": baseline_verification.event_count,
                        "fresh_replay_state_hash": (
                            baseline_verification.final_state_hash
                        ),
                    },
                    "interrupted": {
                        **interrupted_observation,
                        "fresh_replay_event_count": interrupted_verification.event_count,
                        "fresh_replay_state_hash": (
                            interrupted_verification.final_state_hash
                        ),
                    },
                    "lineage": lineage,
                    "nodes": {
                        "baseline": baseline_result.nodes,
                        "interrupted": interrupted_result.nodes,
                    },
                    "path_failure_count": {
                        "baseline": len(baseline_result.path_failures),
                        "interrupted": len(interrupted_result.path_failures),
                    },
                    "replays": {
                        "baseline": baseline_result.replays,
                        "interrupted": interrupted_result.replays,
                    },
                    "run_ids": {
                        "baseline": baseline_result.run_id,
                        "interrupted": interrupted_result.run_id,
                    },
                    "strategy_id": strategy_id,
                    "termination_reasons": {
                        "baseline": baseline_result.termination_reason,
                        "interrupted": interrupted_result.termination_reason,
                    },
                }
            )
        baseline_ids = {run["baseline"]["semantic_id"] for run in strategy_runs}
        interrupted_ids = {
            run["interrupted"]["semantic_id"] for run in strategy_runs
        }
        divergence_ids = {run["lineage"]["divergence_id"] for run in strategy_runs}
        if len(baseline_ids) != 1:
            raise StrategyInterruptionCrossValidationError(
                f"{profile_id} baseline semantics differ across strategies"
            )
        if len(interrupted_ids) != 1:
            raise StrategyInterruptionCrossValidationError(
                f"{profile_id} interrupted/recovery semantics differ across strategies"
            )
        if len(divergence_ids) != 1:
            raise StrategyInterruptionCrossValidationError(
                f"{profile_id} first divergence differs across strategies"
            )
        profiles.append(
            {
                "cross_strategy": {
                    "baseline_semantic_id": next(iter(baseline_ids)),
                    "divergence_id": next(iter(divergence_ids)),
                    "interrupted_semantic_id": next(iter(interrupted_ids)),
                    "status": "matched",
                },
                "deck": {
                    "deck_id": preflight.manifest.deck_id,
                    "deck_sha256": preflight.manifest.deck_sha256,
                    "source": preflight.manifest.deck_source,
                },
                "profile_id": profile_id,
                "strategy_runs": strategy_runs,
            }
        )
    deck_hashes = {profile["deck"]["deck_sha256"] for profile in profiles}
    if len(deck_hashes) != len(STRATEGY_INTERRUPTION_PROFILE_IDS):
        raise StrategyInterruptionCrossValidationError(
            "matrix profiles must use three distinct normalized decks"
        )
    identity = {
        "coverage": {
            "deck_count": len(profiles),
            "matrix_cell_count": len(profiles) * len(STRATEGY_MATRIX_IDS),
            "profile_ids": list(STRATEGY_INTERRUPTION_PROFILE_IDS),
            "strategy_ids": list(STRATEGY_MATRIX_IDS),
            "treatments": ["baseline", "interrupted", "recovery"],
            "route_stop_policy": "first_core_legal_stop",
        },
        "execution_invariance_contracts": {
            "cache": "prefix-cache-verification-v1",
            "parallel": "parallel-search-aggregate-v2",
            "retry": "parallel-worker-attempt-v1",
            "scope": "validated by strategy conformance and failure-injection regressions",
        },
        "profiles": profiles,
        "schema_version": STRATEGY_INTERRUPTION_MATRIX_SCHEMA_VERSION,
        "status": "qualified_local",
    }
    return {
        **identity,
        "qualification_id": stable_digest(identity, prefix="strategyintmatrix_"),
    }


def write_strategy_interruption_cross_validation(
    path: str | Path, report: Mapping[str, Any]
) -> None:
    if report.get("schema_version") != STRATEGY_INTERRUPTION_MATRIX_SCHEMA_VERSION:
        raise StrategyInterruptionCrossValidationError(
            "unsupported strategy/interruption matrix schema"
        )
    identity = {key: value for key, value in report.items() if key != "qualification_id"}
    if report.get("qualification_id") != stable_digest(
        identity, prefix="strategyintmatrix_"
    ):
        raise StrategyInterruptionCrossValidationError(
            "strategy/interruption matrix qualification ID mismatch"
        )
    atomic_write_text(path, canonical_json(report) + "\n")


__all__ = [
    "STRATEGY_INTERRUPTION_LINEAGE_SCHEMA_VERSION",
    "STRATEGY_INTERRUPTION_MATRIX_SCHEMA_VERSION",
    "STRATEGY_INTERRUPTION_PROFILE_IDS",
    "STRATEGY_MATRIX_IDS",
    "StrategyInterruptionCrossValidationError",
    "build_route_semantic_observation",
    "build_strategy_interruption_lineage",
    "run_strategy_interruption_cross_validation",
    "write_strategy_interruption_cross_validation",
]
