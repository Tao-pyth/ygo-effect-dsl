from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from ygo_effect_dsl.analyze.report import build_report
from ygo_effect_dsl.ingest.jsonl_reader import load_dataset, resolve_dataset_paths
from ygo_effect_dsl.transform.dsl_writer import write_card_yaml
from ygo_effect_dsl.transform.etl_to_dsl import to_dsl_yaml_dict
from ygo_effect_dsl.util.yaml_io import load_yaml
from ygo_effect_dsl.validate.validator import validate_card_yaml


def _load_cards_with_path(cards_dir: str) -> list[tuple[str, dict[str, Any]]]:
    cards_path = Path(cards_dir)
    files = sorted(p for p in cards_path.iterdir() if p.suffix in {".yml", ".yaml"})
    return [(str(path), load_yaml(str(path))) for path in files]


def _add_dataset_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--dataset", help="dataset directory that contains manifest.json and cards.jsonl")
    parser.add_argument("--manifest", help="path to manifest.json")
    parser.add_argument("--jsonl", help="path to cards.jsonl")


def _load_from_args(args: argparse.Namespace) -> tuple[int, Any | None]:
    if not args.dataset and not (args.manifest and args.jsonl):
        print("dataset error: specify --dataset or both --manifest and --jsonl")
        return 2, None

    try:
        paths = resolve_dataset_paths(args.dataset, args.manifest, args.jsonl)
        loaded = load_dataset(paths)
    except FileNotFoundError as exc:
        print(f"dataset error: {exc}")
        return 2, None
    except ValueError as exc:
        print(f"dataset error: {exc}")
        return 1, None
    return 0, loaded


def cmd_ingest(args: argparse.Namespace) -> int:
    rc, loaded = _load_from_args(args)
    if rc != 0 or loaded is None:
        return rc

    print(f"ingest: schema_version={loaded.manifest.export_schema_version}")
    print(f"ingest: record_count={loaded.manifest.record_count}")
    print(f"ingest: loaded={len(loaded.cards)}")
    print(f"ingest: fields={','.join(loaded.manifest.fields)}")
    return 0


def cmd_transform(args: argparse.Namespace) -> int:
    rc, loaded = _load_from_args(args)
    if rc != 0 or loaded is None:
        return rc

    Path(args.out_dir).mkdir(parents=True, exist_ok=True)

    dataset_name = Path(args.dataset).name if args.dataset else ""
    exported_at = getattr(loaded.manifest, "exported_at", "")

    count = 0
    for card in loaded.cards:
        dsl = to_dsl_yaml_dict(card, dataset_name=dataset_name, exported_at=exported_at)
        write_card_yaml(dsl, args.out_dir)
        count += 1

    print(f"transform: wrote={count}")
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    try:
        cards = _load_cards_with_path(args.cards_dir)
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


def cmd_analyze(args: argparse.Namespace) -> int:
    try:
        cards = _load_cards_with_path(args.cards_dir)
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


def main() -> int:
    ap = argparse.ArgumentParser(prog="ygo-effect-dsl")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p0 = sub.add_parser("ingest", help="validate dataset manifest + read cards.jsonl")
    _add_dataset_arguments(p0)
    p0.set_defaults(func=cmd_ingest)

    p1 = sub.add_parser("transform", help="dataset -> DSL YAML")
    _add_dataset_arguments(p1)
    p1.add_argument("--out", dest="out_dir", required=True, help="output directory for YAML cards")
    p1.set_defaults(func=cmd_transform)

    p2 = sub.add_parser("validate", help="validate DSL YAML files for spec v0.0 minimum")
    p2.add_argument("cards_dir", help="directory that contains YAML cards")
    p2.set_defaults(func=cmd_validate)

    p3 = sub.add_parser("analyze", help="analyze DSL YAML cards and output report")
    p3.add_argument("cards_dir", help="directory that contains YAML cards")
    p3.add_argument("--out", dest="out_dir", required=True, help="report output directory")
    p3.set_defaults(func=cmd_analyze)

    args = ap.parse_args()
    try:
        return int(args.func(args))
    except (ValueError, OSError) as exc:
        print(f"error: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
