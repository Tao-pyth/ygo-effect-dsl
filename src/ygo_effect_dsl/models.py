from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


CATEGORY_KEYS = (
    "attributes",
    "races",
    "zones",
    "levels",
    "ranks",
    "links",
    "card_types",
    "phases",
)


@dataclass(slots=True)
class NormalizedPayload:
    text_en: str = ""
    text_ja: str = ""
    params: dict[str, list[Any]] = field(default_factory=lambda: {"N": [], "CARD_NAME": []})
    categories: dict[str, list[Any]] = field(
        default_factory=lambda: {key: [] for key in CATEGORY_KEYS}
    )

    def as_dict(self) -> dict[str, Any]:
        return {
            "text_en": self.text_en,
            "text_ja": self.text_ja,
            "params": self.params,
            "categories": self.categories,
        }


@dataclass(slots=True)
class Rule:
    id: str
    version: str
    priority: int
    language: str
    applies_to: str
    pattern: str
    emit: dict[str, Any]
    capture: dict[str, Any] = field(default_factory=dict)
    on_fail: str = "ignore"


@dataclass(slots=True)
class LoadedDictionary:
    vocab: dict[str, Any]
    rules_by_stage: dict[str, list[Rule]]


@dataclass(slots=True)
class StageOutcome:
    stage: str
    matched: bool
    matched_rule_ids: list[str] = field(default_factory=list)
    unmatched_fragment: str = ""
    unmatched_fragments: list[str] = field(default_factory=list)
    unmatched_details: list[dict[str, str]] = field(default_factory=list)


@dataclass(slots=True)
class TransformResult:
    cid: str
    output: dict[str, Any]
    stage_outcomes: dict[str, StageOutcome]
