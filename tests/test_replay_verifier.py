from __future__ import annotations

from copy import deepcopy

import pytest

from ygo_effect_dsl.engine.replay import (
    ReplaySignatureMismatchError,
    assert_replay_request_signatures,
    first_request_difference,
    request_signature_identity,
)


def _request(candidate_id: str, *, label: str = "Display label") -> dict[str, object]:
    return {
        "request_id": "display-only-request-id",
        "request_signature": f"req_{candidate_id}",
        "request_schema_version": "0.3a",
        "request_type": "select_card",
        "player": 0,
        "candidates": [
            {
                "candidate_id": candidate_id,
                "kind": "card",
                "label": label,
                "card_ref": {"controller": 0, "location": 2, "sequence": 0},
                "effect_ref": None,
                "payload": {"response_index": 0},
            }
        ],
        "constraints": {
            "allow_duplicates": False,
            "max_selections": 1,
            "min_selections": 1,
            "ordered": False,
            "required": True,
        },
        "context": {
            "chain": [],
            "extra": {},
            "phase": "main1",
            "priority_player": 0,
            "request_source": "ocgcore",
            "turn_player": 0,
            "version_metadata": {"ocgcore_api": "11.0"},
            "visible_board": {},
        },
    }


def _replay(request: dict[str, object]) -> dict[str, object]:
    return {
        "events": [
            {
                "step": 0,
                "request_signature": request["request_signature"],
                "request": request,
            }
        ]
    }


def test_request_identity_excludes_request_id_signature_and_display_label() -> None:
    first = _request("card:0", label="Original")
    second = deepcopy(first)
    second["request_id"] = "renamed"
    second["request_signature"] = "req_display-change"
    second["candidates"][0]["label"] = "Renamed"

    assert request_signature_identity(first) == request_signature_identity(second)
    assert first_request_difference(first, second) is None


def test_replay_verifier_reports_first_candidate_identity_difference() -> None:
    recorded_request = _request("card:0")
    current_request = _request("card:1")

    with pytest.raises(ReplaySignatureMismatchError) as captured:
        assert_replay_request_signatures(
            _replay(recorded_request), _replay(current_request)
        )

    assert captured.value.step == 0
    assert captured.value.path == "candidates[0].candidate_id"
    assert captured.value.recorded == "card:0"
    assert captured.value.current == "card:1"
    assert "first difference" in str(captured.value)


def test_replay_verifier_reports_request_count_before_field_comparison() -> None:
    with pytest.raises(ReplaySignatureMismatchError) as captured:
        assert_replay_request_signatures(_replay(_request("card:0")), {"events": []})

    assert captured.value.path == "events.length"
    assert captured.value.recorded == 1
    assert captured.value.current == 0
