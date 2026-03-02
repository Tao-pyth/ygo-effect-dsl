from __future__ import annotations

import re
import unicodedata
from typing import Any

from ygo_effect_dsl.models import CATEGORY_KEYS, NormalizedPayload

_QUOTE_PATTERN = re.compile(r'"([^"]+)"')
_NUMBER_PATTERN = re.compile(r"\b\d+\b")
_WHITESPACE_PATTERN = re.compile(r"\s+")


def _normalize_quotes(text: str) -> str:
    return (
        text.replace("“", '"')
        .replace("”", '"')
        .replace("＂", '"')
        .replace("‘", "'")
        .replace("’", "'")
    )


def _normalize_text(text: str) -> str:
    if not isinstance(text, str):
        return ""
    normed = unicodedata.normalize("NFKC", text)
    normed = _normalize_quotes(normed)
    normed = normed.lower()
    normed = normed.replace("\n", " ").replace("\r", " ")
    normed = _WHITESPACE_PATTERN.sub(" ", normed).strip()
    return normed


def _extract_card_names(text: str) -> tuple[str, list[str]]:
    captures: list[str] = []

    def repl(match: re.Match[str]) -> str:
        captures.append(match.group(1))
        return "【CARD_NAME】"

    return _QUOTE_PATTERN.sub(repl, text), captures


def _extract_numbers(text: str) -> tuple[str, list[int]]:
    captures: list[int] = []

    def repl(match: re.Match[str]) -> str:
        captures.append(int(match.group(0)))
        return "【N】"

    return _NUMBER_PATTERN.sub(repl, text), captures


def _extract_categories(text: str, vocab: dict[str, Any]) -> dict[str, list[Any]]:
    categories = {key: [] for key in CATEGORY_KEYS}

    for key in ("attributes", "races", "zones", "card_types", "phases"):
        items = vocab.get(key, {})
        if not isinstance(items, dict):
            continue
        for canonical, synonyms in items.items():
            if not isinstance(synonyms, list):
                continue
            for synonym in synonyms:
                if isinstance(synonym, str) and synonym in text:
                    if canonical not in categories[key]:
                        categories[key].append(canonical)
                    break

    for key, pattern in (("levels", r"\blevel\s+(\d+)"), ("ranks", r"\brank\s+(\d+)"), ("links", r"\blink\s+(\d+)")):
        for match in re.finditer(pattern, text):
            value = int(match.group(1))
            if value not in categories[key]:
                categories[key].append(value)

    return categories


def normalize_card_texts(card_fields: dict[str, Any], vocab: dict[str, Any]) -> NormalizedPayload:
    normalized = NormalizedPayload()
    for source_key, out_key in (
        ("card_text_en", "text_en"),
        ("card_text_ja", "text_ja"),
        ("card_info_en", "info_en"),
        ("card_info_ja", "info_ja"),
    ):
        value = _normalize_text(str(card_fields.get(source_key, "")))
        setattr(normalized, out_key, value)

    normalized.text_en, card_names_text = _extract_card_names(normalized.text_en)
    normalized.info_en, card_names_info = _extract_card_names(normalized.info_en)

    normalized.text_en, nums_text = _extract_numbers(normalized.text_en)
    normalized.info_en, nums_info = _extract_numbers(normalized.info_en)

    normalized.params["CARD_NAME"] = card_names_text + card_names_info
    normalized.params["N"] = nums_text + nums_info
    normalized.categories = _extract_categories(
        f"{normalized.text_en} {normalized.info_en}",
        vocab,
    )

    return normalized
