from __future__ import annotations

import ctypes
from dataclasses import dataclass
from enum import Enum, IntEnum
from typing import Any

from ygo_effect_dsl.engine.bridge.ocgcore.errors import OcgcoreArchitectureError


API_VERSION = (11, 0)
MAX_NATIVE_BUFFER_BYTES = 1024 * 1024
MAX_RESPONSE_BYTES = 1024 * 1024


class DuelCreationStatus(IntEnum):
    SUCCESS = 0
    NO_OUTPUT = 1
    NOT_CREATED = 2
    NULL_DATA_READER = 3
    NULL_SCRIPT_READER = 4


class DuelProcessStatus(IntEnum):
    END = 0
    AWAITING = 1
    CONTINUE = 2


class LogType(IntEnum):
    ERROR = 0
    FROM_SCRIPT = 1
    FOR_DEBUG = 2
    UNDEFINED = 3


class LibraryState(str, Enum):
    DISCOVERED = "discovered"
    VERSION_CHECKED = "version_checked"
    CLOSED = "closed"


class DuelState(str, Enum):
    VERSION_CHECKED = "version_checked"
    DUEL_CREATED = "duel_created"
    CARDS_LOADED = "cards_loaded"
    STARTED = "started"
    PROCESSING = "processing"
    AWAITING_RESPONSE = "awaiting_response"
    ENDED = "ended"
    FAILED = "failed"
    DESTROYED = "destroyed"


class OCGPlayer(ctypes.Structure):
    _fields_ = [
        ("startingLP", ctypes.c_uint32),
        ("startingDrawCount", ctypes.c_uint32),
        ("drawCountPerTurn", ctypes.c_uint32),
    ]


class OCGCardData(ctypes.Structure):
    _fields_ = [
        ("code", ctypes.c_uint32),
        ("alias", ctypes.c_uint32),
        ("setcodes", ctypes.POINTER(ctypes.c_uint16)),
        ("type", ctypes.c_uint32),
        ("level", ctypes.c_uint32),
        ("attribute", ctypes.c_uint32),
        ("race", ctypes.c_uint64),
        ("attack", ctypes.c_int32),
        ("defense", ctypes.c_int32),
        ("lscale", ctypes.c_uint32),
        ("rscale", ctypes.c_uint32),
        ("link_marker", ctypes.c_uint32),
    ]


DataReader = ctypes.CFUNCTYPE(
    None, ctypes.c_void_p, ctypes.c_uint32, ctypes.POINTER(OCGCardData)
)
ScriptReader = ctypes.CFUNCTYPE(
    ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_char_p
)
LogHandler = ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int)
DataReaderDone = ctypes.CFUNCTYPE(
    None, ctypes.c_void_p, ctypes.POINTER(OCGCardData)
)


class OCGDuelOptions(ctypes.Structure):
    _fields_ = [
        ("seed", ctypes.c_uint64 * 4),
        ("flags", ctypes.c_uint64),
        ("team1", OCGPlayer),
        ("team2", OCGPlayer),
        ("cardReader", DataReader),
        ("payload1", ctypes.c_void_p),
        ("scriptReader", ScriptReader),
        ("payload2", ctypes.c_void_p),
        ("logHandler", LogHandler),
        ("payload3", ctypes.c_void_p),
        ("cardReaderDone", DataReaderDone),
        ("payload4", ctypes.c_void_p),
        ("enableUnsafeLibraries", ctypes.c_uint8),
    ]


class OCGNewCardInfo(ctypes.Structure):
    _fields_ = [
        ("team", ctypes.c_uint8),
        ("duelist", ctypes.c_uint8),
        ("code", ctypes.c_uint32),
        ("con", ctypes.c_uint8),
        ("loc", ctypes.c_uint32),
        ("seq", ctypes.c_uint32),
        ("pos", ctypes.c_uint32),
    ]


class OCGQueryInfo(ctypes.Structure):
    _fields_ = [
        ("flags", ctypes.c_uint32),
        ("con", ctypes.c_uint8),
        ("loc", ctypes.c_uint32),
        ("seq", ctypes.c_uint32),
        ("overlay_seq", ctypes.c_uint32),
    ]


EXPECTED_LAYOUT = {
    "pointer_width": 8,
    "OCGPlayer": 12,
    "OCGCardData": 64,
    "OCGDuelOptions": 136,
    "OCGNewCardInfo": 24,
    "OCGQueryInfo": 20,
}


def native_layout() -> dict[str, int]:
    return {
        "pointer_width": ctypes.sizeof(ctypes.c_void_p),
        "OCGPlayer": ctypes.sizeof(OCGPlayer),
        "OCGCardData": ctypes.sizeof(OCGCardData),
        "OCGDuelOptions": ctypes.sizeof(OCGDuelOptions),
        "OCGNewCardInfo": ctypes.sizeof(OCGNewCardInfo),
        "OCGQueryInfo": ctypes.sizeof(OCGQueryInfo),
    }


def validate_native_layout() -> None:
    observed = native_layout()
    if observed != EXPECTED_LAYOUT:
        raise OcgcoreArchitectureError(
            f"ocgcore C layout mismatch: expected {EXPECTED_LAYOUT}, got {observed}"
        )


def _unsigned(value: int, bits: int, field: str) -> int:
    if not 0 <= value < (1 << bits):
        raise ValueError(f"{field} must fit uint{bits}")
    return value


def _signed(value: int, bits: int, field: str) -> int:
    lower = -(1 << (bits - 1))
    upper = (1 << (bits - 1)) - 1
    if not lower <= value <= upper:
        raise ValueError(f"{field} must fit int{bits}")
    return value


@dataclass(frozen=True)
class PlayerConfig:
    starting_lp: int = 8000
    starting_draw_count: int = 5
    draw_count_per_turn: int = 1

    def to_native(self) -> OCGPlayer:
        return OCGPlayer(
            _unsigned(self.starting_lp, 32, "starting_lp"),
            _unsigned(self.starting_draw_count, 32, "starting_draw_count"),
            _unsigned(self.draw_count_per_turn, 32, "draw_count_per_turn"),
        )


@dataclass(frozen=True)
class DuelConfig:
    seed: tuple[int, int, int, int]
    flags: int = 0
    team1: PlayerConfig = PlayerConfig()
    team2: PlayerConfig = PlayerConfig()
    enable_unsafe_libraries: bool = False

    def validate(self) -> None:
        if len(self.seed) != 4:
            raise ValueError("seed must contain four uint64 values")
        for index, value in enumerate(self.seed):
            _unsigned(value, 64, f"seed[{index}]")
        _unsigned(self.flags, 64, "flags")
        if self.enable_unsafe_libraries:
            raise ValueError("unsafe Lua libraries are disabled by the bridge contract")


@dataclass(frozen=True)
class CardRecord:
    code: int
    alias: int = 0
    setcodes: tuple[int, ...] = ()
    type: int = 0
    level: int = 0
    attribute: int = 0
    race: int = 0
    attack: int = 0
    defense: int = 0
    lscale: int = 0
    rscale: int = 0
    link_marker: int = 0

    def validate(self) -> None:
        for field in ("code", "alias", "type", "level", "attribute", "lscale", "rscale", "link_marker"):
            _unsigned(getattr(self, field), 32, field)
        _unsigned(self.race, 64, "race")
        _signed(self.attack, 32, "attack")
        _signed(self.defense, 32, "defense")
        for index, setcode in enumerate(self.setcodes):
            if setcode == 0:
                raise ValueError("setcodes must not contain the zero terminator")
            _unsigned(setcode, 16, f"setcodes[{index}]")


@dataclass(frozen=True)
class NewCard:
    team: int
    duelist: int
    code: int
    controller: int
    location: int
    sequence: int
    position: int

    def to_native(self) -> OCGNewCardInfo:
        return OCGNewCardInfo(
            _unsigned(self.team, 8, "team"),
            _unsigned(self.duelist, 8, "duelist"),
            _unsigned(self.code, 32, "code"),
            _unsigned(self.controller, 8, "controller"),
            _unsigned(self.location, 32, "location"),
            _unsigned(self.sequence, 32, "sequence"),
            _unsigned(self.position, 32, "position"),
        )


@dataclass(frozen=True)
class Query:
    flags: int
    controller: int
    location: int
    sequence: int = 0
    overlay_sequence: int = 0

    def to_native(self) -> OCGQueryInfo:
        return OCGQueryInfo(
            _unsigned(self.flags, 32, "flags"),
            _unsigned(self.controller, 8, "controller"),
            _unsigned(self.location, 32, "location"),
            _unsigned(self.sequence, 32, "sequence"),
            _unsigned(self.overlay_sequence, 32, "overlay_sequence"),
        )


@dataclass(frozen=True)
class Diagnostic:
    severity: str
    category: str
    message: str
    context: dict[str, Any]


@dataclass(frozen=True)
class CoreLog:
    sequence: int
    log_type: LogType
    message: str


@dataclass(frozen=True)
class ProcessBatch:
    status: DuelProcessStatus
    messages: tuple[bytes, ...]
    steps: int
    elapsed_seconds: float
    logs: tuple[CoreLog, ...] = ()
