"""Bridge boundary contracts."""

from ygo_effect_dsl.engine.bridge.decision import (
    Candidate,
    DecisionConstraints,
    DecisionContext,
    DecisionRequest,
    DecisionResponse,
    validate_decision_request,
    validate_decision_response,
)
from ygo_effect_dsl.engine.bridge.errors import (
    InvalidBridgeMessageError,
    InvalidBridgeResponseError,
    UnsupportedBridgeMessageError,
)
from ygo_effect_dsl.engine.bridge.mock import MockBridge

__all__ = [
    "Candidate",
    "DecisionConstraints",
    "DecisionContext",
    "DecisionRequest",
    "DecisionResponse",
    "InvalidBridgeMessageError",
    "InvalidBridgeResponseError",
    "MockBridge",
    "UnsupportedBridgeMessageError",
    "validate_decision_request",
    "validate_decision_response",
]
