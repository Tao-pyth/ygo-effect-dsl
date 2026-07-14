from __future__ import annotations

import json
from pathlib import Path

import pytest

from ygo_effect_dsl.engine.bridge.ocgcore import (
    DIRECT_RANDOM_TRACE_LUA_SOURCE,
    DIRECT_RANDOM_TRACE_TRANSPORT,
    direct_random_trace_metadata,
)
from ygo_effect_dsl.engine.canonical import stable_digest
from ygo_effect_dsl.external.ocgcore import (
    OcgcoreBootstrapError,
    verify_ocgcore,
    verify_ocgcore_assets,
)
from ygo_effect_dsl.spikes.direct_random_trace_evidence import (
    build_direct_random_trace_evidence,
)


EVIDENCE = (
    Path(__file__).parents[1]
    / "docs"
    / "ocgcore"
    / "evidence"
    / "direct_random_trace.json"
)
TRANSPORT_EVIDENCE = (
    Path(__file__).parents[1]
    / "docs"
    / "ocgcore"
    / "evidence"
    / "direct_random_transport.json"
)


def test_direct_random_wrapper_calls_original_once_before_trace_packets() -> None:
    source = DIRECT_RANDOM_TRACE_LUA_SOURCE.decode("ascii")

    assert source.count("original_get_random_number(...)") == 1
    assert source.index("original_get_random_number(...)") < source.index(
        "Debug.Message("
    )
    assert direct_random_trace_metadata(enabled=True)["instrumentation_id"] != (
        direct_random_trace_metadata(enabled=False)["instrumentation_id"]
    )


def test_checked_direct_random_evidence_satisfies_issue_acceptance() -> None:
    evidence = json.loads(EVIDENCE.read_text(encoding="utf-8"))

    assert all(evidence["checks"].values())
    events = [
        event
        for event in evidence["instrumented"]["random_events"]
        if event["kind"] == "direct_lua_random"
    ]
    assert len(events) == 6
    assert events[0]["outcome"] == {
        "draw_index": 1,
        "maximum": 4,
        "minimum": 0,
        "result": 0,
    }
    assert events[0]["transport"] == DIRECT_RANDOM_TRACE_TRANSPORT
    assert evidence["fixture"]["card_code"] == 97268402
    assert evidence["fixture"]["card_data_source"] == "pinned_babelcdb_record"
    assert evidence["fixture"]["synthetic_card_data_codes"] == []


def test_checked_transport_audit_has_valid_identity_and_safe_decision() -> None:
    evidence = json.loads(TRANSPORT_EVIDENCE.read_text(encoding="utf-8"))
    evidence_id = evidence.pop("evidence_id")

    assert evidence_id == stable_digest(evidence, prefix="rngtransportev_")
    assert all(evidence["checks"].values())
    assert evidence["transport"] == DIRECT_RANDOM_TRACE_TRANSPORT
    assert evidence["supported_edopro"]["commit"] == (
        "650ec7b2273f60733b178d238cf6fec46722d8b4"
    )
    assert evidence["upstream_core_observation"][
        "dedicated_random_hook_found"
    ] is False


def test_direct_random_evidence_matches_fresh_real_core_runs() -> None:
    try:
        verify_ocgcore()
        verify_ocgcore_assets()
    except (OcgcoreBootstrapError, OSError) as exc:
        pytest.skip(f"pinned local ocgcore runtime/assets are unavailable: {exc}")

    expected = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    assert build_direct_random_trace_evidence() == expected
