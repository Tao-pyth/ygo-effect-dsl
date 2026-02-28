from __future__ import annotations

import os
from typing import Any

from ygo_effect_dsl.util.yaml_io import dump_yaml


def write_card_yaml(card_dsl: dict[str, Any], out_dir: str) -> str:
    """{cid}.yaml へ保存。返り値は保存先パス。"""
    card = card_dsl.get("card")
    cid = card.get("cid", 0) if isinstance(card, dict) else 0
    filename = f"{cid}.yaml" if isinstance(cid, int) and cid > 0 else "unknown.yaml"
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, filename)
    dump_yaml(card_dsl, out_path)
    return out_path
