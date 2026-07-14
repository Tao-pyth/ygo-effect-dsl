from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from ygo_effect_dsl import __version__
from ygo_effect_dsl.cli.cmd_analyze import cmd_analyze
from ygo_effect_dsl.cli.cmd_experiment import (
    cmd_experiment_inspect,
    cmd_experiment_interrupt,
    cmd_experiment_report,
    cmd_experiment_replay,
    cmd_experiment_run,
    cmd_experiment_search,
    cmd_migrate_experiment,
    cmd_validate_experiment,
)
from ygo_effect_dsl.cli.cmd_ocgcore import (
    cmd_ocgcore_assets_bootstrap,
    cmd_ocgcore_assets_verify,
    cmd_ocgcore_bootstrap,
    cmd_ocgcore_doctor,
    cmd_ocgcore_verify,
)
from ygo_effect_dsl.cli.cmd_prototype import (
    cmd_prototype_real_run,
    cmd_prototype_real_stress,
    cmd_prototype_real_verify,
    cmd_prototype_run,
    cmd_prototype_verify,
)
from ygo_effect_dsl.cli.cmd_transform import cmd_transform
from ygo_effect_dsl.cli.cmd_validate import cmd_validate
from ygo_effect_dsl.dict_loader import load_dictionary, validate_dictionary
from ygo_effect_dsl.io_input import load_inputs
from ygo_effect_dsl.normalize import normalize_card_texts
from ygo_effect_dsl.pipeline.transform import load_dataset_from_args
from ygo_effect_dsl.project_identity import PROJECT_IDENTITY
from ygo_effect_dsl.route_dsl import load_route_document, validate_route_document


def _default_dict_dir() -> str:
    if getattr(sys, "frozen", False):
        bundle_root = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
        return str(bundle_root / "resources" / "dict" / "v0_0")
    return "resources/dict/v0_0"


def _add_dataset_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--dataset", help="dataset directory that contains manifest.json and cards.jsonl")
    parser.add_argument("--manifest", help="path to manifest.json")
    parser.add_argument("--jsonl", help="path to cards.jsonl")


def cmd_ingest(args: argparse.Namespace) -> int:
    rc, loaded = load_dataset_from_args(args)
    if rc != 0 or loaded is None:
        return rc

    print(f"ingest: schema_version={loaded.manifest.export_schema_version}")
    print(f"ingest: record_count={loaded.manifest.record_count}")
    print(f"ingest: loaded={len(loaded.cards)}")
    print(f"ingest: fields={','.join(loaded.manifest.fields)}")
    return 0


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


def cmd_validate_route(args: argparse.Namespace) -> int:
    document = load_route_document(args.route_file)
    issues = validate_route_document(document)
    if issues:
        print(f"validate-route: failed issues={len(issues)}")
        for issue in issues:
            print(f"  - {issue}")
        return 1
    print(f"validate-route: ok route_id={document['route_id']}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(
        prog=PROJECT_IDENTITY.cli_name,
        description=(
            f"{PROJECT_IDENTITY.product_description}. Validate Route DSL artifacts, "
            "run experiments, and access legacy migration utilities."
        ),
    )
    ap.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    sub = ap.add_subparsers(dest="cmd", required=True)

    pr = sub.add_parser("validate-route", help="validate a Route DSL YAML or JSON document")
    pr.add_argument("route_file", help="path to a Route DSL document")
    pr.set_defaults(func=cmd_validate_route)

    experiment_validate = sub.add_parser(
        "validate-experiment",
        help="validate an Experiment YAML document",
    )
    experiment_validate.add_argument(
        "experiment_file", help="path to an Experiment YAML document"
    )
    experiment_validate.set_defaults(func=cmd_validate_experiment)

    experiment_migrate = sub.add_parser(
        "experiment-migrate",
        help="explicitly migrate an Experiment 0.3a document to 0.3b",
    )
    experiment_migrate.add_argument("experiment_file")
    experiment_migrate.add_argument("--out", required=True)
    experiment_migrate.add_argument(
        "--deck-order", choices=["known", "unknown"], required=True
    )
    experiment_migrate.add_argument(
        "--opening-hand",
        choices=["natural", "fixed", "probability_distribution"],
        required=True,
    )
    experiment_migrate.add_argument(
        "--sampling-reference-json",
        help="JSON object with sampler identity/version/seed when sampling is used",
    )
    experiment_migrate.set_defaults(func=cmd_migrate_experiment)

    def add_experiment_source(parser: argparse.ArgumentParser) -> None:
        parser.add_argument("experiment_file", help="path to an Experiment YAML document")

    def add_experiment_overrides(parser: argparse.ArgumentParser) -> None:
        parser.add_argument("--max-nodes", type=int)
        parser.add_argument("--max-seconds", type=float)
        parser.add_argument("--evaluator-id")
        parser.add_argument("--evaluator-version")
        parser.add_argument(
            "--interruption-mode",
            choices=["none", "scripted", "sampled", "specified"],
        )

    experiment_run = sub.add_parser(
        "experiment-run",
        help="run a validated Experiment and write Route DSL",
    )
    add_experiment_source(experiment_run)
    add_experiment_overrides(experiment_run)
    experiment_run.add_argument("--out", required=True, help="output Route DSL path")
    experiment_run.add_argument("--external-root")
    experiment_run.add_argument("--run-id")
    experiment_run.add_argument("--catalog", help="optional SQLite run catalog path")
    experiment_run.add_argument("--raw-log", help="optional JSONL raw log path")
    experiment_run.set_defaults(func=cmd_experiment_run)

    experiment_search = sub.add_parser(
        "experiment-search",
        help="run deterministic Random Search on a preflighted Experiment 0.4",
    )
    add_experiment_source(experiment_search)
    add_experiment_overrides(experiment_search)
    experiment_search.add_argument("--out", required=True, help="best Route DSL path")
    experiment_search.add_argument(
        "--search-report", required=True, help="SearchRun JSON report path"
    )
    experiment_search.add_argument("--external-root")
    experiment_search.add_argument("--worker-timeout", type=float, default=30.0)
    experiment_search.add_argument("--max-retries", type=int, default=1)
    experiment_search.set_defaults(func=cmd_experiment_search)

    experiment_replay = sub.add_parser(
        "experiment-replay",
        help="re-run an Experiment and verify its Route DSL",
    )
    add_experiment_source(experiment_replay)
    experiment_replay.add_argument("route_file", help="Route DSL path")
    experiment_replay.add_argument("--external-root")
    experiment_replay.add_argument("--run-id")
    experiment_replay.add_argument(
        "--verification-report",
        help="optional canonical JSON report written only after fresh Replay succeeds",
    )
    experiment_replay.set_defaults(func=cmd_experiment_replay)

    experiment_inspect = sub.add_parser(
        "experiment-inspect",
        help="validate and summarize an Experiment Route DSL",
    )
    add_experiment_source(experiment_inspect)
    experiment_inspect.add_argument("route_file", help="Route DSL path")
    experiment_inspect.set_defaults(func=cmd_experiment_inspect)

    experiment_interrupt = sub.add_parser(
        "experiment-interrupt",
        help="derive an Experiment with a configured interruption",
    )
    add_experiment_source(experiment_interrupt)
    experiment_interrupt.add_argument("--id", dest="interruption_id", required=True)
    experiment_interrupt.add_argument(
        "--mode", choices=["scripted", "sampled"], default="scripted"
    )
    experiment_interrupt.add_argument("--experiment-id")
    experiment_interrupt.add_argument("--replace", action="store_true")
    experiment_interrupt.add_argument("--out", required=True)
    experiment_interrupt.set_defaults(func=cmd_experiment_interrupt)

    experiment_report = sub.add_parser(
        "experiment-report",
        help="render a Markdown report from a validated Experiment Route",
    )
    add_experiment_source(experiment_report)
    experiment_report.add_argument("route_file", help="Route DSL path")
    experiment_report.add_argument("--out", required=True, help="Markdown report path")
    experiment_report.set_defaults(func=cmd_experiment_report)

    prototype_run = sub.add_parser(
        "prototype-run",
        help="run a scripted fixed-hand prototype and write Route DSL",
    )
    prototype_run.add_argument("scenario", help="path to a prototype scenario YAML")
    prototype_run.add_argument("--out", required=True, help="output Route DSL YAML or JSON path")
    prototype_run.set_defaults(func=cmd_prototype_run)

    prototype_verify = sub.add_parser(
        "prototype-verify",
        help="re-run a scripted scenario and verify an existing Route DSL document",
    )
    prototype_verify.add_argument("scenario", help="path to a prototype scenario YAML")
    prototype_verify.add_argument("route_file", help="path to the generated Route DSL document")
    prototype_verify.set_defaults(func=cmd_prototype_verify)

    prototype_real_run = sub.add_parser(
        "prototype-real-run",
        help="run the pinned fixed-hand scenario in an isolated ocgcore worker",
    )
    prototype_real_run.add_argument(
        "--out", required=True, help="output Route DSL YAML or JSON path"
    )
    prototype_real_run.add_argument(
        "--external-root", help="override the external dependency root"
    )
    prototype_real_run.set_defaults(func=cmd_prototype_real_run)

    prototype_real_verify = sub.add_parser(
        "prototype-real-verify",
        help="re-run the real-core scenario in a fresh worker and verify Route DSL",
    )
    prototype_real_verify.add_argument(
        "route_file", help="path to the generated Route DSL document"
    )
    prototype_real_verify.add_argument(
        "--external-root", help="override the external dependency root"
    )
    prototype_real_verify.set_defaults(func=cmd_prototype_real_verify)

    prototype_real_stress = sub.add_parser(
        "prototype-real-stress",
        help="stress deterministic scheduling against isolated ocgcore workers",
    )
    prototype_real_stress.add_argument(
        "--out", required=True, help="output stress evidence JSON path"
    )
    prototype_real_stress.add_argument(
        "--pool-sizes",
        default="1,2,4,8",
        help="comma-separated worker pool sizes",
    )
    prototype_real_stress.add_argument(
        "--tasks", type=int, default=8, help="unique tasks per pool run"
    )
    prototype_real_stress.add_argument(
        "--skip-failure-injection",
        action="store_true",
        help="run only pool-size and ordering checks",
    )
    prototype_real_stress.add_argument(
        "--external-root", help="override the external dependency root"
    )
    prototype_real_stress.set_defaults(func=cmd_prototype_real_stress)

    ocgcore_bootstrap = sub.add_parser(
        "ocgcore-bootstrap",
        help="explicitly acquire and build the pinned Windows x64 ocgcore runtime",
    )
    ocgcore_bootstrap.add_argument("--external-root", help="override the external dependency root")
    ocgcore_bootstrap.add_argument(
        "--offline",
        action="store_true",
        help="prohibit network access and use only verified cached inputs",
    )
    ocgcore_bootstrap.add_argument(
        "--source-only",
        action="store_true",
        help="acquire and verify source without downloading build tools or compiling",
    )
    ocgcore_bootstrap.set_defaults(func=cmd_ocgcore_bootstrap)

    ocgcore_verify = sub.add_parser(
        "ocgcore-verify",
        help="verify cached source, lock manifest, runtime hash, and C API version",
    )
    ocgcore_verify.add_argument("--external-root", help="override the external dependency root")
    ocgcore_verify.set_defaults(func=cmd_ocgcore_verify)

    ocgcore_doctor = sub.add_parser(
        "ocgcore-doctor",
        help="report the pinned ocgcore build prerequisites without installing them",
    )
    ocgcore_doctor.add_argument("--external-root", help="override the external dependency root")
    ocgcore_doctor.set_defaults(func=cmd_ocgcore_doctor)

    ocgcore_assets_bootstrap = sub.add_parser(
        "ocgcore-assets-bootstrap",
        help="explicitly acquire the pinned CardScripts and BabelCDB revisions",
    )
    ocgcore_assets_bootstrap.add_argument(
        "--external-root", help="override the external dependency root"
    )
    ocgcore_assets_bootstrap.add_argument(
        "--offline",
        action="store_true",
        help="prohibit network access and use only verified cached assets",
    )
    ocgcore_assets_bootstrap.set_defaults(func=cmd_ocgcore_assets_bootstrap)

    ocgcore_assets_verify = sub.add_parser(
        "ocgcore-assets-verify",
        help="verify pinned asset repositories and required file hashes",
    )
    ocgcore_assets_verify.add_argument(
        "--external-root", help="override the external dependency root"
    )
    ocgcore_assets_verify.set_defaults(func=cmd_ocgcore_assets_verify)

    p0 = sub.add_parser("ingest", help="legacy: validate card-text dataset manifest + cards.jsonl")
    _add_dataset_arguments(p0)
    p0.set_defaults(func=cmd_ingest)

    p1 = sub.add_parser("transform", help="legacy: ETL JSON/JSONL -> v0.0 card-text artifact")
    p1.add_argument("--in", dest="in_path", help="input file or directory")
    p1.add_argument("--glob", help="glob pattern when --in is directory")
    p1.add_argument("--dict", dest="dict_dir", default=_default_dict_dir(), help="dictionary directory")
    p1.add_argument("--out", dest="out_dir", default="data/export", help="output root directory")
    p1.add_argument("--limit", type=int, help="limit number of cards")
    p1.add_argument("--fail-fast", action="store_true", help="stop at first card failure")
    p1.add_argument("--log-level", default="INFO", choices=["INFO", "DEBUG"], help="log verbosity")
    p1.add_argument("--report", action=argparse.BooleanOptionalAction, default=True, help="write summary and unmatched reports")
    _add_dataset_arguments(p1)
    p1.set_defaults(func=cmd_transform)

    pvd = sub.add_parser("validate-dict", help="legacy: validate card-text conversion dictionary")
    pvd.add_argument("--dict", dest="dict_dir", default=_default_dict_dir(), help="dictionary directory")
    pvd.set_defaults(func=cmd_validate_dict)

    pn = sub.add_parser("normalize", help="legacy: normalize ETL card text and dump JSON")
    pn.add_argument("--in", dest="in_path", required=True, help="input file or directory")
    pn.add_argument("--glob", help="glob pattern when --in is directory")
    pn.add_argument("--dict", dest="dict_dir", default=_default_dict_dir(), help="dictionary directory")
    pn.add_argument("--out", dest="out_path", required=True, help="output JSON path")
    pn.add_argument("--limit", type=int, help="limit number of cards")
    pn.set_defaults(func=cmd_normalize)

    p2 = sub.add_parser("validate", help="legacy: validate v0.0 card-text artifacts")
    p2.add_argument("cards_dir", help="directory that contains YAML cards")
    p2.set_defaults(func=cmd_validate)

    p3 = sub.add_parser("analyze", help="legacy: analyze v0.0 card-text artifacts")
    p3.add_argument("cards_dir", help="directory that contains YAML cards")
    p3.add_argument("--out", dest="out_dir", required=True, help="report output directory")
    p3.set_defaults(func=cmd_analyze)

    args = ap.parse_args()
    try:
        return int(args.func(args))
    except (ValueError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
