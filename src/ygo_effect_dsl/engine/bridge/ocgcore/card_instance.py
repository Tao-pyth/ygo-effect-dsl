from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
import re
from typing import Any

from ygo_effect_dsl.engine.bridge.decision import (
    Candidate,
    DecisionRequest,
)
from ygo_effect_dsl.engine.bridge.ocgcore.providers import ResolvedScript, resolve_script
from ygo_effect_dsl.engine.bridge.ocgcore.types import CoreLog, LogType
from ygo_effect_dsl.engine.canonical import stable_digest, to_canonical_data
from ygo_effect_dsl.engine.state import InformationMode


CARD_INSTANCE_TRACE_SCHEMA_VERSION = "ocgcore-card-instance-trace-v1"
CARD_INSTANCE_TRACE_LOG_PREFIX = "YGO_EFFECT_DSL_CARD_INSTANCE_V1"
CARD_INSTANCE_TRACE_SCRIPT_NAME = "ygo_effect_dsl_card_instance_trace.lua"
CARD_INSTANCE_TRACE_TRANSPORT = "ocgcore_log_handler_from_script_v1"
CARD_INSTANCE_AUTHORITY = "ocgcore_lua_card_get_card_id_v1"
CARD_INSTANCE_TRACE_V2_SCHEMA_VERSION = "ocgcore-card-instance-trace-v2"
CARD_INSTANCE_TRACE_V2_LOG_PREFIX = "YGO_EFFECT_DSL_CARD_INSTANCE_V2"
CARD_INSTANCE_TRACE_V2_SCRIPT_NAME = "ygo_effect_dsl_card_instance_trace_v2.lua"
CARD_INSTANCE_PROVENANCE_V2_SCHEMA_VERSION = "card-instance-provenance-v2"
CARD_INSTANCE_TRACE_V2_TRANSPORT = "ocgcore_log_handler_from_script_v2"
_LABEL = re.compile(r"^[a-z][a-z0-9_]*$")
_PUBLIC_LOCATIONS = frozenset({0x04, 0x08, 0x10, 0x20})
_FACEUP_POSITIONS = 0x05


CARD_INSTANCE_TRACE_LUA_SOURCE = b"""if YGO_EFFECT_DSL_CARD_INSTANCE_SCAN then
    return
end

local observation_index = 0
local trace_locations = (LOCATION_DECK + LOCATION_HAND + LOCATION_MZONE
    + LOCATION_SZONE + LOCATION_GRAVE + LOCATION_REMOVED + LOCATION_EXTRA)

local function emit(label, c)
    observation_index = observation_index + 1
    local original_code = c:GetOriginalCode()
    local is_token = 0
    if c:IsType(TYPE_TOKEN) then
        is_token = 1
    end
    Debug.Message(string.format(
        "YGO_EFFECT_DSL_CARD_INSTANCE_V1|%d|%s|%d|%d|%d|%d|%d|%d|%d|%d|%d|%d|%d|%d",
        observation_index,
        label,
        c:GetCardID(),
        original_code,
        c:GetOwner(),
        c:GetControler(),
        c:GetLocation(),
        c:GetSequence(),
        c:GetPosition(),
        c:GetPreviousControler(),
        c:GetPreviousLocation(),
        c:GetPreviousSequence(),
        c:GetPreviousPosition(),
        is_token
    ))
end

function YGO_EFFECT_DSL_CARD_INSTANCE_OBSERVE(label, c)
    emit(label, c)
end

function YGO_EFFECT_DSL_CARD_INSTANCE_SCAN(label)
    local cards = Duel.GetFieldGroup(0, trace_locations, trace_locations)
    local card = cards:GetFirst()
    while card do
        emit(label, card)
        card = cards:GetNext()
    end
end

local startup = Effect.GlobalEffect()
startup:SetType(EFFECT_TYPE_FIELD + EFFECT_TYPE_CONTINUOUS)
startup:SetCode(EVENT_STARTUP)
startup:SetOperation(function()
    YGO_EFFECT_DSL_CARD_INSTANCE_SCAN("startup")
    if YGO_EFFECT_DSL_CARD_INSTANCE_STARTUP_HOOK then
        YGO_EFFECT_DSL_CARD_INSTANCE_STARTUP_HOOK()
    end
end)
Duel.RegisterEffect(startup, 0)

local moved = Effect.GlobalEffect()
moved:SetType(EFFECT_TYPE_FIELD + EFFECT_TYPE_CONTINUOUS)
moved:SetCode(EVENT_MOVE)
moved:SetOperation(function()
    YGO_EFFECT_DSL_CARD_INSTANCE_SCAN("move_scan")
end)
Duel.RegisterEffect(moved, 0)
"""


CARD_INSTANCE_TRACE_V2_LUA_SOURCE = b"""if YGO_EFFECT_DSL_CARD_INSTANCE_SCAN_V2 then
    return
end

local observation_index = 0
local scan_index = 0
local scanning = false
local trace_locations = (LOCATION_DECK + LOCATION_HAND + LOCATION_MZONE
    + LOCATION_SZONE + LOCATION_GRAVE + LOCATION_REMOVED + LOCATION_EXTRA)

local function emit(scan_id, c)
    observation_index = observation_index + 1
    local is_token = 0
    if c:IsType(TYPE_TOKEN) then
        is_token = 1
    end
    Debug.Message(string.format(
        "YGO_EFFECT_DSL_CARD_INSTANCE_V2|CARD|%d|%d|%d|%d|%d|%d|%d|%d|%d|%d|%d|%d|%d|%d",
        scan_id,
        observation_index,
        c:GetCardID(),
        c:GetOriginalCode(),
        c:GetOwner(),
        c:GetControler(),
        c:GetLocation(),
        c:GetSequence(),
        c:GetPosition(),
        c:GetPreviousControler(),
        c:GetPreviousLocation(),
        c:GetPreviousSequence(),
        c:GetPreviousPosition(),
        is_token
    ))
end

function YGO_EFFECT_DSL_CARD_INSTANCE_SCAN_V2(label)
    if scanning then
        return
    end
    scanning = true
    scan_index = scan_index + 1
    local scan_id = scan_index
    Debug.Message(string.format(
        "YGO_EFFECT_DSL_CARD_INSTANCE_V2|BEGIN|%d|%s", scan_id, label
    ))
    local count = 0
    local cards = Duel.GetFieldGroup(0, trace_locations, trace_locations)
    local card = cards:GetFirst()
    while card do
        emit(scan_id, card)
        count = count + 1
        card = cards:GetNext()
    end
    Debug.Message(string.format(
        "YGO_EFFECT_DSL_CARD_INSTANCE_V2|END|%d|%s|%d", scan_id, label, count
    ))
    scanning = false
end

local function register_boundary(code, label)
    local effect = Effect.GlobalEffect()
    effect:SetType(EFFECT_TYPE_FIELD + EFFECT_TYPE_CONTINUOUS)
    effect:SetCode(code)
    effect:SetOperation(function()
        YGO_EFFECT_DSL_CARD_INSTANCE_SCAN_V2(label)
        if code == EVENT_STARTUP and YGO_EFFECT_DSL_CARD_INSTANCE_STARTUP_HOOK then
            YGO_EFFECT_DSL_CARD_INSTANCE_STARTUP_HOOK()
        end
    end)
    Duel.RegisterEffect(effect, 0)
end

register_boundary(EVENT_STARTUP, "startup")
register_boundary(EVENT_ADJUST, "adjust")
register_boundary(EVENT_MOVE, "move")
register_boundary(EVENT_CHAINING, "chaining")
register_boundary(EVENT_CHAIN_SOLVING, "chain_solving")
register_boundary(EVENT_CHAIN_SOLVED, "chain_solved")
register_boundary(EVENT_SUMMON_SUCCESS, "summon_success")
register_boundary(EVENT_SPSUMMON_SUCCESS, "special_summon_success")
register_boundary(EVENT_FLIP_SUMMON_SUCCESS, "flip_summon_success")
register_boundary(EVENT_TO_HAND, "to_hand")
register_boundary(EVENT_TO_DECK, "to_deck")
register_boundary(EVENT_TO_GRAVE, "to_grave")
register_boundary(EVENT_REMOVE, "removed")
register_boundary(EVENT_CONTROL_CHANGED, "control_changed")
register_boundary(EVENT_PHASE_START + PHASE_DRAW, "phase_draw")
register_boundary(EVENT_PHASE_START + PHASE_STANDBY, "phase_standby")
register_boundary(EVENT_PHASE_START + PHASE_MAIN1, "phase_main1")
register_boundary(EVENT_PHASE_START + PHASE_BATTLE_START, "phase_battle")
register_boundary(EVENT_PHASE_START + PHASE_MAIN2, "phase_main2")
register_boundary(EVENT_PHASE_START + PHASE_END, "phase_end")
"""


def build_card_instance_scope_id(identity: Mapping[str, Any]) -> str:
    return stable_digest(
        {
            "authority": CARD_INSTANCE_AUTHORITY,
            "identity": to_canonical_data(identity),
            "schema_version": CARD_INSTANCE_TRACE_SCHEMA_VERSION,
        },
        prefix="cardinstscope_",
    )


@dataclass(frozen=True)
class CardInstanceObservation:
    observation_index: int
    label: str
    card_id: int
    card_code: int
    owner: int
    controller: int
    location: int
    sequence: int
    position: int
    previous_controller: int
    previous_location: int
    previous_sequence: int
    previous_position: int
    is_token: bool
    log_sequence: int
    instance_id: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "authority": CARD_INSTANCE_AUTHORITY,
            "card_code": self.card_code,
            "card_id": self.card_id,
            "controller": self.controller,
            "instance_id": self.instance_id,
            "is_token": self.is_token,
            "label": self.label,
            "location": self.location,
            "log_sequence": self.log_sequence,
            "observation_index": self.observation_index,
            "owner": self.owner,
            "position": self.position,
            "previous_controller": self.previous_controller,
            "previous_location": self.previous_location,
            "previous_position": self.previous_position,
            "previous_sequence": self.previous_sequence,
            "schema_version": CARD_INSTANCE_TRACE_SCHEMA_VERSION,
            "sequence": self.sequence,
            "transport": CARD_INSTANCE_TRACE_TRANSPORT,
        }


def _integer(value: str, field: str, *, minimum: int = 0) -> int:
    try:
        parsed = int(value, 10)
    except ValueError as exc:
        raise ValueError(f"card instance trace {field} must be an integer") from exc
    if parsed < minimum or parsed > 0xFFFFFFFF:
        raise ValueError(
            f"card instance trace {field} must be between {minimum} and 2^32-1"
        )
    return parsed


def parse_card_instance_log(
    log: CoreLog,
    *,
    scope_id: str,
) -> CardInstanceObservation | None:
    if not log.message.startswith(CARD_INSTANCE_TRACE_LOG_PREFIX):
        return None
    if log.log_type != LogType.FROM_SCRIPT:
        raise ValueError("card instance trace must use FROM_SCRIPT log type")
    if not isinstance(scope_id, str) or not scope_id.startswith("cardinstscope_"):
        raise ValueError("scope_id must be a card instance scope ID")
    parts = log.message.split("|")
    if len(parts) != 15 or parts[0] != CARD_INSTANCE_TRACE_LOG_PREFIX:
        raise ValueError("card instance trace record must contain 15 fields")
    label = parts[2]
    if not _LABEL.fullmatch(label):
        raise ValueError("card instance trace label is invalid")
    values = {
        "observation_index": _integer(parts[1], "observation_index", minimum=1),
        "card_id": _integer(parts[3], "card_id", minimum=1),
        "card_code": _integer(parts[4], "card_code"),
        "owner": _integer(parts[5], "owner"),
        "controller": _integer(parts[6], "controller"),
        "location": _integer(parts[7], "location"),
        "sequence": _integer(parts[8], "sequence"),
        "position": _integer(parts[9], "position"),
        "previous_controller": _integer(parts[10], "previous_controller"),
        "previous_location": _integer(parts[11], "previous_location"),
        "previous_sequence": _integer(parts[12], "previous_sequence"),
        "previous_position": _integer(parts[13], "previous_position"),
        "is_token": _integer(parts[14], "is_token"),
    }
    if values["owner"] not in (0, 1):
        raise ValueError("card instance trace owner must be 0 or 1")
    if values["controller"] not in (0, 1, 2):
        raise ValueError("card instance trace controller must be 0, 1, or 2")
    if values["previous_controller"] not in (0, 1, 2):
        raise ValueError(
            "card instance trace previous_controller must be 0, 1, or 2"
        )
    if values["is_token"] not in (0, 1):
        raise ValueError("card instance trace is_token must be 0 or 1")
    identity = {
        "authority": CARD_INSTANCE_AUTHORITY,
        "card_id": values["card_id"],
        "scope_id": scope_id,
        "schema_version": CARD_INSTANCE_TRACE_SCHEMA_VERSION,
    }
    return CardInstanceObservation(
        observation_index=values["observation_index"],
        label=label,
        card_id=values["card_id"],
        card_code=values["card_code"],
        owner=values["owner"],
        controller=values["controller"],
        location=values["location"],
        sequence=values["sequence"],
        position=values["position"],
        previous_controller=values["previous_controller"],
        previous_location=values["previous_location"],
        previous_sequence=values["previous_sequence"],
        previous_position=values["previous_position"],
        is_token=bool(values["is_token"]),
        log_sequence=log.sequence,
        instance_id=stable_digest(identity, prefix="corecard_"),
    )


class CardInstanceTracker:
    def __init__(self, *, scope_id: str) -> None:
        if not isinstance(scope_id, str) or not scope_id.startswith(
            "cardinstscope_"
        ):
            raise ValueError("scope_id must be a card instance scope ID")
        self.scope_id = scope_id
        self._last_observation_index = 0
        self._last_log_sequence = -1
        self._latest_by_card_id: dict[int, CardInstanceObservation] = {}
        self._observations: list[CardInstanceObservation] = []

    @property
    def observations(self) -> tuple[CardInstanceObservation, ...]:
        return tuple(self._observations)

    def consume(self, logs: Sequence[CoreLog]) -> tuple[CardInstanceObservation, ...]:
        consumed: list[CardInstanceObservation] = []
        for log in logs:
            observation = parse_card_instance_log(log, scope_id=self.scope_id)
            if observation is None:
                continue
            expected = self._last_observation_index + 1
            if observation.observation_index != expected:
                raise ValueError(
                    "card instance observation_index must be contiguous; "
                    f"expected {expected}, got {observation.observation_index}"
                )
            if observation.log_sequence <= self._last_log_sequence:
                raise ValueError("card instance log_sequence must increase")
            previous = self._latest_by_card_id.get(observation.card_id)
            if previous is not None and (
                previous.card_code != observation.card_code
                or previous.owner != observation.owner
                or previous.is_token != observation.is_token
                or previous.instance_id != observation.instance_id
            ):
                raise ValueError(
                    "card instance authority fields changed for one card_id"
                )
            self._last_observation_index = observation.observation_index
            self._last_log_sequence = observation.log_sequence
            self._latest_by_card_id[observation.card_id] = observation
            self._observations.append(observation)
            consumed.append(observation)
        return tuple(consumed)

    def resolve(
        self,
        *,
        controller: int,
        location: int,
        sequence: int,
        public_card_id: int | None = None,
    ) -> CardInstanceObservation:
        matches = [
            observation
            for observation in self._latest_by_card_id.values()
            if observation.controller == controller
            and observation.location == location
            and observation.sequence == sequence
        ]
        if len(matches) != 1:
            raise ValueError(
                "card instance location must resolve to exactly one authority record; "
                f"got {len(matches)} for {controller}:{location}:{sequence}"
            )
        match = matches[0]
        if public_card_id not in (None, 0, match.card_code):
            raise ValueError(
                "card instance authority code differs from request card code"
            )
        return match

    def enrich_request(self, request: DecisionRequest) -> DecisionRequest:
        candidates: list[Candidate] = []
        for candidate in request.candidates:
            raw = candidate.card_ref
            if not isinstance(raw, Mapping):
                candidates.append(candidate)
                continue
            coordinate = tuple(raw.get(field) for field in (
                "controller",
                "location",
                "sequence",
            ))
            if any(
                not isinstance(value, int) or isinstance(value, bool)
                for value in coordinate
            ):
                raise ValueError("card candidate has an invalid core location")
            observation = self.resolve(
                controller=coordinate[0],
                location=coordinate[1],
                sequence=coordinate[2],
                public_card_id=raw.get("public_card_id"),
            )
            card_ref = dict(raw)
            card_ref["instance_id"] = observation.instance_id
            card_ref["owner"] = observation.owner
            candidates.append(replace(candidate, card_ref=card_ref))
        return replace(request, candidates=tuple(candidates))


def _is_visible(observation: CardInstanceObservation, viewer: int) -> bool:
    if observation.owner == viewer:
        return True
    return (
        observation.location in _PUBLIC_LOCATIONS
        and bool(observation.position & _FACEUP_POSITIONS)
    )


def project_card_instance_observations(
    observations: Sequence[CardInstanceObservation],
    *,
    information_mode: InformationMode | str,
    viewer: int | None = None,
) -> list[dict[str, Any]]:
    mode = InformationMode(information_mode)
    if mode == InformationMode.COMPLETE_INFORMATION:
        if viewer is not None:
            raise ValueError("viewer is invalid for complete_information")
        return [observation.to_dict() for observation in observations]
    if viewer not in (0, 1):
        raise ValueError("non-complete card instance projection requires viewer 0 or 1")
    visible = [
        observation
        for observation in observations
        if _is_visible(observation, viewer)
    ]
    return [
        {
            "card_code": observation.card_code,
            "controller": observation.controller,
            "instance_id": observation.instance_id,
            "is_token": observation.is_token,
            "label": observation.label,
            "location": observation.location,
            "owner": observation.owner,
            "position": observation.position,
            "schema_version": CARD_INSTANCE_TRACE_SCHEMA_VERSION,
            "sequence": observation.sequence,
            "visible_sequence": index,
        }
        for index, observation in enumerate(visible)
    ]


def build_card_instance_scope_id_v2(identity: Mapping[str, Any]) -> str:
    return stable_digest(
        {
            "authority": CARD_INSTANCE_AUTHORITY,
            "identity": to_canonical_data(identity),
            "schema_version": CARD_INSTANCE_TRACE_V2_SCHEMA_VERSION,
        },
        prefix="cardinstscope_",
    )


@dataclass(frozen=True)
class CardInstanceScanV2:
    scan_id: int
    label: str
    observations: tuple[CardInstanceObservation, ...]
    begin_log_sequence: int
    end_log_sequence: int

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "boundary": self.label,
            "card_count": len(self.observations),
            "scan_id": self.scan_id,
            "schema_version": CARD_INSTANCE_TRACE_V2_SCHEMA_VERSION,
        }


def _v2_label(value: str) -> str:
    if not _LABEL.fullmatch(value):
        raise ValueError("card instance v2 trace label is invalid")
    return value


def _parse_v2_card(
    log: CoreLog,
    *,
    scope_id: str,
) -> tuple[int, CardInstanceObservation]:
    parts = log.message.split("|")
    if len(parts) != 16 or parts[:2] != [CARD_INSTANCE_TRACE_V2_LOG_PREFIX, "CARD"]:
        raise ValueError("card instance v2 CARD record must contain 16 fields")
    scan_id = _integer(parts[2], "scan_id", minimum=1)
    values = {
        "observation_index": _integer(parts[3], "observation_index", minimum=1),
        "card_id": _integer(parts[4], "card_id", minimum=1),
        "card_code": _integer(parts[5], "card_code"),
        "owner": _integer(parts[6], "owner"),
        "controller": _integer(parts[7], "controller"),
        "location": _integer(parts[8], "location"),
        "sequence": _integer(parts[9], "sequence"),
        "position": _integer(parts[10], "position"),
        "previous_controller": _integer(parts[11], "previous_controller"),
        "previous_location": _integer(parts[12], "previous_location"),
        "previous_sequence": _integer(parts[13], "previous_sequence"),
        "previous_position": _integer(parts[14], "previous_position"),
        "is_token": _integer(parts[15], "is_token"),
    }
    if values["owner"] not in (0, 1):
        raise ValueError("card instance v2 owner must be 0 or 1")
    if values["controller"] not in (0, 1, 2):
        raise ValueError("card instance v2 controller must be 0, 1, or 2")
    if values["previous_controller"] not in (0, 1, 2):
        raise ValueError("card instance v2 previous_controller must be 0, 1, or 2")
    if values["is_token"] not in (0, 1):
        raise ValueError("card instance v2 is_token must be 0 or 1")
    identity = {
        "authority": CARD_INSTANCE_AUTHORITY,
        "card_id": values["card_id"],
        "card_code": values["card_code"],
        "owner": values["owner"],
        "scope_id": scope_id,
        "schema_version": CARD_INSTANCE_TRACE_V2_SCHEMA_VERSION,
    }
    observation = CardInstanceObservation(
        observation_index=values["observation_index"],
        label=f"scan_{scan_id}",
        card_id=values["card_id"],
        card_code=values["card_code"],
        owner=values["owner"],
        controller=values["controller"],
        location=values["location"],
        sequence=values["sequence"],
        position=values["position"],
        previous_controller=values["previous_controller"],
        previous_location=values["previous_location"],
        previous_sequence=values["previous_sequence"],
        previous_position=values["previous_position"],
        is_token=bool(values["is_token"]),
        log_sequence=log.sequence,
        instance_id=stable_digest(identity, prefix="corecard_"),
    )
    return scan_id, observation


class CardInstanceTrackerV2:
    """Fail-closed Request and snapshot identity adapter for real-core routes."""

    def __init__(self, *, scope_id: str) -> None:
        if not isinstance(scope_id, str) or not scope_id.startswith("cardinstscope_"):
            raise ValueError("scope_id must be a card instance scope ID")
        self.scope_id = scope_id
        self._last_scan_id = 0
        self._last_observation_index = 0
        self._latest_by_card_id: dict[int, CardInstanceObservation] = {}
        self._latest_by_coordinate: dict[tuple[int, int, int], CardInstanceObservation] = {}
        self._scans: list[CardInstanceScanV2] = []
        self._viewer_visible: dict[tuple[int, int], bool] = {}
        self._viewer_epoch: dict[tuple[int, int], int] = {}
        self._viewer_alias: dict[tuple[int, int], str] = {}
        self._request_boundaries: list[dict[str, Any]] = []
        self._movement_transitions: list[dict[str, Any]] = []
        self._last_synchronized_transition = 0
        self._shuffle_boundaries: list[dict[str, Any]] = []

    @property
    def scans(self) -> tuple[CardInstanceScanV2, ...]:
        return tuple(self._scans)

    @property
    def observations(self) -> tuple[CardInstanceObservation, ...]:
        return tuple(
            observation
            for scan in self._scans
            for observation in scan.observations
        )

    def _validate_authority(self, observation: CardInstanceObservation) -> None:
        previous = self._latest_by_card_id.get(observation.card_id)
        if previous is not None and (
            previous.card_code != observation.card_code
            or previous.owner != observation.owner
            or previous.is_token != observation.is_token
            or previous.instance_id != observation.instance_id
        ):
            raise ValueError("card instance v2 authority fields changed for one card_id")

    def _record_transition(
        self,
        previous: CardInstanceObservation | None,
        observation: CardInstanceObservation,
        *,
        scan: CardInstanceScanV2,
    ) -> None:
        if previous is None:
            if not observation.is_token:
                return
            movement_kind = "generated_token"
            before = None
        else:
            before = {
                "controller": previous.controller,
                "location": previous.location,
                "sequence": previous.sequence,
            }
            after_coordinate = (
                observation.controller,
                observation.location,
                observation.sequence,
            )
            before_coordinate = (
                previous.controller,
                previous.location,
                previous.sequence,
            )
            if before_coordinate == after_coordinate:
                return
            if previous.controller != observation.controller:
                movement_kind = "control_change"
            elif previous.location == 0x01 and observation.location == 0x02:
                movement_kind = "deck_to_hand_pending"
            elif previous.location == 0x10 and observation.location == 0x02:
                movement_kind = "salvage"
            elif previous.location == observation.location:
                movement_kind = "sequence_change"
            else:
                movement_kind = "location_move"
        self._movement_transitions.append(
            {
                "after": {
                    "controller": observation.controller,
                    "location": observation.location,
                    "sequence": observation.sequence,
                },
                "before": before,
                "boundary": scan.label,
                "instance_id": observation.instance_id,
                "movement_kind": movement_kind,
                "owner": observation.owner,
                "scan_id": scan.scan_id,
            }
        )

    def _update_viewer_aliases(
        self, observations: Sequence[CardInstanceObservation]
    ) -> None:
        observed_ids = {item.card_id for item in observations}
        for viewer in (0, 1):
            for card_id in set(self._latest_by_card_id) | observed_ids:
                key = (viewer, card_id)
                observation = next(
                    (item for item in observations if item.card_id == card_id),
                    None,
                )
                visible = observation is not None and _is_visible(observation, viewer)
                was_visible = self._viewer_visible.get(key, False)
                if visible and not was_visible:
                    epoch = self._viewer_epoch.get(key, -1) + 1
                    self._viewer_epoch[key] = epoch
                    assert observation is not None
                    self._viewer_alias[key] = stable_digest(
                        {
                            "instance_id": observation.instance_id,
                            "knowledge_epoch": epoch,
                            "viewer": viewer,
                        },
                        prefix="viewcard_",
                    )
                self._viewer_visible[key] = visible

    def consume(self, logs: Sequence[CoreLog]) -> tuple[CardInstanceScanV2, ...]:
        trace_logs = [
            log
            for log in logs
            if log.message.startswith(CARD_INSTANCE_TRACE_V2_LOG_PREFIX)
        ]
        scans: list[CardInstanceScanV2] = []
        current_id: int | None = None
        current_label: str | None = None
        begin_sequence = -1
        cards: list[CardInstanceObservation] = []
        for log in trace_logs:
            if log.log_type != LogType.FROM_SCRIPT:
                raise ValueError("card instance v2 trace must use FROM_SCRIPT log type")
            parts = log.message.split("|")
            record_type = parts[1] if len(parts) > 1 else ""
            if record_type == "BEGIN":
                if len(parts) != 4:
                    raise ValueError("card instance v2 BEGIN record must contain 4 fields")
                if current_id is not None:
                    raise ValueError("card instance v2 scan boundaries must not nest")
                current_id = _integer(parts[2], "scan_id", minimum=1)
                if current_id != self._last_scan_id + len(scans) + 1:
                    raise ValueError("card instance v2 scan_id must be contiguous")
                current_label = _v2_label(parts[3])
                begin_sequence = log.sequence
                cards = []
            elif record_type == "CARD":
                if current_id is None:
                    raise ValueError("card instance v2 CARD appeared outside a scan")
                scan_id, observation = _parse_v2_card(log, scope_id=self.scope_id)
                if scan_id != current_id:
                    raise ValueError("card instance v2 CARD scan_id differs from BEGIN")
                expected = self._last_observation_index + sum(
                    len(scan.observations) for scan in scans
                ) + len(cards) + 1
                if observation.observation_index != expected:
                    raise ValueError("card instance v2 observation_index must be contiguous")
                self._validate_authority(observation)
                cards.append(observation)
            elif record_type == "END":
                if len(parts) != 5:
                    raise ValueError("card instance v2 END record must contain 5 fields")
                if current_id is None or current_label is None:
                    raise ValueError("card instance v2 END appeared outside a scan")
                scan_id = _integer(parts[2], "scan_id", minimum=1)
                label = _v2_label(parts[3])
                count = _integer(parts[4], "card_count")
                if scan_id != current_id or label != current_label or count != len(cards):
                    raise ValueError("card instance v2 END does not match its BEGIN/CARD records")
                scans.append(
                    CardInstanceScanV2(
                        scan_id=scan_id,
                        label=label,
                        observations=tuple(cards),
                        begin_log_sequence=begin_sequence,
                        end_log_sequence=log.sequence,
                    )
                )
                current_id = None
                current_label = None
                cards = []
            else:
                raise ValueError("unknown card instance v2 trace record type")
        if current_id is not None:
            raise ValueError("card instance v2 scan is missing END")
        for scan in scans:
            self._update_viewer_aliases(scan.observations)
            latest_by_coordinate: dict[
                tuple[int, int, int], CardInstanceObservation
            ] = {}
            seen_card_ids: set[int] = set()
            for observation in scan.observations:
                self._validate_authority(observation)
                if observation.card_id in seen_card_ids:
                    raise ValueError("card instance v2 scan repeats a card_id")
                seen_card_ids.add(observation.card_id)
                coordinate = (
                    observation.controller,
                    observation.location,
                    observation.sequence,
                )
                if coordinate in latest_by_coordinate:
                    raise ValueError("card instance v2 scan repeats a core coordinate")
                self._record_transition(
                    self._latest_by_card_id.get(observation.card_id),
                    observation,
                    scan=scan,
                )
                latest_by_coordinate[coordinate] = observation
                self._latest_by_card_id[observation.card_id] = observation
            self._latest_by_coordinate = latest_by_coordinate
            self._scans.append(scan)
            self._last_scan_id = scan.scan_id
            if scan.observations:
                self._last_observation_index = scan.observations[-1].observation_index
        return tuple(scans)

    def _resolve(self, raw: Mapping[str, Any]) -> CardInstanceObservation:
        coordinate = tuple(raw.get(field) for field in ("controller", "location", "sequence"))
        if any(
            not isinstance(value, int) or isinstance(value, bool)
            for value in coordinate
        ):
            raise ValueError("card candidate has an invalid core location")
        observation = self._latest_by_coordinate.get(coordinate)
        if observation is None:
            raise ValueError(
                "card instance v2 candidate has no authority observation for "
                f"{coordinate[0]}:{coordinate[1]}:{coordinate[2]}"
            )
        public_card_id = raw.get("public_card_id")
        if public_card_id not in (None, 0, observation.card_code):
            raise ValueError("card instance v2 authority code differs from Request")
        return observation

    def synchronize_request(
        self,
        logs: Sequence[CoreLog],
        request: DecisionRequest,
        *,
        expected_scan_label: str,
        message_types: Sequence[int] = (),
    ) -> DecisionRequest:
        scans = self.consume(logs)
        draw_observed = 90 in message_types
        for index in range(
            self._last_synchronized_transition,
            len(self._movement_transitions),
        ):
            transition = self._movement_transitions[index]
            if transition["movement_kind"] == "deck_to_hand_pending":
                transition["movement_kind"] = "draw" if draw_observed else "search"
        self._last_synchronized_transition = len(self._movement_transitions)
        shuffle_names = {
            32: "shuffle_deck",
            33: "shuffle_hand",
            36: "shuffle_set_card",
            39: "shuffle_extra",
        }
        for message_type in message_types:
            if message_type in shuffle_names:
                self._shuffle_boundaries.append(
                    {
                        "message_type": message_type,
                        "mutation": shuffle_names[message_type],
                        "request_id": request.request_id,
                        "scan_id": self._last_scan_id,
                    }
                )
        has_card_candidates = any(
            isinstance(candidate.card_ref, Mapping) for candidate in request.candidates
        )
        if has_card_candidates:
            if not scans or scans[-1].label != expected_scan_label:
                raise ValueError(
                    "card instance v2 requires the expected complete Request-boundary "
                    f"scan; request_type={request.request_type!r} "
                    f"request_id={request.request_id!r}"
                )
            self._request_boundaries.append(
                {
                    "mode": "complete_scan_in_request_batch",
                    "request_id": request.request_id,
                    "request_type": request.request_type,
                    "scan_id": self._last_scan_id,
                }
            )
        candidates: list[Candidate] = []
        for candidate in request.candidates:
            if not isinstance(candidate.card_ref, Mapping):
                candidates.append(candidate)
                continue
            observation = self._resolve(candidate.card_ref)
            card_ref = dict(candidate.card_ref)
            card_ref["instance_id"] = observation.instance_id
            card_ref["owner"] = observation.owner
            candidates.append(replace(candidate, card_ref=card_ref))
        return replace(request, candidates=tuple(candidates))

    def enrich_snapshot(self, snapshot: Any) -> Any:
        from ygo_effect_dsl.engine.bridge.ocgcore.state import (
            CARD_INSTANCE_SNAPSHOT_SCHEMA_VERSION,
        )

        zones: list[dict[str, Any]] = []
        for zone in snapshot.zones:
            cards: list[dict[str, Any] | None] = []
            for card in zone["cards"]:
                if card is None:
                    cards.append(None)
                    continue
                coordinate = (
                    int(card["controller"]),
                    int(card["location"]),
                    int(card["slot"]),
                )
                observation = self._latest_by_coordinate.get(coordinate)
                if observation is None:
                    history_matches = [
                        item
                        for item in self._latest_by_card_id.values()
                        if (
                            item.controller,
                            item.location,
                            item.sequence,
                        )
                        == coordinate
                    ]
                    if len(history_matches) == 1:
                        observation = history_matches[0]
                if observation is None:
                    raise ValueError(
                        "card instance v2 snapshot card has no authority observation for "
                        f"{coordinate[0]}:{coordinate[1]}:{coordinate[2]}"
                    )
                query_fields = {
                    field.get("name"): field.get("value")
                    for field in card.get("fields", [])
                    if isinstance(field, Mapping)
                }
                if query_fields.get("code") != observation.card_code:
                    raise ValueError("card instance v2 snapshot code differs from authority")
                if query_fields.get("owner") != observation.owner:
                    raise ValueError("card instance v2 snapshot owner differs from authority")
                enriched = dict(card)
                enriched["owner"] = observation.owner
                enriched["persistent_instance_id"] = observation.instance_id
                enriched["player_view_instance_ids"] = {
                    str(viewer): self._viewer_alias[(viewer, observation.card_id)]
                    for viewer in (0, 1)
                    if (viewer, observation.card_id) in self._viewer_alias
                    and self._viewer_visible.get((viewer, observation.card_id)) is True
                }
                cards.append(enriched)
            zones.append({**dict(zone), "cards": tuple(cards)})
        pending_request = snapshot.pending_request
        if pending_request is not None:
            pending_request = dict(pending_request)
            if "request_observation_id" not in pending_request:
                observation_identity = {
                    key: value
                    for key, value in pending_request.items()
                    if key != "request_signature"
                }
                pending_request["request_observation_id"] = stable_digest(
                    observation_identity,
                    prefix="requestview_",
                )
        return replace(
            snapshot,
            zones=tuple(zones),
            pending_request=pending_request,
            card_instance_schema_version=CARD_INSTANCE_SNAPSHOT_SCHEMA_VERSION,
        )

    def provenance_document(self) -> dict[str, Any]:
        latest = sorted(
            self._latest_by_card_id.values(),
            key=lambda item: item.instance_id,
        )
        transitions = []
        for transition in self._movement_transitions:
            canonical = to_canonical_data(transition)
            transitions.append(
                {
                    **canonical,
                    "transition_id": stable_digest(canonical, prefix="cardmove_"),
                }
            )
        identity = to_canonical_data(
            {
                "authority": CARD_INSTANCE_AUTHORITY,
                "instances": [
                    {
                        "card_code": item.card_code,
                        "instance_id": item.instance_id,
                        "is_token": item.is_token,
                        "owner": item.owner,
                    }
                    for item in latest
                ],
                "knowledge_policy": {
                    "hidden_identity": "omitted",
                    "opponent_reidentification": "viewer_scoped_new_alias_after_knowledge_loss",
                    "owner_identity": "persistent_instance_id",
                },
                "movement_transitions": transitions,
                "request_boundaries": self._request_boundaries,
                "scan_boundaries": [scan.to_public_dict() for scan in self._scans],
                "schema_version": CARD_INSTANCE_PROVENANCE_V2_SCHEMA_VERSION,
                "scope_id": self.scope_id,
                "shuffle_boundaries": self._shuffle_boundaries,
            }
        )
        return {
            **identity,
            "provenance_id": stable_digest(identity, prefix="cardprov_"),
        }


def filter_card_instance_trace_logs(logs: Sequence[CoreLog]) -> tuple[CoreLog, ...]:
    return tuple(
        log
        for log in logs
        if not log.message.startswith(CARD_INSTANCE_TRACE_V2_LOG_PREFIX)
    )


def assert_public_card_instance_document(value: Any, *, path: str = "$") -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            if key == "card_id":
                raise ValueError(f"{path}.card_id exposes private ocgcore authority")
            assert_public_card_instance_document(child, path=f"{path}.{key}")
        return
    if isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            assert_public_card_instance_document(child, path=f"{path}[{index}]")
        return
    if isinstance(value, str) and CARD_INSTANCE_TRACE_V2_LOG_PREFIX in value:
        raise ValueError(f"{path} exposes private card-instance instrumentation")


class CardInstanceAuditedScriptProvider:
    """Reject source paths that bypass the incremental v2 registry."""

    def __init__(self, base: Any) -> None:
        self.base = base

    @property
    def script_resolution_profile_id(self) -> str:
        return str(
            getattr(
                self.base,
                "script_resolution_profile_id",
                "custom-script-provider-v1",
            )
        )

    def get_script(self, name: str) -> bytes:
        return self.resolve_script(name).content

    def resolve_script(self, name: str) -> ResolvedScript:
        resolved = resolve_script(self.base, name)
        script = resolved.content
        is_card_script = re.fullmatch(r"c\d+\.lua", name) is not None
        if is_card_script and b"Debug.ReloadFieldBegin" in script:
            raise ValueError(
                f"card instance v2 rejects unsupported Debug.ReloadFieldBegin in {name!r}"
            )
        return resolved
