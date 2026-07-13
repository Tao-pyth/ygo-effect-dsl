from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from enum import Enum
from hashlib import sha256
from typing import Any


def to_canonical_data(value: Any) -> Any:
    if is_dataclass(value):
        return to_canonical_data(asdict(value))
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {str(key): to_canonical_data(value[key]) for key in sorted(value)}
    if isinstance(value, (list, tuple)):
        return [to_canonical_data(item) for item in value]
    return value


def canonical_json(value: Any) -> str:
    return json.dumps(
        to_canonical_data(value),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def stable_digest(value: Any, *, prefix: str = "") -> str:
    digest = sha256(canonical_json(value).encode("utf-8")).hexdigest()
    return f"{prefix}{digest}"
