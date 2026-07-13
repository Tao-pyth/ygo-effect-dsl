"""Bridge-specific errors."""


class BridgeError(ValueError):
    """Base class for bridge boundary errors."""


class InvalidBridgeMessageError(BridgeError):
    """Raised when a Message or Action-like dict has an invalid shape."""


class UnsupportedBridgeMessageError(BridgeError):
    """Raised when a valid Message uses a message_type outside the V0.2 mock vocabulary."""
