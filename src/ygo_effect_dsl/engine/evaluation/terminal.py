from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
import math
from typing import Any

from ygo_effect_dsl.engine.canonical import stable_digest, to_canonical_data


TERMINAL_BOARD_PROJECTION_SCHEMA_VERSION = "terminal-board-projection-v1"
TERMINAL_PREFERENCE_PROFILE_SCHEMA_VERSION = "terminal-preference-profile-v1"
TERMINAL_PREFERENCE_EVALUATION_SCHEMA_VERSION = (
    "terminal-preference-evaluation-v1"
)


class TerminalLocation(str, Enum):
    HAND = "HAND"
    MONSTER_ZONE = "MONSTER_ZONE"
    SPELL_TRAP_ZONE = "SPELL_TRAP_ZONE"
    FIELD_ZONE = "FIELD_ZONE"
    GRAVEYARD = "GRAVEYARD"
    BANISHED = "BANISHED"


class TerminalPosition(str, Enum):
    ANY = "ANY"
    FACE_UP = "FACE_UP"
    FACE_DOWN = "FACE_DOWN"


class TerminalVisibility(str, Enum):
    PUBLIC = "public"
    PRIVATE = "private"
    REDACTED = "redacted"


class TerminalScoringMode(str, Enum):
    ONCE = "once"
    PER_COPY = "per_copy"
    THRESHOLD = "threshold"


_LOCATION_ALIASES: dict[Any, TerminalLocation] = {
    0x02: TerminalLocation.HAND,
    0x04: TerminalLocation.MONSTER_ZONE,
    0x08: TerminalLocation.SPELL_TRAP_ZONE,
    0x10: TerminalLocation.GRAVEYARD,
    0x20: TerminalLocation.BANISHED,
    "hand": TerminalLocation.HAND,
    "HAND": TerminalLocation.HAND,
    "monster_zone": TerminalLocation.MONSTER_ZONE,
    "MONSTER_ZONE": TerminalLocation.MONSTER_ZONE,
    "spell_trap_zone": TerminalLocation.SPELL_TRAP_ZONE,
    "SPELL_TRAP_ZONE": TerminalLocation.SPELL_TRAP_ZONE,
    "field_zone": TerminalLocation.FIELD_ZONE,
    "FIELD_ZONE": TerminalLocation.FIELD_ZONE,
    "graveyard": TerminalLocation.GRAVEYARD,
    "GRAVEYARD": TerminalLocation.GRAVEYARD,
    "banished": TerminalLocation.BANISHED,
    "BANISHED": TerminalLocation.BANISHED,
}

_POSITION_ALIASES: dict[Any, TerminalPosition] = {
    None: TerminalPosition.ANY,
    0: TerminalPosition.ANY,
    1: TerminalPosition.FACE_UP,
    4: TerminalPosition.FACE_UP,
    2: TerminalPosition.FACE_DOWN,
    8: TerminalPosition.FACE_DOWN,
    "ANY": TerminalPosition.ANY,
    "any": TerminalPosition.ANY,
    "FACE_UP": TerminalPosition.FACE_UP,
    "face_up": TerminalPosition.FACE_UP,
    "face_up_attack": TerminalPosition.FACE_UP,
    "face_up_defense": TerminalPosition.FACE_UP,
    "FACE_DOWN": TerminalPosition.FACE_DOWN,
    "face_down": TerminalPosition.FACE_DOWN,
    "face_down_attack": TerminalPosition.FACE_DOWN,
    "face_down_defense": TerminalPosition.FACE_DOWN,
}

_FIELD_LOCATIONS = {
    TerminalLocation.MONSTER_ZONE,
    TerminalLocation.SPELL_TRAP_ZONE,
    TerminalLocation.FIELD_ZONE,
}
_LOCATION_SORT = {
    TerminalLocation.HAND: 0,
    TerminalLocation.MONSTER_ZONE: 1,
    TerminalLocation.SPELL_TRAP_ZONE: 2,
    TerminalLocation.FIELD_ZONE: 3,
    TerminalLocation.GRAVEYARD: 4,
    TerminalLocation.BANISHED: 5,
}


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


def _optional_finite_number(value: Any, path: str) -> int | float | None:
    return None if value is None else _finite_number(value, path)


def _location(value: Any, path: str) -> TerminalLocation:
    try:
        return _LOCATION_ALIASES[value]
    except KeyError as exc:
        raise ValueError(f"{path} is not a supported terminal location") from exc


def _position(value: Any, path: str) -> TerminalPosition:
    try:
        return _POSITION_ALIASES[value]
    except KeyError as exc:
        raise ValueError(f"{path} is not a supported terminal position") from exc


@dataclass(frozen=True)
class TerminalCardEntry:
    instance_id: str
    card_code: int | None
    owner: int | None
    controller: int
    location: TerminalLocation
    position: TerminalPosition
    sequence: int
    visibility: TerminalVisibility
    redacted_identity: str | None = None

    def __post_init__(self) -> None:
        _string(self.instance_id, "instance_id")
        if self.card_code is not None:
            _integer(self.card_code, "card_code", minimum=1)
        if self.owner is not None:
            _integer(self.owner, "owner")
        _integer(self.controller, "controller")
        _integer(self.sequence, "sequence")
        if not isinstance(self.location, TerminalLocation):
            object.__setattr__(self, "location", TerminalLocation(self.location))
        if not isinstance(self.position, TerminalPosition):
            object.__setattr__(self, "position", TerminalPosition(self.position))
        if not isinstance(self.visibility, TerminalVisibility):
            object.__setattr__(self, "visibility", TerminalVisibility(self.visibility))
        if self.visibility == TerminalVisibility.PUBLIC:
            if self.card_code is None:
                raise ValueError("public terminal card requires card_code")
            if self.redacted_identity is not None:
                raise ValueError("public terminal card must not have redacted_identity")
        elif self.redacted_identity is None:
            raise ValueError("private/redacted terminal card requires redacted_identity")

    def to_dict(self) -> dict[str, Any]:
        return {
            "card_code": self.card_code,
            "controller": self.controller,
            "instance_id": self.instance_id,
            "location": self.location.value,
            "owner": self.owner,
            "position": self.position.value,
            "redacted_identity": self.redacted_identity,
            "sequence": self.sequence,
            "visibility": self.visibility.value,
        }


@dataclass(frozen=True)
class TerminalBoardProjection:
    state_hash: str
    cards: tuple[TerminalCardEntry, ...]
    schema_version: str = TERMINAL_BOARD_PROJECTION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != TERMINAL_BOARD_PROJECTION_SCHEMA_VERSION:
            raise ValueError("unsupported terminal board projection schema")
        _string(self.state_hash, "state_hash")
        if not isinstance(self.cards, tuple) or any(
            not isinstance(card, TerminalCardEntry) for card in self.cards
        ):
            raise ValueError("terminal projection cards must be TerminalCardEntry")
        ordered = tuple(
            sorted(
                self.cards,
                key=lambda card: (
                    card.controller,
                    _LOCATION_SORT[card.location],
                    card.sequence,
                    card.instance_id,
                ),
            )
        )
        object.__setattr__(self, "cards", ordered)

    @property
    def projection_id(self) -> str:
        identity = {
            "cards": [card.to_dict() for card in self.cards],
            "schema_version": self.schema_version,
            "state_hash": self.state_hash,
        }
        return stable_digest(identity, prefix="terminalproj_")

    def to_dict(self) -> dict[str, Any]:
        identity = to_canonical_data(
            {
                "cards": [card.to_dict() for card in self.cards],
                "schema_version": self.schema_version,
                "state_hash": self.state_hash,
            }
        )
        return {
            **identity,
            "projection_id": stable_digest(identity, prefix="terminalproj_"),
        }


def _entry_from_card(raw_card: Mapping[str, Any], index: int) -> TerminalCardEntry:
    controller = _integer(raw_card.get("controller"), f"public_cards[{index}].controller")
    sequence = _integer(
        raw_card.get("slot", raw_card.get("sequence", index)),
        f"public_cards[{index}].slot",
    )
    location = _location(raw_card.get("location"), f"public_cards[{index}].location")
    hidden = raw_card.get("hidden") is True or raw_card.get("redacted") is True
    if hidden:
        position = TerminalPosition.ANY
        visibility = TerminalVisibility.REDACTED
        card_code = None
        owner = None
        redacted_identity = stable_digest(
            {
                "controller": controller,
                "location": location.value,
                "sequence": sequence,
                "source": "terminal-board-projection-v1",
            },
            prefix="redactedcard_",
        )
        instance_id = redacted_identity
    else:
        card_code = _integer(raw_card.get("code"), f"public_cards[{index}].code", minimum=1)
        owner = _integer(raw_card.get("owner", controller), f"public_cards[{index}].owner")
        position = _position(raw_card.get("position"), f"public_cards[{index}].position")
        visibility = TerminalVisibility.PUBLIC
        redacted_identity = None
        instance_id = str(
            raw_card.get(
                "instance_id",
                raw_card.get(
                    "persistent_instance_id",
                    stable_digest(
                        {
                            "card_code": card_code,
                            "controller": controller,
                            "location": location.value,
                            "owner": owner,
                            "sequence": sequence,
                        },
                        prefix="terminalcard_",
                    ),
                ),
            )
        )
    return TerminalCardEntry(
        instance_id=instance_id,
        card_code=card_code,
        owner=owner,
        controller=controller,
        location=location,
        position=position,
        sequence=sequence,
        visibility=visibility,
        redacted_identity=redacted_identity,
    )


def build_terminal_board_projection(
    board_summary: Mapping[str, Any],
) -> TerminalBoardProjection:
    if not isinstance(board_summary, Mapping):
        raise ValueError("board_summary must be a mapping")
    state_hash = _string(board_summary.get("state_hash"), "board_summary.state_hash")
    raw_cards = board_summary.get("public_cards")
    if not isinstance(raw_cards, Sequence) or isinstance(raw_cards, (str, bytes)):
        raise ValueError("board_summary.public_cards must be a list")
    cards: list[TerminalCardEntry] = []
    for index, raw_card in enumerate(raw_cards):
        if not isinstance(raw_card, Mapping):
            raise ValueError("board_summary.public_cards items must be mappings")
        cards.append(_entry_from_card(raw_card, index))
    return TerminalBoardProjection(state_hash=state_hash, cards=tuple(cards))


@dataclass(frozen=True)
class TerminalPreferenceRule:
    rule_id: str
    card_code: int
    controller: int
    location: TerminalLocation
    position: TerminalPosition
    min_count: int
    max_count: int | None
    scoring_mode: TerminalScoringMode
    weight: int
    enabled: bool = True

    def __post_init__(self) -> None:
        _string(self.rule_id, "rule_id")
        _integer(self.card_code, "card_code", minimum=1)
        _integer(self.controller, "controller")
        _integer(self.min_count, "min_count", minimum=1)
        if self.max_count is not None:
            maximum = _integer(self.max_count, "max_count", minimum=1)
            if maximum < self.min_count:
                raise ValueError("max_count must be >= min_count")
        if not isinstance(self.location, TerminalLocation):
            object.__setattr__(self, "location", _location(self.location, "location"))
        if not isinstance(self.position, TerminalPosition):
            object.__setattr__(self, "position", _position(self.position, "position"))
        if not isinstance(self.scoring_mode, TerminalScoringMode):
            object.__setattr__(
                self,
                "scoring_mode",
                TerminalScoringMode(self.scoring_mode),
            )
        if not isinstance(self.weight, int) or isinstance(self.weight, bool):
            raise ValueError("weight must be an integer score unit")
        if not isinstance(self.enabled, bool):
            raise ValueError("enabled must be a boolean")
        if (
            self.position == TerminalPosition.FACE_DOWN
            and self.location not in _FIELD_LOCATIONS
        ):
            raise ValueError("FACE_DOWN is only valid for field locations")

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> TerminalPreferenceRule:
        expected = {
            "card_code",
            "controller",
            "enabled",
            "location",
            "max_count",
            "min_count",
            "position",
            "rule_id",
            "scoring_mode",
            "weight",
        }
        if not isinstance(value, Mapping) or set(value) != expected:
            raise ValueError(f"terminal preference rule fields must be {sorted(expected)}")
        return cls(
            rule_id=value["rule_id"],
            card_code=value["card_code"],
            controller=value["controller"],
            location=_location(value["location"], "location"),
            position=_position(value["position"], "position"),
            min_count=value["min_count"],
            max_count=value["max_count"],
            scoring_mode=TerminalScoringMode(value["scoring_mode"]),
            weight=value["weight"],
            enabled=value["enabled"],
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "card_code": self.card_code,
            "controller": self.controller,
            "enabled": self.enabled,
            "location": self.location.value,
            "max_count": self.max_count,
            "min_count": self.min_count,
            "position": self.position.value,
            "rule_id": self.rule_id,
            "scoring_mode": self.scoring_mode.value,
            "weight": self.weight,
        }


@dataclass(frozen=True)
class TerminalPreferenceProfile:
    name: str
    rules: tuple[TerminalPreferenceRule, ...]
    schema_version: str = TERMINAL_PREFERENCE_PROFILE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != TERMINAL_PREFERENCE_PROFILE_SCHEMA_VERSION:
            raise ValueError("unsupported terminal preference profile schema")
        _string(self.name, "name")
        if not isinstance(self.rules, tuple) or any(
            not isinstance(rule, TerminalPreferenceRule) for rule in self.rules
        ):
            raise ValueError("rules must be TerminalPreferenceRule instances")
        if len({rule.rule_id for rule in self.rules}) != len(self.rules):
            raise ValueError("terminal preference rule IDs must be unique")

    @property
    def profile_id(self) -> str:
        return self.to_dict()["profile_id"]

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> TerminalPreferenceProfile:
        expected = {"name", "rules", "schema_version"}
        if not isinstance(value, Mapping) or set(value) != expected:
            raise ValueError(f"terminal preference profile fields must be {sorted(expected)}")
        raw_rules = value["rules"]
        if not isinstance(raw_rules, list):
            raise ValueError("terminal preference profile rules must be a list")
        return cls(
            name=value["name"],
            rules=tuple(TerminalPreferenceRule.from_mapping(rule) for rule in raw_rules),
            schema_version=value["schema_version"],
        )

    def clone_with(
        self,
        *,
        name: str | None = None,
        rules: Sequence[Mapping[str, Any] | TerminalPreferenceRule] | None = None,
    ) -> TerminalPreferenceProfile:
        resolved_rules = self.rules if rules is None else tuple(
            rule
            if isinstance(rule, TerminalPreferenceRule)
            else TerminalPreferenceRule.from_mapping(rule)
            for rule in rules
        )
        return TerminalPreferenceProfile(
            name=self.name if name is None else name,
            rules=resolved_rules,
        )

    def to_dict(self) -> dict[str, Any]:
        identity = to_canonical_data(
            {
                "name": self.name,
                "rules": [rule.to_dict() for rule in self.rules],
                "schema_version": self.schema_version,
            }
        )
        return {
            **identity,
            "profile_id": stable_digest(identity, prefix="termpref_"),
        }


def _matches(rule: TerminalPreferenceRule, card: TerminalCardEntry) -> bool:
    if card.visibility != TerminalVisibility.PUBLIC:
        return False
    if card.card_code != rule.card_code or card.controller != rule.controller:
        return False
    if card.location != rule.location:
        return False
    return rule.position == TerminalPosition.ANY or card.position == rule.position


def _applied_value(rule: TerminalPreferenceRule, count: int) -> int:
    if not rule.enabled or count < rule.min_count:
        return 0
    if rule.max_count is not None and count > rule.max_count:
        count = rule.max_count
    if rule.scoring_mode == TerminalScoringMode.ONCE:
        return rule.weight
    if rule.scoring_mode == TerminalScoringMode.PER_COPY:
        return rule.weight * count
    return rule.weight


def evaluate_terminal_preferences(
    projection: TerminalBoardProjection,
    profile: TerminalPreferenceProfile | None,
    *,
    base_score: int | float,
    randomness_penalty: int = 0,
) -> dict[str, Any]:
    _finite_number(base_score, "base_score")
    if not isinstance(randomness_penalty, int) or isinstance(randomness_penalty, bool):
        raise ValueError("randomness_penalty must be an integer")
    if profile is None:
        preference_score = 0
        components: list[dict[str, Any]] = []
        profile_id = None
    else:
        preference_score = 0
        components = []
        profile_id = profile.profile_id
        for rule in profile.rules:
            matching = tuple(card for card in projection.cards if _matches(rule, card))
            redacted_possible = any(
                card.visibility != TerminalVisibility.PUBLIC
                and card.controller == rule.controller
                and card.location == rule.location
                for card in projection.cards
            )
            applied = _applied_value(rule, len(matching))
            preference_score += applied
            components.append(
                {
                    "applied_value": applied,
                    "enabled": rule.enabled,
                    "match_status": (
                        "matched"
                        if matching
                        else "redacted_or_unknown"
                        if redacted_possible
                        else "not_matched"
                    ),
                    "matched_instances": [card.instance_id for card in matching],
                    "observed_count": len(matching),
                    "observed_location": rule.location.value,
                    "observed_position": rule.position.value,
                    "rule_id": rule.rule_id,
                    "weight": rule.weight,
                }
            )
    identity = to_canonical_data(
        {
            "base_score": base_score,
            "components": components,
            "preference_profile_id": profile_id,
            "preference_score": preference_score,
            "projection_id": projection.projection_id,
            "randomness_penalty": randomness_penalty,
            "schema_version": TERMINAL_PREFERENCE_EVALUATION_SCHEMA_VERSION,
            "terminal_composite_score": (
                base_score + preference_score - randomness_penalty
            ),
        }
    )
    return {
        **identity,
        "terminal_evaluation_id": stable_digest(identity, prefix="termeval_"),
    }
