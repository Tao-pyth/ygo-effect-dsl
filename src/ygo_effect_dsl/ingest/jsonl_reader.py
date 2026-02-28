from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Iterator


REQUIRED_RAW_KEYS = ("cid",)


@dataclass(frozen=True)
class IngestIssue:
    line: int
    missing_keys: list[str]


def iter_jsonl(path: str) -> Iterator[dict[str, Any]]:
    """JSONL（1行=1JSON）をストリームで読む。空行は無視。"""
    with open(path, "r", encoding="utf-8") as f:
        for lineno, line in enumerate(f, start=1):
            s = line.strip()
            if not s:
                continue
            try:
                obj = json.loads(s)
            except json.JSONDecodeError as e:
                raise ValueError(f"Invalid JSON at line {lineno}: {e}") from e
            if not isinstance(obj, dict):
                raise ValueError(f"JSONL line {lineno} must be object/dict. got={type(obj)}")
            yield obj


def check_minimum_contract(record: dict[str, Any]) -> list[str]:
    """ETL export の最小契約をゆるくチェックする。"""
    missing: list[str] = []
    for key in REQUIRED_RAW_KEYS:
        if key not in record:
            missing.append(key)
    return missing


def load_raw_cards_with_issues(path: str) -> tuple[list[dict[str, Any]], list[IngestIssue]]:
    cards: list[dict[str, Any]] = []
    issues: list[IngestIssue] = []
    for idx, record in enumerate(iter_jsonl(path), start=1):
        cards.append(record)
        missing = check_minimum_contract(record)
        if missing:
            issues.append(IngestIssue(line=idx, missing_keys=missing))
    return cards, issues
