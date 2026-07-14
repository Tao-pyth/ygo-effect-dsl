from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Mapping

from ygo_effect_dsl.engine.action import Action, ActionKind
from ygo_effect_dsl.engine.bridge import Candidate, DecisionConstraints, DecisionContext, DecisionRequest
from ygo_effect_dsl.engine.canonical import stable_digest


PROTOTYPE_SCENARIO_SCHEMA_VERSION = "0.1"


def _mapping(value: Any, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{path} must be a mapping")
    return value


def _list(value: Any, path: str) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError(f"{path} must be a list")
    return value


def _string(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{path} must be a non-empty string")
    return value


@dataclass(frozen=True)
class ScriptedTransition:
    state_before: dict[str, Any]
    state_after: dict[str, Any]
    state_hash_before: str
    state_hash_after: str
    can_stop: bool
    stop_reason: str


class ScriptedCoreSession:
    """Deterministic core test double driven only by a scenario fixture."""

    def __init__(self, scenario: Mapping[str, Any]) -> None:
        validate_scenario(scenario)
        self._scenario = deepcopy(dict(scenario))
        self._steps = list(self._scenario["steps"])
        self._step_index = 0
        self._state = deepcopy(dict(self._scenario["initial_state"]))

    @property
    def scenario_id(self) -> str:
        return str(self._scenario["scenario_id"])

    @property
    def initial_snapshot(self) -> dict[str, Any]:
        return deepcopy(dict(self._scenario["initial_state"]))

    @property
    def version_metadata(self) -> dict[str, Any]:
        metadata = dict(self._scenario.get("version_metadata", {}))
        return {"bridge_adapter": "scripted-prototype", **deepcopy(metadata)}

    @property
    def seeds(self) -> dict[str, int | None]:
        return deepcopy(dict(self._scenario.get("seeds", {})))

    @property
    def is_exhausted(self) -> bool:
        return self._step_index == len(self._steps)

    @property
    def current_state(self) -> dict[str, Any]:
        return deepcopy(self._state)

    @property
    def selected_candidate_ids(self) -> tuple[str, ...]:
        if self.is_exhausted:
            return ()
        step = _mapping(self._steps[self._step_index], f"steps[{self._step_index}]")
        return tuple(str(item) for item in _list(step["select"], f"steps[{self._step_index}].select"))

    def next_request(self) -> DecisionRequest | None:
        if self.is_exhausted:
            return None

        step_path = f"steps[{self._step_index}]"
        step = _mapping(self._steps[self._step_index], step_path)
        request_data = _mapping(step["request"], f"{step_path}.request")
        constraint_data = _mapping(request_data.get("constraints", {}), f"{step_path}.request.constraints")
        candidates = tuple(
            Candidate(
                candidate_id=_string(candidate["candidate_id"], f"{step_path}.request.candidates[{index}].candidate_id"),
                kind=_string(candidate["kind"], f"{step_path}.request.candidates[{index}].kind"),
                label=str(candidate.get("label", "")),
                card_ref=deepcopy(candidate.get("card_ref")),
                effect_ref=deepcopy(candidate.get("effect_ref")),
                payload=deepcopy(dict(candidate.get("payload", {}))),
            )
            for index, raw_candidate in enumerate(_list(request_data["candidates"], f"{step_path}.request.candidates"))
            for candidate in [_mapping(raw_candidate, f"{step_path}.request.candidates[{index}]")]
        )
        state = self.current_state
        return DecisionRequest(
            request_id=f"{self.scenario_id}:{self._step_index}",
            request_type=_string(request_data["request_type"], f"{step_path}.request.request_type"),
            player=int(request_data["player"]),
            candidates=candidates,
            constraints=DecisionConstraints(
                min_selections=int(constraint_data.get("min_selections", 1)),
                max_selections=int(constraint_data.get("max_selections", 1)),
                ordered=bool(constraint_data.get("ordered", False)),
                allow_duplicates=bool(constraint_data.get("allow_duplicates", False)),
                required=bool(constraint_data.get("required", True)),
            ),
            context=DecisionContext(
                phase=str(state.get("phase", "")),
                chain=tuple(deepcopy(state.get("chain", []))),
                turn_player=state.get("turn_player"),
                priority_player=request_data.get("player"),
                visible_board=state,
                request_source="scripted-prototype",
                version_metadata=self.version_metadata,
                extra={"scenario_id": self.scenario_id, "step": self._step_index},
            ),
        )

    def apply(self, action: Action) -> ScriptedTransition:
        request = self.next_request()
        if request is None:
            raise ValueError("scripted core has no pending DecisionRequest")
        if action.request_signature != request.request_signature:
            raise ValueError("action.request_signature does not match the pending DecisionRequest")

        selected = tuple(selection.candidate_id for selection in action.selections)
        if selected != self.selected_candidate_ids:
            raise ValueError(f"scripted selection mismatch: expected {self.selected_candidate_ids}, got {selected}")

        candidates = {candidate.candidate_id: candidate for candidate in request.candidates}
        kinds = {
            ActionKind(str(candidates[candidate_id].payload["action_kind"]))
            for candidate_id in selected
        }
        if len(kinds) != 1 or action.kind not in kinds:
            raise ValueError("action.kind does not match the scripted candidate action_kind")

        step = _mapping(self._steps[self._step_index], f"steps[{self._step_index}]")
        before = self.current_state
        after = deepcopy(dict(_mapping(step["next_state"], f"steps[{self._step_index}].next_state")))
        self._state = after
        self._step_index += 1
        can_stop = bool(step.get("can_stop", False))
        return ScriptedTransition(
            state_before=before,
            state_after=self.current_state,
            state_hash_before=state_hash(before),
            state_hash_after=state_hash(after),
            can_stop=can_stop,
            stop_reason=str(step.get("stop_reason", "legal_stop" if can_stop else "pending")),
        )


def state_hash(state: Mapping[str, Any]) -> str:
    return stable_digest(state, prefix="state_")


def validate_scenario(scenario: Mapping[str, Any]) -> None:
    root = _mapping(scenario, "scenario")
    if root.get("schema_version") != PROTOTYPE_SCENARIO_SCHEMA_VERSION:
        raise ValueError(f"scenario.schema_version must be {PROTOTYPE_SCENARIO_SCHEMA_VERSION!r}")
    _string(root.get("scenario_id"), "scenario.scenario_id")
    experiment = _mapping(root.get("experiment"), "scenario.experiment")
    _string(experiment.get("experiment_id"), "scenario.experiment.experiment_id")
    _mapping(root.get("initial_state"), "scenario.initial_state")
    steps = _list(root.get("steps"), "scenario.steps")
    if not steps:
        raise ValueError("scenario.steps must not be empty")

    for index, raw_step in enumerate(steps):
        path = f"scenario.steps[{index}]"
        step = _mapping(raw_step, path)
        request = _mapping(step.get("request"), f"{path}.request")
        _string(request.get("request_type"), f"{path}.request.request_type")
        if not isinstance(request.get("player"), int) or isinstance(request.get("player"), bool):
            raise ValueError(f"{path}.request.player must be an integer")
        candidates = _list(request.get("candidates"), f"{path}.request.candidates")
        if not candidates:
            raise ValueError(f"{path}.request.candidates must not be empty")
        candidate_ids: set[str] = set()
        for candidate_index, raw_candidate in enumerate(candidates):
            candidate_path = f"{path}.request.candidates[{candidate_index}]"
            candidate = _mapping(raw_candidate, candidate_path)
            candidate_id = _string(candidate.get("candidate_id"), f"{candidate_path}.candidate_id")
            if candidate_id in candidate_ids:
                raise ValueError(f"{candidate_path}.candidate_id must be unique within the request")
            candidate_ids.add(candidate_id)
            _string(candidate.get("kind"), f"{candidate_path}.kind")
            payload = _mapping(candidate.get("payload"), f"{candidate_path}.payload")
            try:
                ActionKind(str(payload.get("action_kind")))
            except ValueError as exc:
                raise ValueError(f"{candidate_path}.payload.action_kind is unsupported") from exc
        selected = _list(step.get("select"), f"{path}.select")
        if not selected:
            raise ValueError(f"{path}.select must not be empty")
        unknown = sorted(str(item) for item in selected if str(item) not in candidate_ids)
        if unknown:
            raise ValueError(f"{path}.select contains unknown candidates: {unknown}")
        _mapping(step.get("next_state"), f"{path}.next_state")

    if not bool(_mapping(steps[-1], f"scenario.steps[{len(steps) - 1}]").get("can_stop", False)):
        raise ValueError("the final scripted step must be a legal stop for a complete prototype route")
