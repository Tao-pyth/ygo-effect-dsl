from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ygo_effect_dsl.cli.main import cmd_transform, cmd_validate_dict
from ygo_effect_dsl.util.yaml_io import load_yaml


class _TransformArgs:
    def __init__(self, in_path: str, out_dir: str):
        self.in_path = in_path
        self.glob = None
        self.dict_dir = "resources/dict/v0_0"
        self.out_dir = out_dir
        self.limit = None
        self.fail_fast = False
        self.log_level = "INFO"
        self.report = True
        self.dataset = None
        self.manifest = None
        self.jsonl = None


class _ValidateDictArgs:
    def __init__(self, dict_dir: str):
        self.dict_dir = dict_dir


def test_validate_dict_ok() -> None:
    assert cmd_validate_dict(_ValidateDictArgs("resources/dict/v0_0")) == 0


def test_transform_action_hit_and_reports(tmp_path: Path) -> None:
    in_path = tmp_path / "cards.jsonl"
    rows = [
        {
            "cid": 100,
            "name_en": "Sample",
            "name_ja": "サンプル",
            "card_text_en": "Draw 2 cards.",
            "card_text_ja": "",
            "card_info_en": "",
            "card_info_ja": "",
        }
    ]
    in_path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows), encoding="utf-8")

    rc = cmd_transform(_TransformArgs(str(in_path), str(tmp_path / "export")))
    assert rc == 0

    out_yaml = tmp_path / "export" / "yaml" / "100.yaml"
    payload = load_yaml(str(out_yaml))

    effect = payload["effects"][0]
    assert effect["action"].get("type") == "draw"
    assert effect["action"].get("n") == 2

    summary_path = tmp_path / "export" / "reports" / "summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary["input_count"] == 1
    assert summary["success_count"] == 1


def test_transform_yaml_has_required_effect_keys(tmp_path: Path) -> None:
    in_path = tmp_path / "single.json"
    in_path.write_text(
        json.dumps(
            {
                "cid": "200",
                "name_en": "NoHit",
                "name_ja": "",
                "card_text_en": "Completely unknown effect text",
                "card_info_en": "",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    rc = cmd_transform(_TransformArgs(str(in_path), str(tmp_path / "export")))
    assert rc == 0

    out_yaml = tmp_path / "export" / "yaml" / "200.yaml"
    payload = load_yaml(str(out_yaml))
    effect = payload["effects"][0]

    for key in ["trigger", "restriction", "condition", "cost", "action"]:
        assert key in effect
        assert isinstance(effect[key], dict)
