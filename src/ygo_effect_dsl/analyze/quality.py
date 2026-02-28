from __future__ import annotations
from typing import Any, DefaultDict
from collections import defaultdict

def collect_quality(cards: list[dict[str, Any]]) -> dict[str, Any]:
    trigger_empty = 0
    cards_effects_empty = 0

    action_kind_freq: DefaultDict[str, int] = defaultdict(int)

    for c in cards:
        effects = c.get("effects") or []
        if not effects:
            cards_effects_empty += 1
            continue

        for e in effects:
            trig = (e.get("trigger") or {})
            if not (isinstance(trig, dict) and trig.get("kind")):
                trigger_empty += 1

            for a in (e.get("action") or []):
                if isinstance(a, dict):
                    k = a.get("kind") or ""
                    action_kind_freq[k] += 1

    return {
        "effects_empty_cards": cards_effects_empty,
        "trigger_kind_empty_effects": trigger_empty,
        "action_kind_frequency": dict(sorted(action_kind_freq.items(), key=lambda kv: (-kv[1], kv[0]))),
    }
