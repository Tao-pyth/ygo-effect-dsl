from __future__ import annotations
from typing import Any, Iterator
import json

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
