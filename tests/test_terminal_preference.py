from __future__ import annotations

import pytest

from ygo_effect_dsl.engine.evaluation import (
    TerminalPreferenceProfile,
    build_terminal_board_projection,
    evaluate_terminal_preferences,
)


CARD = 10000


def _board() -> dict[str, object]:
    return {
        "public_cards": [
            {
                "code": CARD,
                "controller": 0,
                "location": 2,
                "position": 1,
                "slot": 0,
            },
            {
                "code": CARD,
                "controller": 0,
                "location": "monster_zone",
                "position": 4,
                "slot": 1,
            },
            {
                "code": CARD,
                "controller": 0,
                "location": "spell_trap_zone",
                "position": 8,
                "slot": 2,
            },
            {
                "code": CARD,
                "controller": 0,
                "location": "graveyard",
                "position": 1,
                "slot": 0,
            },
            {
                "controller": 1,
                "hidden": True,
                "location": "hand",
                "slot": 0,
            },
        ],
        "state_hash": "state_terminal",
    }


def test_terminal_projection_normalizes_location_position_and_redaction() -> None:
    projection = build_terminal_board_projection(_board())
    payload = projection.to_dict()

    assert payload["schema_version"] == "terminal-board-projection-v1"
    assert [card["location"] for card in payload["cards"]] == [
        "HAND",
        "MONSTER_ZONE",
        "SPELL_TRAP_ZONE",
        "GRAVEYARD",
        "HAND",
    ]
    assert [card["position"] for card in payload["cards"]] == [
        "FACE_UP",
        "FACE_UP",
        "FACE_DOWN",
        "FACE_UP",
        "ANY",
    ]
    redacted = payload["cards"][-1]
    assert redacted["visibility"] == "redacted"
    assert redacted["card_code"] is None
    assert redacted["redacted_identity"].startswith("redactedcard_")


def test_preference_profile_is_content_addressed_and_clone_on_edit() -> None:
    profile = TerminalPreferenceProfile.from_mapping(
        {
            "name": "terminal preference",
            "rules": [
                {
                    "card_code": CARD,
                    "controller": 0,
                    "enabled": True,
                    "location": "HAND",
                    "max_count": None,
                    "min_count": 1,
                    "position": "ANY",
                    "rule_id": "hand-copy",
                    "scoring_mode": "once",
                    "weight": 3,
                }
            ],
            "schema_version": "terminal-preference-profile-v1",
        }
    )
    edited = profile.clone_with(
        rules=(
            {
                **profile.to_dict()["rules"][0],
                "weight": 4,
            },
        )
    )

    assert profile.profile_id.startswith("termpref_")
    assert edited.profile_id.startswith("termpref_")
    assert profile.profile_id != edited.profile_id
    assert profile.to_dict()["rules"][0]["weight"] == 3
    assert edited.to_dict()["rules"][0]["weight"] == 4


def test_terminal_preference_scores_location_position_modes_and_breakdown() -> None:
    projection = build_terminal_board_projection(_board())
    profile = TerminalPreferenceProfile.from_mapping(
        {
            "name": "terminal scoring",
            "rules": [
                {
                    "card_code": CARD,
                    "controller": 0,
                    "enabled": True,
                    "location": "HAND",
                    "max_count": None,
                    "min_count": 1,
                    "position": "ANY",
                    "rule_id": "hand-once",
                    "scoring_mode": "once",
                    "weight": 5,
                },
                {
                    "card_code": CARD,
                    "controller": 0,
                    "enabled": True,
                    "location": "MONSTER_ZONE",
                    "max_count": None,
                    "min_count": 1,
                    "position": "FACE_UP",
                    "rule_id": "monster-per-copy",
                    "scoring_mode": "per_copy",
                    "weight": 2,
                },
                {
                    "card_code": CARD,
                    "controller": 0,
                    "enabled": True,
                    "location": "SPELL_TRAP_ZONE",
                    "max_count": None,
                    "min_count": 1,
                    "position": "FACE_DOWN",
                    "rule_id": "set-threshold",
                    "scoring_mode": "threshold",
                    "weight": 7,
                },
                {
                    "card_code": CARD,
                    "controller": 0,
                    "enabled": True,
                    "location": "GRAVEYARD",
                    "max_count": None,
                    "min_count": 2,
                    "position": "ANY",
                    "rule_id": "grave-missing",
                    "scoring_mode": "once",
                    "weight": 99,
                },
                {
                    "card_code": CARD,
                    "controller": 1,
                    "enabled": True,
                    "location": "HAND",
                    "max_count": None,
                    "min_count": 1,
                    "position": "ANY",
                    "rule_id": "redacted-opponent-hand",
                    "scoring_mode": "once",
                    "weight": 99,
                },
            ],
            "schema_version": "terminal-preference-profile-v1",
        }
    )

    result = evaluate_terminal_preferences(
        projection,
        profile,
        base_score=10,
        randomness_penalty=3,
    )

    assert result["schema_version"] == "terminal-preference-evaluation-v1"
    assert result["base_score"] == 10
    assert result["preference_score"] == 14
    assert result["randomness_penalty"] == 3
    assert result["terminal_composite_score"] == 21
    assert {component["rule_id"]: component["applied_value"] for component in result["components"]} == {
        "hand-once": 5,
        "monster-per-copy": 2,
        "set-threshold": 7,
        "grave-missing": 0,
        "redacted-opponent-hand": 0,
    }
    assert result["components"][-1]["match_status"] == "redacted_or_unknown"


def test_preference_rejects_invalid_location_position_combinations() -> None:
    with pytest.raises(ValueError, match="FACE_DOWN is only valid for field"):
        TerminalPreferenceProfile.from_mapping(
            {
                "name": "invalid",
                "rules": [
                    {
                        "card_code": CARD,
                        "controller": 0,
                        "enabled": True,
                        "location": "HAND",
                        "max_count": None,
                        "min_count": 1,
                        "position": "FACE_DOWN",
                        "rule_id": "hidden-hand",
                        "scoring_mode": "once",
                        "weight": 1,
                    }
                ],
                "schema_version": "terminal-preference-profile-v1",
            }
        )
