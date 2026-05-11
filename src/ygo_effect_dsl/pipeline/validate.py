from __future__ import annotations

from pathlib import Path
from typing import Any

from ygo_effect_dsl.util.yaml_io import load_yaml
from ygo_effect_dsl.validate.validator import validate_card_yaml


def load_cards_with_path(cards_dir: str) -> list[tuple[str, dict[str, Any]]]:
    cards_path = Path(cards_dir)
    files = sorted(p for p in cards_path.iterdir() if p.suffix in {".yml", ".yaml"})
    return [(str(path), load_yaml(str(path))) for path in files]


def run_validate(args: object) -> int:
    try:
        cards = load_cards_with_path(args.cards_dir)
    except (OSError, ValueError) as exc:
        print(f"validate: argument/config error: {exc}")
        return 2

    diagnostics: list[tuple[str, Any]] = []
    for path, card in cards:
        for err in validate_card_yaml(card):
            diagnostics.append((path, err))

    severity_counts = {"error": 0, "warning": 0, "info": 0}
    for _, err in diagnostics:
        severity_counts[err.severity] = severity_counts.get(err.severity, 0) + 1

    print(f"validate: scanned={len(cards)}")
    print(f"validate: errors={severity_counts['error']} warnings={severity_counts['warning']} info={severity_counts['info']}")
    for path, err in diagnostics:
        print(f"  {path}: {err.path} [{err.severity}:{err.code}] {err.message}")

    return 1 if severity_counts["error"] else 0
