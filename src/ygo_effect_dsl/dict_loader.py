from __future__ import annotations

import re
from pathlib import Path
from typing import Any
import yaml

from ygo_effect_dsl.models import LoadedDictionary, Rule
from ygo_effect_dsl.util.yaml_io import load_yaml

RULE_FILES = {
    "cost": "30_cost_rules.yaml",
    "action": "31_action_rules.yaml",
    "trigger": "32_trigger_rules.yaml",
    "restriction": "33_restriction_rules.yaml",
}


def _load_yaml_list(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if data is None:
        return []
    if not isinstance(data, list):
        raise ValueError(f"dictionary file must be list: {path}")
    return [r for r in data if isinstance(r, dict)]


def load_dictionary(dict_dir: str) -> LoadedDictionary:
    root = Path(dict_dir)
    vocab = load_yaml(str(root / "00_vocab.yaml"))

    rules_by_stage: dict[str, list[Rule]] = {"cost": [], "action": [], "trigger": [], "restriction_global": []}
    for stage, filename in RULE_FILES.items():
        rows = _load_yaml_list(root / filename)
        for row in rows:
            applies_to = str(row.get("applies_to", "")).strip()
            if stage == "restriction":
                applies_to = "restriction_global"
            rule = Rule(
                id=str(row.get("id", "")),
                version=str(row.get("version", "")),
                priority=int(row.get("priority", 0)),
                language=str(row.get("language", "")),
                applies_to=applies_to,
                pattern=str(row.get("pattern", "")),
                emit=row.get("emit", {}) if isinstance(row.get("emit"), dict) else {},
                capture=row.get("capture", {}) if isinstance(row.get("capture"), dict) else {},
                on_fail=str(row.get("on_fail", "ignore")),
            )
            rules_by_stage.setdefault(rule.applies_to, []).append(rule)

    for rules in rules_by_stage.values():
        rules.sort(key=lambda r: (-r.priority, r.id))
    return LoadedDictionary(vocab=vocab, rules_by_stage=rules_by_stage)


def validate_dictionary(dict_dir: str) -> list[str]:
    errors: list[str] = []
    root = Path(dict_dir)
    if not (root / "00_vocab.yaml").exists():
        return [f"missing required vocab file: {root / '00_vocab.yaml'}"]

    seen_ids: set[str] = set()
    required_rule_keys = {"id", "version", "priority", "language", "applies_to", "pattern", "emit"}

    for filename in RULE_FILES.values():
        path = root / filename
        if not path.exists():
            errors.append(f"missing required rule file: {path}")
            continue
        try:
            rows = _load_yaml_list(path)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"failed to parse {path}: {exc}")
            continue

        for idx, row in enumerate(rows):
            for key in required_rule_keys:
                if key not in row:
                    errors.append(f"{path}:{idx} missing key: {key}")
            rid = str(row.get("id", ""))
            if not rid:
                errors.append(f"{path}:{idx} has empty id")
            elif rid in seen_ids:
                errors.append(f"duplicate rule id: {rid}")
            else:
                seen_ids.add(rid)

            pattern = row.get("pattern", "")
            try:
                re.compile(str(pattern))
            except re.error as exc:
                errors.append(f"{path}:{idx} invalid regex pattern: {exc}")

    return errors
