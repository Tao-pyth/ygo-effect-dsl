from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ygo_effect_dsl.engine.bridge import InvalidBridgeMessageError, MockBridge, UnsupportedBridgeMessageError


def test_mock_bridge_converts_message_to_action_like_dict() -> None:
    bridge = MockBridge()
    message = {
        "message_type": "select_card",
        "payload": {"candidates": ["card-1", "card-2"], "min": 1, "max": 1},
        "source": "mock",
        "sequence": 0,
    }

    action = bridge.message_to_action(message)

    assert action == {
        "action_type": "select_card",
        "payload": {"candidates": ["card-1", "card-2"], "min": 1, "max": 1},
        "source": {
            "kind": "bridge_message",
            "message_source": "mock",
            "message_type": "select_card",
            "sequence": 0,
        },
    }


def test_mock_bridge_converts_action_like_dict_to_core_input() -> None:
    bridge = MockBridge()
    action = {
        "action_type": "select_card",
        "payload": {"candidates": ["card-1", "card-2"], "min": 1, "max": 1},
        "source": {"kind": "bridge_message", "message_type": "select_card", "sequence": 0},
    }

    core_input = bridge.action_to_core_input(action, response_payload={"selected": ["card-1"]})

    assert core_input == {
        "input_type": "select_card",
        "payload": {"selected": ["card-1"]},
        "source_action_type": "select_card",
    }


@pytest.mark.parametrize(
    "message",
    [
        {},
        {"message_type": "select_card"},
        {"payload": {}},
        {"message_type": 1, "payload": {}},
        {"message_type": "select_card", "payload": []},
    ],
)
def test_mock_bridge_rejects_invalid_message_shape(message: dict) -> None:
    with pytest.raises(InvalidBridgeMessageError):
        MockBridge().message_to_action(message)


def test_mock_bridge_distinguishes_unsupported_message() -> None:
    message = {"message_type": "unknown_request", "payload": {}}

    with pytest.raises(UnsupportedBridgeMessageError, match="unknown_request"):
        MockBridge().message_to_action(message)


@pytest.mark.parametrize(
    "action",
    [
        {},
        {"action_type": "select_card"},
        {"payload": {}},
        {"action_type": "select_card", "payload": []},
    ],
)
def test_mock_bridge_rejects_invalid_action_shape(action: dict) -> None:
    with pytest.raises(InvalidBridgeMessageError):
        MockBridge().action_to_core_input(action)
