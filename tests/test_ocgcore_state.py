from __future__ import annotations

from dataclasses import replace
import json
import struct
from typing import Any

import pytest

from ygo_effect_dsl.engine.bridge import (
    Candidate,
    DecisionConstraints,
    DecisionContext,
    DecisionRequest,
)
from ygo_effect_dsl.engine.bridge.ocgcore import (
    DuelState,
    OcgcoreDuel,
    OcgcoreSnapshotError,
    OcgcoreStateAdapter,
    build_board_summary,
    build_search_projection,
    decode_query_field,
    decode_query_location,
    evaluate_legal_stop,
    project_visible,
)
from ygo_effect_dsl.engine.bridge.ocgcore.state import (
    LOCATION_DECK,
    LOCATION_HAND,
    LOCATION_MZONE,
    LOCATION_ORDER,
    LOCATION_SZONE,
    QUERY_CODE,
    QUERY_END,
    QUERY_IS_HIDDEN,
    QUERY_IS_PUBLIC,
    QUERY_OWNER,
    QUERY_POSITION,
)
from ygo_effect_dsl.engine.state import (
    StateEquivalenceError,
    StateKeyPurpose,
    build_state_key,
)


REAL_QUERY_FIELD_HEX = (
    "00000000401f0000010100000000000000000000000000000000000000000000"
    "0000000000000000000000000000000000000000401f00000000000000000000"
    "0000000000000000000000000000000000000000000000000000000000000000000000"
)


def _field_buffer(*, player0_monster: bool = False, chain_count: int = 0) -> bytes:
    data = bytearray(struct.pack("<I", 0))
    for player in range(2):
        data += struct.pack("<I", 8000)
        for slot in range(7):
            if player == 0 and slot == 0 and player0_monster:
                data += struct.pack("<BBI", 1, 1, 0)
            else:
                data += b"\0"
        data += b"\0" * 8
        data += struct.pack("<6I", 0, 0, 0, 0, 0, 0)
    data += struct.pack("<I", chain_count)
    if chain_count:
        data += struct.pack("<IBBII BBIQ", 1234, 0, 4, 2, 1, 0, 4, 2, 99)
    return bytes(data)


def _query_card(
    code: int,
    *,
    position: int = 1,
    owner: int = 0,
    is_public: int = 0,
    is_hidden: int = 0,
) -> bytes:
    fields = (
        (QUERY_CODE, struct.pack("<I", code)),
        (QUERY_POSITION, struct.pack("<I", position)),
        (QUERY_OWNER, bytes((owner,))),
        (QUERY_IS_PUBLIC, bytes((is_public,))),
        (QUERY_IS_HIDDEN, bytes((is_hidden,))),
        (QUERY_END, b""),
    )
    body = b"".join(
        struct.pack("<HI", 4 + len(payload), flag) + payload
        for flag, payload in fields
    )
    return struct.pack("<I", len(body)) + body


def _empty_location(location: int) -> bytes:
    slot_count = {LOCATION_MZONE: 7, LOCATION_SZONE: 8}.get(location, 0)
    body = b"\0\0" * slot_count
    return struct.pack("<I", len(body)) + body


class _FakeDuel:
    def __init__(self, locations: dict[tuple[int, int], bytes]) -> None:
        self.state = DuelState.AWAITING_RESPONSE
        self._locations = locations

    def query_field(self) -> bytes:
        return _field_buffer()

    def query_location(self, query: Any) -> bytes:
        return self._locations.get(
            (query.controller, query.location), _empty_location(query.location)
        )

    def query_count(self, controller: int, location: int) -> int:
        return sum(
            card is not None
            for card in decode_query_location(
                self.query_location(
                    type("QueryKey", (), {"controller": controller, "location": location})()
                ),
                controller=controller,
                location=location,
            )
        )


def _idle_request(*, forced: bool = False) -> DecisionRequest:
    return DecisionRequest(
        request_id="request-1",
        request_type="select_idle_command",
        player=0,
        candidates=(
            Candidate(
                candidate_id="control:end_turn",
                kind="end_turn",
                payload={"action_kind": "END_TURN", "response_value": 7},
            ),
        ),
        constraints=DecisionConstraints(),
        context=DecisionContext(extra={"forced": forced}),
    )


def _snapshot(
    *,
    locations: tuple[int, ...] = LOCATION_ORDER,
    display_metadata: dict[str, Any] | None = None,
    information_mode: str = "complete_information",
    sampling_reference: dict[str, Any] | None = None,
):
    buffers = {
        (0, LOCATION_HAND): _query_card(97268402),
        (1, LOCATION_HAND): _query_card(46986414, owner=1),
    }
    return OcgcoreStateAdapter().capture(
        _FakeDuel(buffers),
        pending_request=_idle_request(),
        environment={"assets": "fixed", "core": "v11", "seed": [1, 2, 3, 4]},
        locations=locations,
        display_metadata=display_metadata,
        information_mode=information_mode,
        sampling_reference=sampling_reference,
    )


def test_real_query_field_fixture_decodes_ocgcore_v11_layout() -> None:
    decoded = decode_query_field(bytes.fromhex(REAL_QUERY_FIELD_HEX))
    assert decoded["players"][0]["life_points"] == 8000
    assert decoded["players"][0]["monster_zones"][0] == {
        "overlay_count": 0,
        "position": 1,
    }
    assert decoded["players"][1]["life_points"] == 8000
    assert decoded["chain_count"] == 0


def test_query_field_chain_order_matches_native_contract() -> None:
    decoded = decode_query_field(_field_buffer(chain_count=1))
    assert decoded["chain"] == [
        {
            "description": 99,
            "handler": {
                "code": 1234,
                "controller": 0,
                "location": 4,
                "position": 1,
                "sequence": 2,
            },
            "triggering_controller": 0,
            "triggering_location": 4,
            "triggering_sequence": 2,
        }
    ]


def test_query_location_is_decoded_into_owned_pointer_free_values() -> None:
    native_buffer = bytearray(_query_card(97268402))
    decoded = decode_query_location(native_buffer, controller=0, location=LOCATION_HAND)
    native_buffer[:] = b"\xff" * len(native_buffer)
    assert decoded[0] is not None
    assert decoded[0]["instance_key"] == "0:2:0"
    assert next(
        field["value"] for field in decoded[0]["fields"] if field["name"] == "code"
    ) == 97268402


def test_complete_hash_ignores_query_order_and_display_metadata() -> None:
    first = _snapshot(display_metadata={"card_name": "Effect Veiler"})
    second = _snapshot(
        locations=tuple(reversed(LOCATION_ORDER)),
        display_metadata={"card_name": "renamed"},
    )
    assert first.state_hash == second.state_hash
    assert first.to_dict()["display_metadata"] != second.to_dict()["display_metadata"]
    assert first.identity_completeness == "query_api_projection"
    assert "effect_usage_history" in first.missing_identity_fields
    identity = first.to_dict()["state_identity"]
    assert identity["schema_version"] == "ygo-state-id-v1"
    assert identity["information_mode"] == "complete_information"
    assert identity["state_id"] == first.state_hash
    assert identity["constraints"]["observation_status"] == (
        "unavailable_from_ocgcore_query_api"
    )
    assert identity["history"]["effect_usage_observation_status"] == (
        "unavailable_from_ocgcore_query_api"
    )
    with pytest.raises(StateEquivalenceError, match="requires exact"):
        build_state_key(
            first.to_state_identity(),
            purpose=StateKeyPurpose.BRANCH_PRUNING,
        )


def test_sampled_private_state_requires_sampling_reference() -> None:
    with pytest.raises(ValueError, match="requires sampling_reference"):
        _snapshot(information_mode="sampled_private_state")


def test_sampling_reference_changes_state_hash_for_the_same_board() -> None:
    first = _snapshot(
        information_mode="sampled_private_state",
        sampling_reference={"sample_id": "sample-1", "sampler": "hidden-hand-v1"},
    )
    duel = _FakeDuel(
        {
            (0, LOCATION_HAND): _query_card(97268402),
            (1, LOCATION_HAND): _query_card(46986414, owner=1),
        }
    )
    second = OcgcoreDuel.capture_snapshot(
        duel,
        pending_request=_idle_request(),
        environment={"assets": "fixed", "core": "v11", "seed": [1, 2, 3, 4]},
        information_mode="sampled_private_state",
        sampling_reference={"sample_id": "sample-2", "sampler": "hidden-hand-v1"},
    )

    assert first.field_state == second.field_state
    assert first.zones == second.zones
    assert first.state_hash != second.state_hash
    assert first.to_state_identity().sampling_reference == {
        "sample_id": "sample-1",
        "sampler": "hidden-hand-v1",
    }
    assert second.to_dict()["state_identity"]["information_mode"] == (
        "sampled_private_state"
    )
    assert second.to_dict()["state_identity"]["sampling_reference"]["sample_id"] == (
        "sample-2"
    )


def test_pending_request_preserves_missing_action_kind_for_state_compatibility() -> None:
    request = DecisionRequest(
        request_id="request-place",
        request_type="select_place",
        player=0,
        candidates=(Candidate(candidate_id="zone:0", kind="zone"),),
        constraints=DecisionConstraints(),
        context=DecisionContext(),
    )

    snapshot = OcgcoreStateAdapter().capture(
        _FakeDuel({}),
        pending_request=request,
        environment={"assets": "fixed", "core": "v11", "seed": [1, 2, 3, 4]},
    )

    assert snapshot.pending_request["candidate_action_kinds"] == [None]


def test_visible_projection_redacts_opponent_hidden_card_and_request() -> None:
    complete = _snapshot()
    visible = project_visible(complete, viewer=1).to_dict()
    serialized = json.dumps(visible, sort_keys=True)
    assert "97268402" not in serialized
    assert visible["data"]["pending_request"] is None
    assert build_search_projection(
        complete, information_mode="visible_information", viewer=1
    ).exact_equivalence is False
    assert build_board_summary(complete, viewer=1).data["zone_counts"]["0"]["hand"] == 1


def test_legal_stop_requires_idle_end_turn_control_from_core() -> None:
    snapshot = _snapshot()
    assert evaluate_legal_stop(snapshot).to_dict()["reason"] == "core_end_turn_available"
    assert evaluate_legal_stop(snapshot).can_stop is True

    active_chain = replace(
        snapshot,
        field_state={**snapshot.field_state, "chain_count": 1},
    )
    assert evaluate_legal_stop(active_chain).reason == "chain_active"

    forced = replace(
        snapshot,
        pending_request={**snapshot.pending_request, "forced": True},
    )
    assert evaluate_legal_stop(forced).reason == "mandatory_request"

    pending_place = replace(
        snapshot,
        pending_request={**snapshot.pending_request, "request_type": "select_place"},
    )
    assert evaluate_legal_stop(pending_place).reason == "pending_request"

    processing = replace(snapshot, process_state=DuelState.PROCESSING.value)
    assert evaluate_legal_stop(processing).reason == "mandatory_processing"


def test_partial_or_malformed_snapshot_is_rejected() -> None:
    with pytest.raises(OcgcoreSnapshotError, match="every canonical location"):
        _snapshot(locations=LOCATION_ORDER[:-1])

    duel = _FakeDuel({(0, LOCATION_MZONE): struct.pack("<I", 0)})
    with pytest.raises(OcgcoreSnapshotError, match="expected 7"):
        OcgcoreStateAdapter().capture(
            duel,
            pending_request=_idle_request(),
            environment={},
        )

    malformed = _query_card(1)[:-1]
    with pytest.raises(OcgcoreSnapshotError):
        decode_query_location(malformed, controller=0, location=LOCATION_DECK)
