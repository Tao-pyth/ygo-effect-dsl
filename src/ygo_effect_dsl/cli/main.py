from __future__ import annotations

import argparse
import json
import os
from typing import Any

from ygo_effect_dsl.analyze.report import build_report
from ygo_effect_dsl.ingest.jsonl_reader import load_raw_cards_with_issues
from ygo_effect_dsl.transform.dsl_writer import write_card_yaml
from ygo_effect_dsl.transform.etl_to_dsl import to_dsl_yaml_dict
from ygo_effect_dsl.util.yaml_io import load_yaml
from ygo_effect_dsl.validate.validator import validate_card_yaml


def _load_cards_from_dir(cards_dir: str) -> list[dict[str, Any]]:
    cards: list[dict[str, Any]] = []
    for name in sorted(os.listdir(cards_dir)):
        if not (name.endswith(".yml") or name.endswith(".yaml")):
            continue
        path = os.path.join(cards_dir, name)
        cards.append(load_yaml(path))
    return cards


def _load_cards_with_path(cards_dir: str) -> list[tuple[str, dict[str, Any]]]:
    results: list[tuple[str, dict[str, Any]]] = []
    for name in sorted(os.listdir(cards_dir)):
        if not (name.endswith(".yml") or name.endswith(".yaml")):
            continue
        path = os.path.join(cards_dir, name)
        results.append((path, load_yaml(path)))
    return results


def cmd_ingest(args: argparse.Namespace) -> int:
    cards, issues = load_raw_cards_with_issues(args.jsonl_path)
    print(f"ingest: loaded {len(cards)} cards")
    print(f"ingest: missing required-key records = {len(issues)}")
    for issue in issues:
        print(f"  line={issue.line} missing={','.join(issue.missing_keys)}")
    return 0


def cmd_transform(args: argparse.Namespace) -> int:
    cards, issues = load_raw_cards_with_issues(args.in_path)
    os.makedirs(args.out_dir, exist_ok=True)

    count = 0
    for card in cards:
        dsl = to_dsl_yaml_dict(card, mode="skeleton")
        write_card_yaml(dsl, args.out_dir)
        count += 1

    print(f"transform: wrote {count} cards into {args.out_dir}")
    if issues:
        print(f"transform: warning raw contract issues = {len(issues)}")
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    try:
        cards = _load_cards_with_path(args.cards_dir)
    except OSError as exc:
        print(f"validate: argument/config error: {exc}")
        return 2

    all_errors: list[tuple[str, Any]] = []
    for path, card in cards:
        errors = validate_card_yaml(card)
        for err in errors:
            all_errors.append((path, err))

    print(f"validate: scanned {len(cards)} files")
    print(f"validate: errors={len(all_errors)}")
    for path, err in all_errors:
        print(f"  {path}: {err.path} [{err.code}] {err.message}")

    return 1 if all_errors else 0


def cmd_analyze(args: argparse.Namespace) -> int:
    cards = _load_cards_from_dir(args.cards_dir)

    validate_errors = 0
    if args.validate_report:
        if os.path.exists(args.validate_report):
            with open(args.validate_report, "r", encoding="utf-8") as f:
                payload = json.load(f)
            validate_errors = int(payload.get("error_count", 0) or 0)

    report = build_report(cards, validate_errors=validate_errors)
    os.makedirs(args.out_dir, exist_ok=True)
    out_path = os.path.join(args.out_dir, "analysis_report.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print(f"analyze: total_cards={report['quality']['total_cards']}")
    print(f"analyze: effects_empty_ratio={report['quality']['effects_empty_ratio']:.4f}")
    for key, ratio in report["quality"]["empty_block_ratio"].items():
        print(f"analyze: {key}_empty_ratio={ratio:.4f}")
    print(f"analyze: validation_error_count={report['validation']['error_count']}")
    print(f"analyze: wrote report to {out_path}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(prog="ygo-effect-dsl")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p0 = sub.add_parser("ingest", help="Read ETL JSONL and check minimum contract")
    p0.add_argument("jsonl_path", help="input JSONL path")
    p0.set_defaults(func=cmd_ingest)

    p1 = sub.add_parser("transform", help="JSONL(ETL) -> DSL YAML")
    p1.add_argument("--in", dest="in_path", required=True, help="input JSONL path")
    p1.add_argument("--out", dest="out_dir", required=True, help="output directory for YAML cards")
    p1.set_defaults(func=cmd_transform)

    p2 = sub.add_parser("validate", help="Validate DSL YAML files for spec v0.0 minimum")
    p2.add_argument("cards_dir", help="directory that contains YAML cards")
    p2.set_defaults(func=cmd_validate)

    p3 = sub.add_parser("analyze", help="Analyze DSL YAML cards and output report")
    p3.add_argument("cards_dir", help="directory that contains YAML cards")
    p3.add_argument("--out", dest="out_dir", required=True, help="report output directory")
    p3.add_argument("--validate-report", dest="validate_report", help="optional validate report json")
    p3.set_defaults(func=cmd_analyze)

    args = ap.parse_args()
    try:
        return int(args.func(args))
    except (ValueError, OSError) as exc:
        print(f"error: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
