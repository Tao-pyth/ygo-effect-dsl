from __future__ import annotations
from typing import Any

def _s(x: Any) -> str:
    return x if isinstance(x, str) else ""

def _d(x: Any) -> dict:
    return x if isinstance(x, dict) else {}

def pick_int(obj: dict[str, Any], keys: list[str], default: int = 0) -> int:
    for k in keys:
        v = obj.get(k)
        if isinstance(v, int):
            return v
        if isinstance(v, str) and v.isdigit():
            return int(v)
    return default

def pick_str(obj: dict[str, Any], keys: list[str], default: str = "") -> str:
    for k in keys:
        v = obj.get(k)
        if isinstance(v, str) and v != "":
            return v
    return default

def pick_nested_str(obj: dict[str, Any], path_candidates: list[tuple[str, str]], default: str = "") -> str:
    """例: ('name','ja') のような2段階候補を拾う"""
    for a, b in path_candidates:
        v1 = obj.get(a)
        if isinstance(v1, dict):
            v2 = v1.get(b)
            if isinstance(v2, str) and v2 != "":
                return v2
    return default

def to_dsl_yaml_dict(etl_card: dict[str, Any], mode: str = "skeleton") -> dict[str, Any]:
    """
    ETL(JSONL) 1件を DSL YAML(dict)へ変換する。
    mode:
      - skeleton: effects を最小骨で1件生成（中身は空）
    """
    cid = pick_int(etl_card, ["cid", "id", "card_id"], default=0)

    name_ja = pick_str(etl_card, ["name_ja", "card_name_ja"], default="")
    name_en = pick_str(etl_card, ["name_en", "card_name_en"], default="")

    # 入力が name: {ja,en} 形式の可能性も考慮
    if not name_ja:
        name_ja = pick_nested_str(etl_card, [("name", "ja"), ("names", "ja")], default="")
    if not name_en:
        name_en = pick_nested_str(etl_card, [("name", "en"), ("names", "en")], default="")

    text_ja = pick_str(etl_card, ["card_text_ja", "text_ja", "desc_ja"], default="")
    text_en = pick_str(etl_card, ["card_text_en", "text_en", "desc_en"], default="")

    card_info_ja = _d(etl_card.get("card_info_ja"))
    card_info_en = _d(etl_card.get("card_info_en"))
    image_path = pick_str(etl_card, ["image_path", "img_path"], default="")

    dsl: dict[str, Any] = {
        "version": 3,
        "cid": cid,
        "name": {"ja": name_ja, "en": name_en},
        "text": {"ja": text_ja, "en": text_en},
        "meta": {
            "source": "ygo-effect-dsl-etl",
            "card_info_ja": card_info_ja,
            "card_info_en": card_info_en,
            "image_path": image_path,
        },
        "effects": [],
    }

    if mode == "skeleton":
        effect_id = f"{cid}_01" if cid else "0_01"
        dsl["effects"] = [{
            "id": effect_id,
            "label": "",
            "order": 1,
            "trigger": {"kind": "", "timing": "", "once": "", "note": ""},
            "restriction": [],
            "condition": [],
            "cost": [],
            "action": [],
        }]

    return dsl
