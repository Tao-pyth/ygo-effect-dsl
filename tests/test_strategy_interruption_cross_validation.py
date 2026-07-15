from __future__ import annotations

from copy import deepcopy
import json

import pytest

from ygo_effect_dsl.engine.canonical import stable_digest
from ygo_effect_dsl.experiment import cross_validation as cross_module
from ygo_effect_dsl.experiment.cross_validation import (
    STRATEGY_INTERRUPTION_LINEAGE_SCHEMA_VERSION,
    STRATEGY_INTERRUPTION_MATRIX_SCHEMA_VERSION,
    StrategyInterruptionCrossValidationError,
    build_route_semantic_observation,
    build_strategy_interruption_lineage,
    write_strategy_interruption_cross_validation,
)


DECK_HASH = "a" * 64


def _event(step: int, *, kind: str, candidate_id: str, before: str, after: str) -> dict:
    request_signature = f"req_{step}"
    return {
        "action": {
            "kind": kind,
            "request_signature": request_signature,
            "selections": [{"candidate_id": candidate_id}],
        },
        "chain_index": 0,
        "core_response": {"selected_candidate_ids": [candidate_id]},
        "request": {
            "candidates": [
                {"candidate_id": "control:pass"},
                {"candidate_id": "chain:opening_source"},
            ],
            "constraints": {"max_selections": 1, "min_selections": 0},
            "player": 0,
            "request_type": "select_chain" if step == 0 else "select_idle_command",
        },
        "request_signature": request_signature,
        "state_hash_after": after,
        "state_hash_before": before,
        "step": step,
        "turn": 1,
        "turn_action_index": step,
    }


def _route(*, interrupted: bool) -> dict:
    first_kind = "ACTIVATE_EFFECT" if interrupted else "PASS"
    first_candidate = "chain:opening_source" if interrupted else "control:pass"
    events = [
        _event(
            0,
            kind=first_kind,
            candidate_id=first_candidate,
            before="state_initial",
            after="state_interrupted" if interrupted else "state_baseline",
        ),
        _event(
            1,
            kind="PASS",
            candidate_id="control:pass",
            before="state_interrupted" if interrupted else "state_baseline",
            after="state_terminal_interrupted" if interrupted else "state_terminal_baseline",
        ),
    ]
    trace = []
    if interrupted:
        record = {
            "activation": {
                "action_step": 0,
                "candidate_ids": ["chain:opening_source"],
            },
            "response_steps": [],
        }
        record["trace_id"] = stable_digest(record, prefix="specifiedinterruption_")
        trace.append(record)
    terminal_hash = events[-1]["state_hash_after"]
    return {
        "presentation": {"specified_interruption_trace": trace},
        "replay": {"events": events},
        "result": {
            "success": True,
            "terminal_board": {
                "phase": "main1",
                "score": 10,
                "state_hash": terminal_hash,
                "stop_reason": "core_end_turn_available",
                "turn": 1,
            },
        },
        "route_id": "route_interrupted" if interrupted else "route_baseline",
    }


@pytest.fixture(autouse=True)
def _accept_compact_route_shape(monkeypatch) -> None:
    monkeypatch.setattr(cross_module, "assert_valid_route_document", lambda _route: None)


def test_lineage_records_first_divergence_and_recovery_tail() -> None:
    baseline = _route(interrupted=False)
    interrupted = _route(interrupted=True)

    lineage = build_strategy_interruption_lineage(
        baseline,
        interrupted,
        deck_sha256=DECK_HASH,
    )
    baseline_observation = build_route_semantic_observation(
        baseline, deck_sha256=DECK_HASH
    )

    assert lineage["schema_version"] == STRATEGY_INTERRUPTION_LINEAGE_SCHEMA_VERSION
    assert lineage["status"] == "validated"
    assert lineage["divergence"]["fork_step"] == 0
    assert lineage["divergence"]["baseline_action"]["kind"] == "PASS"
    assert lineage["divergence"]["interrupted_action"]["kind"] == "ACTIVATE_EFFECT"
    assert lineage["recovery_action_count"] == 1
    assert lineage["lineage_id"].startswith("strategylineage_")
    assert baseline_observation["event_semantic_ids"][0].startswith(
        "strategyevent_"
    )


def test_lineage_rejects_candidate_disappearance_and_missing_recovery() -> None:
    baseline = _route(interrupted=False)
    interrupted = _route(interrupted=True)
    baseline["replay"]["events"][0]["request"]["candidates"] = [
        {"candidate_id": "control:pass"}
    ]

    with pytest.raises(
        StrategyInterruptionCrossValidationError, match="DecisionRequest"
    ):
        build_strategy_interruption_lineage(
            baseline,
            interrupted,
            deck_sha256=DECK_HASH,
        )

    baseline = _route(interrupted=False)
    interrupted = _route(interrupted=True)
    interrupted["replay"]["events"] = interrupted["replay"]["events"][:1]
    with pytest.raises(
        StrategyInterruptionCrossValidationError, match="no recovery tail"
    ):
        build_strategy_interruption_lineage(
            baseline,
            interrupted,
            deck_sha256=DECK_HASH,
        )


def test_lineage_validates_explicit_response_sequence() -> None:
    baseline = _route(interrupted=False)
    interrupted = _route(interrupted=True)
    response = _event(
        1,
        kind="SELECT_CARD",
        candidate_id="target:1",
        before="state_interrupted",
        after="state_response",
    )
    response["request"]["candidates"] = [{"candidate_id": "target:1"}]
    recovery = interrupted["replay"]["events"][1]
    recovery["step"] = 2
    recovery["state_hash_before"] = "state_response"
    interrupted["replay"]["events"].insert(1, response)
    trace = interrupted["presentation"]["specified_interruption_trace"][0]
    trace["response_steps"] = [
        {
            "action_step": 1,
            "candidate_ids": ["target:1"],
            "role": "target",
        }
    ]

    lineage = build_strategy_interruption_lineage(
        baseline,
        interrupted,
        deck_sha256=DECK_HASH,
    )

    assert lineage["recovery_action_count"] == 1
    interrupted["replay"]["events"][1]["action"]["selections"][0][
        "candidate_id"
    ] = "target:changed"
    with pytest.raises(
        StrategyInterruptionCrossValidationError, match="response Action"
    ):
        build_strategy_interruption_lineage(
            baseline,
            interrupted,
            deck_sha256=DECK_HASH,
        )


def test_lineage_rejects_prefix_state_divergence_before_fork() -> None:
    baseline = _route(interrupted=False)
    interrupted = _route(interrupted=True)
    baseline["replay"]["events"].insert(
        0,
        _event(
            0,
            kind="PASS",
            candidate_id="control:pass",
            before="state_initial",
            after="state_prefix",
        ),
    )
    interrupted["replay"]["events"].insert(
        0,
        _event(
            0,
            kind="PASS",
            candidate_id="control:pass",
            before="state_initial",
            after="state_changed",
        ),
    )
    for route in (baseline, interrupted):
        route["presentation"]["specified_interruption_trace"] = deepcopy(
            route["presentation"]["specified_interruption_trace"]
        )
    interrupted["presentation"]["specified_interruption_trace"][0]["activation"][
        "action_step"
    ] = 1

    with pytest.raises(
        StrategyInterruptionCrossValidationError, match="prefix diverged"
    ):
        build_strategy_interruption_lineage(
            baseline,
            interrupted,
            deck_sha256=DECK_HASH,
        )


def test_evidence_writer_is_atomic_and_rejects_tampering(tmp_path) -> None:
    identity = {
        "coverage": {"matrix_cell_count": 9},
        "profiles": [],
        "schema_version": STRATEGY_INTERRUPTION_MATRIX_SCHEMA_VERSION,
        "status": "qualified_local",
    }
    report = {
        **identity,
        "qualification_id": stable_digest(identity, prefix="strategyintmatrix_"),
    }
    output = tmp_path / "matrix.json"

    write_strategy_interruption_cross_validation(output, report)

    assert json.loads(output.read_text(encoding="utf-8")) == report
    tampered = {**report, "status": "failed"}
    with pytest.raises(
        StrategyInterruptionCrossValidationError, match="ID mismatch"
    ):
        write_strategy_interruption_cross_validation(output, tampered)
    assert json.loads(output.read_text(encoding="utf-8")) == report
