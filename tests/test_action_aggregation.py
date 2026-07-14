from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import struct
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ygo_effect_dsl.engine.action import (
    Action,
    ActionAggregationHint,
    ActionKind,
    ActionRole,
    Selection,
    aggregate_replay_events,
    action_aggregation_compatibility_report,
    derive_ocgcore_action_aggregation,
    diff_action_aggregations,
)
from ygo_effect_dsl.engine.bridge import (
    Candidate,
    DecisionConstraints,
    DecisionContext,
    DecisionRequest,
)
from ygo_effect_dsl.engine.replay import ReplayEventV03a
from ygo_effect_dsl.spikes.action_aggregation_edge_evidence import (
    build_action_aggregation_edge_evidence,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
EDGE_EVIDENCE = (
    REPO_ROOT
    / "docs"
    / "ocgcore"
    / "evidence"
    / "action_aggregation_edges.json"
)


def _event(
    step: int,
    *,
    request_type: str,
    candidate_id: str,
    label: str,
    action_kind: ActionKind,
) -> dict[str, object]:
    request = DecisionRequest(
        request_id=f"request:{step}",
        request_type=request_type,
        player=0,
        candidates=(Candidate(candidate_id=candidate_id, kind="card", label=label),),
        constraints=DecisionConstraints(min_selections=1, max_selections=1),
        context=DecisionContext(),
    )
    action = Action(
        kind=action_kind,
        player=0,
        selections=(Selection(candidate_id=candidate_id),),
        request_signature=request.request_signature,
    )
    return ReplayEventV03a(
        step=step,
        request_signature=request.request_signature,
        action=action,
        request=request.to_dict(),
        state_hash_before=f"state:{step}",
        state_hash_after=f"state:{step + 1}",
        turn=1,
        turn_action_index=step,
        chain_index=1,
    ).to_dict()


def _effect_events(*, target_id: str = "target:card-a") -> list[dict[str, object]]:
    return [
        _event(
            0,
            request_type="select_chain",
            candidate_id="effect:activate",
            label="Activate Sample Effect",
            action_kind=ActionKind.ACTIVATE_EFFECT,
        ),
        _event(
            1,
            request_type="select_card",
            candidate_id="cost:card-a",
            label="Cost Card A",
            action_kind=ActionKind.SELECT_CARD,
        ),
        _event(
            2,
            request_type="select_card",
            candidate_id=target_id,
            label=f"Target {target_id}",
            action_kind=ActionKind.SELECT_CARD,
        ),
        _event(
            3,
            request_type="select_option",
            candidate_id="option:draw",
            label="Draw one card",
            action_kind=ActionKind.SELECT_OPTION,
        ),
    ]


def _effect_hints() -> tuple[ActionAggregationHint, ...]:
    return (
        ActionAggregationHint(0, "effect:sample", ActionRole.PRIMARY),
        ActionAggregationHint(1, "effect:sample", ActionRole.COST),
        ActionAggregationHint(2, "effect:sample", ActionRole.TARGET),
        ActionAggregationHint(3, "effect:sample", ActionRole.OPTION),
    )


def test_aggregation_tracks_atomic_mapping_and_display_roles() -> None:
    aggregation = aggregate_replay_events(_effect_events(), hints=_effect_hints())

    assert len(aggregation.groups) == 1
    group = aggregation.groups[0]
    assert tuple(part.step for part in group.parts) == (0, 1, 2, 3)
    assert [item.label for item in group.selections_for(ActionRole.COST)] == ["Cost Card A"]
    assert [item.candidate_id for item in group.selections_for(ActionRole.TARGET)] == [
        "target:card-a"
    ]
    assert [item.label for item in group.selections_for(ActionRole.OPTION)] == [
        "Draw one card"
    ]
    assert {link.step for link in aggregation.links} == {0, 1, 2, 3}
    assert {link.composite_id for link in aggregation.links} == {group.composite_id}
    displayed = group.to_dict()
    assert displayed["costs"][0]["label"] == "Cost Card A"
    assert displayed["targets"][0]["candidate_id"] == "target:card-a"
    assert displayed["options"][0]["label"] == "Draw one card"


def test_aggregation_is_conservative_without_group_hints() -> None:
    aggregation = aggregate_replay_events(_effect_events())

    assert len(aggregation.groups) == 4
    assert aggregation.groups[3].parts[0].role == ActionRole.OPTION
    assert all(len(group.parts) == 1 for group in aggregation.groups)


def test_composite_action_diff_reports_one_group_replacement() -> None:
    before = aggregate_replay_events(_effect_events(), hints=_effect_hints())
    after = aggregate_replay_events(
        _effect_events(target_id="target:card-b"),
        hints=_effect_hints(),
    )

    operations = diff_action_aggregations(before, after)

    assert len(operations) == 1
    assert operations[0].tag.value == "replace"
    assert operations[0].before_start == 0
    assert operations[0].after_start == 0


def test_aggregation_rejects_non_contiguous_group_key() -> None:
    hints = (
        ActionAggregationHint(0, "effect:sample", ActionRole.PRIMARY),
        ActionAggregationHint(2, "effect:sample", ActionRole.TARGET),
    )

    with pytest.raises(ValueError, match="contiguous"):
        aggregate_replay_events(_effect_events(), hints=hints)


def _trace(*frames: tuple[int, bytes]) -> dict[str, object]:
    return {
        "frames": [
            {
                "frame_index": index,
                "message_type": message_type,
                "payload_hex": payload.hex(),
            }
            for index, (message_type, payload) in enumerate(frames)
        ]
    }


def test_ocgcore_lifecycle_derives_cost_target_and_option_roles() -> None:
    events = _effect_events()
    cost_card_ref = {
        "controller": 0,
        "location": 2,
        "position": 10,
        "public_card_id": 97268402,
        "sequence": 1,
    }
    events[1]["request"]["candidates"][0]["card_ref"] = cost_card_ref
    move_payload = struct.pack(
        "<IBBIIBBIII",
        97268402,
        0,
        2,
        1,
        10,
        0,
        16,
        0,
        1,
        0x80 | 0x4000,
    )
    target_hint = struct.pack("<BBQ", 3, 0, 551)
    events[0]["core_output"] = _trace((2, struct.pack("<BBQ", 3, 0, 501)), (15, b""))
    events[1]["core_output"] = _trace((50, move_payload), (2, target_hint), (15, b""))
    events[2]["core_output"] = _trace((14, b""))
    events[3]["core_output"] = _trace((71, b"\x01"), (16, b""))
    replay = {
        "initial_core_output": _trace((16, b"")),
        "events": events,
    }

    aggregation, evidence = derive_ocgcore_action_aggregation(replay)

    assert len(aggregation.groups) == 1
    assert [part.role for part in aggregation.groups[0].parts] == [
        ActionRole.PRIMARY,
        ActionRole.COST,
        ActionRole.TARGET,
        ActionRole.OPTION,
    ]
    assert [item["evidence"]["basis"] for item in evidence["role_evidence"]] == [
        "action_kind",
        "selected_card_reason_cost_move",
        "select_hint_target",
        "selection_message_type",
    ]
    assert evidence["group_boundaries"][0]["end_message_type"] == 71


def test_ocgcore_lifecycle_does_not_treat_discard_hint_as_cost() -> None:
    events = _effect_events()[:2]
    events[0]["core_output"] = _trace((2, struct.pack("<BBQ", 3, 0, 501)), (15, b""))
    events[1]["core_output"] = _trace((71, b"\x01"))
    replay = {
        "initial_core_output": _trace((16, b"")),
        "events": events,
    }

    aggregation, evidence = derive_ocgcore_action_aggregation(replay)

    assert aggregation.groups[0].parts[1].role == ActionRole.SELECTION
    assert evidence["role_evidence"][1]["evidence"]["basis"] == (
        "conservative_fallback"
    )


def _edge_replay(events: list[dict[str, object]]) -> dict[str, object]:
    return {
        "events": events,
        "initial_core_output": _trace((16, b"")),
        "version_metadata": {"ocgcore_api": "11.0"},
    }


def _cost_move_payload(card_ref: dict[str, int]) -> bytes:
    return struct.pack(
        "<IBBIIBBIII",
        card_ref["public_card_id"],
        card_ref["controller"],
        card_ref["location"],
        card_ref["sequence"],
        card_ref["position"],
        card_ref["controller"],
        16,
        0,
        1,
        0x80 | 0x4000,
    )


def test_cancelled_activation_closes_group_and_preserves_atomic_replay() -> None:
    events = [
        _event(
            0,
            request_type="select_chain",
            candidate_id="effect:activate",
            label="Activate",
            action_kind=ActionKind.ACTIVATE_EFFECT,
        ),
        _event(
            1,
            request_type="select_card",
            candidate_id="card:cancel",
            label="Cancel",
            action_kind=ActionKind.DECLINE,
        ),
    ]
    events[1]["action"]["selections"] = []
    events[1]["request"]["context"]["extra"] = {"cancelable": True}
    events[0]["core_output"] = _trace((15, b""))
    events[1]["core_output"] = _trace((16, b""))
    replay = _edge_replay(events)
    unchanged = deepcopy(replay)

    aggregation, evidence = derive_ocgcore_action_aggregation(replay)

    assert replay == unchanged
    assert [part.step for part in aggregation.groups[0].parts] == [0, 1]
    assert [part.role for part in aggregation.groups[0].parts] == [
        ActionRole.PRIMARY,
        ActionRole.CONTROL,
    ]
    assert evidence["group_boundaries"] == [
        {
            "boundary_kind": "cancelled_selection",
            "end_after_response_step": 1,
            "end_frame_index": None,
            "end_message_type": None,
            "group_key": (
                "ocgcore-activation:" + events[0]["action_occurrence_id"]
            ),
            "group_kind": "activation_setup",
            "start_step": 0,
        }
    ]


def test_fizzled_chain_does_not_absorb_following_action() -> None:
    events = [
        _event(
            0,
            request_type="select_chain",
            candidate_id="effect:activate",
            label="Activate",
            action_kind=ActionKind.ACTIVATE_EFFECT,
        ),
        _event(
            1,
            request_type="select_chain",
            candidate_id="control:pass",
            label="Pass",
            action_kind=ActionKind.PASS,
        ),
        _event(
            2,
            request_type="select_chain",
            candidate_id="control:pass",
            label="Pass",
            action_kind=ActionKind.PASS,
        ),
    ]
    events[0]["core_output"] = _trace((71, b"\x01"), (16, b""))
    events[1]["core_output"] = _trace(
        (72, b"\x01"),
        (76, b"\x01"),
        (73, b"\x01"),
        (74, b""),
        (16, b""),
    )
    events[2]["core_output"] = _trace((16, b""))

    aggregation, evidence = derive_ocgcore_action_aggregation(_edge_replay(events))

    assert [[part.step for part in group.parts] for group in aggregation.groups] == [
        [0],
        [1],
        [2],
    ]
    lifecycle_names = [item["message_name"] for item in evidence["chain_lifecycle"]]
    assert lifecycle_names == [
        "MSG_CHAINED",
        "MSG_CHAIN_SOLVING",
        "MSG_CHAIN_DISABLED",
        "MSG_CHAIN_SOLVED",
        "MSG_CHAIN_END",
    ]


def test_multiple_chain_links_and_negation_keep_separate_boundaries() -> None:
    events = [
        _event(
            0,
            request_type="select_chain",
            candidate_id="effect:first",
            label="First link",
            action_kind=ActionKind.ACTIVATE_EFFECT,
        ),
        _event(
            1,
            request_type="select_chain",
            candidate_id="effect:second",
            label="Second link",
            action_kind=ActionKind.ACTIVATE_EFFECT,
        ),
        _event(
            2,
            request_type="select_chain",
            candidate_id="control:pass",
            label="Pass",
            action_kind=ActionKind.PASS,
        ),
        _event(
            3,
            request_type="select_chain",
            candidate_id="control:after",
            label="After chain",
            action_kind=ActionKind.PASS,
        ),
    ]
    events[0]["core_output"] = _trace((71, b"\x01"), (16, b""))
    events[1]["core_output"] = _trace((71, b"\x02"), (16, b""))
    events[2]["core_output"] = _trace(
        (72, b"\x02"),
        (75, b"\x02"),
        (73, b"\x02"),
        (72, b"\x01"),
        (73, b"\x01"),
        (74, b""),
        (16, b""),
    )
    events[3]["core_output"] = _trace((16, b""))

    aggregation, evidence = derive_ocgcore_action_aggregation(_edge_replay(events))

    assert [[part.step for part in group.parts] for group in aggregation.groups] == [
        [0],
        [1],
        [2],
        [3],
    ]
    assert [boundary["start_step"] for boundary in evidence["group_boundaries"]] == [
        0,
        1,
    ]
    assert "MSG_CHAIN_NEGATED" in {
        item["message_name"] for item in evidence["chain_lifecycle"]
    }


def test_multiple_cost_selection_requests_remain_one_activation_group() -> None:
    events = [
        _event(
            0,
            request_type="select_chain",
            candidate_id="effect:activate",
            label="Activate",
            action_kind=ActionKind.ACTIVATE_EFFECT,
        ),
        _event(
            1,
            request_type="select_card",
            candidate_id="cost:a",
            label="Cost A",
            action_kind=ActionKind.SELECT_CARD,
        ),
        _event(
            2,
            request_type="select_card",
            candidate_id="cost:b",
            label="Cost B",
            action_kind=ActionKind.SELECT_CARD,
        ),
        _event(
            3,
            request_type="select_card",
            candidate_id="target:a",
            label="Target",
            action_kind=ActionKind.SELECT_CARD,
        ),
    ]
    cost_refs = [
        {
            "controller": 0,
            "location": 2,
            "position": 10,
            "public_card_id": 1001 + index,
            "sequence": index,
        }
        for index in (1, 2)
    ]
    for step, card_ref in zip((1, 2), cost_refs, strict=True):
        events[step]["request"]["candidates"][0]["card_ref"] = card_ref
    events[3]["request"]["candidates"][0]["card_ref"] = {
        "controller": 0,
        "location": 4,
        "position": 1,
        "public_card_id": 2001,
        "sequence": 0,
    }
    discard_hint = struct.pack("<BBQ", 3, 0, 501)
    target_hint = struct.pack("<BBQ", 3, 0, 551)
    events[0]["core_output"] = _trace((2, discard_hint), (15, b""))
    events[1]["core_output"] = _trace(
        (50, _cost_move_payload(cost_refs[0])),
        (2, discard_hint),
        (15, b""),
    )
    events[2]["core_output"] = _trace(
        (50, _cost_move_payload(cost_refs[1])),
        (2, target_hint),
        (15, b""),
    )
    events[3]["core_output"] = _trace((71, b"\x01"), (16, b""))

    aggregation, evidence = derive_ocgcore_action_aggregation(_edge_replay(events))

    assert len(aggregation.groups) == 1
    assert [part.role for part in aggregation.groups[0].parts] == [
        ActionRole.PRIMARY,
        ActionRole.COST,
        ActionRole.COST,
        ActionRole.TARGET,
    ]
    assert [item["step"] for item in evidence["role_evidence"]] == [0, 1, 2, 3]


def test_resolution_time_selections_form_a_separate_group() -> None:
    events = [
        _event(
            0,
            request_type="select_chain",
            candidate_id="effect:activate",
            label="Activate",
            action_kind=ActionKind.ACTIVATE_EFFECT,
        ),
        _event(
            1,
            request_type="select_chain",
            candidate_id="control:pass",
            label="Pass",
            action_kind=ActionKind.PASS,
        ),
        _event(
            2,
            request_type="select_card",
            candidate_id="resolution:card",
            label="Resolve card",
            action_kind=ActionKind.SELECT_CARD,
        ),
        _event(
            3,
            request_type="select_option",
            candidate_id="resolution:option",
            label="Resolve option",
            action_kind=ActionKind.SELECT_OPTION,
        ),
    ]
    events[0]["core_output"] = _trace((71, b"\x01"), (16, b""))
    events[1]["core_output"] = _trace(
        (72, b"\x01"),
        (2, struct.pack("<BBQ", 3, 0, 551)),
        (15, b""),
    )
    events[2]["core_output"] = _trace((14, b""))
    events[3]["core_output"] = _trace(
        (73, b"\x01"), (74, b""), (16, b"")
    )

    aggregation, evidence = derive_ocgcore_action_aggregation(_edge_replay(events))

    assert [[part.step for part in group.parts] for group in aggregation.groups] == [
        [0],
        [1],
        [2, 3],
    ]
    assert [part.role for part in aggregation.groups[2].parts] == [
        ActionRole.RESOLUTION,
        ActionRole.RESOLUTION,
    ]
    assert evidence["group_boundaries"][1]["group_kind"] == "resolution"
    assert evidence["group_boundaries"][1]["end_message_type"] == 74


def test_api_and_known_frame_layout_changes_fail_closed() -> None:
    events = _effect_events()[:1]
    events[0]["core_output"] = _trace((71, b"\x01"))
    replay = _edge_replay(events)
    replay["version_metadata"]["ocgcore_api"] = "12.0"

    with pytest.raises(ValueError, match="does not support ocgcore_api"):
        derive_ocgcore_action_aggregation(replay)

    replay["version_metadata"]["ocgcore_api"] = "11.0"
    events[0]["core_output"] = _trace((71, b""))
    with pytest.raises(ValueError, match="MSG_CHAINED payload"):
        derive_ocgcore_action_aggregation(replay)

    compatibility = action_aggregation_compatibility_report()
    assert compatibility["apis"]["11.0"]["status"] == "supported"
    assert compatibility["apis"]["11.0"]["fixture_status"] == {
        "activation_setup": "real_core",
        "cancel": "raw_replay_contract_core_unreachable",
        "chain_disabled": "real_core",
        "chain_negated": "real_core",
        "multi_chain": "real_core",
        "multi_selection": "real_core",
        "resolution_selection": "real_core",
        "target_loss_fizzle": "real_core",
    }
    assert compatibility["limitations"]["activation_cancel"]["tracking_issue"] == 115
    assert compatibility["fail_close"] == {
        "malformed_known_frame": True,
        "unfinished_activation_group": True,
        "unfinished_resolution_group": True,
        "unknown_api_version": True,
    }


def test_fixed_edge_evidence_matches_fresh_recalculation() -> None:
    expected = json.loads(EDGE_EVIDENCE.read_text(encoding="utf-8"))

    assert build_action_aggregation_edge_evidence(repo_root=REPO_ROOT) == expected
    for fixture in expected["edge_fixtures"].values():
        assert fixture["atomic_replay_digest_before"] == (
            fixture["atomic_replay_digest_after"]
        )
    interruption_digests = {
        route["filename"]: route["interruption_digest"]
        for route in expected["real_core_routes"]
    }
    assert interruption_digests["real_core_effect_veiler_interrupted.route.yaml"] != (
        interruption_digests["real_core_effect_veiler.route.yaml"]
    )
