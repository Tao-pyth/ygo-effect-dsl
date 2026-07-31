from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from ygo_effect_dsl import __version__
from ygo_effect_dsl.cli.cmd_analyze import cmd_analyze
from ygo_effect_dsl.cli.cmd_corpus import cmd_ocgcore_decision_corpus
from ygo_effect_dsl.cli.cmd_export import cmd_analytics_export
from ygo_effect_dsl.cli.cmd_experiment import (
    cmd_experiment_inspect,
    cmd_experiment_interrupt,
    cmd_experiment_player_view,
    cmd_experiment_report,
    cmd_experiment_replay,
    cmd_experiment_run,
    cmd_experiment_search,
    cmd_migrate_experiment,
    cmd_validate_experiment,
)
from ygo_effect_dsl.cli.cmd_jobs import cmd_job_inspect
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
from ygo_effect_dsl.cli.cmd_qualification import (
    cmd_clean_bootstrap_qualify,
    cmd_japanese_i18n_gate,
    cmd_lua_load_qualify,
    cmd_parallel_search_collect,
    cmd_parallel_search_gate,
    cmd_parallel_search_records,
    cmd_production_distribution_gate,
    cmd_real_deck_qualify,
    cmd_research_dashboard_qualification,
    cmd_research_dashboard_qualification_bundle,
    cmd_research_dashboard_qualification_manifest_template,
    cmd_research_dashboard_gate,
    cmd_release_readiness_status,
    cmd_release_readiness_verify,
    cmd_release_self_hosted_evidence_adopt,
    cmd_release_self_hosted_evidence_audit,
    cmd_release_self_hosted_evidence_verify_adopted,
    cmd_strategy_interruption_qualify,
    cmd_v1_authenticode_signing,
    cmd_v1_installer_packaging,
)
from ygo_effect_dsl.cli.cmd_transform import cmd_transform
from ygo_effect_dsl.cli.cmd_validate import cmd_validate
from ygo_effect_dsl.dict_loader import load_dictionary, validate_dictionary
from ygo_effect_dsl.io_input import load_inputs
from ygo_effect_dsl.normalize import normalize_card_texts
from ygo_effect_dsl.pipeline.transform import load_dataset_from_args
from ygo_effect_dsl.project_identity import PROJECT_IDENTITY
from ygo_effect_dsl.route_dsl import load_route_document, validate_route_document
from ygo_effect_dsl.test_profile_plan import (
    TEST_PROFILE_PHASE_ORDER,
    TEST_PROFILE_ORDER,
    TEST_PROFILE_TEMPERATURE_ORDER,
    write_pytest_profile_measurement,
    write_pytest_profile_plan,
    write_pytest_profile_release_gate,
    write_pytest_profile_summary,
    write_pytest_profile_suite,
)


def _default_dict_dir() -> str:
    if getattr(sys, "frozen", False):
        bundle_root = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
        return str(bundle_root / "resources" / "dict" / "v0_0")
    return "resources/dict/v0_0"


def _add_dataset_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--dataset",
        help="dataset directory that contains manifest.json and cards.jsonl",
    )
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
    cards = load_inputs(
        args.in_path,
        glob_pattern=getattr(args, "glob", None),
        limit=getattr(args, "limit", None),
    )
    out_rows: list[dict[str, Any]] = []
    from ygo_effect_dsl.io_input import extract_card_fields

    for row in cards:
        fields = extract_card_fields(row)
        norm = normalize_card_texts(fields, dictionary.vocab)
        out_rows.append({"cid": fields.get("cid", ""), "norm": norm.as_dict()})

    out_path = Path(args.out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(out_rows, ensure_ascii=False, indent=2), encoding="utf-8"
    )
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


def cmd_test_profile_plan(args: argparse.Namespace) -> int:
    evidence = write_pytest_profile_plan(args.repo_root, output_path=args.out)
    print(
        "test-profile-plan: "
        f"evidence_id={evidence['evidence_id']} "
        f"tests={evidence['source']['discovered_file_count']} out={args.out}"
    )
    return 0


def cmd_test_profile_run(args: argparse.Namespace) -> int:
    evidence = write_pytest_profile_measurement(
        args.repo_root,
        output_path=args.out,
        profile=args.profile,
        extra_pytest_args=args.pytest_arg,
        suppress_success_output=args.suppress_success_output,
    )
    status = "passed" if evidence["passed"] else "failed"
    print(
        "test-profile-run: "
        f"{status} profile={evidence['profile']} "
        f"evidence_id={evidence['evidence_id']} "
        f"wall_seconds={evidence['wall_seconds']} "
        f"stdout_bytes={evidence['stdout_bytes']} "
        f"stderr_bytes={evidence['stderr_bytes']} out={args.out}"
    )
    return 0 if evidence["passed"] else 1


def cmd_test_profile_summary(args: argparse.Namespace) -> int:
    required_profiles = args.required_profile or list(TEST_PROFILE_ORDER)
    evidence = write_pytest_profile_summary(
        args.measurement,
        output_path=args.out,
        baseline_path=args.baseline,
        suite_path=args.suite,
        suite_phase=args.suite_phase,
        suite_temperature=args.suite_temperature,
        baseline_suite_path=args.baseline_suite,
        baseline_suite_phase=args.baseline_suite_phase,
        baseline_suite_temperature=args.baseline_suite_temperature,
        required_profiles=required_profiles,
    )
    status = "passed" if evidence["release_gate_passed"] else "failed"
    print(
        "test-profile-summary: "
        f"{status} evidence_id={evidence['evidence_id']} "
        f"measurements={evidence['included_measurement_count']} "
        f"missing_profiles={','.join(evidence['missing_profiles']) or '-'} "
        f"rejections={','.join(evidence['rejection_reasons']) or '-'} out={args.out}"
    )
    return 0 if evidence["release_gate_passed"] else 1


def cmd_test_profile_suite(args: argparse.Namespace) -> int:
    profiles = args.profile or list(TEST_PROFILE_ORDER)
    phases = args.phase or ["current"]
    temperatures = args.temperature or ["warm"]
    required_profiles = args.required_profile or list(TEST_PROFILE_ORDER)
    required_phases = args.required_phase or list(TEST_PROFILE_PHASE_ORDER)
    required_temperatures = (
        args.required_temperature or list(TEST_PROFILE_TEMPERATURE_ORDER)
    )
    evidence = write_pytest_profile_suite(
        args.repo_root,
        output_path=args.out,
        profiles=profiles,
        phases=phases,
        temperatures=temperatures,
        repeats=args.repeat,
        required_profiles=required_profiles,
        required_phases=required_phases,
        required_temperatures=required_temperatures,
        extra_pytest_args=args.pytest_arg,
        suppress_success_output=args.suppress_success_output,
        existing_suite_path=args.existing_suite,
    )
    status = "passed" if evidence["passed"] else "failed"
    print(
        "test-profile-suite: "
        f"{status} evidence_id={evidence['evidence_id']} "
        f"measurements={evidence['included_measurement_count']} "
        f"missing_cells={evidence['coverage']['missing_cell_count']} out={args.out}"
    )
    return 0 if evidence["passed"] else 1


def cmd_test_profile_gate(args: argparse.Namespace) -> int:
    evidence = write_pytest_profile_release_gate(
        plan_path=args.plan,
        suite_path=args.suite,
        summary_path=args.summary,
        output_path=args.out,
    )
    status = "passed" if evidence["passed"] else "failed"
    print(
        "test-profile-gate: "
        f"{status} evidence_id={evidence['evidence_id']} "
        f"rejections={','.join(evidence['rejection_reasons']) or '-'} out={args.out}"
    )
    return 0 if evidence["passed"] else 1


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

    pr = sub.add_parser(
        "validate-route", help="validate a Route DSL YAML or JSON document"
    )
    pr.add_argument("route_file", help="path to a Route DSL document")
    pr.set_defaults(func=cmd_validate_route)

    job_inspect = sub.add_parser(
        "job-inspect",
        help="print job state, recovery position, transitions, and artifacts",
    )
    job_inspect.add_argument(
        "job_id",
        help="content-addressed job ID",
    )
    job_inspect.add_argument(
        "--catalog",
        required=True,
        help="job catalog SQLite path",
    )
    job_inspect.set_defaults(func=cmd_job_inspect)

    analytics_export = sub.add_parser(
        "analytics-export",
        help="write a versioned JSON, CSV, or Parquet analytics export",
    )
    analytics_export.add_argument(
        "--format", choices=["json", "csv", "parquet"], required=True
    )
    analytics_export.add_argument(
        "--out", required=True, help="caller-owned export output directory"
    )
    export_source = analytics_export.add_mutually_exclusive_group(required=True)
    export_source.add_argument("--query", help="analytics query request JSON path")
    export_source.add_argument(
        "--comparison", help="validated analytics comparison response JSON path"
    )
    analytics_export.add_argument(
        "--snapshot", help="immutable analytics snapshot JSON path for --query"
    )
    analytics_export.set_defaults(func=cmd_analytics_export)

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
        parser.add_argument(
            "experiment_file", help="path to an Experiment YAML document"
        )

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
    experiment_replay.add_argument("--worker-timeout", type=float, default=30.0)
    experiment_replay.add_argument(
        "--verification-report",
        help="optional canonical JSON report written only after fresh Replay succeeds",
    )
    experiment_replay.set_defaults(func=cmd_experiment_replay)

    experiment_player_view = sub.add_parser(
        "experiment-player-view",
        help="fresh-Replay a complete Route and publish an audited PlayerView artifact",
    )
    add_experiment_source(experiment_player_view)
    experiment_player_view.add_argument("route_file", help="complete Route DSL path")
    experiment_player_view.add_argument(
        "--viewer", type=int, choices=[0, 1], required=True
    )
    experiment_player_view.add_argument(
        "--out", required=True, help="public PlayerView JSON path"
    )
    experiment_player_view.add_argument(
        "--audit-report", required=True, help="public information-audit JSON path"
    )
    experiment_player_view.add_argument(
        "--verification-report",
        required=True,
        help="public fresh-Replay verification JSON path",
    )
    experiment_player_view.add_argument(
        "--private-lineage",
        required=True,
        help="private source-Route lineage JSON path",
    )
    experiment_player_view.add_argument("--external-root")
    experiment_player_view.add_argument("--worker-timeout", type=float, default=30.0)
    experiment_player_view.add_argument("--max-retries", type=int, default=1)
    experiment_player_view.set_defaults(func=cmd_experiment_player_view)

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

    real_deck_qualify = sub.add_parser(
        "real-deck-qualify",
        help="qualify three repository-external real decks with Search and fresh Replay",
    )
    real_deck_qualify.add_argument(
        "--experiment",
        action="append",
        default=[],
        metavar="PROFILE=PATH",
        help="repeat exactly for short, long, and grave_banish",
    )
    real_deck_qualify.add_argument(
        "--artifact-root",
        required=True,
        help="repository-external directory for raw qualification artifacts",
    )
    real_deck_qualify.add_argument(
        "--index-out",
        required=True,
        help="sanitized qualification index JSON path",
    )
    real_deck_qualify.add_argument("--external-root")
    real_deck_qualify.add_argument("--worker-timeout", type=float, default=30.0)
    real_deck_qualify.add_argument("--max-retries", type=int, default=1)
    real_deck_qualify.set_defaults(func=cmd_real_deck_qualify)

    strategy_interruption_qualify = sub.add_parser(
        "strategy-interruption-qualify",
        help="cross-validate three real decks across Random, Beam, and MCTS",
    )
    strategy_interruption_qualify.add_argument(
        "--experiment",
        action="append",
        default=[],
        metavar="PROFILE=PATH",
        help="repeat exactly for short, long, and grave_banish",
    )
    strategy_interruption_qualify.add_argument(
        "--out",
        required=True,
        help="sanitized cross-validation evidence JSON path",
    )
    strategy_interruption_qualify.add_argument("--external-root")
    strategy_interruption_qualify.add_argument(
        "--worker-timeout", type=float, default=30.0
    )
    strategy_interruption_qualify.add_argument("--max-retries", type=int, default=1)
    strategy_interruption_qualify.set_defaults(func=cmd_strategy_interruption_qualify)

    parallel_search_gate = sub.add_parser(
        "parallel-search-gate",
        help="evaluate self-hosted parallel Search release-gate records",
    )
    parallel_search_gate.add_argument(
        "--records",
        type=Path,
        required=True,
        help="JSON list or object with records from self-hosted pool benchmarks",
    )
    parallel_search_gate.add_argument(
        "--out",
        required=True,
        help="content-addressed release-gate evidence JSON path",
    )
    parallel_search_gate.add_argument(
        "--required-repeats",
        type=int,
        default=5,
        help="minimum non-censored repeats per profile/pool cell",
    )
    parallel_search_gate.add_argument(
        "--source-evidence",
        action="append",
        type=Path,
        default=[],
        help=(
            "optional supporting evidence JSON to summarize in the gate output; "
            "the logical 100k, real-core replay benchmark, and real-core stress "
            "sources form the composite 0.6 release-scale claim"
        ),
    )
    parallel_search_gate.set_defaults(func=cmd_parallel_search_gate)

    parallel_search_collect = sub.add_parser(
        "parallel-search-collect",
        help=(
            "run a self-hosted profile/pool/repeat SearchRun grid and write "
            "0.6 release records"
        ),
    )
    parallel_search_collect.add_argument(
        "--experiment",
        action="append",
        default=[],
        help="PROFILE=Experiment YAML path; repeat for each release profile",
    )
    parallel_search_collect.add_argument(
        "--artifact-root",
        type=Path,
        required=True,
        help="directory for generated per-run Experiment, Route, and SearchRun files",
    )
    parallel_search_collect.add_argument(
        "--manifest-out",
        required=True,
        help="working parallel-search-records input manifest path",
    )
    parallel_search_collect.add_argument(
        "--records-out",
        required=True,
        help="content-addressed parallel-search-release-records-v1 JSON path",
    )
    parallel_search_collect.add_argument(
        "--pool-sizes",
        default="1,2,4",
        help="comma-separated pool sizes to run",
    )
    parallel_search_collect.add_argument(
        "--repeat-count",
        type=int,
        default=5,
        help="repeat count per profile/pool cell",
    )
    parallel_search_collect.add_argument("--max-nodes", type=int, default=100_000)
    parallel_search_collect.add_argument("--max-replays", type=int, default=100_000)
    parallel_search_collect.add_argument("--max-depth", type=int)
    parallel_search_collect.add_argument("--max-seconds", type=float)
    parallel_search_collect.add_argument("--base-seed", type=int, default=7_000)
    parallel_search_collect.add_argument(
        "--parallel-max-retries",
        type=int,
        default=1,
        help="parallel policy retry budget recorded in each generated Experiment",
    )
    parallel_search_collect.add_argument(
        "--require-release-grid",
        action="store_true",
        help=(
            "require the 0.6 release profile set, pool 1/2/4, repeat count, "
            "and 100k node/replay budgets before running Search"
        ),
    )
    parallel_search_collect.add_argument("--external-root")
    parallel_search_collect.add_argument("--worker-timeout", type=float, default=30.0)
    parallel_search_collect.add_argument("--max-retries", type=int, default=1)
    parallel_search_collect.set_defaults(func=cmd_parallel_search_collect)

    parallel_search_records = sub.add_parser(
        "parallel-search-records",
        help="normalize SearchRun reports into 0.6 parallel-search gate records",
    )
    parallel_search_records.add_argument(
        "--manifest",
        type=Path,
        required=True,
        help=(
            "JSON list/object with inputs, or parallel-search-record-input-manifest-v1 "
            "grid pointing at SearchRun report files"
        ),
    )
    parallel_search_records.add_argument(
        "--out",
        required=True,
        help="content-addressed parallel-search-release-records-v1 JSON path",
    )
    parallel_search_records.set_defaults(func=cmd_parallel_search_records)

    test_profile_plan = sub.add_parser(
        "test-profile-plan",
        help="write the 0.5.1 pytest profile classification evidence",
    )
    test_profile_plan.add_argument(
        "--repo-root",
        type=Path,
        default=Path("."),
        help="checkout root to scan for tests/test_*.py",
    )
    test_profile_plan.add_argument(
        "--out",
        required=True,
        help="content-addressed pytest profile plan JSON path",
    )
    test_profile_plan.set_defaults(func=cmd_test_profile_plan)

    test_profile_run = sub.add_parser(
        "test-profile-run",
        help="run one 0.5.1 pytest profile and write measurement evidence",
    )
    test_profile_run.add_argument(
        "--repo-root",
        type=Path,
        default=Path("."),
        help="checkout root containing tests/",
    )
    test_profile_run.add_argument(
        "--profile",
        choices=list(TEST_PROFILE_ORDER),
        required=True,
        help="pytest profile to execute",
    )
    test_profile_run.add_argument(
        "--out",
        required=True,
        help="content-addressed pytest profile measurement JSON path",
    )
    test_profile_run.add_argument(
        "--pytest-arg",
        action="append",
        default=[],
        help="extra pytest argument appended after the selected profile files",
    )
    test_profile_run.add_argument(
        "--suppress-success-output",
        action="store_true",
        help=(
            "disable pytest terminal output on successful runs; failing runs are "
            "rerun with normal output to keep failure evidence"
        ),
    )
    test_profile_run.set_defaults(func=cmd_test_profile_run)

    test_profile_summary = sub.add_parser(
        "test-profile-summary",
        help="summarize 0.5.1 pytest profile measurements and evaluate reduction gates",
    )
    test_profile_summary.add_argument(
        "--measurement",
        action="append",
        type=Path,
        default=[],
        help="repeat for each pytest-profile-measurement-v1 JSON file",
    )
    test_profile_summary.add_argument(
        "--suite",
        type=Path,
        help="optional pytest-profile-suite-v1 JSON path to extract measurements from",
    )
    test_profile_summary.add_argument(
        "--suite-phase",
        choices=list(TEST_PROFILE_PHASE_ORDER),
        default="current",
        help="phase to extract from --suite",
    )
    test_profile_summary.add_argument(
        "--suite-temperature",
        choices=list(TEST_PROFILE_TEMPERATURE_ORDER),
        default="warm",
        help="temperature to extract from --suite",
    )
    test_profile_summary.add_argument(
        "--baseline",
        type=Path,
        help="optional baseline pytest-profile-summary-v1 JSON path",
    )
    test_profile_summary.add_argument(
        "--baseline-suite",
        type=Path,
        help="optional pytest-profile-suite-v1 JSON path to derive baseline summary",
    )
    test_profile_summary.add_argument(
        "--baseline-suite-phase",
        choices=list(TEST_PROFILE_PHASE_ORDER),
        default="baseline",
        help="phase to extract from --baseline-suite",
    )
    test_profile_summary.add_argument(
        "--baseline-suite-temperature",
        choices=list(TEST_PROFILE_TEMPERATURE_ORDER),
        default="warm",
        help="temperature to extract from --baseline-suite",
    )
    test_profile_summary.add_argument(
        "--required-profile",
        action="append",
        choices=list(TEST_PROFILE_ORDER),
        help="repeat to override the required profile set; defaults to all profiles",
    )
    test_profile_summary.add_argument(
        "--out",
        required=True,
        help="content-addressed pytest profile summary JSON path",
    )
    test_profile_summary.set_defaults(func=cmd_test_profile_summary)

    test_profile_suite = sub.add_parser(
        "test-profile-suite",
        help="run labelled 0.5.1 pytest profile suite cells for cold/warm evidence",
    )
    test_profile_suite.add_argument(
        "--repo-root",
        type=Path,
        default=Path("."),
        help="checkout root containing tests/",
    )
    test_profile_suite.add_argument(
        "--profile",
        action="append",
        choices=list(TEST_PROFILE_ORDER),
        help="repeat to choose profiles to execute; defaults to all profiles",
    )
    test_profile_suite.add_argument(
        "--phase",
        action="append",
        choices=list(TEST_PROFILE_PHASE_ORDER),
        help="repeat to label executed cells; defaults to current",
    )
    test_profile_suite.add_argument(
        "--temperature",
        action="append",
        choices=list(TEST_PROFILE_TEMPERATURE_ORDER),
        help="repeat to label executed cells; defaults to warm",
    )
    test_profile_suite.add_argument(
        "--repeat",
        type=int,
        default=1,
        help="number of repeats for each selected phase/temperature/profile cell",
    )
    test_profile_suite.add_argument(
        "--existing-suite",
        type=Path,
        help="optional pytest-profile-suite-v1 JSON whose cells are merged first",
    )
    test_profile_suite.add_argument(
        "--required-profile",
        action="append",
        choices=list(TEST_PROFILE_ORDER),
        help="repeat to override profiles required by the suite gate",
    )
    test_profile_suite.add_argument(
        "--required-phase",
        action="append",
        choices=list(TEST_PROFILE_PHASE_ORDER),
        help="repeat to override phases required by the suite gate",
    )
    test_profile_suite.add_argument(
        "--required-temperature",
        action="append",
        choices=list(TEST_PROFILE_TEMPERATURE_ORDER),
        help="repeat to override temperatures required by the suite gate",
    )
    test_profile_suite.add_argument(
        "--pytest-arg",
        action="append",
        default=[],
        help="extra pytest argument appended after the selected profile files",
    )
    test_profile_suite.add_argument(
        "--suppress-success-output",
        action="store_true",
        help=(
            "disable pytest terminal output on successful runs; failing runs are "
            "rerun with normal output to keep failure evidence"
        ),
    )
    test_profile_suite.add_argument(
        "--out",
        required=True,
        help="content-addressed pytest profile suite JSON path",
    )
    test_profile_suite.set_defaults(func=cmd_test_profile_suite)

    test_profile_gate = sub.add_parser(
        "test-profile-gate",
        help="evaluate the 0.5.1 pytest profile release gate",
    )
    test_profile_gate.add_argument(
        "--plan",
        type=Path,
        required=True,
        help="pytest-profile-plan-v1 JSON path",
    )
    test_profile_gate.add_argument(
        "--suite",
        type=Path,
        required=True,
        help="pytest-profile-suite-v1 JSON path",
    )
    test_profile_gate.add_argument(
        "--summary",
        type=Path,
        required=True,
        help="pytest-profile-summary-v1 JSON path",
    )
    test_profile_gate.add_argument(
        "--out",
        required=True,
        help="content-addressed pytest profile release gate JSON path",
    )
    test_profile_gate.set_defaults(func=cmd_test_profile_gate)

    research_dashboard_gate = sub.add_parser(
        "research-dashboard-gate",
        help="evaluate 0.7 research dashboard release-readiness evidence",
    )
    research_dashboard_gate.add_argument(
        "--repo-root",
        type=Path,
        default=Path("."),
        help="checkout root to inspect",
    )
    research_dashboard_gate.add_argument(
        "--out",
        required=True,
        help="content-addressed research dashboard gate JSON path",
    )
    research_dashboard_gate.add_argument(
        "--qualification",
        type=Path,
        help="optional real-core dashboard qualification evidence JSON path",
    )
    research_dashboard_gate.set_defaults(func=cmd_research_dashboard_gate)

    japanese_i18n_gate = sub.add_parser(
        "japanese-i18n-gate",
        help="evaluate 0.8 Japanese desktop UI and i18n release-readiness evidence",
    )
    japanese_i18n_gate.add_argument(
        "--repo-root",
        type=Path,
        default=Path("."),
        help="checkout root to inspect",
    )
    japanese_i18n_gate.add_argument(
        "--out",
        required=True,
        help="content-addressed Japanese i18n gate JSON path",
    )
    japanese_i18n_gate.set_defaults(func=cmd_japanese_i18n_gate)

    research_dashboard_qualification = sub.add_parser(
        "research-dashboard-qualification",
        help="write content-addressed 0.7 real-core dashboard qualification evidence",
    )
    research_dashboard_qualification.add_argument(
        "--checks",
        type=Path,
        required=True,
        help=(
            "JSON list or object with checks for research-dashboard-qualification-v1; "
            "evidence_artifacts[].path is hashed and redacted"
        ),
    )
    research_dashboard_qualification.add_argument(
        "--out",
        required=True,
        help="content-addressed qualification evidence JSON path",
    )
    research_dashboard_qualification.set_defaults(
        func=cmd_research_dashboard_qualification
    )

    research_dashboard_qualification_bundle = sub.add_parser(
        "research-dashboard-qualification-bundle",
        help=(
            "build 0.7 qualification checks from a self-hosted artifact manifest "
            "and write qualification evidence"
        ),
    )
    research_dashboard_qualification_bundle.add_argument(
        "--manifest",
        type=Path,
        required=True,
        help="research-dashboard-qualification-artifact-manifest-v1 JSON path",
    )
    research_dashboard_qualification_bundle.add_argument(
        "--checks-out",
        help="optional generated checks JSON path before hashing/redaction",
    )
    research_dashboard_qualification_bundle.add_argument(
        "--out",
        required=True,
        help="content-addressed qualification evidence JSON path",
    )
    research_dashboard_qualification_bundle.set_defaults(
        func=cmd_research_dashboard_qualification_bundle
    )

    research_dashboard_qualification_manifest_template = sub.add_parser(
        "research-dashboard-qualification-manifest-template",
        help="write a 0.7 self-hosted dashboard qualification manifest template",
    )
    research_dashboard_qualification_manifest_template.add_argument(
        "--artifact-root",
        default="artifacts",
        help="relative runner-local directory used in template artifact paths",
    )
    research_dashboard_qualification_manifest_template.add_argument(
        "--out",
        required=True,
        help="research-dashboard-qualification-artifact-manifest-v1 JSON path",
    )
    research_dashboard_qualification_manifest_template.set_defaults(
        func=cmd_research_dashboard_qualification_manifest_template
    )

    release_self_hosted_evidence_audit = sub.add_parser(
        "release-self-hosted-evidence-audit",
        help="validate downloaded release-self-hosted-evidence workflow artifacts",
    )
    release_self_hosted_evidence_audit.add_argument(
        "--artifact-dir",
        type=Path,
        required=True,
        help="directory containing downloaded release-self-hosted-evidence files",
    )
    release_self_hosted_evidence_audit.add_argument(
        "--out",
        required=True,
        help="content-addressed release self-hosted evidence audit JSON path",
    )
    release_self_hosted_evidence_audit.add_argument(
        "--expected-commit",
        help="optional exact summary commit expected before audit passes",
    )
    release_self_hosted_evidence_audit.add_argument(
        "--expected-run-id",
        help="optional exact GitHub run_id expected before audit passes",
    )
    release_self_hosted_evidence_audit.add_argument(
        "--require-parallel-search",
        action="store_true",
        help="require 0.6 records/gate evidence and a passing parallel-search gate",
    )
    release_self_hosted_evidence_audit.add_argument(
        "--require-research-dashboard",
        action="store_true",
        help="require 0.7 qualification/gate evidence and a passing dashboard gate",
    )
    release_self_hosted_evidence_audit.set_defaults(
        func=cmd_release_self_hosted_evidence_audit
    )

    release_self_hosted_evidence_adopt = sub.add_parser(
        "release-self-hosted-evidence-adopt",
        help="adopt audited release-self-hosted-evidence artifacts into release evidence",
    )
    release_self_hosted_evidence_adopt.add_argument(
        "--artifact-dir",
        type=Path,
        required=True,
        help="directory containing downloaded release-self-hosted-evidence files",
    )
    release_self_hosted_evidence_adopt.add_argument(
        "--output-dir",
        type=Path,
        default=Path("docs/release/evidence"),
        help="release evidence directory to update",
    )
    release_self_hosted_evidence_adopt.add_argument(
        "--readiness-out",
        type=Path,
        help=(
            "release-readiness-status-v1 output path; defaults to "
            "OUTPUT_DIR/release_readiness_status.json"
        ),
    )
    release_self_hosted_evidence_adopt.add_argument(
        "--expected-commit",
        help="optional exact summary commit expected before adoption",
    )
    release_self_hosted_evidence_adopt.add_argument(
        "--expected-run-id",
        help="optional exact GitHub run_id expected before adoption",
    )
    release_self_hosted_evidence_adopt.add_argument(
        "--adopt-parallel-search",
        action="store_true",
        help="adopt 0.6 records/gate after requiring a passing parallel-search gate",
    )
    release_self_hosted_evidence_adopt.add_argument(
        "--adopt-research-dashboard",
        action="store_true",
        help="adopt 0.7 qualification/gate after requiring a passing dashboard gate",
    )
    release_self_hosted_evidence_adopt.set_defaults(
        func=cmd_release_self_hosted_evidence_adopt
    )

    release_self_hosted_evidence_verify_adopted = sub.add_parser(
        "release-self-hosted-evidence-verify-adopted",
        help="verify adopted release evidence still matches its self-hosted audit",
    )
    release_self_hosted_evidence_verify_adopted.add_argument(
        "--evidence-dir",
        type=Path,
        default=Path("docs/release/evidence"),
        help="release evidence directory containing the adopted audit JSON",
    )
    release_self_hosted_evidence_verify_adopted.add_argument(
        "--out",
        required=True,
        help="content-addressed adopted release evidence verification JSON path",
    )
    release_self_hosted_evidence_verify_adopted.add_argument(
        "--expected-commit",
        help="optional exact audit commit expected before verification",
    )
    release_self_hosted_evidence_verify_adopted.add_argument(
        "--expected-run-id",
        help="optional exact GitHub run_id expected before verification",
    )
    release_self_hosted_evidence_verify_adopted.add_argument(
        "--require-parallel-search",
        action="store_true",
        help="require adopted 0.6 evidence and a passing parallel-search gate",
    )
    release_self_hosted_evidence_verify_adopted.add_argument(
        "--require-research-dashboard",
        action="store_true",
        help="require adopted 0.7 evidence and a passing dashboard gate",
    )
    release_self_hosted_evidence_verify_adopted.set_defaults(
        func=cmd_release_self_hosted_evidence_verify_adopted
    )

    release_readiness_status = sub.add_parser(
        "release-readiness-status",
        help="summarize 0.5.1 through 0.8.0 release readiness evidence",
    )
    release_readiness_status.add_argument(
        "--evidence-dir",
        type=Path,
        default=Path("docs/release/evidence"),
        help="release evidence directory containing package gate evidence",
    )
    release_readiness_status.add_argument(
        "--out",
        required=True,
        help="content-addressed release readiness status JSON path",
    )
    release_readiness_status.set_defaults(func=cmd_release_readiness_status)

    release_readiness_verify = sub.add_parser(
        "release-readiness-verify",
        help="verify a saved release readiness status against current evidence files",
    )
    release_readiness_verify.add_argument(
        "--evidence-dir",
        type=Path,
        default=Path("docs/release/evidence"),
        help="release evidence directory to compare against the saved status",
    )
    release_readiness_verify.add_argument(
        "--status",
        type=Path,
        default=Path("docs/release/evidence/release_readiness_status.json"),
        help="saved release-readiness-status-v1 JSON path",
    )
    release_readiness_verify.add_argument(
        "--require-passed",
        action="store_true",
        help="return non-zero when the saved status is current but incomplete",
    )
    release_readiness_verify.add_argument(
        "--expected-commit",
        help=(
            "optional adopted self-hosted commit expected when adopted branch "
            "evidence is present"
        ),
    )
    release_readiness_verify.add_argument(
        "--expected-run-id",
        help=(
            "optional adopted self-hosted GitHub run_id expected when adopted "
            "branch evidence is present"
        ),
    )
    release_readiness_verify.set_defaults(func=cmd_release_readiness_verify)

    production_distribution_gate = sub.add_parser(
        "production-distribution-gate",
        help="evaluate the v1.0.0 production distribution release gate",
    )
    production_distribution_gate.add_argument(
        "--repo-root",
        type=Path,
        default=Path("."),
        help="checkout root containing release evidence and workflows",
    )
    production_distribution_gate.add_argument(
        "--evidence-dir",
        type=Path,
        default=Path("docs/release/evidence"),
        help="release evidence directory to aggregate",
    )
    production_distribution_gate.add_argument(
        "--out",
        required=True,
        help="content-addressed production distribution gate JSON path",
    )
    production_distribution_gate.add_argument(
        "--allow-failed",
        action="store_true",
        help="write failed gate evidence but return zero for CI dry-runs",
    )
    production_distribution_gate.set_defaults(func=cmd_production_distribution_gate)

    v1_installer_packaging = sub.add_parser(
        "v1-installer-packaging",
        help="evaluate the v1.0.0 Windows distribution package decision",
    )
    v1_installer_packaging.add_argument(
        "--repo-root",
        type=Path,
        default=Path("."),
        help="checkout root containing packaging docs and workflows",
    )
    v1_installer_packaging.add_argument(
        "--out",
        required=True,
        help="content-addressed v1 installer packaging evidence JSON path",
    )
    v1_installer_packaging.set_defaults(func=cmd_v1_installer_packaging)

    v1_authenticode_signing = sub.add_parser(
        "v1-authenticode-signing",
        help="evaluate the v1.0.0 Windows Authenticode signing gate",
    )
    v1_authenticode_signing.add_argument(
        "--repo-root",
        type=Path,
        default=Path("."),
        help="checkout root containing signing docs and workflows",
    )
    v1_authenticode_signing.add_argument(
        "--out",
        required=True,
        help="content-addressed v1 Authenticode signing evidence JSON path",
    )
    v1_authenticode_signing.set_defaults(func=cmd_v1_authenticode_signing)

    lua_load_qualify = sub.add_parser(
        "ocgcore-lua-qualify",
        help="qualify the pinned official CardScripts corpus through real ocgcore",
    )
    lua_load_qualify.add_argument(
        "--out",
        required=True,
        help="sanitized Lua load qualification JSON path",
    )
    lua_load_qualify.add_argument("--external-root")
    lua_load_qualify.add_argument("--batch-size", type=int, default=2048)
    lua_load_qualify.add_argument("--worker-timeout", type=float, default=300.0)
    lua_load_qualify.add_argument(
        "--smoke-limit",
        type=int,
        help="explicitly produce partial smoke evidence for the first N scripts",
    )
    lua_load_qualify.set_defaults(func=cmd_lua_load_qualify)

    clean_bootstrap_qualify = sub.add_parser(
        "ocgcore-clean-bootstrap-qualify",
        help="qualify clean, repeat, and interrupted ocgcore bootstraps",
    )
    clean_bootstrap_qualify.add_argument(
        "--work-root",
        required=True,
        help="repository-external directory that retains raw build artifacts",
    )
    clean_bootstrap_qualify.add_argument(
        "--out",
        required=True,
        help="sanitized clean-bootstrap qualification JSON path",
    )
    clean_bootstrap_qualify.set_defaults(func=cmd_clean_bootstrap_qualify)

    decision_corpus = sub.add_parser(
        "ocgcore-decision-corpus",
        help="verify Route Decision frames and write a sanitized shape corpus",
    )
    decision_corpus.add_argument(
        "--route",
        action="append",
        required=True,
        help="Route DSL path; repeat to aggregate multiple real-core Routes",
    )
    decision_corpus.add_argument("--out", required=True, help="output corpus JSON path")
    decision_corpus.set_defaults(func=cmd_ocgcore_decision_corpus)

    prototype_run = sub.add_parser(
        "prototype-run",
        help="run a scripted fixed-hand prototype and write Route DSL",
    )
    prototype_run.add_argument("scenario", help="path to a prototype scenario YAML")
    prototype_run.add_argument(
        "--out", required=True, help="output Route DSL YAML or JSON path"
    )
    prototype_run.set_defaults(func=cmd_prototype_run)

    prototype_verify = sub.add_parser(
        "prototype-verify",
        help="re-run a scripted scenario and verify an existing Route DSL document",
    )
    prototype_verify.add_argument("scenario", help="path to a prototype scenario YAML")
    prototype_verify.add_argument(
        "route_file", help="path to the generated Route DSL document"
    )
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
    ocgcore_bootstrap.add_argument(
        "--external-root", help="override the external dependency root"
    )
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
    ocgcore_verify.add_argument(
        "--external-root", help="override the external dependency root"
    )
    ocgcore_verify.set_defaults(func=cmd_ocgcore_verify)

    ocgcore_doctor = sub.add_parser(
        "ocgcore-doctor",
        help="fail-close the Windows x64 platform and pinned build prerequisites",
    )
    ocgcore_doctor.add_argument(
        "--external-root", help="override the external dependency root"
    )
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

    p0 = sub.add_parser(
        "ingest", help="legacy: validate card-text dataset manifest + cards.jsonl"
    )
    _add_dataset_arguments(p0)
    p0.set_defaults(func=cmd_ingest)

    p1 = sub.add_parser(
        "transform", help="legacy: ETL JSON/JSONL -> v0.0 card-text artifact"
    )
    p1.add_argument("--in", dest="in_path", help="input file or directory")
    p1.add_argument("--glob", help="glob pattern when --in is directory")
    p1.add_argument(
        "--dict",
        dest="dict_dir",
        default=_default_dict_dir(),
        help="dictionary directory",
    )
    p1.add_argument(
        "--out", dest="out_dir", default="data/export", help="output root directory"
    )
    p1.add_argument("--limit", type=int, help="limit number of cards")
    p1.add_argument(
        "--fail-fast", action="store_true", help="stop at first card failure"
    )
    p1.add_argument(
        "--log-level", default="INFO", choices=["INFO", "DEBUG"], help="log verbosity"
    )
    p1.add_argument(
        "--report",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="write summary and unmatched reports",
    )
    _add_dataset_arguments(p1)
    p1.set_defaults(func=cmd_transform)

    pvd = sub.add_parser(
        "validate-dict", help="legacy: validate card-text conversion dictionary"
    )
    pvd.add_argument(
        "--dict",
        dest="dict_dir",
        default=_default_dict_dir(),
        help="dictionary directory",
    )
    pvd.set_defaults(func=cmd_validate_dict)

    pn = sub.add_parser(
        "normalize", help="legacy: normalize ETL card text and dump JSON"
    )
    pn.add_argument(
        "--in", dest="in_path", required=True, help="input file or directory"
    )
    pn.add_argument("--glob", help="glob pattern when --in is directory")
    pn.add_argument(
        "--dict",
        dest="dict_dir",
        default=_default_dict_dir(),
        help="dictionary directory",
    )
    pn.add_argument("--out", dest="out_path", required=True, help="output JSON path")
    pn.add_argument("--limit", type=int, help="limit number of cards")
    pn.set_defaults(func=cmd_normalize)

    p2 = sub.add_parser("validate", help="legacy: validate v0.0 card-text artifacts")
    p2.add_argument("cards_dir", help="directory that contains YAML cards")
    p2.set_defaults(func=cmd_validate)

    p3 = sub.add_parser("analyze", help="legacy: analyze v0.0 card-text artifacts")
    p3.add_argument("cards_dir", help="directory that contains YAML cards")
    p3.add_argument(
        "--out", dest="out_dir", required=True, help="report output directory"
    )
    p3.set_defaults(func=cmd_analyze)

    args = ap.parse_args()
    try:
        return int(args.func(args))
    except (ValueError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
