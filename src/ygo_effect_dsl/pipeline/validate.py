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

    all_errors: list[tuple[str, Any]] = []
    for path, card in cards:
        for err in validate_card_yaml(card):
            all_errors.append((path, err))

    print(f"validate: scanned={len(cards)}")
    print(f"validate: critical_errors={len(all_errors)}")
    for path, err in all_errors:
        print(f"  {path}: {err.path} [{err.code}] {err.message}")

    return 1 if all_errors else 0
