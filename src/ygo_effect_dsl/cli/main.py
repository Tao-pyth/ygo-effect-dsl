from __future__ import annotations

import argparse
import json
import logging
import time
from pathlib import Path
from typing import Any

from ygo_effect_dsl.analyze.report import build_report
from ygo_effect_dsl.dict_loader import load_dictionary, validate_dictionary
from ygo_effect_dsl.ingest.jsonl_reader import load_dataset, resolve_dataset_paths
from ygo_effect_dsl.io_input import load_inputs
from ygo_effect_dsl.normalize import normalize_card_texts
from ygo_effect_dsl.pipeline import transform_card
from ygo_effect_dsl.report import TransformReporter
from ygo_effect_dsl.rule_engine import RuleEngine
from ygo_effect_dsl.util.yaml_io import load_yaml
from ygo_effect_dsl.validate.validator import validate_card_yaml
from ygo_effect_dsl.yaml_writer import write_yaml_by_cid

logger = logging.getLogger("ygo_effect_dsl")


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
    in_path = getattr(args, "in_path", None)
    dataset = getattr(args, "dataset", None)
    dataset_loaded = None
    if dataset and in_path is None:
        rc, dataset_loaded = _load_from_args(args)
        if rc != 0:
            return rc
    elif not in_path:
        print("transform error: --in is required")
        return 2

    logging.basicConfig(level=getattr(logging, args.log_level.upper(), logging.INFO), format="%(asctime)s [%(levelname)s] %(message)s")

    dict_errors = validate_dictionary(args.dict_dir)
    if dict_errors:
        print("validate-dict failed:")
        for err in dict_errors:
            print(f"  - {err}")
        return 2

    dictionary = load_dictionary(args.dict_dir)
    if logger.isEnabledFor(logging.DEBUG):
        logger.debug("loaded vocab categories=%s", sorted(dictionary.vocab.keys()))
        for stage, rules in dictionary.rules_by_stage.items():
            logger.debug("loaded rules stage=%s count=%d", stage, len(rules))

    engine = RuleEngine()
    reporter = TransformReporter()

    start = time.time()
    if dataset_loaded is not None:
        cards = dataset_loaded.cards[: args.limit] if args.limit else dataset_loaded.cards
    else:
        cards = load_inputs(in_path, glob_pattern=getattr(args, "glob", None), limit=getattr(args, "limit", None))
    logger.info("loaded %d records", len(cards))

    for idx, card in enumerate(cards, start=1):
        cid = str(card.get("cid", card.get("id", "")))
        try:
            result = transform_card(card, dictionary, engine)
            write_yaml_by_cid(result.output, args.out_dir)
            reporter.record_success(result.output, result.stage_outcomes)
            if logger.isEnabledFor(logging.DEBUG):
                for stage, outcome in result.stage_outcomes.items():
                    logger.debug("cid=%s stage=%s hits=%s", cid, stage, outcome.matched_rule_ids)
        except Exception as exc:  # noqa: BLE001
            reporter.record_failure(cid, str(exc))
            logger.exception("failed to transform cid=%s", cid)
            if args.fail_fast:
                break

        if idx % 100 == 0 or idx == len(cards):
            elapsed = time.time() - start
            logger.info("progress: %d/%d elapsed=%.2fs failures=%d", idx, len(cards), elapsed, len(reporter.failures))

    if args.report:
        reporter.write_reports(args.out_dir, include_unmatched=True)

    if logger.isEnabledFor(logging.DEBUG):
        for stage, total in reporter.stage_total.items():
            hits = reporter.stage_hits[stage]
            logger.debug("stage=%s applied=%d matched=%d", stage, total, hits)

    print(f"transform: input={reporter.total} success={reporter.success} failure={len(reporter.failures)}")
    return 1 if args.fail_fast and reporter.failures else 0


def cmd_validate_dict(args: argparse.Namespace) -> int:
    errors = validate_dictionary(args.dict_dir)
    if errors:
        print("validate-dict: failed")
        for err in errors:
            print(f"  - {err}")
        return 1
    print("validate-dict: ok")
    return 0


def cmd_normalize(args: argparse.Namespace) -> int:
    dict_errors = validate_dictionary(args.dict_dir)
    if dict_errors:
        print("validate-dict failed:")
        for err in dict_errors:
            print(f"  - {err}")
        return 2

    dictionary = load_dictionary(args.dict_dir)
    cards = load_inputs(args.in_path, glob_pattern=getattr(args, "glob", None), limit=getattr(args, "limit", None))
    out_rows: list[dict[str, Any]] = []
    from ygo_effect_dsl.io_input import extract_card_fields

    for row in cards:
        fields = extract_card_fields(row)
        norm = normalize_card_texts(fields, dictionary.vocab)
        out_rows.append({"cid": fields.get("cid", ""), "norm": norm.as_dict()})

    out_path = Path(args.out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out_rows, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"normalize: wrote={len(out_rows)} to {out_path}")
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

    p1 = sub.add_parser("transform", help="ETL JSON/JSONL -> v0.0 DSL YAML")
    p1.add_argument("--in", dest="in_path", help="input file or directory")
    p1.add_argument("--glob", help="glob pattern when --in is directory")
    p1.add_argument("--dict", dest="dict_dir", default="resources/dict/v0_0", help="dictionary directory")
    p1.add_argument("--out", dest="out_dir", default="data/export", help="output root directory")
    p1.add_argument("--limit", type=int, help="limit number of cards")
    p1.add_argument("--fail-fast", action="store_true", help="stop at first card failure")
    p1.add_argument("--log-level", default="INFO", choices=["INFO", "DEBUG"], help="log verbosity")
    p1.add_argument("--report", action=argparse.BooleanOptionalAction, default=True, help="write summary and unmatched reports")
    _add_dataset_arguments(p1)  # backward compatibility
    p1.set_defaults(func=cmd_transform)

    pvd = sub.add_parser("validate-dict", help="validate dictionary files and regex patterns")
    pvd.add_argument("--dict", dest="dict_dir", default="resources/dict/v0_0", help="dictionary directory")
    pvd.set_defaults(func=cmd_validate_dict)

    pn = sub.add_parser("normalize", help="debug: normalize ETL text and dump JSON")
    pn.add_argument("--in", dest="in_path", required=True, help="input file or directory")
    pn.add_argument("--glob", help="glob pattern when --in is directory")
    pn.add_argument("--dict", dest="dict_dir", default="resources/dict/v0_0", help="dictionary directory")
    pn.add_argument("--out", dest="out_path", required=True, help="output JSON path")
    pn.add_argument("--limit", type=int, help="limit number of cards")
    pn.set_defaults(func=cmd_normalize)

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
