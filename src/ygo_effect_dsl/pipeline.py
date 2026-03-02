from __future__ import annotations

import logging
from collections import Counter
from typing import Any

from ygo_effect_dsl.io_input import extract_card_fields
from ygo_effect_dsl.models import LoadedDictionary, StageOutcome, TransformResult
from ygo_effect_dsl.normalize import normalize_card_texts
from ygo_effect_dsl.rule_engine import RuleEngine

logger = logging.getLogger("ygo_effect_dsl")

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


def _split_sentences(text: str) -> list[str]:
    sentences: list[str] = []
    for chunk in text.split("."):
        stripped = chunk.strip()
        if stripped:
            sentences.append(f"{stripped}.")
    return sentences


def _build_candidates(text: str) -> dict[str, list[str]]:
    sentences = _split_sentences(text)
    colon_actions: list[str] = []
    semicolon_cost: list[str] = []
    semicolon_action: list[str] = []
    action_sentences: list[str] = []
    trigger_sentences: list[str] = []

    for sentence in sentences:
        if ":" in sentence:
            left, right = sentence.split(":", 1)
            trigger_sentences.append(f"{left.strip()}:")
            right = right.strip()
            if right:
                colon_actions.append(right)

        if ";" in sentence:
            left, right = sentence.split(";", 1)
            left = left.strip()
            right = right.strip()
            if left:
                semicolon_cost.append(f"{left};")
            if right:
                semicolon_action.append(right)

        if sentence.startswith("you can "):
            action_sentences.append(sentence)

    return {
        "sentences": sentences,
        "colon_actions": colon_actions,
        "semicolon_cost": semicolon_cost,
        "semicolon_action": semicolon_action,
        "action_sentences": action_sentences,
        "trigger_sentences": trigger_sentences,
    }


def _apply_candidates(
    candidates: list[str],
    rules: list[Any],
    payload: dict[str, Any],
    params: dict[str, list[Any]],
    engine: RuleEngine,
) -> tuple[dict[str, Any], list[str], list[str]]:
    out = payload
    hits: list[str] = []
    unmatched: list[str] = []
    for fragment in candidates:
        out, fragment_hits = engine.apply_rules(fragment, rules, out, params)
        if fragment_hits:
            hits.extend(fragment_hits)
        else:
            unmatched.append(fragment)
    return out, hits, unmatched


def transform_card(card: dict[str, Any], dictionary: LoadedDictionary, engine: RuleEngine) -> TransformResult:
    fields = extract_card_fields(card)
    output = _base_output(fields, {})
    effect = output["effects"][0]

    normalize_source = {
        "card_text_en": effect["meta"].get("raw_text_en", ""),
        "card_text_ja": effect["meta"].get("raw_text_ja", ""),
        "card_info_en": "",
        "card_info_ja": "",
    }
    normalized = normalize_card_texts(normalize_source, dictionary.vocab)
    output["meta"]["norm"] = normalized.as_dict()

    candidates = _build_candidates(normalized.text_en)
    if logger.isEnabledFor(logging.DEBUG):
        logger.debug("cid=%s candidates=%s", fields.get("cid", ""), candidates)

    outcomes: dict[str, StageOutcome] = {}

    output, restriction_hits, restriction_unmatched = _apply_candidates(
        candidates["sentences"],
        dictionary.rules_by_stage.get("restriction_global", []),
        output,
        normalized.params,
        engine,
    )
    outcomes["restriction"] = StageOutcome(
        stage="restriction",
        matched=bool(restriction_hits),
        matched_rule_ids=restriction_hits,
        unmatched_fragments=restriction_unmatched,
    )

    cost_payload, cost_hits, cost_unmatched = _apply_candidates(
        candidates["semicolon_cost"],
        dictionary.rules_by_stage.get("cost", []),
        {"cost": effect["cost"]},
        normalized.params,
        engine,
    )
    effect["cost"] = cost_payload.get("cost", {})
    outcomes["cost"] = StageOutcome(
        stage="cost",
        matched=bool(cost_hits),
        matched_rule_ids=cost_hits,
        unmatched_fragments=cost_unmatched,
    )

    action_candidates = candidates["colon_actions"] + candidates["semicolon_action"] + candidates["action_sentences"] + candidates["sentences"]
    action_payload, action_hits, action_unmatched = _apply_candidates(
        action_candidates,
        dictionary.rules_by_stage.get("action", []),
        {"action": effect["action"]},
        normalized.params,
        engine,
    )
    effect["action"] = action_payload.get("action", {})
    outcomes["action"] = StageOutcome(
        stage="action",
        matched=bool(action_hits),
        matched_rule_ids=action_hits,
        unmatched_fragments=action_unmatched,
    )

    trigger_candidates = candidates["trigger_sentences"] or candidates["sentences"]
    trigger_payload, trigger_hits, trigger_unmatched = _apply_candidates(
        trigger_candidates,
        dictionary.rules_by_stage.get("trigger", []),
        {"trigger": effect["trigger"], "condition": effect["condition"]},
        normalized.params,
        engine,
    )
    effect["trigger"] = trigger_payload.get("trigger", {})
    effect["condition"] = trigger_payload.get("condition", effect["condition"])
    outcomes["trigger"] = StageOutcome(
        stage="trigger",
        matched=bool(trigger_hits),
        matched_rule_ids=trigger_hits,
        unmatched_fragments=trigger_unmatched,
    )

    if logger.isEnabledFor(logging.DEBUG):
        for stage, outcome in outcomes.items():
            logger.debug("cid=%s stage=%s matched_rule_ids=%s", fields.get("cid", ""), stage, outcome.matched_rule_ids)

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
