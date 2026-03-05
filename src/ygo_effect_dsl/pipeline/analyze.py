from __future__ import annotations

import json
from pathlib import Path

from ygo_effect_dsl.analyze.report import build_report
from ygo_effect_dsl.pipeline.validate import load_cards_with_path
from ygo_effect_dsl.validate.validator import validate_card_yaml


def run_analyze(args: object) -> int:
    try:
        cards = load_cards_with_path(args.cards_dir)
    except (OSError, ValueError) as exc:
        print(f"analyze: argument/config error: {exc}")
        return 2

    validate_errors = 0
    for _, card in cards:
        validate_errors += len(validate_card_yaml(card))

    payload_cards = [card for _, card in cards]
    report = build_report(payload_cards, validate_errors=validate_errors)

    Path(args.out_dir).mkdir(parents=True, exist_ok=True)
    out_path = Path(args.out_dir) / "analysis_report.json"
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"analyze: total_cards={report['quality']['total_cards']}")
    print(f"analyze: effects_empty_ratio={report['quality']['effects_empty_ratio']:.4f}")
    for key, ratio in report["quality"]["empty_block_ratio"].items():
        print(f"analyze: {key}_empty_ratio={ratio:.4f}")
    print(f"analyze: validation_error_count={report['validation']['error_count']}")
    print(f"analyze: wrote report to {out_path}")
    return 0
