from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from ygo_effect_dsl.engine.action import Action
from ygo_effect_dsl.engine.canonical import stable_digest, to_canonical_data


SEARCH_STRATEGY_CONFORMANCE_SCHEMA_VERSION = "search-strategy-conformance-v1"
SEARCH_STRATEGY_CONFORMANCE_REPORT_SCHEMA_VERSION = (
    "search-strategy-conformance-report-v1"
)
SEARCH_STRATEGY_EVIDENCE_SCHEMA_VERSION = "search-strategy-evidence-v1"
RANDOM_SEARCH_STRATEGY_SCHEMA_VERSION = "random-search-strategy-v1"
BEAM_SEARCH_STRATEGY_SCHEMA_VERSION = "beam-search-strategy-v1"
MCTS_STRATEGY_SCHEMA_VERSION = "mcts-strategy-v1"


class UnsupportedSearchStrategyError(NotImplementedError):
    pass


class SearchStrategy(Protocol):
    execution_mode: str
    strategy_id: str
    schema_version: str

    @property
    def parameters(self) -> Mapping[str, Any]: ...

    def order_actions(
        self, *, node_id: str, actions: Sequence[Action]
    ) -> tuple[Action, ...]: ...


def _integer(value: Any, name: str, *, minimum: int) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < minimum:
        raise ValueError(f"{name} must be an integer >= {minimum}")
    return value


def _finite_number(value: Any, name: str, *, minimum: float | None = None) -> float:
    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not math.isfinite(value)
    ):
        raise ValueError(f"{name} must be a finite number")
    number = float(value)
    if minimum is not None and number < minimum:
        raise ValueError(f"{name} must be >= {minimum}")
    return number


def _parameters(
    value: Mapping[str, Any],
    *,
    known: set[str],
    required: set[str],
) -> dict[str, Any]:
    unknown = sorted(set(value) - known)
    if unknown:
        raise ValueError(f"unknown strategy parameters: {unknown}")
    missing = sorted(required - set(value))
    if missing:
        raise ValueError(f"missing strategy parameters: {missing}")
    return dict(value)


def deterministic_decision_key(
    *,
    seed: int,
    strategy_id: str,
    strategy_version: str,
    node_id: str,
    purpose: str,
    candidate_id: str,
) -> str:
    _integer(seed, "seed", minimum=0)
    for name, value in (
        ("strategy_id", strategy_id),
        ("strategy_version", strategy_version),
        ("node_id", node_id),
        ("purpose", purpose),
        ("candidate_id", candidate_id),
    ):
        if not isinstance(value, str) or not value:
            raise ValueError(f"{name} must be a non-empty string")
    return stable_digest(
        {
            "candidate_id": candidate_id,
            "node_id": node_id,
            "purpose": purpose,
            "seed": seed,
            "strategy_id": strategy_id,
            "strategy_version": strategy_version,
        },
        prefix="decisionkey_",
    )


@dataclass(frozen=True)
class RandomSearchStrategyV1:
    seed: int
    execution_mode: str = "depth_first"
    strategy_id: str = "random_search_v1"
    schema_version: str = RANDOM_SEARCH_STRATEGY_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _integer(self.seed, "Random Search seed", minimum=0)

    @property
    def parameters(self) -> Mapping[str, Any]:
        return {"seed": self.seed}

    def order_actions(
        self, *, node_id: str, actions: Sequence[Action]
    ) -> tuple[Action, ...]:
        return tuple(
            sorted(
                actions,
                key=lambda action: (
                    deterministic_decision_key(
                        seed=self.seed,
                        strategy_id=self.strategy_id,
                        strategy_version=self.schema_version,
                        node_id=node_id,
                        purpose="expand_action_order",
                        candidate_id=action.action_id,
                    ),
                    action.action_id,
                ),
            )
        )


@dataclass(frozen=True)
class BeamSearchParametersV1:
    beam_width: int
    seed: int = 0

    def __post_init__(self) -> None:
        _integer(self.beam_width, "beam_width", minimum=1)
        _integer(self.seed, "seed", minimum=0)

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> BeamSearchParametersV1:
        parameters = _parameters(
            value,
            known={"beam_width", "seed"},
            required={"beam_width"},
        )
        return cls(
            beam_width=_integer(parameters["beam_width"], "beam_width", minimum=1),
            seed=_integer(parameters.get("seed", 0), "seed", minimum=0),
        )

    def to_dict(self) -> dict[str, Any]:
        return {"beam_width": self.beam_width, "seed": self.seed}


@dataclass(frozen=True)
class BeamSearchStrategyV1:
    beam_width: int
    seed: int = 0
    execution_mode: str = "beam"
    strategy_id: str = "beam_search_v1"
    schema_version: str = BEAM_SEARCH_STRATEGY_SCHEMA_VERSION

    def __post_init__(self) -> None:
        BeamSearchParametersV1(beam_width=self.beam_width, seed=self.seed)

    @property
    def parameters(self) -> Mapping[str, Any]:
        return {"beam_width": self.beam_width, "seed": self.seed}

    def order_actions(
        self, *, node_id: str, actions: Sequence[Action]
    ) -> tuple[Action, ...]:
        return tuple(
            sorted(
                actions,
                key=lambda action: (
                    deterministic_decision_key(
                        seed=self.seed,
                        strategy_id=self.strategy_id,
                        strategy_version=self.schema_version,
                        node_id=node_id,
                        purpose="expand_action_order",
                        candidate_id=action.action_id,
                    ),
                    action.action_id,
                ),
            )
        )


def beam_rank_key(
    *,
    success: bool,
    peak_score: int | float,
    terminal_score: int | float,
    action_count: int,
    semantic_prefix_id: str,
) -> tuple[Any, ...]:
    if not isinstance(success, bool):
        raise ValueError("success must be boolean")
    peak = _finite_number(peak_score, "peak_score")
    terminal = _finite_number(terminal_score, "terminal_score")
    count = _integer(action_count, "action_count", minimum=0)
    if not isinstance(semantic_prefix_id, str) or not semantic_prefix_id:
        raise ValueError("semantic_prefix_id must be a non-empty string")
    return (-int(success), -peak, -terminal, count, semantic_prefix_id)


@dataclass(frozen=True)
class MctsSearchParametersV1:
    simulations: int
    reward_floor: float
    reward_ceiling: float
    exploration_constant: float = math.sqrt(2.0)
    seed: int = 0

    def __post_init__(self) -> None:
        _integer(self.simulations, "simulations", minimum=1)
        floor = _finite_number(self.reward_floor, "reward_floor")
        ceiling = _finite_number(self.reward_ceiling, "reward_ceiling")
        if floor >= ceiling:
            raise ValueError("reward_floor must be less than reward_ceiling")
        _finite_number(
            self.exploration_constant, "exploration_constant", minimum=0.0
        )
        _integer(self.seed, "seed", minimum=0)

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> MctsSearchParametersV1:
        parameters = _parameters(
            value,
            known={
                "exploration_constant",
                "reward_ceiling",
                "reward_floor",
                "seed",
                "simulations",
            },
            required={"reward_ceiling", "reward_floor", "simulations"},
        )
        return cls(
            simulations=_integer(parameters["simulations"], "simulations", minimum=1),
            reward_floor=_finite_number(parameters["reward_floor"], "reward_floor"),
            reward_ceiling=_finite_number(
                parameters["reward_ceiling"], "reward_ceiling"
            ),
            exploration_constant=_finite_number(
                parameters.get("exploration_constant", math.sqrt(2.0)),
                "exploration_constant",
                minimum=0.0,
            ),
            seed=_integer(parameters.get("seed", 0), "seed", minimum=0),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "exploration_constant": self.exploration_constant,
            "reward_ceiling": self.reward_ceiling,
            "reward_floor": self.reward_floor,
            "seed": self.seed,
            "simulations": self.simulations,
        }


@dataclass(frozen=True)
class MctsSearchStrategyV1:
    simulations: int
    reward_floor: float
    reward_ceiling: float
    exploration_constant: float = math.sqrt(2.0)
    seed: int = 0
    execution_mode: str = "mcts"
    strategy_id: str = "mcts_v1"
    schema_version: str = MCTS_STRATEGY_SCHEMA_VERSION

    def __post_init__(self) -> None:
        MctsSearchParametersV1(
            simulations=self.simulations,
            reward_floor=self.reward_floor,
            reward_ceiling=self.reward_ceiling,
            exploration_constant=self.exploration_constant,
            seed=self.seed,
        )

    @property
    def parameters(self) -> Mapping[str, Any]:
        return {
            "exploration_constant": self.exploration_constant,
            "reward_ceiling": self.reward_ceiling,
            "reward_floor": self.reward_floor,
            "seed": self.seed,
            "simulations": self.simulations,
        }

    def decision_key(
        self,
        *,
        node_id: str,
        purpose: str,
        candidate_id: str,
    ) -> str:
        return deterministic_decision_key(
            seed=self.seed,
            strategy_id=self.strategy_id,
            strategy_version=self.schema_version,
            node_id=node_id,
            purpose=purpose,
            candidate_id=candidate_id,
        )

    def order_actions_for_purpose(
        self,
        *,
        node_id: str,
        actions: Sequence[Action],
        purpose: str,
    ) -> tuple[Action, ...]:
        if purpose not in {"mcts_expansion", "mcts_rollout"}:
            raise ValueError(f"unsupported MCTS decision purpose {purpose!r}")
        return tuple(
            sorted(
                actions,
                key=lambda action: (
                    self.decision_key(
                        node_id=node_id,
                        purpose=purpose,
                        candidate_id=action.action_id,
                    ),
                    action.action_id,
                ),
            )
        )

    def order_actions(
        self, *, node_id: str, actions: Sequence[Action]
    ) -> tuple[Action, ...]:
        return self.order_actions_for_purpose(
            node_id=node_id,
            actions=actions,
            purpose="mcts_expansion",
        )


def normalize_mcts_reward(
    *,
    success: bool,
    terminal_score: int | float,
    reward_floor: int | float,
    reward_ceiling: int | float,
) -> float:
    if not isinstance(success, bool):
        raise ValueError("success must be boolean")
    score = _finite_number(terminal_score, "terminal_score")
    floor = _finite_number(reward_floor, "reward_floor")
    ceiling = _finite_number(reward_ceiling, "reward_ceiling")
    if floor >= ceiling:
        raise ValueError("reward_floor must be less than reward_ceiling")
    bounded = min(max(score, floor), ceiling)
    normalized = (bounded - floor) / (ceiling - floor)
    return ((2.0 if success else 0.0) + normalized) / 3.0


def mcts_uct_score(
    *,
    parent_visits: int,
    child_visits: int,
    child_value_sum: int | float,
    exploration_constant: int | float,
) -> float:
    parent = _integer(parent_visits, "parent_visits", minimum=1)
    child = _integer(child_visits, "child_visits", minimum=0)
    value_sum = _finite_number(child_value_sum, "child_value_sum")
    exploration = _finite_number(
        exploration_constant, "exploration_constant", minimum=0.0
    )
    if child == 0:
        return math.inf
    return (value_sum / child) + exploration * math.sqrt(math.log(parent) / child)


def build_strategy_conformance_report(
    strategy: SearchStrategy,
    *,
    node_id: str,
    actions: Sequence[Action],
) -> dict[str, Any]:
    for name in ("execution_mode", "strategy_id", "schema_version"):
        value = getattr(strategy, name, None)
        if not isinstance(value, str) or not value:
            raise ValueError(f"strategy.{name} must be a non-empty string")
    parameters = strategy.parameters
    if not isinstance(parameters, Mapping):
        raise ValueError("strategy.parameters must be a mapping")
    input_ids = tuple(action.action_id for action in actions)
    if len(input_ids) != len(set(input_ids)):
        raise ValueError("conformance actions must have unique action IDs")
    first = strategy.order_actions(node_id=node_id, actions=actions)
    second = strategy.order_actions(node_id=node_id, actions=actions)
    first_ids = tuple(action.action_id for action in first)
    if first_ids != tuple(action.action_id for action in second):
        raise ValueError("strategy action ordering is not deterministic")
    if len(first_ids) != len(input_ids) or set(first_ids) != set(input_ids):
        raise ValueError("strategy action ordering must preserve candidates exactly")
    identity = {
        "execution_mode": strategy.execution_mode,
        "ordered_action_ids": list(first_ids),
        "parameters": to_canonical_data(parameters),
        "schema_version": SEARCH_STRATEGY_CONFORMANCE_REPORT_SCHEMA_VERSION,
        "strategy_conformance_schema_version": (
            SEARCH_STRATEGY_CONFORMANCE_SCHEMA_VERSION
        ),
        "strategy_id": strategy.strategy_id,
        "strategy_schema_version": strategy.schema_version,
        "test_node_id": node_id,
    }
    return {
        **identity,
        "conformance_id": stable_digest(identity, prefix="strategyconf_"),
    }


def build_strategy_evidence(
    strategy: SearchStrategy,
    *,
    logical_updates: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    identity = {
        "execution_mode": strategy.execution_mode,
        "logical_updates": [to_canonical_data(update) for update in logical_updates],
        "parameters": to_canonical_data(strategy.parameters),
        "schema_version": SEARCH_STRATEGY_EVIDENCE_SCHEMA_VERSION,
        "strategy_id": strategy.strategy_id,
        "strategy_schema_version": strategy.schema_version,
    }
    return {
        **identity,
        "evidence_id": stable_digest(identity, prefix="strategyevidence_"),
    }


def strategy_from_experiment(experiment: Mapping[str, Any]) -> SearchStrategy:
    search = experiment.get("search")
    if not isinstance(search, Mapping):
        raise ValueError("experiment.search must be a mapping")
    strategy_id = search.get("strategy")
    parameters = search.get("parameters", {})
    if not isinstance(parameters, Mapping):
        raise ValueError("experiment.search.parameters must be a mapping")
    shared_parameter_names = {"max_frontier_actions", "termination"}
    if strategy_id == "random_search_v1":
        checked = _parameters(
            parameters,
            known={"seed", *shared_parameter_names},
            required=set(),
        )
        return RandomSearchStrategyV1(
            seed=_integer(checked.get("seed", 0), "seed", minimum=0)
        )
    if strategy_id == "beam_search_v1":
        checked_parameters = _parameters(
            parameters,
            known={"beam_width", "seed", *shared_parameter_names},
            required={"beam_width"},
        )
        checked = BeamSearchParametersV1.from_mapping(
            {
                name: value
                for name, value in checked_parameters.items()
                if name not in shared_parameter_names
            }
        )
        return BeamSearchStrategyV1(
            beam_width=checked.beam_width,
            seed=checked.seed,
        )
    if strategy_id == "mcts_v1":
        checked_parameters = _parameters(
            parameters,
            known={
                "exploration_constant",
                "reward_ceiling",
                "reward_floor",
                "seed",
                "simulations",
                *shared_parameter_names,
            },
            required={"reward_ceiling", "reward_floor", "simulations"},
        )
        checked = MctsSearchParametersV1.from_mapping(
            {
                name: value
                for name, value in checked_parameters.items()
                if name not in shared_parameter_names
            }
        )
        return MctsSearchStrategyV1(
            simulations=checked.simulations,
            reward_floor=checked.reward_floor,
            reward_ceiling=checked.reward_ceiling,
            exploration_constant=checked.exploration_constant,
            seed=checked.seed,
        )
    raise UnsupportedSearchStrategyError(f"unsupported search strategy {strategy_id!r}")
