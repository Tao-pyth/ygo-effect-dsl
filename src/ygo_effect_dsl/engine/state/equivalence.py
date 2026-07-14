from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from enum import Enum
from typing import Any

from ygo_effect_dsl.engine.canonical import stable_digest
from ygo_effect_dsl.engine.state.identity import (
    CanonicalState,
    StateIdentityCompleteness,
)


APPROXIMATION_POLICY_SCHEMA_VERSION = "ygo-state-approximation-policy-v1"


class StateEquivalenceError(ValueError):
    pass


class StateKeyPurpose(str, Enum):
    REPLAY_VALIDATION = "replay_validation"
    LEGALITY_CACHE = "legality_cache"
    BRANCH_PRUNING = "branch_pruning"
    TRANSPOSITION_HINT = "transposition_hint"
    EVALUATION_CACHE = "evaluation_cache"
    SEARCH_ORDERING = "search_ordering"


_APPROXIMATE_PURPOSES = frozenset(
    {
        StateKeyPurpose.TRANSPOSITION_HINT,
        StateKeyPurpose.EVALUATION_CACHE,
        StateKeyPurpose.SEARCH_ORDERING,
    }
)


@dataclass(frozen=True)
class ApproximationPolicy:
    policy_id: str
    version: str
    drop_paths: tuple[tuple[str, ...], ...]
    allowed_purposes: tuple[StateKeyPurpose, ...]
    risk_notes: tuple[str, ...]
    schema_version: str = APPROXIMATION_POLICY_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.policy_id, str) or not self.policy_id:
            raise StateEquivalenceError("policy_id must be a non-empty string")
        if not isinstance(self.version, str) or not self.version:
            raise StateEquivalenceError("policy version must be a non-empty string")
        if self.schema_version != APPROXIMATION_POLICY_SCHEMA_VERSION:
            raise StateEquivalenceError(
                f"unsupported approximation policy schema {self.schema_version!r}"
            )
        normalized_paths = tuple(
            sorted(tuple(path) for path in self.drop_paths)
        )
        if not normalized_paths:
            raise StateEquivalenceError("approximation policy must drop at least one path")
        for path in normalized_paths:
            if not path or any(not isinstance(part, str) or not part for part in path):
                raise StateEquivalenceError(
                    "drop paths must contain non-empty string components"
                )
            if path[0] != "private_state":
                raise StateEquivalenceError(
                    "approximation may only drop private_state paths"
                )
        for index, path in enumerate(normalized_paths):
            if any(
                path[: len(other)] == other
                for other in normalized_paths[:index]
            ):
                raise StateEquivalenceError("drop paths must not overlap")
        purposes = tuple(
            sorted(
                (
                    purpose
                    if isinstance(purpose, StateKeyPurpose)
                    else StateKeyPurpose(purpose)
                    for purpose in self.allowed_purposes
                ),
                key=lambda purpose: purpose.value,
            )
        )
        if not purposes or any(purpose not in _APPROXIMATE_PURPOSES for purpose in purposes):
            raise StateEquivalenceError(
                "approximation is limited to transposition hints, evaluation cache, "
                "and search ordering"
            )
        if not self.risk_notes or any(
            not isinstance(note, str) or not note for note in self.risk_notes
        ):
            raise StateEquivalenceError(
                "approximation policy requires non-empty risk notes"
            )
        object.__setattr__(self, "drop_paths", normalized_paths)
        object.__setattr__(self, "allowed_purposes", purposes)
        object.__setattr__(self, "risk_notes", tuple(sorted(set(self.risk_notes))))

    def to_identity_dict(self) -> dict[str, Any]:
        return {
            "allowed_purposes": [purpose.value for purpose in self.allowed_purposes],
            "drop_paths": [list(path) for path in self.drop_paths],
            "policy_id": self.policy_id,
            "risk_notes": list(self.risk_notes),
            "schema_version": self.schema_version,
            "version": self.version,
        }

    @property
    def policy_hash(self) -> str:
        return stable_digest(self.to_identity_dict(), prefix="state_policy_")

    def project(self, state: CanonicalState) -> dict[str, Any]:
        projected = deepcopy(state.to_identity_dict())
        for path in self.drop_paths:
            current: Any = projected
            for part in path[:-1]:
                if not isinstance(current, dict) or part not in current:
                    raise StateEquivalenceError(
                        f"drop path {'.'.join(path)!r} does not exist"
                    )
                current = current[part]
            if not isinstance(current, dict) or path[-1] not in current:
                raise StateEquivalenceError(
                    f"drop path {'.'.join(path)!r} does not exist"
                )
            del current[path[-1]]
        return projected


@dataclass(frozen=True)
class StateKey:
    key: str
    purpose: StateKeyPurpose
    exact: bool
    requires_exact_confirmation: bool
    policy_hash: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "exact": self.exact,
            "key": self.key,
            "policy_hash": self.policy_hash,
            "purpose": self.purpose.value,
            "requires_exact_confirmation": self.requires_exact_confirmation,
        }


def exact_state_equivalent(left: CanonicalState, right: CanonicalState) -> bool:
    for name, state in (("left", left), ("right", right)):
        if state.completeness != StateIdentityCompleteness.EXACT:
            raise StateEquivalenceError(
                f"{name} State is {state.completeness.value}, not exact"
            )
    coordinates = (
        "schema_version",
        "information_mode",
        "viewer",
        "sampling_reference",
    )
    for name in coordinates:
        if getattr(left, name) != getattr(right, name):
            raise StateEquivalenceError(
                f"exact State comparison requires matching {name}"
            )
    return left.state_id == right.state_id


def build_state_key(
    state: CanonicalState,
    *,
    purpose: StateKeyPurpose,
    approximation: ApproximationPolicy | None = None,
) -> StateKey:
    if not isinstance(purpose, StateKeyPurpose):
        purpose = StateKeyPurpose(purpose)
    if approximation is None:
        if state.completeness != StateIdentityCompleteness.EXACT:
            raise StateEquivalenceError(
                f"{purpose.value} requires exact State identity; got "
                f"{state.completeness.value}"
            )
        return StateKey(
            key=state.state_id,
            purpose=purpose,
            exact=True,
            requires_exact_confirmation=False,
        )
    if purpose not in approximation.allowed_purposes:
        raise StateEquivalenceError(
            f"approximation policy {approximation.policy_id!r} does not allow "
            f"{purpose.value}"
        )
    projected = approximation.project(state)
    key = stable_digest(
        {
            "policy": approximation.to_identity_dict(),
            "projected_state": projected,
        },
        prefix="search_state_",
    )
    return StateKey(
        key=key,
        purpose=purpose,
        exact=False,
        requires_exact_confirmation=True,
        policy_hash=approximation.policy_hash,
    )
