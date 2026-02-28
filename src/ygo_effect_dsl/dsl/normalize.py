from __future__ import annotations
from typing import Any

def _d(x: Any) -> dict:
    return x if isinstance(x, dict) else {}

def _l(x: Any) -> list:
    return x if isinstance(x, list) else []

def _s(x: Any) -> str:
    return x if isinstance(x, str) else ""

def normalize_card_dsl(d: dict[str, Any]) -> dict[str, Any]:
    """
    YAML保存向けの安全な正規化。
    - 欠損キーは空で補う
    - 型不一致は空へ
    """
    out = dict(d)
    out["version"] = int(out.get("version", 3) or 3)
    out["cid"] = int(out.get("cid", 0) or 0)

    name = _d(out.get("name"))
    out["name"] = {"ja": _s(name.get("ja")), "en": _s(name.get("en"))}

    text = _d(out.get("text"))
    out["text"] = {"ja": _s(text.get("ja")), "en": _s(text.get("en"))}

    out["meta"] = _d(out.get("meta"))

    effects = _l(out.get("effects"))
    neffs: list[dict[str, Any]] = []
    for i, e in enumerate(effects):
        e = _d(e)
        trig = _d(e.get("trigger"))
        neffs.append({
            "id": _s(e.get("id")),
            "label": _s(e.get("label")),
            "order": int(e.get("order", i+1) or (i+1)),
            "trigger": {
                "kind": _s(trig.get("kind")),
                "timing": _s(trig.get("timing")),
                "once": _s(trig.get("once")),
                "note": _s(trig.get("note")),
            },
            "restriction": _l(e.get("restriction")),
            "condition": _l(e.get("condition")),
            "cost": _l(e.get("cost")),
            "action": _l(e.get("action")),
        })
    out["effects"] = neffs
    return out
