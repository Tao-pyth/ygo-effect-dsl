from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ygo_effect_dsl.engine.bridge.ocgcore.protocol import (
    KNOWN_MESSAGE_TYPES,
    MESSAGE_REGISTRY_VERSION,
    NON_DECISION_MESSAGE_TYPES,
    SELECTION_MESSAGE_TYPES,
    UNSUPPORTED_MESSAGE_TYPES,
    MessageType,
)


COMPATIBILITY_SCHEMA_VERSION = "ocgcore-v11-compatibility-v2"
COMPATIBILITY_STATUSES = frozenset(
    {"real_core", "codec_only", "state_observed", "unsupported"}
)


@dataclass(frozen=True)
class CompatibilityCase:
    category: str
    status: str
    evidence: tuple[str, ...]
    notes: str

    def __post_init__(self) -> None:
        if self.status not in COMPATIBILITY_STATUSES:
            raise ValueError(f"unsupported compatibility status {self.status!r}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "category": self.category,
            "evidence": list(self.evidence),
            "notes": self.notes,
            "status": self.status,
        }


MESSAGE_COMPATIBILITY = {
    MessageType.SELECT_IDLE_COMMAND: CompatibilityCase(
        "select_idle_command",
        "real_core",
        ("tests/test_real_core_prototype.py", "tests/test_ocgcore_protocol.py"),
        "Normal summon and end-turn controls are decoded from a real fixed-hand duel.",
    ),
    MessageType.SELECT_YES_NO: CompatibilityCase(
        "select_yes_no",
        "codec_only",
        ("tests/golden/ocgcore_v11/codec_cases.json",),
        "Golden decode/encode coverage; no end-to-end card scenario yet.",
    ),
    MessageType.SELECT_OPTION: CompatibilityCase(
        "select_option",
        "real_core",
        (
            "examples/prototype/real_core_action_aggregation.route.yaml",
            "tests/test_action_aggregation.py",
        ),
        "An option inside a trigger-effect activation setup is replayed and grouped.",
    ),
    MessageType.SELECT_CARD: CompatibilityCase(
        "select_card",
        "real_core",
        (
            "examples/prototype/real_core_action_aggregation.route.yaml",
            "examples/prototype/real_core_effect_veiler_interrupted.route.yaml",
        ),
        "Cost and target selections are replayed; ordered/cancelable variants remain codec-only.",
    ),
    MessageType.SELECT_CHAIN: CompatibilityCase(
        "select_chain",
        "real_core",
        ("tests/test_real_core_prototype.py", "tests/test_ocgcore_protocol.py"),
        "Four optional empty-chain passes are replayed through the real core.",
    ),
    MessageType.SELECT_PLACE: CompatibilityCase(
        "select_place",
        "real_core",
        ("tests/test_real_core_prototype.py", "tests/test_ocgcore_protocol.py"),
        "Monster-zone selection is replayed through the real core.",
    ),
    MessageType.SELECT_POSITION: CompatibilityCase(
        "select_position",
        "codec_only",
        ("tests/golden/ocgcore_v11/codec_cases.json",),
        "Golden decode/encode coverage; no end-to-end card scenario yet.",
    ),
    MessageType.SELECT_BATTLE_COMMAND: CompatibilityCase(
        "select_battle_command",
        "codec_only",
        ("tests/test_ocgcore_protocol.py",),
        "Activation, attack, Main Phase 2, and End Phase responses are covered.",
    ),
    MessageType.SELECT_EFFECT_YES_NO: CompatibilityCase(
        "select_effect_yes_no",
        "real_core",
        ("examples/prototype/real_core_action_aggregation.route.yaml",),
        "The affirmative branch activates a pinned optional trigger effect.",
    ),
    MessageType.SELECT_TRIBUTE: CompatibilityCase(
        "select_tribute",
        "codec_only",
        ("tests/test_ocgcore_protocol.py",),
        "Weighted tribute value and card-index response are covered.",
    ),
    MessageType.SELECT_COUNTER: CompatibilityCase(
        "select_counter",
        "codec_only",
        ("tests/test_ocgcore_protocol.py",),
        "Per-card int16 allocation and exact total validation are covered.",
    ),
    MessageType.SELECT_SUM: CompatibilityCase(
        "select_sum",
        "codec_only",
        ("tests/test_ocgcore_protocol.py",),
        "Exact/threshold sum constraints and card-index response are covered.",
    ),
    MessageType.SELECT_DISABLED_FIELD: CompatibilityCase(
        "select_disabled_field",
        "codec_only",
        ("tests/test_ocgcore_protocol.py",),
        "Disabled-field zone selection reuses the validated place codec.",
    ),
    MessageType.SELECT_UNSELECT_CARD: CompatibilityCase(
        "select_unselect_card",
        "codec_only",
        ("tests/test_ocgcore_protocol.py",),
        "Select/unselect toggle and finish response are covered.",
    ),
    MessageType.SORT_CHAIN: CompatibilityCase(
        "sort_chain",
        "codec_only",
        ("tests/test_ocgcore_protocol.py",),
        "Original-card-index to selected-order response mapping is covered.",
    ),
    MessageType.SORT_CARD: CompatibilityCase(
        "sort_card",
        "codec_only",
        ("tests/test_ocgcore_protocol.py",),
        "Original-card-index to selected-order response mapping is covered.",
    ),
    MessageType.ROCK_PAPER_SCISSORS: CompatibilityCase(
        "rock_paper_scissors",
        "codec_only",
        ("tests/test_ocgcore_protocol.py",),
        "The three finite hand-sign responses are covered.",
    ),
    MessageType.ANNOUNCE_RACE: CompatibilityCase(
        "announce_race",
        "codec_only",
        ("tests/test_ocgcore_protocol.py",),
        "64-bit available-mask and exact selected-bit count are covered.",
    ),
    MessageType.ANNOUNCE_ATTRIBUTE: CompatibilityCase(
        "announce_attribute",
        "codec_only",
        ("tests/test_ocgcore_protocol.py",),
        "32-bit available-mask and exact selected-bit count are covered.",
    ),
    MessageType.ANNOUNCE_CARD: CompatibilityCase(
        "announce_card",
        "codec_only",
        ("tests/test_ocgcore_protocol.py",),
        "Free card-code input is encoded; declarability remains core-owned.",
    ),
    MessageType.ANNOUNCE_NUMBER: CompatibilityCase(
        "announce_number",
        "codec_only",
        ("tests/test_ocgcore_protocol.py",),
        "Finite number-option index responses are covered.",
    ),
}


OPERATION_COMPATIBILITY = (
    CompatibilityCase(
        "normal_summon",
        "real_core",
        ("examples/prototype/real_core_effect_veiler.route.yaml",),
        "Fixed hand to legal-stop replay is deterministic in a fresh worker.",
    ),
    CompatibilityCase(
        "special_summon",
        "codec_only",
        ("tests/test_ocgcore_protocol.py",),
        "Idle-command candidate is modeled; summon continuation is not covered.",
    ),
    CompatibilityCase(
        "search",
        "unsupported",
        (),
        "No real card search-effect route exists.",
    ),
    CompatibilityCase(
        "draw",
        "state_observed",
        ("tests/test_ocgcore_state.py",),
        "Hand/deck counts are queryable; draw effect replay is not covered.",
    ),
    CompatibilityCase(
        "send_to_graveyard",
        "real_core",
        ("examples/prototype/real_core_action_aggregation.route.yaml",),
        "A selected hand card moves to the graveyard with REASON_COST.",
    ),
    CompatibilityCase(
        "banish",
        "state_observed",
        ("tests/test_ocgcore_state.py",),
        "Banished zone is queryable; effect replay is not covered.",
    ),
    CompatibilityCase(
        "targeting_effect",
        "real_core",
        ("examples/prototype/real_core_action_aggregation.route.yaml",),
        "A pinned effect emits HINTMSG_TARGET and a real card-selection continuation.",
    ),
    CompatibilityCase(
        "non_targeting_effect",
        "unsupported",
        (),
        "No representative real route exists.",
    ),
    CompatibilityCase(
        "cost",
        "real_core",
        ("examples/prototype/real_core_action_aggregation.route.yaml",),
        "Selected-card MSG_MOVE evidence includes the REASON_COST bit.",
    ),
    CompatibilityCase(
        "chain",
        "real_core",
        (
            "examples/prototype/real_core_action_aggregation.route.yaml",
            "examples/prototype/real_core_effect_veiler_interrupted.route.yaml",
        ),
        "Optional pass, effect activation setup, MSG_CHAINED, and resolution are replayed.",
    ),
    CompatibilityCase(
        "mandatory_optional_effect",
        "real_core",
        ("examples/prototype/real_core_action_aggregation.route.yaml",),
        "An optional summon trigger is accepted through SELECT_EFFECT_YES_NO; mandatory remains codec-only.",
    ),
    CompatibilityCase(
        "simultaneous_trigger",
        "unsupported",
        (),
        "No decoder/replay fixture exists.",
    ),
    CompatibilityCase(
        "continuous_replacement_effect",
        "unsupported",
        (),
        "State observation exists, but behavior coverage does not.",
    ),
    CompatibilityCase(
        "special_summon_method",
        "unsupported",
        (),
        "Fusion/Synchro/Xyz/Link-specific request sequences are not covered.",
    ),
)


def compatibility_report() -> dict[str, Any]:
    return {
        "message_registry": {
            "decision_message_types": sorted(SELECTION_MESSAGE_TYPES),
            "known_message_types": sorted(KNOWN_MESSAGE_TYPES),
            "non_decision_message_types": sorted(NON_DECISION_MESSAGE_TYPES),
            "schema_version": MESSAGE_REGISTRY_VERSION,
            "unknown_message_policy": "fail_close",
            "unsupported_message_types": sorted(UNSUPPORTED_MESSAGE_TYPES),
        },
        "schema_version": COMPATIBILITY_SCHEMA_VERSION,
        "message_types": {
            str(int(message_type)): case.to_dict()
            for message_type, case in sorted(
                MESSAGE_COMPATIBILITY.items(), key=lambda item: int(item[0])
            )
        },
        "operations": [case.to_dict() for case in OPERATION_COMPATIBILITY],
    }
