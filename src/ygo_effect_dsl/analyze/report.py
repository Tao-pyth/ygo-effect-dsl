from __future__ import annotations
from typing import Any
from ygo_effect_dsl.analyze.stats import collect_stats
from ygo_effect_dsl.analyze.quality import collect_quality

def build_report(cards: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "stats": collect_stats(cards),
        "quality": collect_quality(cards),
    }
