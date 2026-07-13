from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ygo_effect_dsl.engine.replay.errors import ReplayFormatError
from ygo_effect_dsl.engine.replay.models import ReplayHistory


def dumps_replay(history: ReplayHistory) -> str:
    """Serialize replay JSON deterministically for reviewable fixtures."""

    return json.dumps(history.to_dict(), ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def loads_replay(text: str) -> ReplayHistory:
    try:
        payload: Any = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ReplayFormatError(f"invalid replay JSON: {exc.msg}") from exc
    return ReplayHistory.from_dict(payload)


def save_replay(history: ReplayHistory, path: str | Path) -> None:
    Path(path).write_text(dumps_replay(history), encoding="utf-8")


def load_replay(path: str | Path) -> ReplayHistory:
    return loads_replay(Path(path).read_text(encoding="utf-8"))
