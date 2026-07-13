from __future__ import annotations

from typing import Any

from ygo_effect_dsl.engine.bridge.errors import InvalidBridgeMessageError, UnsupportedBridgeMessageError


DEFAULT_SUPPORTED_MESSAGE_TYPES = frozenset(
    {
        "activate_effect",
        "end_turn",
        "normal_summon",
        "select_card",
        "select_option",
        "special_summon",
    }
)


def _require_mapping(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise InvalidBridgeMessageError(f"{path} must be object")
    return value


def _require_string(value: Any, path: str) -> str:
    if not isinstance(value, str):
        raise InvalidBridgeMessageError(f"{path} must be string")
    return value


class MockBridge:
    """V0.2 bridge mock that converts shapes without judging legality."""

    def __init__(self, supported_message_types: set[str] | frozenset[str] | None = None):
        self.supported_message_types = supported_message_types or DEFAULT_SUPPORTED_MESSAGE_TYPES

    def message_to_action(self, message: dict[str, Any]) -> dict[str, Any]:
        message_dict = _require_mapping(message, "message")
        if "message_type" not in message_dict:
            raise InvalidBridgeMessageError("message.message_type is required")
        if "payload" not in message_dict:
            raise InvalidBridgeMessageError("message.payload is required")
        message_type = _require_string(message_dict["message_type"], "message.message_type")
        if message_type not in self.supported_message_types:
            raise UnsupportedBridgeMessageError(f"unsupported message_type: {message_type}")
        payload = _require_mapping(message_dict["payload"], "message.payload")
        source: dict[str, Any] = {
            "kind": "bridge_message",
            "message_type": message_type,
        }
        if "sequence" in message_dict:
            source["sequence"] = message_dict["sequence"]
        if "source" in message_dict:
            source["message_source"] = message_dict["source"]
        return {
            "action_type": message_type,
            "payload": dict(payload),
            "source": source,
        }

    def action_to_core_input(
        self,
        action: dict[str, Any],
        response_payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        action_dict = _require_mapping(action, "action")
        if "action_type" not in action_dict:
            raise InvalidBridgeMessageError("action.action_type is required")
        if "payload" not in action_dict:
            raise InvalidBridgeMessageError("action.payload is required")
        action_type = _require_string(action_dict["action_type"], "action.action_type")
        _require_mapping(action_dict["payload"], "action.payload")
        if response_payload is None:
            response_payload = dict(action_dict["payload"])
        else:
            response_payload = dict(_require_mapping(response_payload, "response_payload"))
        return {
            "input_type": action_type,
            "payload": response_payload,
            "source_action_type": action_type,
        }
