from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path

import pytest
import yaml

from ygo_effect_dsl.engine.bridge.decision import (
    Candidate,
    DecisionConstraints,
    DecisionContext,
    DecisionRequest,
)
from ygo_effect_dsl.engine.bridge.ocgcore import (
    CARD_INSTANCE_SNAPSHOT_SCHEMA_VERSION,
    CARD_INSTANCE_TRACE_V2_LOG_PREFIX,
    CardInstanceAuditedScriptProvider,
    CardInstanceTrackerV2,
    CompleteSnapshot,
    CoreLog,
    OcgcoreMessageDecoder,
    assert_public_card_instance_document,
    build_card_instance_scope_id_v2,
    project_visible,
)
from ygo_effect_dsl.engine.bridge.errors import UnsupportedBridgeMessageError
from ygo_effect_dsl.engine.bridge.ocgcore.types import LogType
from ygo_effect_dsl.prototype.real_core import run_real_core_worker


def _scope_id() -> str:
    return build_card_instance_scope_id_v2({"fixture": "v2-unit"})


def _scan(
    scan_id: int,
    label: str,
    cards: list[dict[str, int]],
    *,
    first_observation: int,
    first_log_sequence: int,
) -> tuple[CoreLog, ...]:
    logs = [
        CoreLog(
            sequence=first_log_sequence,
            log_type=LogType.FROM_SCRIPT,
            message=f"{CARD_INSTANCE_TRACE_V2_LOG_PREFIX}|BEGIN|{scan_id}|{label}",
        )
    ]
    for offset, card in enumerate(cards):
        values = (
            scan_id,
            first_observation + offset,
            card["card_id"],
            card.get("card_code", 123),
            card.get("owner", 0),
            card.get("controller", 0),
            card.get("location", 2),
            card.get("sequence", offset),
            card.get("position", 1),
            card.get("previous_controller", 0),
            card.get("previous_location", 0),
            card.get("previous_sequence", 0),
            card.get("previous_position", 0),
            card.get("is_token", 0),
        )
        logs.append(
            CoreLog(
                sequence=first_log_sequence + offset + 1,
                log_type=LogType.FROM_SCRIPT,
                message=(
                    f"{CARD_INSTANCE_TRACE_V2_LOG_PREFIX}|CARD|"
                    + "|".join(str(value) for value in values)
                ),
            )
        )
    logs.append(
        CoreLog(
            sequence=first_log_sequence + len(cards) + 1,
            log_type=LogType.FROM_SCRIPT,
            message=(
                f"{CARD_INSTANCE_TRACE_V2_LOG_PREFIX}|END|{scan_id}|"
                f"{label}|{len(cards)}"
            ),
        )
    )
    return tuple(logs)


def _request(*sequences: int, request_id: str = "request_1") -> DecisionRequest:
    return DecisionRequest(
        request_id=request_id,
        request_type="select_card",
        player=0,
        candidates=tuple(
            Candidate(
                candidate_id=f"card:{sequence}",
                kind="card",
                card_ref={
                    "controller": 0,
                    "location": 2,
                    "public_card_id": 123,
                    "sequence": sequence,
                },
                payload={"response_codec": "card_indices", "response_index": sequence},
            )
            for sequence in sequences
        ),
        constraints=DecisionConstraints(min_selections=1, max_selections=1),
        context=DecisionContext(),
    )


def _snapshot(cards_by_player: dict[int, list[dict[str, object]]]) -> CompleteSnapshot:
    zones = []
    for controller in (0, 1):
        zones.append(
            {
                "cards": cards_by_player.get(controller, []),
                "controller": controller,
                "location": 2,
                "location_name": "hand",
            }
        )
    return CompleteSnapshot(
        environment={"fixture": "v2-unit"},
        field_state={"chain": [], "chain_count": 0},
        zones=tuple(zones),
        process_state="awaiting_response",
        pending_request=None,
    )


def _query_card(controller: int, slot: int, code: int, owner: int) -> dict[str, object]:
    return {
        "controller": controller,
        "fields": [
            {"flag": 1, "name": "code", "value": code},
            {"flag": 2, "name": "owner", "value": owner},
            {"flag": 3, "name": "is_hidden", "value": 0},
            {"flag": 4, "name": "is_public", "value": 0},
        ],
        "instance_key": f"{controller}:2:{slot}",
        "location": 2,
        "slot": slot,
    }


def test_v2_request_scan_distinguishes_same_code_instances() -> None:
    tracker = CardInstanceTrackerV2(scope_id=_scope_id())
    request = tracker.synchronize_request(
        _scan(
            1,
            "request_0",
            [{"card_id": 10}, {"card_id": 11}],
            first_observation=1,
            first_log_sequence=0,
        ),
        _request(0, 1),
        expected_scan_label="request_0",
    )

    refs = [candidate.card_ref for candidate in request.candidates]
    assert len({ref["instance_id"] for ref in refs if ref is not None}) == 2
    assert all(ref["owner"] == 0 for ref in refs if ref is not None)


def test_v2_request_scan_fails_closed_for_stale_or_wrong_nonce() -> None:
    tracker = CardInstanceTrackerV2(scope_id=_scope_id())
    tracker.synchronize_request(
        _scan(
            1,
            "request_0",
            [{"card_id": 10}, {"card_id": 11}],
            first_observation=1,
            first_log_sequence=0,
        ),
        _request(0),
        expected_scan_label="request_0",
    )

    with pytest.raises(ValueError, match="expected complete Request-boundary scan"):
        tracker.synchronize_request(
            (),
            _request(0, request_id="request_1"),
            expected_scan_label="request_1",
        )

    with pytest.raises(ValueError, match="no authority observation"):
        tracker.synchronize_request(
            _scan(
                2,
                "request_1",
                [{"card_id": 11, "sequence": 0}],
                first_observation=3,
                first_log_sequence=4,
            ),
            _request(1, request_id="request_1"),
            expected_scan_label="request_1",
        )


def test_v2_hidden_swap_does_not_change_visible_hash() -> None:
    tracker = CardInstanceTrackerV2(scope_id=_scope_id())
    own = _query_card(0, 0, 123, 0)
    opponent = _query_card(1, 0, 456, 1)
    tracker.consume(
        _scan(
            1,
            "request_0",
            [
                {"card_id": 10},
                {
                    "card_id": 20,
                    "card_code": 456,
                    "owner": 1,
                    "controller": 1,
                    "sequence": 0,
                },
            ],
            first_observation=1,
            first_log_sequence=0,
        )
    )
    first = tracker.enrich_snapshot(_snapshot({0: [own], 1: [opponent]}))
    assert first.card_instance_schema_version == CARD_INSTANCE_SNAPSHOT_SCHEMA_VERSION

    tracker.consume(
        _scan(
            2,
            "request_1",
            [
                {"card_id": 10},
                {
                    "card_id": 21,
                    "card_code": 456,
                    "owner": 1,
                    "controller": 1,
                    "sequence": 0,
                },
            ],
            first_observation=3,
            first_log_sequence=4,
        )
    )
    second = tracker.enrich_snapshot(_snapshot({0: [own], 1: [opponent]}))

    visible_request = {
        "candidate_action_kinds": ["SELECT_CARD"],
        "candidate_ids": ["card:hidden:0"],
        "forced": False,
        "player": 0,
        "request_observation_id": "requestview_same",
        "request_type": "select_card",
    }
    first = replace(
        first,
        pending_request={
            **visible_request,
            "request_signature": "req_hidden_corecard_a",
        },
    )
    second = replace(
        second,
        pending_request={
            **visible_request,
            "request_signature": "req_hidden_corecard_b",
        },
    )

    assert first.state_hash != second.state_hash
    first_visible = project_visible(first, viewer=0)
    second_visible = project_visible(second, viewer=0)
    assert first_visible.visible_hash == second_visible.visible_hash
    assert "request_signature" not in first_visible.data["pending_request"]


def test_v2_opponent_reidentification_uses_a_new_viewer_alias() -> None:
    tracker = CardInstanceTrackerV2(scope_id=_scope_id())
    public_card = _query_card(1, 0, 456, 1)
    public_card["location"] = 4
    public_card["instance_key"] = "1:4:0"
    public_card["fields"][-1]["value"] = 1
    public_snapshot = CompleteSnapshot(
        environment={"fixture": "v2-unit"},
        field_state={"chain": [], "chain_count": 0},
        zones=(
            {
                "cards": [public_card],
                "controller": 1,
                "location": 4,
                "location_name": "monster_zone",
            },
        ),
        process_state="awaiting_response",
        pending_request=None,
    )
    tracker.consume(
        _scan(
            1,
            "request_0",
            [
                {
                    "card_id": 20,
                    "card_code": 456,
                    "owner": 1,
                    "controller": 1,
                    "location": 4,
                    "sequence": 0,
                }
            ],
            first_observation=1,
            first_log_sequence=0,
        )
    )
    first = project_visible(tracker.enrich_snapshot(public_snapshot), viewer=0)
    first_alias = first.data["zones"][0]["cards"][0]["viewer_instance_id"]

    tracker.consume(
        _scan(
            2,
            "request_1",
            [
                {
                    "card_id": 20,
                    "card_code": 456,
                    "owner": 1,
                    "controller": 1,
                    "location": 2,
                    "sequence": 0,
                }
            ],
            first_observation=2,
            first_log_sequence=3,
        )
    )
    tracker.consume(
        _scan(
            3,
            "request_2",
            [
                {
                    "card_id": 20,
                    "card_code": 456,
                    "owner": 1,
                    "controller": 1,
                    "location": 4,
                    "sequence": 0,
                }
            ],
            first_observation=3,
            first_log_sequence=6,
        )
    )
    second = project_visible(tracker.enrich_snapshot(public_snapshot), viewer=0)
    second_alias = second.data["zones"][0]["cards"][0]["viewer_instance_id"]

    assert first_alias.startswith("viewcard_")
    assert second_alias.startswith("viewcard_")
    assert first_alias != second_alias
    assert "persistent_instance_id" not in second.data["zones"][0]["cards"][0]


def test_v2_script_audit_and_reload_field_frame_fail_closed() -> None:
    class Provider:
        def get_script(self, name: str) -> bytes:
            return b"Debug.ReloadFieldBegin(0)"

    provider = CardInstanceAuditedScriptProvider(Provider())
    with pytest.raises(ValueError, match="ReloadFieldBegin"):
        provider.get_script("c123.lua")
    assert provider.get_script("proc_test.lua") == b"Debug.ReloadFieldBegin(0)"

    decoder = OcgcoreMessageDecoder()
    with pytest.raises(UnsupportedBridgeMessageError, match="RELOAD_FIELD"):
        decoder.decode_batch(b"\x01\x00\x00\x00\xa2", request_id="reload")

    with pytest.raises(ValueError, match="private ocgcore authority"):
        assert_public_card_instance_document({"nested": {"card_id": 10}})
    with pytest.raises(ValueError, match="private card-instance instrumentation"):
        assert_public_card_instance_document(
            {"logs": [CARD_INSTANCE_TRACE_V2_LOG_PREFIX + "|BEGIN|1|scan"]}
        )


def test_real_core_v2_is_deterministic_and_keeps_private_trace_private() -> None:
    experiment = yaml.safe_load(
        (
            Path(__file__).parents[1]
            / "examples"
            / "experiments"
            / "real_core_effect_veiler.yaml"
        ).read_text(encoding="utf-8")
    )
    experiment["runner"]["card_instance_provenance"] = "v2"

    first = run_real_core_worker(experiment=experiment)
    second = run_real_core_worker(experiment=experiment)

    assert first["route_id"] == second["route_id"]
    assert first["replay"] == second["replay"]
    assert first["presentation"]["card_instance_provenance"] == second[
        "presentation"
    ]["card_instance_provenance"]
    serialized = json.dumps(first, sort_keys=True)
    assert first["replay"]["initial_snapshot"]["card_instance_schema_version"] == (
        CARD_INSTANCE_SNAPSHOT_SCHEMA_VERSION
    )
    assert '"card_id"' not in serialized
    assert CARD_INSTANCE_TRACE_V2_LOG_PREFIX not in serialized
    assert all(
        selection["card_ref"] is None
        or selection["card_ref"]["instance_id"].startswith("corecard_")
        for event in first["replay"]["events"]
        for selection in event["action"]["selections"]
    )
