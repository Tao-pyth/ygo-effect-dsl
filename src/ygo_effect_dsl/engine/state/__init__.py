"""Canonical State identity contracts."""

from ygo_effect_dsl.engine.state.equivalence import (
    APPROXIMATION_POLICY_SCHEMA_VERSION,
    ApproximationPolicy,
    StateEquivalenceError,
    StateKey,
    StateKeyPurpose,
    build_state_key,
    exact_state_equivalent,
)
from ygo_effect_dsl.engine.state.identity import (
    STATE_ID_SCHEMA_VERSION,
    CanonicalState,
    InformationMode,
    StateIdentityCompleteness,
)
from ygo_effect_dsl.engine.state.rules import (
    RULE_STATE_SCHEMA_VERSION,
    VISIBILITY_STATE_SCHEMA_VERSION,
    ConstraintExpiration,
    EffectUsage,
    ExpirationBoundary,
    PlayerSummonState,
    RuleState,
    StateCoordinate,
    TimedConstraint,
    VisibilityState,
)

__all__ = [
    "APPROXIMATION_POLICY_SCHEMA_VERSION",
    "ApproximationPolicy",
    "STATE_ID_SCHEMA_VERSION",
    "CanonicalState",
    "ConstraintExpiration",
    "EffectUsage",
    "ExpirationBoundary",
    "InformationMode",
    "PlayerSummonState",
    "RULE_STATE_SCHEMA_VERSION",
    "RuleState",
    "StateCoordinate",
    "StateEquivalenceError",
    "StateIdentityCompleteness",
    "StateKey",
    "StateKeyPurpose",
    "TimedConstraint",
    "VISIBILITY_STATE_SCHEMA_VERSION",
    "VisibilityState",
    "build_state_key",
    "exact_state_equivalent",
]
