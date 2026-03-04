from __future__ import annotations

from typing import Any


EMPTY_EFFECT_BLOCK = {
    "trigger": {},
    "restriction": {},
    "condition": {},
    "cost": {},
    "actions": [],
    "action": {},
}


def _pick_int(obj: dict[str, Any], keys: list[str], default: int = 0) -> int:
    for k in keys:
        v = obj.get(k)
        if isinstance(v, int):
            return v
        if isinstance(v, str) and v.isdigit():
            return int(v)
    return default


def _pick_str(obj: dict[str, Any], keys: list[str], default: str = "") -> str:
    for k in keys:
        v = obj.get(k)
        if isinstance(v, str):
            return v
    return default


def _pick_nested_str(obj: dict[str, Any], parents: list[str], child: str, default: str = "") -> str:
    for parent in parents:
        node = obj.get(parent)
        if isinstance(node, dict):
            value = node.get(child)
            if isinstance(value, str):
                return value
    return default


def to_dsl_yaml_dict(etl_card: dict[str, Any], dataset_name: str = "", exported_at: str = "") -> dict[str, Any]:
    cid = _pick_int(etl_card, ["cid", "id", "card_id"], default=0)
    name_ja = _pick_str(etl_card, ["name_ja", "card_name_ja"], default="")
    name_en = _pick_str(etl_card, ["name_en", "card_name_en"], default="")

    if not name_ja:
        name_ja = _pick_nested_str(etl_card, ["name", "names"], "ja", default="")
    if not name_en:
        name_en = _pick_nested_str(etl_card, ["name", "names"], "en", default="")

    effect_id = f"{cid}_001" if cid else "0_001"
    effects = [
        {
            "id": effect_id,
            "order": 1,
            **EMPTY_EFFECT_BLOCK,
        }
    ]

    return {
        "dsl_version": "0.0",
        "card": {
            "cid": cid,
            "name": {
                "en": name_en,
                "ja": name_ja,
            },
        },
        "effects": effects,
        "meta": {
            "source": {
                "dataset": dataset_name,
                "exported_at": exported_at,
            }
        },
    }
