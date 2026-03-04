from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ygo_effect_dsl.analyze.stats import collect_stats
from ygo_effect_dsl.validate.validator import validate_card_yaml


def _base_card(effect: dict) -> dict:
    return {
        "dsl_version": "0.0",
        "card": {"cid": 1, "name": {"en": "A", "ja": "B"}},
        "effects": [{"id": "1_001", "order": 1, "trigger": {}, "restriction": {}, "condition": {}, "cost": {}, **effect}],
    }


def test_validate_accepts_actions_without_action() -> None:
    payload = _base_card({"actions": [{"type": "draw", "n": 2}]})
    assert validate_card_yaml(payload) == []


def test_collect_stats_actions_count_with_legacy_fallback() -> None:
    cards = [
        _base_card({"actions": [{"type": "draw"}, {"type": "discard"}], "action": {"type": "draw"}}),
        _base_card({"action": {"type": "special_summon"}}),
    ]

    stats = collect_stats(cards)
    assert stats["actions_count"]["min"] == 1
    assert stats["actions_count"]["max"] == 2
    assert stats["actions_count"]["avg"] == 1.5
