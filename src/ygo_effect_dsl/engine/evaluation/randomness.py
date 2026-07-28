from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
import math
from typing import Any

from ygo_effect_dsl.engine.canonical import stable_digest, to_canonical_data


ROUTE_RANDOMNESS_SUMMARY_SCHEMA_VERSION = "route-randomness-summary-v1"
ROUTE_RANKING_POLICY_SCHEMA_VERSION = "route-ranking-policy-v1"
ROUTE_RANKING_SCHEMA_VERSION = "route-ranking-v1"


class GameplayReliability(str, Enum):
    DETERMINISTIC = "deterministic"
    STOCHASTIC = "stochastic"
    UNKNOWN = "unknown"


_DEFAULT_RELIABILITY_ORDER = (
    GameplayReliability.DETERMINISTIC,
    GameplayReliability.STOCHASTIC,
    GameplayReliability.UNKNOWN,
)
_UNKNOWN_EVENT_COUNT_RANK = 2_147_483_647


def _string(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{path} must be a non-empty string")
    return value


def _integer(value: Any, path: str, *, minimum: int = 0) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < minimum:
        raise ValueError(f"{path} must be an integer >= {minimum}")
    return value


def _finite_number(value: Any, path: str) -> int | float:
    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not math.isfinite(value)
    ):
        raise ValueError(f"{path} must be a finite number")
    return value


def _mapping(value: Any, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{path} must be a mapping")
    return value


def _random_event_entry(event: Mapping[str, Any], index: int) -> dict[str, Any]:
    event_id = _string(
        event.get("random_event_id", event.get("event_id")),
        f"random_events[{index}].random_event_id",
    )
    kind = _string(event.get("kind"), f"random_events[{index}].kind")
    entry: dict[str, Any] = {
        "event_id": event_id,
        "kind": kind,
        "outcome_observed": "outcome" in event,
        "probability": event.get("probability"),
        "step": event.get("after_response_step", event.get("step")),
    }
    if entry["probability"] is not None:
        _finite_number(entry["probability"], f"random_events[{index}].probability")
    if entry["step"] is not None:
        _integer(entry["step"], f"random_events[{index}].step")
    return to_canonical_data(entry)


def build_route_randomness_summary(route: Mapping[str, Any]) -> dict[str, Any]:
    """Build a conservative gameplay-randomness summary from Route replay evidence."""

    route = _mapping(route, "route")
    route_id = _string(route.get("route_id"), "route.route_id")
    replay = route.get("replay")
    if not isinstance(replay, Mapping) or "random_events" not in replay:
        identity = to_canonical_data(
            {
                "evidence_completeness": "missing_replay_random_events",
                "gameplay_random_event_count": None,
                "has_gameplay_randomness": None,
                "random_events": [],
                "reliability_class": GameplayReliability.UNKNOWN.value,
                "replay_determinism": "unknown",
                "route_id": route_id,
                "schema_version": ROUTE_RANDOMNESS_SUMMARY_SCHEMA_VERSION,
            }
        )
        return {**identity, "summary_id": stable_digest(identity, prefix="rngsum_")}

    raw_events = replay.get("random_events")
    if not isinstance(raw_events, list):
        raise ValueError("route.replay.random_events must be a list")
    events = [
        _random_event_entry(_mapping(event, f"route.replay.random_events[{index}]"), index)
        for index, event in enumerate(raw_events)
    ]
    reliability = (
        GameplayReliability.STOCHASTIC
        if events
        else GameplayReliability.DETERMINISTIC
    )
    identity = to_canonical_data(
        {
            "evidence_completeness": "complete",
            "gameplay_random_event_count": len(events),
            "has_gameplay_randomness": bool(events),
            "random_events": events,
            "reliability_class": reliability.value,
            "replay_determinism": "indexed_core_output_trace",
            "route_id": route_id,
            "schema_version": ROUTE_RANDOMNESS_SUMMARY_SCHEMA_VERSION,
        }
    )
    return {**identity, "summary_id": stable_digest(identity, prefix="rngsum_")}


@dataclass(frozen=True)
class RouteRankingPolicy:
    require_deterministic: bool = False
    reliability_order: tuple[GameplayReliability, ...] = _DEFAULT_RELIABILITY_ORDER
    schema_version: str = ROUTE_RANKING_POLICY_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != ROUTE_RANKING_POLICY_SCHEMA_VERSION:
            raise ValueError("unsupported route ranking policy schema")
        if not isinstance(self.require_deterministic, bool):
            raise ValueError("require_deterministic must be boolean")
        if not isinstance(self.reliability_order, tuple):
            object.__setattr__(self, "reliability_order", tuple(self.reliability_order))
        resolved = tuple(
            item if isinstance(item, GameplayReliability) else GameplayReliability(item)
            for item in self.reliability_order
        )
        if set(resolved) != set(GameplayReliability) or len(resolved) != 3:
            raise ValueError("reliability_order must contain each reliability class once")
        object.__setattr__(self, "reliability_order", resolved)

    @property
    def policy_id(self) -> str:
        return self.to_dict()["policy_id"]

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> RouteRankingPolicy:
        expected = {"reliability_order", "require_deterministic", "schema_version"}
        if not isinstance(value, Mapping) or set(value) != expected:
            raise ValueError(f"route ranking policy fields must be {sorted(expected)}")
        return cls(
            require_deterministic=value["require_deterministic"],
            reliability_order=tuple(value["reliability_order"]),
            schema_version=value["schema_version"],
        )

    def to_dict(self) -> dict[str, Any]:
        identity = to_canonical_data(
            {
                "reliability_order": [item.value for item in self.reliability_order],
                "require_deterministic": self.require_deterministic,
                "schema_version": self.schema_version,
            }
        )
        return {**identity, "policy_id": stable_digest(identity, prefix="rankpol_")}


def _reliability_from_candidate(candidate: Mapping[str, Any]) -> GameplayReliability:
    summary = candidate.get("randomness_summary")
    if isinstance(summary, Mapping):
        return GameplayReliability(summary.get("reliability_class"))
    return GameplayReliability(candidate.get("gameplay_reliability", "unknown"))


def _random_event_count(candidate: Mapping[str, Any]) -> tuple[int | None, int]:
    summary = candidate.get("randomness_summary")
    if isinstance(summary, Mapping):
        count = summary.get("gameplay_random_event_count")
        if count is None:
            return None, _UNKNOWN_EVENT_COUNT_RANK
        observed = _integer(count, "gameplay_random_event_count")
        return observed, observed
    if "gameplay_random_event_count" not in candidate:
        return None, _UNKNOWN_EVENT_COUNT_RANK
    observed = _integer(
        candidate.get("gameplay_random_event_count"),
        "gameplay_random_event_count",
    )
    return observed, observed


def _candidate_record(candidate: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "action_count": _integer(candidate.get("action_count"), "action_count"),
        "peak_score": _finite_number(candidate.get("peak_score"), "peak_score"),
        "route_id": _string(candidate.get("route_id"), "route_id"),
        "success": candidate.get("success"),
        "terminal_composite_score": _finite_number(
            candidate.get("terminal_composite_score"),
            "terminal_composite_score",
        ),
    }


def rank_route_candidates(
    candidates: Sequence[Mapping[str, Any]],
    *,
    policy: RouteRankingPolicy | None = None,
) -> dict[str, Any]:
    if not isinstance(candidates, Sequence) or isinstance(candidates, (str, bytes)):
        raise ValueError("candidates must be a sequence")
    if not candidates:
        raise ValueError("at least one candidate is required")
    policy = RouteRankingPolicy() if policy is None else policy
    if not isinstance(policy, RouteRankingPolicy):
        raise ValueError("policy must be RouteRankingPolicy")
    reliability_rank = {
        reliability: index for index, reliability in enumerate(policy.reliability_order)
    }
    records: list[dict[str, Any]] = []
    route_ids: list[str] = []
    for index, raw_candidate in enumerate(candidates):
        candidate = _mapping(raw_candidate, f"candidates[{index}]")
        record = _candidate_record(candidate)
        if not isinstance(record["success"], bool):
            raise ValueError("success must be boolean")
        reliability = _reliability_from_candidate(candidate)
        event_count, event_count_rank = _random_event_count(candidate)
        route_ids.append(record["route_id"])
        excluded = (
            policy.require_deterministic
            and reliability != GameplayReliability.DETERMINISTIC
        )
        record.update(
            {
                "exclusion_reason": (
                    "requires_deterministic_gameplay" if excluded else None
                ),
                "gameplay_random_event_count": event_count,
                "gameplay_reliability": reliability.value,
                "included": not excluded,
                "ranking_tuple": [
                    -int(record["success"]),
                    -record["terminal_composite_score"],
                    reliability_rank[reliability],
                    event_count_rank,
                    -record["peak_score"],
                    record["action_count"],
                    record["route_id"],
                ],
            }
        )
        records.append(record)
    duplicates = sorted(
        route_id for route_id in set(route_ids) if route_ids.count(route_id) > 1
    )
    if duplicates:
        raise ValueError(f"route_id must be unique: {duplicates}")
    ranked = sorted(
        (record for record in records if record["included"]),
        key=lambda item: tuple(item["ranking_tuple"]),
    )
    excluded = sorted(
        (record for record in records if not record["included"]),
        key=lambda item: item["route_id"],
    )
    ranked_payload = [
        {
            **to_canonical_data(record),
            "rank": rank,
        }
        for rank, record in enumerate(ranked, start=1)
    ]
    excluded_payload = [to_canonical_data(record) for record in excluded]
    identity = to_canonical_data(
        {
            "best_route_id": ranked_payload[0]["route_id"] if ranked_payload else None,
            "excluded_routes": excluded_payload,
            "policy": policy.to_dict(),
            "ranked_routes": ranked_payload,
            "schema_version": ROUTE_RANKING_SCHEMA_VERSION,
        }
    )
    return {**identity, "ranking_id": stable_digest(identity, prefix="routerank_")}
