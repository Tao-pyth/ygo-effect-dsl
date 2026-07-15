from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from ygo_effect_dsl.engine.action import Action, ActionKind
from ygo_effect_dsl.engine.canonical import stable_digest, to_canonical_data


MULTI_TURN_LIFECYCLE_SCHEMA_VERSION = "multi-turn-lifecycle-v1"
SEARCH_BUDGET_OWNERSHIP_SCHEMA_VERSION = "search-budget-ownership-v1"
SEARCH_BUDGET_PRIORITY = (
    "max_seconds",
    "max_nodes",
    "max_replays",
    "max_depth",
    "turn_limit",
)


class MultiTurnLifecycleError(ValueError):
    category = "multi_turn_lifecycle"

    def __init__(
        self,
        code: str,
        message: str,
        *,
        path_failure: bool,
        context: Mapping[str, Any] | None = None,
    ) -> None:
        self.code = code
        self.path_failure = path_failure
        self.context = to_canonical_data({"code": code, **dict(context or {})})
        super().__init__(f"{code}: {message}")


@dataclass(frozen=True)
class MultiTurnLifecycleDecision:
    turn: int
    phase: str
    turn_limit: int
    request_type: str
    process_state: str
    chain_count: int
    legal_stop: bool
    forced_response: bool
    duel_ended: bool
    core_end_turn_offered: bool
    end_turn_allowed: bool
    turn_limit_reached: bool
    mandatory_response_pending: bool
    boundary_reason: str
    schema_version: str = MULTI_TURN_LIFECYCLE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != MULTI_TURN_LIFECYCLE_SCHEMA_VERSION:
            raise ValueError("unsupported multi-turn lifecycle schema")
        for name, value in (("turn", self.turn), ("turn_limit", self.turn_limit)):
            if not isinstance(value, int) or isinstance(value, bool) or value < 1:
                raise ValueError(f"{name} must be an integer >= 1")
        if self.turn > self.turn_limit:
            raise ValueError("turn cannot exceed turn_limit in lifecycle evidence")
        if not isinstance(self.phase, str) or not self.phase:
            raise ValueError("phase must be a non-empty string")
        if not isinstance(self.request_type, str) or not self.request_type:
            raise ValueError("request_type must be a non-empty string")
        if not isinstance(self.process_state, str) or not self.process_state:
            raise ValueError("process_state must be a non-empty string")
        if (
            not isinstance(self.chain_count, int)
            or isinstance(self.chain_count, bool)
            or self.chain_count < 0
        ):
            raise ValueError("chain_count must be an integer >= 0")
        for name in (
            "legal_stop",
            "forced_response",
            "duel_ended",
            "core_end_turn_offered",
            "end_turn_allowed",
            "turn_limit_reached",
            "mandatory_response_pending",
        ):
            if not isinstance(getattr(self, name), bool):
                raise ValueError(f"{name} must be a boolean")
        if not isinstance(self.boundary_reason, str) or not self.boundary_reason:
            raise ValueError("boundary_reason must be a non-empty string")
        if self.duel_ended != (self.process_state == "ended"):
            raise ValueError("duel_ended does not match process_state")
        if self.duel_ended and not self.legal_stop:
            raise ValueError("duel end must be a legal stop")
        expected_limit_reached = self.turn == self.turn_limit
        if self.turn_limit_reached != expected_limit_reached:
            raise ValueError("turn_limit_reached does not match turn and turn_limit")
        expected_end_turn_allowed = (
            self.core_end_turn_offered
            and not self.turn_limit_reached
            and not self.duel_ended
        )
        if self.end_turn_allowed != expected_end_turn_allowed:
            raise ValueError("end_turn_allowed is inconsistent with lifecycle state")
        expected_mandatory_pending = not self.legal_stop and (
            self.forced_response or self.chain_count > 0
        )
        if self.mandatory_response_pending != expected_mandatory_pending:
            raise ValueError(
                "mandatory_response_pending is inconsistent with lifecycle state"
            )
        if self.boundary_reason != _boundary_reason(
            legal_stop=self.legal_stop,
            duel_ended=self.duel_ended,
            turn_limit_reached=self.turn_limit_reached,
            chain_count=self.chain_count,
            forced_response=self.forced_response,
        ):
            raise ValueError("boundary_reason is inconsistent with lifecycle state")

    def semantic_dict(self) -> dict[str, Any]:
        return {
            "boundary_reason": self.boundary_reason,
            "chain_count": self.chain_count,
            "core_end_turn_offered": self.core_end_turn_offered,
            "duel_ended": self.duel_ended,
            "end_turn_allowed": self.end_turn_allowed,
            "forced_response": self.forced_response,
            "legal_stop": self.legal_stop,
            "mandatory_response_pending": self.mandatory_response_pending,
            "phase": self.phase,
            "process_state": self.process_state,
            "request_type": self.request_type,
            "schema_version": self.schema_version,
            "turn": self.turn,
            "turn_limit": self.turn_limit,
            "turn_limit_reached": self.turn_limit_reached,
        }

    @property
    def lifecycle_id(self) -> str:
        return stable_digest(self.semantic_dict(), prefix="turnlifecycle_")

    def to_dict(self) -> dict[str, Any]:
        return {**self.semantic_dict(), "lifecycle_id": self.lifecycle_id}

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "MultiTurnLifecycleDecision":
        if not isinstance(value, Mapping):
            raise ValueError("multi-turn lifecycle evidence must be a mapping")
        try:
            decision = cls(
                turn=value["turn"],
                phase=value["phase"],
                turn_limit=value["turn_limit"],
                request_type=value["request_type"],
                process_state=value["process_state"],
                chain_count=value["chain_count"],
                legal_stop=value["legal_stop"],
                forced_response=value["forced_response"],
                duel_ended=value["duel_ended"],
                core_end_turn_offered=value["core_end_turn_offered"],
                end_turn_allowed=value["end_turn_allowed"],
                turn_limit_reached=value["turn_limit_reached"],
                mandatory_response_pending=value["mandatory_response_pending"],
                boundary_reason=value["boundary_reason"],
                schema_version=value["schema_version"],
            )
        except KeyError as exc:
            raise ValueError(
                f"multi-turn lifecycle evidence is missing {exc.args[0]}"
            ) from exc
        if value.get("lifecycle_id") != decision.lifecycle_id:
            raise ValueError("multi-turn lifecycle evidence ID mismatch")
        return decision


def _boundary_reason(
    *,
    legal_stop: bool,
    duel_ended: bool,
    turn_limit_reached: bool,
    chain_count: int,
    forced_response: bool,
) -> str:
    if duel_ended:
        return "duel_end"
    if legal_stop and turn_limit_reached:
        return "turn_limit"
    if legal_stop:
        return "legal_stop"
    if chain_count > 0:
        return "pending_chain"
    if forced_response:
        return "mandatory_response"
    return "pending_process"


def apply_turn_lifecycle(
    actions: Sequence[Action],
    *,
    turn: int,
    phase: str,
    turn_limit: int,
    request_type: str,
    process_state: str,
    chain_count: int,
    legal_stop: bool,
    forced_response: bool,
) -> tuple[tuple[Action, ...], MultiTurnLifecycleDecision]:
    if (
        not isinstance(turn_limit, int)
        or isinstance(turn_limit, bool)
        or turn_limit < 1
    ):
        raise MultiTurnLifecycleError(
            "invalid_turn_limit",
            "turn_limit must be an integer >= 1",
            path_failure=False,
            context={"turn_limit": turn_limit},
        )
    if not isinstance(turn, int) or isinstance(turn, bool) or turn < 1:
        raise MultiTurnLifecycleError(
            "invalid_turn_counter",
            "core turn counter must be an integer >= 1",
            path_failure=True,
            context={"turn": turn},
        )
    if turn > turn_limit:
        raise MultiTurnLifecycleError(
            "turn_limit_exceeded",
            "Action prefix advanced beyond the Experiment turn_limit",
            path_failure=True,
            context={"turn": turn, "turn_limit": turn_limit},
        )
    normalized = tuple(actions)
    duel_ended = process_state == "ended"
    if duel_ended and normalized:
        raise MultiTurnLifecycleError(
            "terminal_actions_present",
            "core duel end cannot expose further Actions",
            path_failure=True,
            context={"action_count": len(normalized), "turn": turn},
        )
    core_end_turn_offered = any(
        action.kind == ActionKind.END_TURN for action in normalized
    )
    turn_limit_reached = turn == turn_limit
    end_turn_allowed = (
        core_end_turn_offered and not turn_limit_reached and not duel_ended
    )
    if turn_limit_reached:
        normalized = tuple(
            action for action in normalized if action.kind != ActionKind.END_TURN
        )
    mandatory_response_pending = not legal_stop and (
        forced_response or chain_count > 0
    )
    boundary_reason = _boundary_reason(
        legal_stop=legal_stop,
        duel_ended=duel_ended,
        turn_limit_reached=turn_limit_reached,
        chain_count=chain_count,
        forced_response=forced_response,
    )
    decision = MultiTurnLifecycleDecision(
        turn=turn,
        phase=phase,
        turn_limit=turn_limit,
        request_type=request_type,
        process_state=process_state,
        chain_count=chain_count,
        legal_stop=legal_stop,
        forced_response=forced_response,
        duel_ended=duel_ended,
        core_end_turn_offered=core_end_turn_offered,
        end_turn_allowed=end_turn_allowed,
        turn_limit_reached=turn_limit_reached,
        mandatory_response_pending=mandatory_response_pending,
        boundary_reason=boundary_reason,
    )
    return normalized, decision


def search_budget_ownership_contract() -> dict[str, Any]:
    payload = {
        "core_owned": ["phase", "draw", "turn_counter", "duel_end"],
        "executor_owned": ["max_seconds", "max_nodes", "max_replays", "max_depth"],
        "priority": list(SEARCH_BUDGET_PRIORITY),
        "scenario_adapter_owned": ["turn_limit"],
        "schema_version": SEARCH_BUDGET_OWNERSHIP_SCHEMA_VERSION,
        "stop_policy": {
            "duel_end": "terminal_when_core_reports_supported_terminal",
            "legal_stop": "STOP_LINE_may_be_recorded",
            "pending_chain_or_mandatory_response": "must_continue",
            "turn_limit": "suppress_END_TURN_at_last_turn",
        },
    }
    return {
        **payload,
        "contract_id": stable_digest(payload, prefix="budgetownership_"),
    }
