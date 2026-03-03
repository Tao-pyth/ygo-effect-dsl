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

    assert "info" not in payload["card"]
    assert "meta" not in payload["effects"][0]
    assert "info_en" not in payload["meta"]["norm"]
    assert "info_ja" not in payload["meta"]["norm"]

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


def test_transform_fragment_candidates_hit_action_and_restriction(tmp_path: Path) -> None:
    in_path = tmp_path / "cards.jsonl"
    rows = [
        {
            "cid": 20194,
            "name_en": "Silvy of the White Forest",
            "name_ja": "",
            "card_text_en": (
                'If this card is Normal Summoned: You can add 1 "White Forest" Spell/Trap from your Deck to your hand. '
                'If this card is in your GY (Quick Effect): You can target 1 face-up monster you control; return it to the hand. '
                'You can only use each effect of "Silvy of the White Forest" once per turn.'
            ),
            "card_text_ja": "",
            "card_info_en": "",
            "card_info_ja": "",
        }
    ]
    in_path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows), encoding="utf-8")

    rc = cmd_transform(_TransformArgs(str(in_path), str(tmp_path / "export")))
    assert rc == 0

    payload = load_yaml(str(tmp_path / "export" / "yaml" / "20194.yaml"))
    effect = payload["effects"][0]
    assert effect["action"].get("type") == "add_to_hand"
    assert payload["meta"]["restrictions"]["global"]["once_per_turn"]["key"] == "each_effect_of_card"

    unmatched_rows = [json.loads(line) for line in (tmp_path / "export" / "reports" / "unmatched_fragments.jsonl").read_text(encoding="utf-8").splitlines()]
    assert any(row["fragment"].startswith("action:") for row in unmatched_rows)


def test_transform_does_not_export_raw_json_fields(tmp_path: Path) -> None:
    in_path = tmp_path / "raw.json"
    in_path.write_text(
        json.dumps(
            {
                "cid": 300,
                "name_en": {"nested": "object"},
                "name_ja": ["nested", "array"],
                "card_text_en": {"raw": "json"},
                "card_text_ja": ["raw", "json"],
                "card_info_en": {"info": "blob"},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    rc = cmd_transform(_TransformArgs(str(in_path), str(tmp_path / "export")))
    assert rc == 0

    payload = load_yaml(str(tmp_path / "export" / "yaml" / "300.yaml"))
    assert payload["card"]["name"]["en"] == ""
    assert payload["card"]["name"]["ja"] == ""
    assert payload["card"]["text"]["en"] == ""
    assert payload["card"]["text"]["ja"] == ""


def test_transform_exports_compact_card_props_from_card_info_en(tmp_path: Path) -> None:
    in_path = tmp_path / "cards.jsonl"
    rows = [
        {
            "cid": 4104,
            "name_en": "Alexandrite Dragon",
            "name_ja": "アレキサンドライドラゴン",
            "card_text_en": "",
            "card_text_ja": "",
            "card_info_en": json.dumps(
                {
                    "frameType": "normal",
                    "attribute": "LIGHT",
                    "race": "Dragon",
                    "level": 4,
                    "atk": 2000,
                    "def": 100,
                    "type": "Normal Monster",
                    "typeline": ["Dragon", "Normal"],
                    "misc_info": [{"has_effect": 0}],
                    "card_sets": [{"set_name": "ignore me"}],
                    "card_prices": [{"cardmarket_price": "1.00"}],
                    "card_images": [{"image_url": "https://example.com/1.jpg", "image_url_small": "https://example.com/1s.jpg"}],
                    "image_relpath": "images/4104.jpg",
                },
                ensure_ascii=False,
            ),
        }
    ]
    in_path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows), encoding="utf-8")

    rc = cmd_transform(_TransformArgs(str(in_path), str(tmp_path / "export")))
    assert rc == 0

    payload = load_yaml(str(tmp_path / "export" / "yaml" / "4104.yaml"))
    assert "info" not in payload["card"]
    assert "info_en" not in payload["meta"]["norm"]

    props = payload["card"]["props"]
    assert props["frame_type"] == "normal"
    assert props["has_effect"] is False
    assert props["attribute"] == "LIGHT"
    assert props["race"] == "Dragon"
    assert props["level"] == 4
    assert props["atk"] == 2000
    assert props["def"] == 100
    assert props["archetype"] == ""
    assert props["card_type"] == "Normal Monster"
    assert props["typeline"] == ["Dragon", "Normal"]

    assert "card_sets" not in props
    assert "card_prices" not in props
    assert "card_images" not in props


def test_transform_spell_trap_props_are_null_for_missing_stats(tmp_path: Path) -> None:
    in_path = tmp_path / "spell.json"
    in_path.write_text(
        json.dumps(
            {
                "cid": 500,
                "name_en": "Sample Spell",
                "card_text_en": "",
                "card_info_en": {
                    "frameType": "spell",
                    "type": "Spell Card",
                    "race": "Quick-Play",
                    "misc_info": [{"has_effect": 1}],
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    rc = cmd_transform(_TransformArgs(str(in_path), str(tmp_path / "export")))
    assert rc == 0

    props = load_yaml(str(tmp_path / "export" / "yaml" / "500.yaml"))["card"]["props"]
    assert props["level"] is None
    assert props["atk"] is None
    assert props["def"] is None
