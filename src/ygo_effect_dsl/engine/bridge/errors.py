"""Bridge-specific errors."""

from __future__ import annotations

from typing import Any, Mapping


class BridgeError(ValueError):
    """Base class for bridge boundary errors."""

    category = "bridge_error"

    def __init__(
        self, message: str, *, context: Mapping[str, Any] | None = None
    ) -> None:
        super().__init__(message)
        self.context = dict(context or {})


class InvalidBridgeMessageError(BridgeError):
    """Raised when a Message or Action-like dict has an invalid shape."""

    category = "invalid_message"


class UnsupportedBridgeMessageError(BridgeError):
    """Raised when a valid Message uses a message_type outside the V0.2 mock vocabulary."""

    category = "unsupported_message"


class InvalidBridgeResponseError(BridgeError):
    """Raised when a Python response does not match its DecisionRequest."""

    category = "invalid_response"
