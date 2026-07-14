"""Route information DSL contracts.

The Route DSL records reproducible routes produced by ocgcore-backed execution.
It does not describe or execute card effects.
"""

from ygo_effect_dsl.route_dsl.analysis import (
    ROUTE_NORMALIZATION_SCHEMA_VERSION,
    RouteTargetBoard,
    normalize_and_explain_routes,
)
from ygo_effect_dsl.route_dsl.validator import (
    ROUTE_DSL_NAME,
    ROUTE_DSL_SCHEMA_VERSION,
    RouteValidationIssue,
    assert_valid_route_document,
    load_route_document,
    validate_route_document,
)

__all__ = [
    "ROUTE_DSL_NAME",
    "ROUTE_DSL_SCHEMA_VERSION",
    "ROUTE_NORMALIZATION_SCHEMA_VERSION",
    "RouteTargetBoard",
    "RouteValidationIssue",
    "assert_valid_route_document",
    "load_route_document",
    "normalize_and_explain_routes",
    "validate_route_document",
]
