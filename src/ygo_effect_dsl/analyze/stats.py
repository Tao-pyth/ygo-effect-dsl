from __future__ import annotations

from typing import Any


def collect_stats(cards: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "cards": len(cards),
        "effects": sum(len(c.get("effects", [])) for c in cards if isinstance(c.get("effects"), list)),
    }
