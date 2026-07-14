from __future__ import annotations

from ygo_effect_dsl.engine.bridge.ocgcore import (
    MESSAGE_COMPATIBILITY,
    OPERATION_COMPATIBILITY,
    OcgcoreMessageDecoder,
    compatibility_report,
)
from ygo_effect_dsl.engine.bridge.ocgcore.protocol import MessageType


def test_every_known_selection_message_has_explicit_compatibility_status() -> None:
    assert set(MESSAGE_COMPATIBILITY) == set(MessageType)
    supported = set(OcgcoreMessageDecoder().supported_message_types)

    for message_type, case in MESSAGE_COMPATIBILITY.items():
        if int(message_type) in supported:
            assert case.status in {"real_core", "codec_only"}
        else:
            assert case.status == "unsupported"
            assert "UnsupportedBridgeMessageError" in case.notes


def test_issue_54_operation_categories_are_classified_without_overclaiming() -> None:
    cases = {case.category: case for case in OPERATION_COMPATIBILITY}
    assert set(cases) == {
        "normal_summon",
        "special_summon",
        "search",
        "draw",
        "send_to_graveyard",
        "banish",
        "targeting_effect",
        "non_targeting_effect",
        "cost",
        "chain",
        "mandatory_optional_effect",
        "simultaneous_trigger",
        "continuous_replacement_effect",
        "special_summon_method",
    }
    assert cases["normal_summon"].status == "real_core"
    assert cases["chain"].status == "real_core"
    assert cases["search"].status == "unsupported"
    assert cases["special_summon_method"].status == "unsupported"


def test_compatibility_report_is_stable_and_machine_readable() -> None:
    report = compatibility_report()
    assert report["schema_version"] == "ocgcore-v11-compatibility-v1"
    assert report["message_types"]["11"]["status"] == "real_core"
    assert report["message_types"]["12"]["status"] == "real_core"
    assert report["message_types"]["14"]["status"] == "real_core"
    assert report["message_types"]["15"]["status"] == "real_core"
    assert report["message_types"]["20"]["status"] == "codec_only"
    assert report["message_types"]["143"]["category"] == "announce_number"


def test_no_known_api_v11_decision_message_is_left_unsupported() -> None:
    assert not {
        message_type
        for message_type, case in MESSAGE_COMPATIBILITY.items()
        if case.status == "unsupported"
    }
