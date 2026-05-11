from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ygo_effect_dsl.cli.main import cmd_transform
from ygo_effect_dsl.util.yaml_io import load_yaml
from ygo_effect_dsl.validate.validator import validate_card_yaml


ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "tests" / "datasets" / "representative_cards"
GOLDEN_PATH = ROOT / "tests" / "golden" / "representative_cards" / "expected.json"


class _TransformArgs:
    def __init__(self, out_dir: str):
        self.in_path = None
        self.glob = None
        self.dict_dir = str(ROOT / "resources" / "dict" / "v0_0")
        self.out_dir = out_dir
        self.limit = None
        self.fail_fast = False
        self.log_level = "INFO"
        self.report = True
        self.dataset = str(DATASET)
        self.manifest = None
        self.jsonl = None


def _summarize_card(path: Path) -> dict[str, object]:
    payload = load_yaml(str(path))
    effect = payload["effects"][0]
    actions = effect.get("actions", [])
    targets = effect.get("targets", [])
    diagnostics = validate_card_yaml(payload)
    return {
        "cid": payload["card"]["cid"],
        "has_card_info": "info" in payload["card"],
        "action_types": [row.get("type", "") for row in actions if isinstance(row, dict)],
        "target_count": len(targets) if isinstance(targets, list) else 0,
        "target_kinds": [
            row.get("selector", {}).get("kind", "")
            for row in targets
            if isinstance(row, dict) and isinstance(row.get("selector"), dict)
        ],
        "diagnostics": [
            {"severity": row.severity, "code": row.code, "path": row.path}
            for row in diagnostics
        ],
    }


def _summarize_dataset(cards_dir: Path) -> dict[str, object]:
    cards = [_summarize_card(path) for path in sorted(cards_dir.glob("*.yaml"))]
    action_counts: dict[str, int] = {}
    for card in cards:
        for action_type in card["action_types"]:
            action_counts[str(action_type)] = action_counts.get(str(action_type), 0) + 1
    return {
        "cards": cards,
        "action_counts": dict(sorted(action_counts.items())),
        "diagnostic_counts": {
            "error": sum(1 for card in cards for row in card["diagnostics"] if row["severity"] == "error"),
            "warning": sum(1 for card in cards for row in card["diagnostics"] if row["severity"] == "warning"),
            "info": sum(1 for card in cards for row in card["diagnostics"] if row["severity"] == "info"),
        },
    }


def test_representative_cards_match_golden(tmp_path: Path) -> None:
    out_dir = tmp_path / "export"
    assert cmd_transform(_TransformArgs(str(out_dir))) == 0

    actual = _summarize_dataset(out_dir / "yaml")
    if os.environ.get("YGO_UPDATE_GOLDEN") == "1":
        GOLDEN_PATH.parent.mkdir(parents=True, exist_ok=True)
        GOLDEN_PATH.write_text(json.dumps(actual, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    expected = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))
    assert actual == expected
