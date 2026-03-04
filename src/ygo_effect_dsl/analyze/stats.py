from __future__ import annotations

from typing import Any


def _effect_actions_count(effect: dict[str, Any]) -> int:
    actions = effect.get("actions")
    if isinstance(actions, list):
        return sum(1 for row in actions if isinstance(row, dict) and row)

    action = effect.get("action")
    if isinstance(action, dict) and action:
        return 1
    return 0


def collect_stats(cards: list[dict[str, Any]]) -> dict[str, Any]:
    effects_count = sum(len(c.get("effects", [])) for c in cards if isinstance(c.get("effects"), list))

    actions_per_effect: list[int] = []
    for card in cards:
        effects = card.get("effects")
        if not isinstance(effects, list):
            continue
        for effect in effects:
            if isinstance(effect, dict):
                actions_per_effect.append(_effect_actions_count(effect))

    if actions_per_effect:
        avg = sum(actions_per_effect) / len(actions_per_effect)
        min_count = min(actions_per_effect)
        max_count = max(actions_per_effect)
    else:
        avg = 0.0
        min_count = 0
        max_count = 0

    return {
        "cards": len(cards),
        "effects": effects_count,
        "actions_count": {
            "avg": avg,
            "min": min_count,
            "max": max_count,
        },
    }
