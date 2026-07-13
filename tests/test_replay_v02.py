from __future__ import annotations

import re
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ygo_effect_dsl.engine.replay import (
    ActionRecord,
    ReplayFormatError,
    ReplayHistory,
    dumps_replay,
    load_replay,
    loads_replay,
    save_replay,
)


def _sample_history() -> ReplayHistory:
    return ReplayHistory(
        seed=12345,
        deck_identifier="sample-deck",
        actions=[
            ActionRecord(
                step=0,
                action_type="select_card",
                payload={"selected": ["card-1"]},
                source="synthetic",
                created_at=None,
            )
        ],
        version_metadata={"project_version": "0.1.0"},
        notes="synthetic smoke fixture",
    )


def test_replay_round_trip_is_deterministic(tmp_path: Path) -> None:
    history = _sample_history()
    text = dumps_replay(history)

    assert text.endswith("\n")
    assert '"actions": [' in text
    assert "カード" not in text

    loaded = loads_replay(text)
    assert loaded.to_dict() == history.to_dict()

    path = tmp_path / "replay.json"
    save_replay(history, path)
    assert path.read_text(encoding="utf-8") == text
    assert load_replay(path).to_dict() == history.to_dict()


def test_replay_serializer_keeps_utf8_unescaped() -> None:
    history = ReplayHistory(
        seed=None,
        deck_identifier="日本語デッキ",
        actions=[],
        version_metadata={},
        notes="日本語メモ",
    )
    text = dumps_replay(history)
    assert "日本語デッキ" in text
    assert "\\u65e5" not in text


@pytest.mark.parametrize(
    "text, expected",
    [
        ("{", "invalid replay JSON"),
        ("[]", "replay must be object"),
        ('{"schema_version":"0.2"}', "missing required fields"),
        (
            '{"schema_version":"0.2","seed":1,"deck_identifier":"d","actions":{},"version_metadata":{},"notes":""}',
            "replay.actions must be array",
        ),
        (
            '{"schema_version":"0.2","seed":1,"deck_identifier":"d","actions":[{"step":0,"action_type":"x","payload":[],"source":"s"}],"version_metadata":{},"notes":""}',
            "actions[0].payload must be object",
        ),
        (
            '{"schema_version":"0.2","seed":1,"deck_identifier":"d","actions":[],"version_metadata":[],"notes":""}',
            "replay.version_metadata must be object",
        ),
    ],
)
def test_invalid_replay_json_raises_format_error(text: str, expected: str) -> None:
    with pytest.raises(ReplayFormatError, match=re.escape(expected)):
        loads_replay(text)
