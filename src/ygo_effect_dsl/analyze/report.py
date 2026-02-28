from __future__ import annotations

from typing import Any

from ygo_effect_dsl.analyze.quality import collect_quality
from ygo_effect_dsl.analyze.stats import collect_stats


def build_report(cards: list[dict[str, Any]], validate_errors: int = 0) -> dict[str, Any]:
    return {
        "stats": collect_stats(cards),
        "quality": collect_quality(cards),
        "validation": {"error_count": validate_errors},
    }
