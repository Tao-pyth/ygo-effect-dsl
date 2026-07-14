from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from typing import Any

from ygo_effect_dsl.engine.canonical import stable_digest, to_canonical_data
from ygo_effect_dsl.engine.state import InformationMode


INFORMATION_AUDIT_SCHEMA_VERSION = "information-audit-v1"
INFORMATION_POLICY_SCHEMA_VERSION = "information-policy-v1"
INFORMATION_POLICY_EXPERIMENT_SCHEMA_VERSION = "0.3b"
OPENING_HAND_SAMPLING_SCHEMA_VERSION = "opening-hand-sampling-v1"
OPENING_HAND_SAMPLER_ID = "stable-digest-mod-v1"


class DeckOrderKnowledge(str, Enum):
    KNOWN = "known"
    UNKNOWN = "unknown"


class OpeningHandPolicy(str, Enum):
    NATURAL = "natural"
    FIXED = "fixed"
    PROBABILITY_DISTRIBUTION = "probability_distribution"


class InformationField(str, Enum):
    PUBLIC_STATE = "public_state"
    HAND_IDENTITY = "hand_identity"
    SET_CARD_IDENTITY = "set_card_identity"
    PRIVATE_EXTRA_DECK = "private_extra_deck"
    DECK_ORDER = "deck_order"
    PROBABILITY_DISTRIBUTION = "probability_distribution"


class AccessDecision(str, Enum):
    ALLOWED = "allowed"
    DENIED_PRIVATE_OWNER = "denied_private_owner"
    DENIED_UNKNOWN_DECK_ORDER = "denied_unknown_deck_order"
    DENIED_DISTRIBUTION_NOT_CONFIGURED = "denied_distribution_not_configured"


class InformationLeakError(ValueError):
    pass


def _sampling_error(path: str, message: str) -> ValueError:
    return ValueError(f"{path}: {message}")


def validate_opening_hand_sampling_reference(
    value: Any,
    *,
    path: str = "$.information_policy.sampling_reference",
) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise _sampling_error(path, "must be a mapping")
    allowed = {
        "candidates",
        "sampled_owners",
        "sampler_id",
        "sampling_policy_id",
        "schema_version",
        "seed",
    }
    unknown = sorted(set(value) - allowed)
    if unknown:
        raise _sampling_error(path, f"contains unsupported fields {unknown}")
    if value.get("schema_version") != OPENING_HAND_SAMPLING_SCHEMA_VERSION:
        raise _sampling_error(
            f"{path}.schema_version",
            f"must be {OPENING_HAND_SAMPLING_SCHEMA_VERSION!r}",
        )
    if value.get("sampler_id") != OPENING_HAND_SAMPLER_ID:
        raise _sampling_error(
            f"{path}.sampler_id", f"must be {OPENING_HAND_SAMPLER_ID!r}"
        )
    seed = value.get("seed")
    if not isinstance(seed, int) or isinstance(seed, bool) or seed < 0:
        raise _sampling_error(f"{path}.seed", "must be an integer >= 0")
    sampled_owners = value.get("sampled_owners")
    if (
        not isinstance(sampled_owners, list)
        or not sampled_owners
        or any(owner not in (0, 1) or isinstance(owner, bool) for owner in sampled_owners)
        or sampled_owners != sorted(set(sampled_owners))
    ):
        raise _sampling_error(
            f"{path}.sampled_owners",
            "must be a non-empty sorted unique list of players 0 or 1",
        )
    candidates = value.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        raise _sampling_error(f"{path}.candidates", "must be a non-empty list")
    normalized_candidates: list[dict[str, Any]] = []
    expected_players = {str(owner) for owner in sampled_owners}
    for index, candidate in enumerate(candidates):
        candidate_path = f"{path}.candidates[{index}]"
        if not isinstance(candidate, Mapping):
            raise _sampling_error(candidate_path, "must be a mapping")
        unknown_candidate = sorted(set(candidate) - {"hands_by_player", "weight"})
        if unknown_candidate:
            raise _sampling_error(
                candidate_path,
                f"contains unsupported fields {unknown_candidate}",
            )
        weight = candidate.get("weight")
        if not isinstance(weight, int) or isinstance(weight, bool) or weight <= 0:
            raise _sampling_error(
                f"{candidate_path}.weight", "must be a positive integer"
            )
        hands = candidate.get("hands_by_player")
        if not isinstance(hands, Mapping) or set(hands) != expected_players:
            raise _sampling_error(
                f"{candidate_path}.hands_by_player",
                f"must contain exactly players {sorted(expected_players)}",
            )
        normalized_hands: dict[str, list[int]] = {}
        for player in sorted(expected_players):
            hand = hands[player]
            if (
                not isinstance(hand, list)
                or not hand
                or any(
                    not isinstance(code, int)
                    or isinstance(code, bool)
                    or code <= 0
                    for code in hand
                )
            ):
                raise _sampling_error(
                    f"{candidate_path}.hands_by_player.{player}",
                    "must be a non-empty list of positive card codes",
                )
            normalized_hands[player] = list(hand)
        normalized_candidates.append(
            {"hands_by_player": normalized_hands, "weight": weight}
        )
    identity = to_canonical_data(
        {
            "candidates": normalized_candidates,
            "sampled_owners": sampled_owners,
            "sampler_id": OPENING_HAND_SAMPLER_ID,
            "schema_version": OPENING_HAND_SAMPLING_SCHEMA_VERSION,
            "seed": seed,
        }
    )
    expected_policy_id = stable_digest(identity, prefix="handsampol_")
    if value.get("sampling_policy_id") != expected_policy_id:
        raise _sampling_error(
            f"{path}.sampling_policy_id",
            "does not match the sampling policy content",
        )
    return {**identity, "sampling_policy_id": expected_policy_id}


def build_opening_hand_sampling_reference(
    *,
    seed: int,
    candidates: Sequence[Mapping[str, Any]],
    sampled_owners: Sequence[int] = (1,),
) -> dict[str, Any]:
    identity = to_canonical_data(
        {
            "candidates": list(candidates),
            "sampled_owners": list(sampled_owners),
            "sampler_id": OPENING_HAND_SAMPLER_ID,
            "schema_version": OPENING_HAND_SAMPLING_SCHEMA_VERSION,
            "seed": seed,
        }
    )
    reference = {
        **identity,
        "sampling_policy_id": stable_digest(identity, prefix="handsampol_"),
    }
    return validate_opening_hand_sampling_reference(reference)


def build_opening_hand_sampling_evidence(
    reference: Mapping[str, Any],
    *,
    information_policy_id: str,
) -> dict[str, Any]:
    normalized = validate_opening_hand_sampling_reference(reference)
    if not isinstance(information_policy_id, str) or not information_policy_id:
        raise ValueError("information_policy_id must be a non-empty string")
    draw_identity = to_canonical_data(
        {
            "sampler_id": normalized["sampler_id"],
            "sampling_policy_id": normalized["sampling_policy_id"],
            "seed": normalized["seed"],
        }
    )
    draw_id = stable_digest(draw_identity, prefix="handdraw_")
    candidates = normalized["candidates"]
    total_weight = sum(int(candidate["weight"]) for candidate in candidates)
    draw = int(draw_id.removeprefix("handdraw_"), 16) % total_weight
    selected_index = 0
    for index, candidate in enumerate(candidates):
        weight = int(candidate["weight"])
        if draw < weight:
            selected_index = index
            break
        draw -= weight
    result = to_canonical_data(
        {"hands_by_player": candidates[selected_index]["hands_by_player"]}
    )
    identity = to_canonical_data(
        {
            "information_policy_id": information_policy_id,
            "result": result,
            "sampled_owners": normalized["sampled_owners"],
            "sampler_id": normalized["sampler_id"],
            "sampling_policy_id": normalized["sampling_policy_id"],
            "schema_version": normalized["schema_version"],
            "seed": normalized["seed"],
            "selected_index": selected_index,
        }
    )
    return {
        **identity,
        "sample_id": stable_digest(identity, prefix="handsample_"),
    }


@dataclass(frozen=True)
class InformationAccessPolicy:
    information_mode: InformationMode
    deck_order: DeckOrderKnowledge
    opening_hand: OpeningHandPolicy
    viewer: int | None = None
    sampling_reference: Mapping[str, Any] | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.information_mode, InformationMode):
            object.__setattr__(
                self, "information_mode", InformationMode(self.information_mode)
            )
        if not isinstance(self.deck_order, DeckOrderKnowledge):
            object.__setattr__(self, "deck_order", DeckOrderKnowledge(self.deck_order))
        if not isinstance(self.opening_hand, OpeningHandPolicy):
            object.__setattr__(
                self, "opening_hand", OpeningHandPolicy(self.opening_hand)
            )
        if self.information_mode == InformationMode.PLAYER_VIEW:
            if self.viewer not in (0, 1):
                raise ValueError("player_view information policy requires viewer 0 or 1")
        elif self.viewer is not None:
            raise ValueError("viewer is only valid for player_view")
        sampling_required = (
            self.information_mode == InformationMode.SAMPLED_PRIVATE_STATE
            or self.opening_hand == OpeningHandPolicy.PROBABILITY_DISTRIBUTION
        )
        if sampling_required and not isinstance(self.sampling_reference, Mapping):
            raise ValueError("sampled/distribution policy requires sampling_reference")
        if not sampling_required and self.sampling_reference is not None:
            raise ValueError("sampling_reference requires sampled or distribution policy")
        if sampling_required:
            object.__setattr__(
                self,
                "sampling_reference",
                validate_opening_hand_sampling_reference(self.sampling_reference),
            )

    def decide(self, field: InformationField, owner: int | None) -> AccessDecision:
        if not isinstance(field, InformationField):
            field = InformationField(field)
        if owner is not None and owner not in (0, 1):
            raise ValueError("information field owner must be 0, 1, or None")
        if field == InformationField.PUBLIC_STATE:
            return AccessDecision.ALLOWED
        if field == InformationField.DECK_ORDER:
            if self.deck_order == DeckOrderKnowledge.UNKNOWN:
                return AccessDecision.DENIED_UNKNOWN_DECK_ORDER
            return self._private_decision(owner)
        if field == InformationField.PROBABILITY_DISTRIBUTION:
            if self.opening_hand != OpeningHandPolicy.PROBABILITY_DISTRIBUTION:
                return AccessDecision.DENIED_DISTRIBUTION_NOT_CONFIGURED
            return AccessDecision.ALLOWED
        return self._private_decision(owner)

    def _private_decision(self, owner: int | None) -> AccessDecision:
        if owner not in (0, 1):
            raise ValueError("private information access requires owner 0 or 1")
        if self.information_mode in {
            InformationMode.COMPLETE_INFORMATION,
            InformationMode.SAMPLED_PRIVATE_STATE,
        }:
            return AccessDecision.ALLOWED
        if owner == self.viewer:
            return AccessDecision.ALLOWED
        return AccessDecision.DENIED_PRIVATE_OWNER

    def to_dict(self) -> dict[str, Any]:
        identity = to_canonical_data(
            {
                "deck_order": self.deck_order.value,
                "information_mode": self.information_mode.value,
                "opening_hand": self.opening_hand.value,
                "sampling_reference": self.sampling_reference,
                "schema_version": INFORMATION_POLICY_SCHEMA_VERSION,
                "viewer": self.viewer,
            }
        )
        return {
            **identity,
            "policy_id": stable_digest(identity, prefix="infopol_"),
        }

    def to_experiment_dict(self) -> dict[str, Any]:
        """Serialize fields persisted by Experiment 0.3b.

        Visibility comes from ``information_mode`` and ``player.perspective``;
        duplicating those values inside the policy would permit contradictory
        experiment documents.
        """

        payload = self.to_dict()
        payload.pop("information_mode")
        payload.pop("viewer")
        return payload

    @classmethod
    def from_experiment(cls, experiment: Mapping[str, Any]) -> "InformationAccessPolicy":
        if experiment.get("schema_version") != (
            INFORMATION_POLICY_EXPERIMENT_SCHEMA_VERSION
        ):
            raise ValueError(
                "information policy requires an explicitly migrated Experiment 0.3b"
            )
        raw_policy = experiment.get("information_policy")
        player = experiment.get("player")
        if not isinstance(raw_policy, Mapping) or not isinstance(player, Mapping):
            raise ValueError("Experiment information_policy and player must be mappings")
        mode = InformationMode(str(experiment.get("information_mode")))
        policy = cls(
            information_mode=mode,
            deck_order=DeckOrderKnowledge(str(raw_policy.get("deck_order"))),
            opening_hand=OpeningHandPolicy(str(raw_policy.get("opening_hand"))),
            viewer=player.get("perspective") if mode == InformationMode.PLAYER_VIEW else None,
            sampling_reference=raw_policy.get("sampling_reference"),
        )
        if raw_policy.get("schema_version") != INFORMATION_POLICY_SCHEMA_VERSION:
            raise ValueError(
                f"information_policy.schema_version must be {INFORMATION_POLICY_SCHEMA_VERSION!r}"
            )
        if raw_policy.get("policy_id") != policy.to_dict()["policy_id"]:
            raise ValueError("information_policy.policy_id does not match policy content")
        return policy


@dataclass(frozen=True)
class InformationAccess:
    sequence: int
    field: InformationField
    owner: int | None
    purpose: str
    decision: AccessDecision

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision": self.decision.value,
            "field": self.field.value,
            "owner": self.owner,
            "purpose": self.purpose,
            "sequence": self.sequence,
        }


class InformationAccessAudit:
    def __init__(self, policy: InformationAccessPolicy) -> None:
        self.policy = policy
        self._accesses: list[InformationAccess] = []

    def record(
        self,
        field: InformationField,
        *,
        owner: int | None,
        purpose: str,
    ) -> AccessDecision:
        if not isinstance(field, InformationField):
            field = InformationField(field)
        if not isinstance(purpose, str) or not purpose:
            raise ValueError("information access purpose must be non-empty")
        decision = self.policy.decide(field, owner)
        self._accesses.append(
            InformationAccess(
                sequence=len(self._accesses),
                field=field,
                owner=owner,
                purpose=purpose,
                decision=decision,
            )
        )
        return decision

    def require(
        self,
        field: InformationField,
        *,
        owner: int | None,
        purpose: str,
    ) -> None:
        decision = self.record(field, owner=owner, purpose=purpose)
        if decision != AccessDecision.ALLOWED:
            raise InformationLeakError(
                f"information access denied: field={field.value} owner={owner} "
                f"purpose={purpose!r} decision={decision.value}"
            )

    def to_dict(self) -> dict[str, Any]:
        accesses = [access.to_dict() for access in self._accesses]
        leaks = [access for access in accesses if access["decision"] != "allowed"]
        identity = to_canonical_data(
            {
                "accesses": accesses,
                "leak_count": len(leaks),
                "leaks": leaks,
                "policy": self.policy.to_dict(),
                "schema_version": INFORMATION_AUDIT_SCHEMA_VERSION,
            }
        )
        return {
            **identity,
            "audit_id": stable_digest(identity, prefix="infoaudit_"),
        }

    def assert_no_leaks(self) -> None:
        report = self.to_dict()
        if report["leak_count"]:
            first = report["leaks"][0]
            raise InformationLeakError(
                "information audit detected forbidden access at sequence "
                f"{first['sequence']}: {first['decision']}"
            )
