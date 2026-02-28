from __future__ import annotations
from typing import Any
import yaml

def load_yaml(path: str) -> dict[str, Any]:
    """YAMLをdictとして読む（rootがdict以外なら例外）"""
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ValueError(f"YAML root must be mapping(dict). got={type(data)}")
    return data

def dump_yaml(data: Any, path: str) -> None:
    """YAMLとして保存"""
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)
