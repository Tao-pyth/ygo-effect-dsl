from __future__ import annotations

from typing import Any


EFFECT_KEYS = ("trigger", "restriction", "condition", "cost", "action", "actions")


def collect_quality(cards: list[dict[str, Any]]) -> dict[str, Any]:
    total_cards = len(cards)
    cards_effects_empty = 0

    total_effects = 0
    empty_blocks = {k: 0 for k in EFFECT_KEYS}

    for card in cards:
        effects = card.get("effects")
        if not isinstance(effects, list) or len(effects) == 0:
            cards_effects_empty += 1
            continue

        for effect in effects:
            total_effects += 1
            if not isinstance(effect, dict):
                for key in EFFECT_KEYS:
                    empty_blocks[key] += 1
                continue

            for key in ("trigger", "restriction", "condition", "cost"):
                block = effect.get(key)
                if not isinstance(block, dict) or block == {}:
                    empty_blocks[key] += 1

            action = effect.get("action")
            if not isinstance(action, dict) or action == {}:
                empty_blocks["action"] += 1

            actions = effect.get("actions")
            if not isinstance(actions, list) or not any(isinstance(row, dict) and row for row in actions):
                # fallback: old data with only action should count as non-empty actions.
                if not (isinstance(action, dict) and action):
                    empty_blocks["actions"] += 1

    effects_empty_ratio = (cards_effects_empty / total_cards) if total_cards else 0.0
    block_empty_ratio = {
        key: (count / total_effects) if total_effects else 0.0 for key, count in empty_blocks.items()
    }

    return {
        "total_cards": total_cards,
        "total_effects": total_effects,
        "effects_empty_cards": cards_effects_empty,
        "effects_empty_ratio": effects_empty_ratio,
        "empty_block_counts": empty_blocks,
        "empty_block_ratio": block_empty_ratio,
    }
