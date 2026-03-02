from __future__ import annotations

from pathlib import Path
from typing import Any

from ygo_effect_dsl.util.yaml_io import dump_yaml


def write_yaml_by_cid(card_dsl: dict[str, Any], out_root: str) -> Path:
    cid = str(card_dsl.get("card", {}).get("cid", ""))
    filename = f"{cid}.yaml" if cid else "unknown.yaml"
    out_path = Path(out_root) / "yaml" / filename
    out_path.parent.mkdir(parents=True, exist_ok=True)
    dump_yaml(card_dsl, str(out_path))
    return out_path
