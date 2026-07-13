"""Bridge mock/interface baseline for V0.2."""

from ygo_effect_dsl.engine.bridge.errors import InvalidBridgeMessageError, UnsupportedBridgeMessageError
from ygo_effect_dsl.engine.bridge.mock import MockBridge

__all__ = [
    "InvalidBridgeMessageError",
    "MockBridge",
    "UnsupportedBridgeMessageError",
]
