from __future__ import annotations

import logging
import re
from collections import Counter
from typing import Any

from ygo_effect_dsl.io_input import extract_card_fields
from ygo_effect_dsl.models import LoadedDictionary, StageOutcome, TransformResult
from ygo_effect_dsl.normalize import normalize_card_texts
from ygo_effect_dsl.rule_engine import RuleEngine

logger = logging.getLogger("ygo_effect_dsl")

RESTRICTION_FORCE_PATTERNS = (
    re.compile(r"^you can only (use|activate|special summon|control)\b"),
    re.compile(r"^once per (turn|duel):\b"),
    re.compile(r"^cannot be\b"),
    re.compile(r"^you cannot\b"),
    re.compile(r"^must\b"),
    re.compile(r"^also\b.*\bonly\b.*\bonce per turn\b"),
)
ACTION_PRIORITY_PATTERNS = (
    re.compile(r"^(you can )?(add|special summon|draw|discard|destroy|banish|send|return|shuffle)\b"),
    re.compile(r"^(you can )?target\b"),
)

EMPTY_EFFECT = {
    "trigger": {},
    "restriction": {},
    "condition": {},
    "cost": {},
    "actions": [],
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
            "props": card_fields.get("card_props", {}),
        },
        "effects": [{"id": effect_id, "order": 1, **EMPTY_EFFECT}],
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
    restriction_candidates: list[str] = []
    cost_candidates: list[str] = []
    action_candidates: list[str] = []
    trigger_sentences: list[str] = []

    for sentence in sentences:
        if ":" in sentence:
            left, right = sentence.split(":", 1)
            trigger_sentences.append(f"{left.strip()}:")
            right = right.strip()
            if right:
                action_candidates.append(right)

        if ";" in sentence:
            left, right = sentence.split(";", 1)
            left = left.strip()
            right = right.strip()
            if left:
                cost_candidates.append(f"{left};")
            if right:
                action_candidates.append(right)

        normalized_sentence = sentence.strip()
        is_restriction = any(pattern.search(normalized_sentence) for pattern in RESTRICTION_FORCE_PATTERNS) or (
            "once per turn" in normalized_sentence
        )
        if is_restriction:
            restriction_candidates.append(sentence)
            continue

        if any(pattern.search(normalized_sentence) for pattern in ACTION_PRIORITY_PATTERNS):
            action_candidates.append(sentence)

    return {
        "sentences": sentences,
        "restriction_candidates": restriction_candidates,
        "cost_candidates": cost_candidates,
        "action_candidates": action_candidates,
        "trigger_sentences": trigger_sentences,
    }


def _apply_candidates(
    candidates: list[tuple[str, str]],
    rules: list[Any],
    payload: dict[str, Any],
    params: dict[str, list[Any]],
    engine: RuleEngine,
) -> tuple[dict[str, Any], list[str], list[dict[str, str]]]:
    out = payload
    hits: list[str] = []
    unmatched: list[dict[str, str]] = []
    for fragment, classified_as in candidates:
        out, fragment_hits = engine.apply_rules(fragment, rules, out, params)
        if fragment_hits:
            hits.extend(fragment_hits)
        else:
            unmatched.append({"fragment": fragment, "classified_as": classified_as})
    return out, hits, unmatched


def _apply_action_candidates(
    candidates: list[str],
    rules: list[Any],
    params: dict[str, list[Any]],
    engine: RuleEngine,
) -> tuple[list[dict[str, Any]], list[str], list[dict[str, Any]], list[dict[str, Any]]]:
    actions: list[dict[str, Any]] = []
    hits: list[str] = []
    details: list[dict[str, Any]] = []

    for index, fragment in enumerate(candidates):
        payload, fragment_hits = engine.apply_rules(fragment, rules, {"action": {}, "actions": []}, params)
        action_obj = payload.get("action", {})
        action_list = payload.get("actions", [])

        mapped_action_index: int | None = None
        if isinstance(action_list, list) and action_list:
            for row in action_list:
                if isinstance(row, dict) and row:
                    actions.append(row)
                    mapped_action_index = len(actions) - 1
        elif isinstance(action_obj, dict) and action_obj:
            actions.append(action_obj)
            mapped_action_index = len(actions) - 1

        details.append(
            {
                "fragment": fragment,
                "classified_as": "action",
                "candidate_index": index,
                "matched_rule_ids": fragment_hits,
                "mapped_action_index": mapped_action_index,
            }
        )

        if fragment_hits:
            hits.extend(fragment_hits)

    unmatched = [row for row in details if not row["matched_rule_ids"]]
    return actions, hits, unmatched, details


def transform_card(card: dict[str, Any], dictionary: LoadedDictionary, engine: RuleEngine) -> TransformResult:
    fields = extract_card_fields(card)
    output = _base_output(fields, {})
    effect = output["effects"][0]

    normalize_source = {
        "card_text_en": fields.get("card_text_en", ""),
        "card_text_ja": fields.get("card_text_ja", ""),
    }
    normalized = normalize_card_texts(normalize_source, dictionary.vocab)
    output["meta"]["norm"] = normalized.as_dict()

    candidates = _build_candidates(normalized.text_en)
    output["meta"]["candidates_count"] = {
        "sentences": len(candidates["sentences"]),
        "restriction": len(candidates["restriction_candidates"]),
        "cost": len(candidates["cost_candidates"]),
        "action": len(candidates["action_candidates"]),
    }
    if logger.isEnabledFor(logging.DEBUG):
        logger.debug("cid=%s candidates=%s", fields.get("cid", ""), candidates)

    outcomes: dict[str, StageOutcome] = {}

    output, restriction_hits, restriction_unmatched = _apply_candidates(
        [(fragment, "restriction") for fragment in candidates["restriction_candidates"]],
        dictionary.rules_by_stage.get("restriction_global", []),
        output,
        normalized.params,
        engine,
    )
    outcomes["restriction"] = StageOutcome(
        stage="restriction",
        matched=bool(restriction_hits),
        matched_rule_ids=restriction_hits,
        unmatched_fragments=[row["fragment"] for row in restriction_unmatched],
        unmatched_details=restriction_unmatched,
    )

    cost_payload, cost_hits, cost_unmatched = _apply_candidates(
        [(fragment, "cost") for fragment in candidates["cost_candidates"]],
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
        unmatched_fragments=[row["fragment"] for row in cost_unmatched],
        unmatched_details=cost_unmatched,
    )

    actions, action_hits, action_unmatched, action_details = _apply_action_candidates(
        candidates["action_candidates"], dictionary.rules_by_stage.get("action", []), normalized.params, engine
    )
    effect["actions"] = actions
    effect["action"] = actions[0] if actions else {}
    output["meta"]["action_candidate_trace"] = action_details
    outcomes["action"] = StageOutcome(
        stage="action",
        matched=bool(action_hits),
        matched_rule_ids=action_hits,
        unmatched_fragments=[row["fragment"] for row in action_unmatched],
        unmatched_details=action_unmatched,
    )

    trigger_candidates = candidates["trigger_sentences"] or candidates["sentences"]
    trigger_payload, trigger_hits, trigger_unmatched = _apply_candidates(
        [(fragment, "sentence") for fragment in trigger_candidates],
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
        unmatched_fragments=[row["fragment"] for row in trigger_unmatched],
        unmatched_details=trigger_unmatched,
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
            if not isinstance(effect, dict):
                continue

            actions = effect.get("actions")
            if isinstance(actions, list) and actions:
                rows = [row for row in actions if isinstance(row, dict)]
            else:
                action = effect.get("action", {})
                rows = [action] if isinstance(action, dict) and action else []

            for row in rows:
                action_type = row.get("type")
                if isinstance(action_type, str) and action_type:
                    counter[action_type] += 1
    return dict(counter.most_common())
