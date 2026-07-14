from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from ygo_effect_dsl.engine.bridge import Candidate, DecisionRequest
from ygo_effect_dsl.engine.canonical import stable_digest, to_canonical_data


CORE_INTERRUPTION_CANDIDATE_POLICY_SCHEMA_VERSION = (
    "core-interruption-candidate-policy-v1"
)
CORE_INTERRUPTION_STEP_SCHEMA_VERSION = "core-interruption-step-v1"
SUPPORTED_RESPONSE_ROLES = frozenset(
    {"confirmation", "cost", "option", "placement", "target"}
)


class InterruptionCandidatePolicyError(ValueError):
    category = "interruption_candidate_policy"

    def __init__(
        self,
        message: str,
        *,
        path: str,
        context: Mapping[str, Any] | None = None,
    ) -> None:
        self.path = path
        self.context = to_canonical_data({"path": path, **dict(context or {})})
        super().__init__(f"{path}: {message}")


def _mapping(value: Any, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise InterruptionCandidatePolicyError("must be a mapping", path=path)
    return value


def _string(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value:
        raise InterruptionCandidatePolicyError(
            "must be a non-empty string", path=path
        )
    return value


def _player(value: Any, path: str) -> int:
    if value not in {0, 1} or isinstance(value, bool):
        raise InterruptionCandidatePolicyError("must be player 0 or 1", path=path)
    return int(value)


def _selection_count(value: Any, path: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise InterruptionCandidatePolicyError(
            "must be a positive integer", path=path
        )
    return value


def _matches_subset(actual: Any, expected: Any) -> bool:
    if isinstance(expected, Mapping):
        return isinstance(actual, Mapping) and all(
            key in actual and _matches_subset(actual[key], value)
            for key, value in expected.items()
        )
    if isinstance(expected, list):
        return isinstance(actual, list) and actual == expected
    return actual == expected


@dataclass(frozen=True)
class CandidateSelector:
    candidate_id: str | None = None
    kind: str | None = None
    card_ref: Mapping[str, Any] | None = None
    effect_ref: Mapping[str, Any] | None = None
    payload: Mapping[str, Any] | None = None

    def __post_init__(self) -> None:
        if not any(
            value is not None
            for value in (
                self.candidate_id,
                self.kind,
                self.card_ref,
                self.effect_ref,
                self.payload,
            )
        ):
            raise InterruptionCandidatePolicyError(
                "requires at least one matching field", path="$.selector"
            )
        for name in ("candidate_id", "kind"):
            value = getattr(self, name)
            if value is not None and (not isinstance(value, str) or not value):
                raise InterruptionCandidatePolicyError(
                    "must be a non-empty string or null", path=f"$.selector.{name}"
                )
        for name in ("card_ref", "effect_ref", "payload"):
            value = getattr(self, name)
            if value is not None and not isinstance(value, Mapping):
                raise InterruptionCandidatePolicyError(
                    "must be a mapping or null", path=f"$.selector.{name}"
                )

    @classmethod
    def from_dict(cls, value: Any, *, path: str) -> "CandidateSelector":
        data = _mapping(value, path)
        allowed = {"candidate_id", "kind", "card_ref", "effect_ref", "payload"}
        unknown = sorted(set(data) - allowed)
        if unknown:
            raise InterruptionCandidatePolicyError(
                f"contains unsupported fields {unknown}", path=path
            )
        try:
            return cls(
                candidate_id=data.get("candidate_id"),
                kind=data.get("kind"),
                card_ref=data.get("card_ref"),
                effect_ref=data.get("effect_ref"),
                payload=data.get("payload"),
            )
        except InterruptionCandidatePolicyError as exc:
            relative = exc.path.removeprefix("$.selector")
            raise InterruptionCandidatePolicyError(
                str(exc).split(": ", 1)[-1], path=f"{path}{relative}"
            ) from exc

    def matches(self, candidate: Candidate) -> bool:
        expected = self.to_dict()
        actual = candidate.to_identity_dict()
        return all(
            _matches_subset(actual.get(key), value)
            for key, value in expected.items()
        )

    def to_dict(self) -> dict[str, Any]:
        return to_canonical_data(
            {
                key: value
                for key, value in {
                    "candidate_id": self.candidate_id,
                    "card_ref": self.card_ref,
                    "effect_ref": self.effect_ref,
                    "kind": self.kind,
                    "payload": self.payload,
                }.items()
                if value is not None
            }
        )


@dataclass(frozen=True)
class CoreInterruptionStep:
    role: str
    request_type: str
    player: int
    selector: CandidateSelector
    selection_count: int = 1
    schema_version: str = CORE_INTERRUPTION_STEP_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _string(self.role, "$.step.role")
        _string(self.request_type, "$.step.request_type")
        _player(self.player, "$.step.player")
        _selection_count(self.selection_count, "$.step.selection_count")
        if not isinstance(self.selector, CandidateSelector):
            raise InterruptionCandidatePolicyError(
                "must be CandidateSelector", path="$.step.selector"
            )
        if self.schema_version != CORE_INTERRUPTION_STEP_SCHEMA_VERSION:
            raise InterruptionCandidatePolicyError(
                f"must be {CORE_INTERRUPTION_STEP_SCHEMA_VERSION!r}",
                path="$.step.schema_version",
            )

    @classmethod
    def from_dict(
        cls,
        value: Any,
        *,
        path: str,
        activation: bool = False,
    ) -> "CoreInterruptionStep":
        data = _mapping(value, path)
        allowed = {
            "player",
            "request_type",
            "role",
            "schema_version",
            "selection_count",
            "selector",
        }
        unknown = sorted(set(data) - allowed)
        if unknown:
            raise InterruptionCandidatePolicyError(
                f"contains unsupported fields {unknown}", path=path
            )
        schema_version = data.get(
            "schema_version", CORE_INTERRUPTION_STEP_SCHEMA_VERSION
        )
        role = _string(data.get("role"), f"{path}.role")
        if activation and role != "activation":
            raise InterruptionCandidatePolicyError(
                "must be 'activation'", path=f"{path}.role"
            )
        if not activation and role not in SUPPORTED_RESPONSE_ROLES:
            raise InterruptionCandidatePolicyError(
                f"must be one of {sorted(SUPPORTED_RESPONSE_ROLES)}",
                path=f"{path}.role",
            )
        return cls(
            role=role,
            request_type=_string(data.get("request_type"), f"{path}.request_type"),
            player=_player(data.get("player"), f"{path}.player"),
            selector=CandidateSelector.from_dict(
                data.get("selector"), path=f"{path}.selector"
            ),
            selection_count=_selection_count(
                data.get("selection_count", 1), f"{path}.selection_count"
            ),
            schema_version=str(schema_version),
        )

    def select(
        self,
        request: DecisionRequest,
        *,
        path: str,
    ) -> tuple[Candidate, ...]:
        if request.request_type != self.request_type:
            raise InterruptionCandidatePolicyError(
                f"expected request_type {self.request_type!r}, got "
                f"{request.request_type!r}",
                path=path,
                context={"request": request.to_dict(), "step": self.to_dict()},
            )
        if request.player != self.player:
            raise InterruptionCandidatePolicyError(
                f"expected player {self.player}, got {request.player}",
                path=path,
                context={"request": request.to_dict(), "step": self.to_dict()},
            )
        matches = tuple(
            sorted(
                (
                    candidate
                    for candidate in request.candidates
                    if self.selector.matches(candidate)
                ),
                key=lambda candidate: candidate.candidate_id,
            )
        )
        if len(matches) != self.selection_count:
            raise InterruptionCandidatePolicyError(
                f"expected {self.selection_count} matching candidate(s), got "
                f"{len(matches)}",
                path=path,
                context={
                    "matching_candidate_ids": [
                        candidate.candidate_id for candidate in matches
                    ],
                    "request": request.to_dict(),
                    "step": self.to_dict(),
                },
            )
        if not (
            request.constraints.min_selections
            <= len(matches)
            <= request.constraints.max_selections
        ):
            raise InterruptionCandidatePolicyError(
                "policy selection count violates core request constraints",
                path=path,
                context={"request": request.to_dict(), "step": self.to_dict()},
            )
        return matches

    def to_dict(self) -> dict[str, Any]:
        return to_canonical_data(
            {
                "player": self.player,
                "request_type": self.request_type,
                "role": self.role,
                "schema_version": self.schema_version,
                "selection_count": self.selection_count,
                "selector": self.selector.to_dict(),
            }
        )


@dataclass(frozen=True)
class CoreInterruptionCandidatePolicy:
    activation: CoreInterruptionStep
    responses: tuple[CoreInterruptionStep, ...] = ()
    schema_version: str = CORE_INTERRUPTION_CANDIDATE_POLICY_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.activation, CoreInterruptionStep):
            raise InterruptionCandidatePolicyError(
                "must be CoreInterruptionStep", path="$.candidate_policy.activation"
            )
        if self.activation.role != "activation":
            raise InterruptionCandidatePolicyError(
                "must have activation role", path="$.candidate_policy.activation.role"
            )
        if not isinstance(self.responses, tuple) or not all(
            isinstance(step, CoreInterruptionStep) for step in self.responses
        ):
            raise InterruptionCandidatePolicyError(
                "must contain CoreInterruptionStep values",
                path="$.candidate_policy.responses",
            )
        if any(step.role == "activation" for step in self.responses):
            raise InterruptionCandidatePolicyError(
                "must not contain activation role",
                path="$.candidate_policy.responses",
            )
        if self.schema_version != CORE_INTERRUPTION_CANDIDATE_POLICY_SCHEMA_VERSION:
            raise InterruptionCandidatePolicyError(
                f"must be {CORE_INTERRUPTION_CANDIDATE_POLICY_SCHEMA_VERSION!r}",
                path="$.candidate_policy.schema_version",
            )

    @classmethod
    def from_dict(
        cls, value: Any, *, path: str = "$.candidate_policy"
    ) -> "CoreInterruptionCandidatePolicy":
        data = _mapping(value, path)
        allowed = {"activation", "responses", "schema_version"}
        unknown = sorted(set(data) - allowed)
        if unknown:
            raise InterruptionCandidatePolicyError(
                f"contains unsupported fields {unknown}", path=path
            )
        raw_responses = data.get("responses", [])
        if not isinstance(raw_responses, Sequence) or isinstance(
            raw_responses, (str, bytes)
        ):
            raise InterruptionCandidatePolicyError(
                "must be a sequence", path=f"{path}.responses"
            )
        return cls(
            activation=CoreInterruptionStep.from_dict(
                data.get("activation"),
                path=f"{path}.activation",
                activation=True,
            ),
            responses=tuple(
                CoreInterruptionStep.from_dict(
                    response,
                    path=f"{path}.responses[{index}]",
                )
                for index, response in enumerate(raw_responses)
            ),
            schema_version=str(data.get("schema_version")),
        )

    @classmethod
    def targeted_hand_activation(
        cls,
        *,
        source_player: int,
        source_card_code: int,
        target_player: int,
        target_card_code: int,
    ) -> "CoreInterruptionCandidatePolicy":
        return cls(
            activation=CoreInterruptionStep(
                role="activation",
                request_type="select_chain",
                player=source_player,
                selector=CandidateSelector(
                    kind="effect",
                    card_ref={
                        "controller": source_player,
                        "location": 0x02,
                        "public_card_id": source_card_code,
                    },
                ),
            ),
            responses=(
                CoreInterruptionStep(
                    role="target",
                    request_type="select_card",
                    player=source_player,
                    selector=CandidateSelector(
                        card_ref={
                            "controller": target_player,
                            "location": 0x04,
                            "public_card_id": target_card_code,
                        }
                    ),
                ),
            ),
        )

    @property
    def policy_id(self) -> str:
        return stable_digest(self.to_dict(), prefix="intpolicy_")

    def to_dict(self) -> dict[str, Any]:
        return to_canonical_data(
            {
                "activation": self.activation.to_dict(),
                "responses": [response.to_dict() for response in self.responses],
                "schema_version": self.schema_version,
            }
        )
