from __future__ import annotations

import logging
import time
from argparse import Namespace

from ygo_effect_dsl.dict_loader import load_dictionary, validate_dictionary
from ygo_effect_dsl.ingest.jsonl_reader import load_dataset, resolve_dataset_paths
from ygo_effect_dsl.io_input import load_inputs
from ygo_effect_dsl.pipeline.core import transform_card
from ygo_effect_dsl.report import TransformReporter
from ygo_effect_dsl.rule_engine import RuleEngine
from ygo_effect_dsl.yaml_writer import write_yaml_by_cid

logger = logging.getLogger("ygo_effect_dsl")


def load_dataset_from_args(args: Namespace) -> tuple[int, object | None]:
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


def run_transform(args: Namespace) -> int:
    in_path = getattr(args, "in_path", None)
    dataset = getattr(args, "dataset", None)
    dataset_loaded = None
    if dataset and in_path is None:
        rc, dataset_loaded = load_dataset_from_args(args)
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
