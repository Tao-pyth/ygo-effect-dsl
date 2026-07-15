from __future__ import annotations

from dataclasses import replace
import json

import pytest

from ygo_effect_dsl.engine.action import Action, ActionKind
from ygo_effect_dsl.engine.bridge.ocgcore.state import (
    CARD_INSTANCE_SNAPSHOT_SCHEMA_VERSION,
    LOCATION_HAND,
    LOCATION_MZONE,
    LOCATION_NAMES,
    LOCATION_ORDER,
    CompleteSnapshot,
)
from ygo_effect_dsl.engine.replay import (
    ReplayEventV03a,
    PlayerViewProjectionError,
    PlayerViewProjectionInput,
    assert_valid_player_view_replay,
    build_player_view_replay,
    project_player_view_observation,
)


OWN_CARD = 11111111
OPPONENT_HAND_CANARY = 22222222
OPPONENT_SET_CANARY = 33333333


def _card(controller: int, location: int, slot: int, code: int, *, hidden: bool) -> dict:
    return {
        "controller": controller,
        "fields": [
            {"flag": 1, "name": "code", "value": code},
            {"flag": 2, "name": "position", "value": 8 if hidden else 1},
            {"flag": 3, "name": "owner", "value": controller},
            {"flag": 4, "name": "is_public", "value": 0 if hidden else 1},
            {"flag": 5, "name": "is_hidden", "value": 1 if hidden else 0},
        ],
        "instance_key": f"{controller}:{location}:{slot}",
        "location": location,
        "slot": slot,
    }


def _players(*, player0_life: int = 8000) -> list[dict]:
    return [
        {
            "banished_count": 0,
            "deck_count": 0,
            "extra_deck_count": 0,
            "face_up_extra_count": 0,
            "graveyard_count": 0,
            "hand_count": 1,
            "life_points": player0_life if player == 0 else 8000,
            "monster_zones": [None] * 7,
            "player": player,
            "spell_trap_zones": [None] * 8,
        }
        for player in (0, 1)
    ]


def _snapshot(*, player0_life: int = 8000) -> CompleteSnapshot:
    players = _players(player0_life=player0_life)
    players[1]["monster_zones"][0] = {"overlay_count": 0, "position": 8}
    zones = []
    for controller in (0, 1):
        for location in LOCATION_ORDER:
            cards = []
            if controller == 0 and location == LOCATION_HAND:
                cards = [_card(controller, location, 0, OWN_CARD, hidden=False)]
            elif controller == 1 and location == LOCATION_HAND:
                cards = [
                    _card(
                        controller,
                        location,
                        0,
                        OPPONENT_HAND_CANARY,
                        hidden=True,
                    )
                ]
            elif controller == 1 and location == LOCATION_MZONE:
                cards = [
                    _card(
                        controller,
                        location,
                        0,
                        OPPONENT_SET_CANARY,
                        hidden=True,
                    )
                ]
            zones.append(
                {
                    "cards": cards,
                    "controller": controller,
                    "location": location,
                    "location_name": LOCATION_NAMES[location],
                }
            )
    return CompleteSnapshot(
        environment={"duel_seed": [1, 2, 3, 4], "private": OPPONENT_HAND_CANARY},
        field_state={
            "chain": [],
            "chain_count": 0,
            "duel_options": 0,
            "players": players,
        },
        zones=tuple(zones),
        process_state="awaiting_response",
        pending_request={
            "candidate_action_kinds": ["END_TURN"],
            "candidate_ids": [f"private:{OPPONENT_HAND_CANARY}"],
            "forced": False,
            "player": 0,
            "request_signature": "req_private_canary",
            "request_type": "select_idle_command",
        },
    )


def _source_route() -> dict:
    return {
        "schema_version": "0.1",
        "route_id": "route_private_canary",
        "replay": {
            "schema_version": "0.3a",
            "manifest": {
                "environment": {
                    "project": {
                        "replay_schema": "0.3a",
                        "snapshot_schema": "ocgcore-query-v1",
                    },
                    "core": {"api": [11, 0], "lock_id": "core-lock-test"},
                    "assets": {"lock_id": "asset-lock-test"},
                }
            },
        },
        "result": {
            "success": True,
            "peak_board": {
                "phase": "main1",
                "score": 2,
                "state_hash": "state_peak_private",
                "stop_reason": "core_end_turn_available",
                "success": True,
                "turn": 1,
            },
            "terminal_board": {
                "phase": "main1",
                "score": 1,
                "state_hash": "state_terminal_private",
                "stop_reason": "core_end_turn_available",
                "success": True,
                "turn": 1,
            },
        },
    }


def _event() -> ReplayEventV03a:
    action = Action(
        kind=ActionKind.END_TURN,
        player=0,
        selections=(),
        request_signature="req_private_canary",
    )
    return ReplayEventV03a(
        step=0,
        request_signature="req_private_canary",
        action=action,
        request={
            "request_type": "select_idle_command",
            "constraints": {
                "allow_duplicates": False,
                "max_selections": 1,
                "min_selections": 1,
                "ordered": False,
                "required": True,
            },
            "candidates": [{"candidate_id": f"private:{OPPONENT_HAND_CANARY}"}],
        },
        core_input_ref="input_private_canary",
        core_response={"raw_hex": str(OPPONENT_HAND_CANARY)},
        core_output={"state_hash": "state_private_canary"},
        state_hash_before="state_before_private",
        state_hash_after="state_after_private",
        turn=1,
        turn_action_index=0,
        chain_index=0,
    )


def test_player_view_replay_is_deterministic_and_excludes_private_identifiers() -> None:
    data = PlayerViewProjectionInput(
        source_route=_source_route(),
        initial_snapshot=_snapshot(),
        initial_turn=1,
        initial_phase="main1",
        checkpoint_snapshots=((_snapshot(player0_life=7000), 1, "main1"),),
        events=(_event(),),
        viewer=0,
    )

    first = build_player_view_replay(data)
    second = build_player_view_replay(data)

    assert first == second
    assert_valid_player_view_replay(first)
    serialized = json.dumps(first, sort_keys=True)
    assert str(OWN_CARD) in serialized
    assert str(OPPONENT_HAND_CANARY) not in serialized
    assert str(OPPONENT_SET_CANARY) not in serialized
    assert "route_private_canary" not in serialized
    assert "state_peak_private" not in serialized
    assert "req_private_canary" not in serialized
    assert "input_private_canary" not in serialized
    assert "duel_seed" not in serialized


def test_hidden_marker_is_observation_scoped_and_not_card_scoped() -> None:
    first = project_player_view_observation(
        _snapshot(), viewer=0, turn=1, phase="main1"
    )
    second = project_player_view_observation(
        _snapshot(player0_life=7000), viewer=0, turn=1, phase="main1"
    )

    def marker(observation: dict) -> str:
        field_zone = next(
            zone
            for zone in observation["zones"]
            if zone["controller"] == 1 and zone["location"] == LOCATION_MZONE
        )
        return field_zone["cards"][0]["hidden_marker"]

    assert marker(first) != marker(second)


def test_unknown_query_shape_fails_closed() -> None:
    snapshot = _snapshot()
    zones = list(snapshot.zones)
    own_hand_index = next(
        index
        for index, zone in enumerate(zones)
        if zone["controller"] == 0 and zone["location"] == LOCATION_HAND
    )
    zone = dict(zones[own_hand_index])
    card = dict(zone["cards"][0])
    card["fields"] = [
        *card["fields"],
        {"flag": 999, "name": "unknown_0x3e7", "value": OPPONENT_HAND_CANARY},
    ]
    zone["cards"] = [card]
    zones[own_hand_index] = zone

    with pytest.raises(PlayerViewProjectionError, match="unprojectable_shape"):
        project_player_view_observation(
            replace(snapshot, zones=tuple(zones)),
            viewer=0,
            turn=1,
            phase="main1",
        )


def test_card_instance_v2_exports_only_viewer_scoped_aliases() -> None:
    snapshot = _snapshot()
    zones = []
    for zone in snapshot.zones:
        projected_zone = dict(zone)
        cards = []
        for raw_card in zone["cards"]:
            card = dict(raw_card)
            card["persistent_instance_id"] = (
                f"corecard_private_{card['controller']}_{card['location']}_{card['slot']}"
            )
            card["player_view_instance_ids"] = {
                "0": f"viewcard_{card['controller']}_{card['location']}_{card['slot']}_viewer0",
                "1": f"viewcard_{card['controller']}_{card['location']}_{card['slot']}_viewer1",
            }
            cards.append(card)
        projected_zone["cards"] = cards
        zones.append(projected_zone)
    snapshot = replace(
        snapshot,
        zones=tuple(zones),
        card_instance_schema_version=CARD_INSTANCE_SNAPSHOT_SCHEMA_VERSION,
    )

    observation = project_player_view_observation(
        snapshot, viewer=0, turn=1, phase="main1"
    )
    serialized = json.dumps(observation, sort_keys=True)

    assert "viewcard_0_2_0_viewer0" in serialized
    assert "corecard_private" not in serialized
    assert "viewer1" not in serialized
