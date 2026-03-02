from __future__ import annotations

from collections import Counter
from typing import Any

from ygo_effect_dsl.io_input import extract_card_fields
from ygo_effect_dsl.models import LoadedDictionary, StageOutcome, TransformResult
from ygo_effect_dsl.normalize import normalize_card_texts
from ygo_effect_dsl.rule_engine import RuleEngine


EMPTY_EFFECT = {
    "trigger": {},
    "restriction": {},
    "condition": {},
    "cost": {},
    "action": {},
}


def _base_output(card_fields: dict[str, Any], norm: dict[str, Any]) -> dict[str, Any]:
    cid = card_fields.get("cid", "")
    effect_id = f"{cid}_001" if cid else "0_001"
    return {
        "dsl_version": "0.0",
        "card": {
            "cid": cid,
            "name": {
                "en": card_fields.get("name_en", ""),
                "ja": card_fields.get("name_ja", ""),
            },
            "text": {
                "en": card_fields.get("card_text_en", ""),
                "ja": card_fields.get("card_text_ja", ""),
            },
            "info": {
                "en": card_fields.get("card_info_en", ""),
                "ja": card_fields.get("card_info_ja", ""),
            },
        },
        "effects": [{"id": effect_id, "order": 1, **EMPTY_EFFECT, "meta": {"raw_text_en": card_fields.get("card_text_en", ""), "raw_text_ja": card_fields.get("card_text_ja", "")}}],
        "meta": {
            "norm": norm,
            "restrictions": {"global": {}},
        },
    }


def _split_skeleton(text: str) -> dict[str, str]:
    trigger = ""
    rest = text
    if ":" in text:
        trigger, rest = text.split(":", 1)
        trigger = trigger.strip() + ":"
        rest = rest.strip()

    cost = ""
    action = rest
    if ";" in rest:
        cost, action = rest.split(";", 1)
        cost = cost.strip() + ";"
        action = action.strip()
    return {"trigger": trigger, "cost": cost, "action": action}


def transform_card(card: dict[str, Any], dictionary: LoadedDictionary, engine: RuleEngine) -> TransformResult:
    fields = extract_card_fields(card)
    normalized = normalize_card_texts(fields, dictionary.vocab)
    norm_dict = normalized.as_dict()
    output = _base_output(fields, norm_dict)
    effect = output["effects"][0]

    outcomes: dict[str, StageOutcome] = {}

    output, restriction_hits = engine.apply_rules(
        normalized.text_en,
        dictionary.rules_by_stage.get("restriction_global", []),
        output,
        normalized.params,
    )
    outcomes["restriction"] = StageOutcome(
        stage="restriction",
        matched=bool(restriction_hits),
        matched_rule_ids=restriction_hits,
        unmatched_fragment="" if restriction_hits else normalized.text_en,
    )

    fragments = _split_skeleton(normalized.text_en)

    cost_payload, cost_hits = engine.apply_rules(
        fragments["cost"],
        dictionary.rules_by_stage.get("cost", []),
        {"cost": effect["cost"]},
        normalized.params,
    )
    effect["cost"] = cost_payload.get("cost", {})
    outcomes["cost"] = StageOutcome(
        stage="cost",
        matched=bool(cost_hits),
        matched_rule_ids=cost_hits,
        unmatched_fragment="" if cost_hits or not fragments["cost"] else fragments["cost"],
    )

    action_payload, action_hits = engine.apply_rules(
        fragments["action"],
        dictionary.rules_by_stage.get("action", []),
        {"action": effect["action"]},
        normalized.params,
    )
    effect["action"] = action_payload.get("action", {})
    outcomes["action"] = StageOutcome(
        stage="action",
        matched=bool(action_hits),
        matched_rule_ids=action_hits,
        unmatched_fragment="" if action_hits or not fragments["action"] else fragments["action"],
    )

    trigger_payload, trigger_hits = engine.apply_rules(
        fragments["trigger"],
        dictionary.rules_by_stage.get("trigger", []),
        {"trigger": effect["trigger"], "condition": effect["condition"]},
        normalized.params,
    )
    effect["trigger"] = trigger_payload.get("trigger", {})
    effect["condition"] = trigger_payload.get("condition", effect["condition"])
    outcomes["trigger"] = StageOutcome(
        stage="trigger",
        matched=bool(trigger_hits),
        matched_rule_ids=trigger_hits,
        unmatched_fragment="" if trigger_hits or not fragments["trigger"] else fragments["trigger"],
    )

    output["effects"][0] = effect
    return TransformResult(cid=str(fields.get("cid", "")), output=output, stage_outcomes=outcomes)


def count_action_types(cards: list[dict[str, Any]]) -> dict[str, int]:
    counter: Counter[str] = Counter()
    for card in cards:
        for effect in card.get("effects", []):
            action = effect.get("action", {}) if isinstance(effect, dict) else {}
            if isinstance(action, dict):
                action_type = action.get("type")
                if isinstance(action_type, str) and action_type:
                    counter[action_type] += 1
    return dict(counter.most_common())
