from __future__ import annotations
import os
from typing import Any
from ygo_effect_dsl.util.yaml_io import dump_yaml

def write_card_yaml(card_dsl: dict[str, Any], out_dir: str) -> str:
    """cards/{cid}.yml へ保存。返り値は保存先パス。"""
    cid = card_dsl.get("cid", 0)
    filename = f"{cid}.yml" if isinstance(cid, int) and cid > 0 else "unknown.yml"
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, filename)
    dump_yaml(card_dsl, out_path)
    return out_path
