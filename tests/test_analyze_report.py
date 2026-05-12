from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ygo_effect_dsl.analyze.report import build_report
from ygo_effect_dsl.errors import DslError


ROOT = Path(__file__).resolve().parents[1]
GOLDEN_PATH = ROOT / "tests" / "golden" / "analyze_dashboard" / "expected_report.json"


def _base_card(cid: int, effects: list[dict] | None, trace: list[dict] | None = None) -> dict:
    card = {
        "dsl_version": "0.0",
        "card": {"cid": cid, "name": {"en": f"Card {cid}", "ja": f"Card {cid} JP"}},
        "effects": effects,
    }
    if trace is not None:
        card["meta"] = {"action_candidate_trace": trace}
    return card


def _effect(**overrides: object) -> dict:
    payload = {
        "id": "effect_001",
        "order": 1,
        "trigger": {},
        "restriction": {},
        "condition": {},
        "cost": {},
        "action": {},
        "actions": [],
    }
    payload.update(overrides)
    return payload


def test_analysis_report_dashboard_fields_match_golden() -> None:
    cards = [
        _base_card(
            1,
            [
                _effect(
                    condition={"if": "controlled monster exists"},
                    actions=[{"type": "destroy", "target_id": "t1"}, {"type": "draw"}],
                    targets=[{"id": "t1", "count": 1, "selector": {"kind": "card"}}],
                )
            ],
            trace=[{"fragment": "cannot parse A", "matched_rule_ids": []}],
        ),
        _base_card(
            2,
            [
                _effect(
                    trigger={"event": "activation"},
                    actions=[{"type": "banish", "target_id": "missing"}],
                    targets=[{"id": "t2", "count": 1, "selector": {"kind": "monster"}}],
                )
            ],
            trace=[
                {"fragment": "cannot parse A", "matched_rule_ids": []},
                {"fragment": "cannot parse B", "matched_rule_ids": []},
                {"fragment": "matched fragment", "matched_rule_ids": ["rule_001"]},
            ],
        ),
        _base_card(3, [_effect(action={"type": "draw"})]),
        _base_card(4, []),
    ]
    diagnostics = [
        DslError("card.cid", "required", "cid is required"),
        DslError("effects[0].actions[0].type", "unknown_action", "unknown action", "warning"),
        DslError("effects[1].actions[0].type", "unknown_action", "unknown action", "warning"),
        DslError("meta", "note", "informational note", "info"),
    ]

    actual = build_report(cards, diagnostics=diagnostics)
    expected = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))

    assert actual == expected
