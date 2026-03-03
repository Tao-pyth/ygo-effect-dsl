from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable


SUPPORTED_SUFFIXES = {".json", ".jsonl"}


def _coerce_record(obj: Any) -> dict[str, Any] | None:
    return obj if isinstance(obj, dict) else None


def _iter_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            raw = line.strip()
            if not raw:
                continue
            data = json.loads(raw)
            rec = _coerce_record(data)
            if rec is None:
                raise ValueError(f"jsonl record at {path}:{line_no} must be object")
            yield rec


def _iter_json(path: Path) -> Iterable[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        for idx, obj in enumerate(data):
            rec = _coerce_record(obj)
            if rec is None:
                raise ValueError(f"json array item at {path}[{idx}] must be object")
            yield rec
        return

    rec = _coerce_record(data)
    if rec is None:
        raise ValueError(f"json root at {path} must be object or list[object]")
    yield rec


def load_inputs(input_path: str, glob_pattern: str | None = None, limit: int | None = None) -> list[dict[str, Any]]:
    base = Path(input_path)
    paths: list[Path] = []

    if base.is_dir():
        pattern = glob_pattern or "*.json*"
        paths = sorted(p for p in base.glob(pattern) if p.suffix in SUPPORTED_SUFFIXES)
    elif base.is_file():
        if base.suffix not in SUPPORTED_SUFFIXES:
            raise ValueError(f"unsupported input suffix: {base.suffix}")
        paths = [base]
    else:
        raise FileNotFoundError(base)

    cards: list[dict[str, Any]] = []
    for path in paths:
        iterator = _iter_jsonl(path) if path.suffix == ".jsonl" else _iter_json(path)
        for record in iterator:
            cards.append(record)
            if limit is not None and len(cards) >= limit:
                return cards

    return cards


def _as_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float)):
        return str(value)
    return ""


def extract_card_fields(card: dict[str, Any]) -> dict[str, Any]:
    cid = card.get("cid", card.get("id", card.get("card_id", "")))
    cid_str = str(cid) if cid is not None else ""

    def _pick(*keys: str) -> str:
        for key in keys:
            if key in card:
                text = _as_text(card.get(key))
                if text:
                    return text
        return ""

    return {
        "cid": cid_str,
        "name_en": _pick("name_en", "card_name_en"),
        "name_ja": _pick("name_ja", "card_name_ja"),
        "card_text_en": _pick("card_text_en", "text_en"),
        "card_text_ja": _pick("card_text_ja", "text_ja"),
        "card_info_en": _pick("card_info_en", "info_en"),
        "card_info_ja": _pick("card_info_ja", "info_ja"),
    }
