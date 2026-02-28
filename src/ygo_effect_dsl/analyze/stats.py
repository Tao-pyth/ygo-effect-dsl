from __future__ import annotations
from typing import Any

def collect_stats(cards: list[dict[str, Any]]) -> dict[str, Any]:
    n_cards = len(cards)
    n_effects = sum(len((c.get("effects") or [])) for c in cards)

    def miss_rate_str(path_fn):
        miss = 0
        for c in cards:
            v = path_fn(c)
            if not isinstance(v, str) or v == "":
                miss += 1
        return {"missing": miss, "total": n_cards, "rate": (miss / n_cards) if n_cards else 0.0}

    stats = {
        "cards": n_cards,
        "effects": n_effects,
        "missing": {
            "name_ja": miss_rate_str(lambda c: ((c.get("name") or {}).get("ja"))),
            "name_en": miss_rate_str(lambda c: ((c.get("name") or {}).get("en"))),
            "text_ja": miss_rate_str(lambda c: ((c.get("text") or {}).get("ja"))),
            "text_en": miss_rate_str(lambda c: ((c.get("text") or {}).get("en"))),
        },
    }
    return stats
