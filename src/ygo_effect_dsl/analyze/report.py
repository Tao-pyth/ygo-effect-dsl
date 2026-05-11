from __future__ import annotations

from typing import Any

from ygo_effect_dsl.errors import DslError
from ygo_effect_dsl.analyze.quality import collect_quality
from ygo_effect_dsl.analyze.stats import collect_stats


def _diagnostics_report(diagnostics: list[DslError]) -> dict[str, Any]:
    severity_counts = {"error": 0, "warning": 0, "info": 0}
    code_counts: dict[str, int] = {}
    for diagnostic in diagnostics:
        severity_counts[diagnostic.severity] = severity_counts.get(diagnostic.severity, 0) + 1
        key = f"{diagnostic.severity}:{diagnostic.code}"
        code_counts[key] = code_counts.get(key, 0) + 1
    return {
        "severity_counts": severity_counts,
        "code_counts": dict(sorted(code_counts.items())),
    }


def build_report(
    cards: list[dict[str, Any]],
    validate_errors: int = 0,
    diagnostics: list[DslError] | None = None,
) -> dict[str, Any]:
    if diagnostics is None:
        diagnostics = [DslError("", "legacy_error_count", "legacy validation error count") for _ in range(validate_errors)]
    return {
        "stats": collect_stats(cards),
        "quality": collect_quality(cards),
        "validation": _diagnostics_report(diagnostics),
    }
