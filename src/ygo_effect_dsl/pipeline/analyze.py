from __future__ import annotations

import json
from pathlib import Path

from ygo_effect_dsl.analyze.report import build_report
from ygo_effect_dsl.pipeline.validate import load_cards_with_path
from ygo_effect_dsl.validate.validator import validate_card_yaml

UNMATCHED_FRAGMENTS_CLI_LIMIT = 5


def _format_counts(counts: dict[str, int]) -> str:
    if not counts:
        return "none"
    return ", ".join(f"{key}={value}" for key, value in counts.items())


def run_analyze(args: object) -> int:
    try:
        cards = load_cards_with_path(args.cards_dir)
    except (OSError, ValueError) as exc:
        print(f"analyze: argument/config error: {exc}")
        return 2

    diagnostics = []
    for _, card in cards:
        diagnostics.extend(validate_card_yaml(card))

    payload_cards = [card for _, card in cards]
    report = build_report(payload_cards, diagnostics=diagnostics)

    Path(args.out_dir).mkdir(parents=True, exist_ok=True)
    out_path = Path(args.out_dir) / "analysis_report.json"
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"analyze: total_cards={report['quality']['total_cards']}")
    print(f"analyze: effects_empty_ratio={report['quality']['effects_empty_ratio']:.4f}")
    for key, ratio in report["quality"]["empty_block_ratio"].items():
        print(f"analyze: {key}_empty_ratio={ratio:.4f}")
    print(f"analyze: action_type_coverage={_format_counts(report['stats']['action_type_coverage'])}")
    targets_count = report["stats"]["targets_count"]
    print(
        "analyze: target_resolution_rate="
        f"{targets_count['resolution_rate']:.4f} "
        f"resolved={targets_count['resolved_references']} "
        f"references={targets_count['references']}"
    )
    unmatched_top = report["stats"]["unmatched_fragments_top"]
    print(f"analyze: unmatched_fragments_top_count={len(unmatched_top)}")
    for index, row in enumerate(unmatched_top[:UNMATCHED_FRAGMENTS_CLI_LIMIT], start=1):
        fragment = json.dumps(row["fragment"], ensure_ascii=True)
        print(f"analyze: unmatched_fragments_top[{index}] count={row['count']} fragment={fragment}")
    print(f"analyze: validation_errors={report['validation']['severity_counts']['error']}")
    print(f"analyze: validation_warnings={report['validation']['severity_counts']['warning']}")
    print(f"analyze: validation_code_counts={_format_counts(report['validation']['code_counts'])}")
    print(f"analyze: wrote report to {out_path}")
    return 1 if report["validation"]["severity_counts"]["error"] else 0
