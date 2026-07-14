from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

import pytest

from ygo_effect_dsl.engine.bridge.ocgcore import (
    CROSS_CHANNEL_ORDERING_SCHEMA_VERSION,
    assert_cross_channel_ordering_evidence,
    build_cross_channel_ordering_evidence,
)
from ygo_effect_dsl.engine.canonical import stable_digest
from ygo_effect_dsl.external.ocgcore import (
    OcgcoreBootstrapError,
    verify_ocgcore,
    verify_ocgcore_assets,
)
from ygo_effect_dsl.spikes.cross_channel_ordering_audit import (
    CROSS_CHANNEL_EVIDENCE_SCHEMA_VERSION,
    FIXTURE_CARD_CODE,
    UPSTREAM_CORE_COMMIT,
    build_cross_channel_ordering_audit,
)


EVIDENCE = (
    Path(__file__).parents[1]
    / "docs"
    / "ocgcore"
    / "evidence"
    / "cross_channel_ordering.json"
)
PINNED_CORE_COMMIT = "158aebe758be3c46249c75d602e3f16d63d2ef31"


def _evidence() -> dict[str, object]:
    return json.loads(EVIDENCE.read_text(encoding="utf-8"))


def test_checked_cross_channel_evidence_has_valid_identity() -> None:
    evidence = _evidence()
    evidence_id = evidence.pop("evidence_id")

    assert evidence_id == stable_digest(evidence, prefix="crossordev_")
    assert evidence["schema_version"] == CROSS_CHANNEL_EVIDENCE_SCHEMA_VERSION
    assert all(evidence["checks"].values())
    assert evidence["decision"] == {
        "actual_cross_channel_chronology": "unavailable_without_core_patch",
        "canonical_storage_order": [
            "script_log_callback_by_log_sequence",
            "core_message_buffer_by_frame_index",
        ],
        "custom_core_patch": False,
        "replay_trace_schema_changed": False,
    }


def test_checked_fixture_proves_both_channels_in_one_native_call() -> None:
    evidence = _evidence()
    mixed = evidence["mixed_process_batch"]
    ordering = mixed["ordering"]

    assert evidence["fixture"]["card_code"] == FIXTURE_CARD_CODE
    assert mixed["native_process_call_count"] == 1
    assert mixed["native_calls_until_request"] >= 1
    assert mixed["native_call_index"] < mixed["native_calls_until_request"]
    assert [event["kind"] for event in mixed["random_events"]] == [
        "direct_lua_random",
        "toss_coin",
    ]
    assert ordering["schema_version"] == CROSS_CHANNEL_ORDERING_SCHEMA_VERSION
    assert ordering["scope"] == "single_ocg_duel_process_call"
    assert ordering["native_process_call_count"] == 1
    assert ordering["cross_domain_chronology"] == "unavailable"
    assert ordering["semantics"] == (
        "canonical_storage_order_is_not_observed_emission_order"
    )
    assert [domain["domain"] for domain in ordering["domains"]] == [
        "script_log_callback",
        "core_message_buffer",
    ]


def test_checked_source_audit_covers_pinned_and_current_upstream() -> None:
    source = _evidence()["source_audit"]

    assert source["pinned"]["commit"] == PINNED_CORE_COMMIT
    assert source["upstream"]["commit"] == UPSTREAM_CORE_COMMIT
    for audit in source.values():
        assert audit["status"] == "no_public_cross_channel_chronology"
        assert all(audit["checks"].values())
        assert len(audit["files"]) == 5


def test_cross_channel_ordering_validator_fails_closed() -> None:
    mixed = _evidence()["mixed_process_batch"]
    ordering = mixed["ordering"]
    events = mixed["random_events"]

    assert_cross_channel_ordering_evidence(
        ordering,
        events,
        native_process_call_count=1,
    )

    tampered = deepcopy(ordering)
    tampered["cross_domain_chronology"] = "observed"
    with pytest.raises(ValueError, match="evidence mismatch"):
        assert_cross_channel_ordering_evidence(
            tampered,
            events,
            native_process_call_count=1,
        )
    with pytest.raises(ValueError, match="exactly one native process call"):
        build_cross_channel_ordering_evidence(
            events,
            native_process_call_count=2,
        )
    with pytest.raises(ValueError, match="requires both domains"):
        build_cross_channel_ordering_evidence(
            [events[0]],
            native_process_call_count=1,
        )


def test_cross_channel_evidence_matches_fresh_real_core_run() -> None:
    try:
        verify_ocgcore()
        verify_ocgcore_assets()
    except (OcgcoreBootstrapError, OSError) as exc:
        pytest.skip(f"pinned local ocgcore runtime/assets are unavailable: {exc}")

    assert build_cross_channel_ordering_audit() == _evidence()
