from __future__ import annotations

import argparse
from copy import deepcopy
import json
from pathlib import Path
from typing import Any

from ygo_effect_dsl.external.clean_bootstrap_qualification import (
    run_clean_bootstrap_qualification,
    write_clean_bootstrap_qualification,
)
from ygo_effect_dsl.cli.cmd_experiment import cmd_experiment_search
from ygo_effect_dsl.engine.bridge.ocgcore.lua_qualification import (
    run_lua_load_qualification,
    write_lua_load_qualification,
)
from ygo_effect_dsl.experiment import (
    dump_experiment_document,
    load_experiment_document,
)
from ygo_effect_dsl.experiment.qualification import (
    QUALIFICATION_PROFILE_IDS,
    run_external_real_deck_qualification,
)
from ygo_effect_dsl.experiment.cross_validation import (
    run_strategy_interruption_cross_validation,
    write_strategy_interruption_cross_validation,
)
from ygo_effect_dsl.spikes.parallel_search_release_gate import (
    DEFAULT_MIN_NODE_BUDGET,
    DEFAULT_MIN_REPLAY_BUDGET,
    DEFAULT_REQUIRED_REPEATS,
    PARALLEL_SEARCH_RELEASE_RECORDS_PENDING_SCHEMA_VERSION,
    PARALLEL_SEARCH_RELEASE_RECORDS_SCHEMA_VERSION,
    REQUIRED_POOLS,
    REQUIRED_PROFILE_IDS,
    _record_bundle_witness,
    expand_parallel_search_release_record_inputs,
    summarize_parallel_search_release_source,
    validate_parallel_search_release_records,
    write_parallel_search_release_records,
    write_parallel_search_release_gate,
)
from ygo_effect_dsl.spikes.japanese_i18n_release_gate import (
    write_japanese_i18n_release_gate,
)
from ygo_effect_dsl.spikes.research_dashboard_release_gate import (
    RESEARCH_DASHBOARD_QUALIFICATION_ARTIFACT_MANIFEST_SCHEMA_VERSION,
    build_research_dashboard_qualification_checks_from_artifact_manifest,
    prepare_research_dashboard_qualification_checks,
    write_research_dashboard_qualification,
    write_research_dashboard_release_gate,
)
from ygo_effect_dsl.spikes.release_self_hosted_evidence import (
    adopt_release_self_hosted_evidence,
    verify_adopted_release_self_hosted_evidence,
    write_adopted_release_self_hosted_evidence_verification,
    write_release_self_hosted_evidence_audit,
)
from ygo_effect_dsl.spikes.release_readiness_status import (
    read_release_readiness_status,
    write_release_readiness_status,
)
from ygo_effect_dsl.spikes.production_distribution_release_gate import (
    write_production_distribution_release_gate,
)
from ygo_effect_dsl.spikes.reproducible_build_release_gate import (
    write_v1_build_provenance,
)
from ygo_effect_dsl.spikes.upgrade_rollback_release_gate import (
    write_v1_upgrade_rollback,
)
from ygo_effect_dsl.spikes.windows_installer_packaging import (
    write_v1_installer_packaging,
)
from ygo_effect_dsl.spikes.windows_authenticode_signing import (
    write_v1_authenticode_signing,
)
from ygo_effect_dsl.spikes.webview2_runtime_release_gate import (
    write_v1_webview2_runtime,
)
from ygo_effect_dsl.spikes.desktop_settings_release_gate import (
    write_v1_desktop_settings,
)
from ygo_effect_dsl.spikes.external_asset_setup_release_gate import (
    write_v1_external_asset_setup,
)
from ygo_effect_dsl.spikes.gated_release_workflow_gate import (
    write_v1_gated_release,
)
from ygo_effect_dsl.spikes.compatibility_policy_release_gate import (
    write_v1_compatibility_policy,
)
from ygo_effect_dsl.spikes.observability_redaction_retention_release_gate import (
    write_v1_observability_redaction_retention,
)


def _profile_inputs(values: list[str]) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for value in values:
        profile_id, separator, path = value.partition("=")
        if not separator or not path:
            raise ValueError("--experiment must use PROFILE=PATH")
        if profile_id in parsed:
            raise ValueError(f"duplicate qualification profile {profile_id!r}")
        parsed[profile_id] = path
    if set(parsed) != set(QUALIFICATION_PROFILE_IDS):
        raise ValueError(
            "--experiment requires exactly short, long, and grave_banish"
        )
    return {profile_id: parsed[profile_id] for profile_id in QUALIFICATION_PROFILE_IDS}


def _profile_path_inputs(values: list[str]) -> dict[str, Path]:
    parsed: dict[str, Path] = {}
    for value in values:
        profile_id, separator, path = value.partition("=")
        if not separator or not profile_id or not path:
            raise ValueError("--experiment must use PROFILE=PATH")
        if profile_id in parsed:
            raise ValueError(f"duplicate experiment profile {profile_id!r}")
        parsed[profile_id] = Path(path)
    if not parsed:
        raise ValueError("--experiment must be supplied at least once")
    return dict(sorted(parsed.items()))


def _int_csv(value: str, option: str) -> tuple[int, ...]:
    try:
        parsed = tuple(int(item) for item in value.split(",") if item)
    except ValueError as exc:
        raise ValueError(f"{option} must be a comma-separated integer list") from exc
    if not parsed or any(item < 1 for item in parsed):
        raise ValueError(f"{option} must contain positive integers")
    if len(set(parsed)) != len(parsed):
        raise ValueError(f"{option} must not contain duplicates")
    return parsed


def _current_rss_bytes() -> int:
    try:
        import psutil

        return int(psutil.Process().memory_info().rss)
    except (ImportError, OSError):
        return 0


def _parallel_search_run_experiment(
    source: dict[str, Any],
    *,
    base_seed: int,
    max_nodes: int,
    max_replays: int,
    max_depth: int | None,
    max_seconds: float | None,
    parallel_max_retries: int,
    pool_size: int,
    repeat_index: int,
) -> dict[str, Any]:
    experiment = deepcopy(source)
    search = experiment.setdefault("search", {})
    if not isinstance(search, dict):
        raise ValueError("experiment.search must be an object")
    budget = search.setdefault("budget", {})
    if not isinstance(budget, dict):
        raise ValueError("experiment.search.budget must be an object")
    budget["max_nodes"] = max_nodes
    budget["max_replays"] = max_replays
    if max_depth is not None:
        budget["max_depth"] = max_depth
    if max_seconds is not None:
        budget["max_seconds"] = max_seconds
    parameters = search.setdefault("parameters", {})
    if not isinstance(parameters, dict):
        raise ValueError("experiment.search.parameters must be an object")
    parameters["parallel"] = {
        "base_seed": base_seed,
        "max_retries": parallel_max_retries,
        "pool_size": pool_size,
    }
    return experiment


def _record_manifest_path(path: Path, *, base_dir: Path) -> str:
    try:
        return str(path.relative_to(base_dir))
    except ValueError:
        return str(path)


def _template_artifact_path(root: str, name: str) -> str:
    normalized = root.replace("\\", "/").rstrip("/")
    if not normalized or normalized == ".":
        return name
    return f"{normalized}/{name}"


def _research_dashboard_qualification_manifest_template(
    artifact_root: str,
) -> dict[str, object]:
    return {
        "committed_artifact": {
            "artifact_id": "REPLACE_WITH_RESULT_ARTIFACT_ID",
            "renderer_path_input": None,
            "report_sha256_verified": None,
            "result_view": _template_artifact_path(artifact_root, "result-view.json"),
            "route": _template_artifact_path(artifact_root, "route.yaml"),
            "route_id": "REPLACE_WITH_ROUTE_ID",
            "route_id_verified": None,
            "route_sha256_verified": None,
            "search_report": _template_artifact_path(artifact_root, "search-report.json"),
            "search_run_id": "REPLACE_WITH_SEARCH_RUN_ID",
        },
        "desktop": {
            "axe_violations": None,
            "high_contrast_passed": None,
            "keyboard_smoke_passed": None,
            "reduced_motion_passed": None,
            "screenshots": {
                "1440x900": _template_artifact_path(
                    artifact_root,
                    "desktop-1440x900.png",
                ),
                "960x600": _template_artifact_path(
                    artifact_root,
                    "desktop-960x600.png",
                ),
                "360x800": _template_artifact_path(
                    artifact_root,
                    "desktop-360x800.png",
                ),
            },
        },
        "fresh_replay": {
            "action_sequence_verified": None,
            "artifact_id": "REPLACE_WITH_FRESH_REPLAY_ARTIFACT_ID",
            "fresh_worker": None,
            "report": _template_artifact_path(
                artifact_root,
                "fresh-replay-report.json",
            ),
            "route_id_verified": None,
            "search_worker_shared_state": None,
            "terminal_state_verified": None,
        },
        "resource_budget": {
            "budget_wall_seconds": None,
            "censor_state_recorded": None,
            "max_artifact_bytes": None,
            "max_peak_rss_bytes": None,
            "max_wall_seconds": None,
            "measured_runs": None,
            "node_budget": 100_000,
            "replay_budget": 100_000,
            "report": _template_artifact_path(artifact_root, "resource-budget.json"),
            "within_budget": None,
        },
        "schema_version": RESEARCH_DASHBOARD_QUALIFICATION_ARTIFACT_MANIFEST_SCHEMA_VERSION,
        "security_redaction": {
            "absolute_paths_redacted": None,
            "csp_checked": None,
            "deck_contents_redacted": None,
            "renderer_path_input_rejected": None,
            "review": _template_artifact_path(
                artifact_root,
                "security-redaction-review.json",
            ),
            "secret_scan_passed": None,
        },
    }


def _parallel_search_timing_censored(report_path: Path) -> bool:
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if not isinstance(report, dict):
        raise ValueError("parallel-search-collect SearchRun report must be an object")
    return report.get("termination_reason") == "max_seconds"


def _validate_parallel_search_release_grid(
    profiles: Mapping[str, Path],
    pool_sizes: tuple[int, ...],
    *,
    max_nodes: int,
    max_replays: int,
    repeat_count: int,
) -> None:
    if tuple(sorted(profiles)) != tuple(sorted(REQUIRED_PROFILE_IDS)):
        raise ValueError(
            "parallel-search release collection requires profiles "
            f"{', '.join(REQUIRED_PROFILE_IDS)}"
        )
    if tuple(pool_sizes) != tuple(REQUIRED_POOLS):
        raise ValueError(
            "parallel-search release collection requires pool sizes "
            f"{','.join(str(pool) for pool in REQUIRED_POOLS)}"
        )
    if repeat_count < DEFAULT_REQUIRED_REPEATS:
        raise ValueError(
            "parallel-search release collection requires at least "
            f"{DEFAULT_REQUIRED_REPEATS} repeats"
        )
    if max_nodes < DEFAULT_MIN_NODE_BUDGET:
        raise ValueError(
            "parallel-search release collection requires max-nodes >= "
            f"{DEFAULT_MIN_NODE_BUDGET}"
        )
    if max_replays < DEFAULT_MIN_REPLAY_BUDGET:
        raise ValueError(
            "parallel-search release collection requires max-replays >= "
            f"{DEFAULT_MIN_REPLAY_BUDGET}"
        )


def cmd_real_deck_qualify(args: argparse.Namespace) -> int:
    experiments = _profile_inputs(args.experiment)
    index = run_external_real_deck_qualification(
        experiments,
        artifact_root=args.artifact_root,
        index_out=args.index_out,
        external_root=args.external_root,
        worker_timeout=args.worker_timeout,
        max_retries=args.max_retries,
    )
    print(
        "real-deck-qualify: ok "
        f"qualification_id={index['qualification_id']} "
        f"profiles={len(index['profiles'])} index={args.index_out}"
    )
    return 0


def cmd_strategy_interruption_qualify(args: argparse.Namespace) -> int:
    experiments = _profile_inputs(args.experiment)
    report = run_strategy_interruption_cross_validation(
        experiments,
        external_root=args.external_root,
        worker_timeout=args.worker_timeout,
        max_retries=args.max_retries,
    )
    write_strategy_interruption_cross_validation(args.out, report)
    print(
        "strategy-interruption-qualify: ok "
        f"qualification_id={report['qualification_id']} "
        f"cells={report['coverage']['matrix_cell_count']} out={args.out}"
    )
    return 0


def cmd_parallel_search_collect(args: argparse.Namespace) -> int:
    profiles = _profile_path_inputs(args.experiment)
    pool_sizes = _int_csv(args.pool_sizes, "--pool-sizes")
    if args.repeat_count < 1:
        raise ValueError("--repeat-count must be positive")
    for name in ("max_nodes", "max_replays", "base_seed", "parallel_max_retries"):
        value = getattr(args, name)
        if not isinstance(value, int) or value < 0:
            raise ValueError(f"--{name.replace('_', '-')} must be a non-negative integer")
    if args.max_nodes < 1 or args.max_replays < 1:
        raise ValueError("--max-nodes and --max-replays must be positive")
    if getattr(args, "require_release_grid", False):
        _validate_parallel_search_release_grid(
            profiles,
            pool_sizes,
            max_nodes=args.max_nodes,
            max_replays=args.max_replays,
            repeat_count=args.repeat_count,
        )
    artifact_root = Path(args.artifact_root)
    manifest_path = Path(args.manifest_out)
    records_out = Path(args.records_out)
    artifact_root.mkdir(parents=True, exist_ok=True)
    manifest_inputs: list[dict[str, object]] = []
    for profile_id, experiment_path in profiles.items():
        source_experiment = load_experiment_document(experiment_path)
        for pool_size in pool_sizes:
            for repeat_index in range(args.repeat_count):
                run_root = (
                    artifact_root
                    / profile_id
                    / f"pool-{pool_size}"
                    / f"repeat-{repeat_index}"
                )
                run_root.mkdir(parents=True, exist_ok=True)
                run_experiment = _parallel_search_run_experiment(
                    source_experiment,
                    base_seed=args.base_seed,
                    max_nodes=args.max_nodes,
                    max_replays=args.max_replays,
                    max_depth=args.max_depth,
                    max_seconds=args.max_seconds,
                    parallel_max_retries=args.parallel_max_retries,
                    pool_size=pool_size,
                    repeat_index=repeat_index,
                )
                run_experiment_path = run_root / "experiment.yaml"
                route_path = run_root / "best.route.yaml"
                report_path = run_root / "search-report.json"
                dump_experiment_document(run_experiment, run_experiment_path)
                rss_before = _current_rss_bytes()
                search_status = cmd_experiment_search(
                    argparse.Namespace(
                        evaluator_id=None,
                        evaluator_version=None,
                        experiment_file=run_experiment_path,
                        external_root=args.external_root,
                        interruption_mode=None,
                        max_nodes=None,
                        max_retries=args.max_retries,
                        max_seconds=None,
                        out=route_path,
                        search_report=report_path,
                        worker_timeout=args.worker_timeout,
                    )
                )
                if search_status != 0:
                    raise ValueError(
                        "parallel-search-collect experiment-search failed for "
                        f"profile={profile_id} pool={pool_size} repeat={repeat_index} "
                        f"status={search_status}"
                    )
                timing_censored = _parallel_search_timing_censored(report_path)
                rss_peak = max(rss_before, _current_rss_bytes())
                manifest_inputs.append(
                    {
                        "node_budget": args.max_nodes,
                        "pool_size": pool_size,
                        "profile_id": profile_id,
                        "repeat_index": repeat_index,
                        "replay_budget": args.max_replays,
                        "report_path": _record_manifest_path(
                            report_path,
                            base_dir=manifest_path.parent,
                        ),
                        "route_path": _record_manifest_path(
                            route_path,
                            base_dir=manifest_path.parent,
                        ),
                        "rss_peak_bytes": rss_peak,
                        "timing_censored": timing_censored,
                        "worker_kind": "real_core",
                    }
                )
    manifest = {
        "inputs": manifest_inputs,
        "schema_version": "parallel-search-record-inputs-v1",
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    evidence = write_parallel_search_release_records(
        _resolve_record_input_paths(manifest_inputs, base_dir=manifest_path.parent),
        output_path=records_out,
    )
    print(
        "parallel-search-collect: "
        f"records={len(evidence['records'])} "
        f"evidence_id={evidence['evidence_id']} "
        f"manifest={manifest_path} out={records_out}"
    )
    return 0


def cmd_parallel_search_gate(args: argparse.Namespace) -> int:
    source = json.loads(args.records.read_text(encoding="utf-8"))
    if not isinstance(source, dict):
        raise ValueError(
            "--records must be a parallel-search-release-records-v1 bundle "
            "produced by parallel-search-records"
        )
    if (
        source.get("schema_version") == PARALLEL_SEARCH_RELEASE_RECORDS_SCHEMA_VERSION
        or "evidence_id" in source
    ):
        source = validate_parallel_search_release_records(source)
    elif source.get("schema_version") == PARALLEL_SEARCH_RELEASE_RECORDS_PENDING_SCHEMA_VERSION:
        if source.get("records") != []:
            raise ValueError("--records pending evidence must contain no records")
    else:
        raise ValueError(
            "--records must be a parallel-search-release-records-v1 bundle "
            "produced by parallel-search-records"
        )
    records = source.get("records")
    if not isinstance(records, list):
        raise ValueError("--records bundle records must be a list")
    record_bundle = _record_bundle_witness(source, source_path=args.records)
    input_sources: list[dict[str, object]] = []
    source_rejections: list[str] = []
    for path in getattr(args, "source_evidence", None) or []:
        evidence_source = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(evidence_source, (dict, list)):
            raise ValueError("--source-evidence must contain a JSON object or list")
        summary, rejections = summarize_parallel_search_release_source(
            evidence_source,
            source_path=path,
        )
        input_sources.append(summary)
        source_rejections.extend(rejections)
    evidence = write_parallel_search_release_gate(
        records,
        extra_rejections=source_rejections,
        input_sources=input_sources,
        record_bundle=record_bundle,
        output_path=args.out,
        required_repeats=args.required_repeats,
    )
    status = "passed" if evidence["passed"] else "failed"
    print(
        "parallel-search-gate: "
        f"{status} evidence_id={evidence['evidence_id']} "
        f"profiles={len(evidence['profile_results'])} out={args.out}"
    )
    return 0 if evidence["passed"] else 1


def _resolve_record_input_paths(
    inputs: list[object],
    *,
    base_dir: Path,
) -> list[dict[str, object]]:
    resolved: list[dict[str, object]] = []
    for raw in inputs:
        if not isinstance(raw, dict):
            raise ValueError("record input entries must be objects")
        item = dict(raw)
        for key in ("report_path", "route_path"):
            value = item.get(key)
            if not isinstance(value, str) or not value:
                continue
            path = Path(value)
            if not path.is_absolute():
                path = base_dir / path
            item[key] = str(path)
        resolved.append(item)
    return resolved


def cmd_parallel_search_records(args: argparse.Namespace) -> int:
    source = json.loads(args.manifest.read_text(encoding="utf-8"))
    inputs = expand_parallel_search_release_record_inputs(source)
    evidence = write_parallel_search_release_records(
        _resolve_record_input_paths(inputs, base_dir=args.manifest.parent),
        output_path=args.out,
    )
    print(
        "parallel-search-records: "
        f"evidence_id={evidence['evidence_id']} "
        f"records={len(evidence['records'])} out={args.out}"
    )
    return 0


def cmd_research_dashboard_gate(args: argparse.Namespace) -> int:
    evidence = write_research_dashboard_release_gate(
        args.repo_root,
        output_path=args.out,
        qualification_path=args.qualification,
    )
    status = "passed" if evidence["passed"] else "failed"
    print(
        "research-dashboard-gate: "
        f"{status} evidence_id={evidence['evidence_id']} "
        f"rejections={len(evidence['rejection_reasons'])} out={args.out}"
    )
    return 0 if evidence["passed"] else 1


def cmd_japanese_i18n_gate(args: argparse.Namespace) -> int:
    evidence = write_japanese_i18n_release_gate(
        args.repo_root,
        output_path=args.out,
    )
    status = "passed" if evidence["passed"] else "failed"
    print(
        "japanese-i18n-gate: "
        f"{status} evidence_id={evidence['evidence_id']} "
        f"rejections={len(evidence['rejection_reasons'])} out={args.out}"
    )
    return 0 if evidence["passed"] else 1


def cmd_research_dashboard_qualification(args: argparse.Namespace) -> int:
    source = json.loads(args.checks.read_text(encoding="utf-8"))
    checks = source.get("checks") if isinstance(source, dict) else source
    if not isinstance(checks, list):
        raise ValueError("--checks must be a JSON list or an object with checks")
    checks = prepare_research_dashboard_qualification_checks(
        checks,
        base_dir=args.checks.parent,
    )
    evidence = write_research_dashboard_qualification(
        checks,
        output_path=args.out,
    )
    status = "passed" if evidence["passed"] else "failed"
    print(
        "research-dashboard-qualification: "
        f"{status} evidence_id={evidence['evidence_id']} "
        f"checks={len(evidence['checks'])} out={args.out}"
    )
    return 0 if evidence["passed"] else 1


def cmd_research_dashboard_qualification_bundle(args: argparse.Namespace) -> int:
    source = json.loads(args.manifest.read_text(encoding="utf-8"))
    if not isinstance(source, dict):
        raise ValueError("--manifest must contain a JSON object")
    checks = build_research_dashboard_qualification_checks_from_artifact_manifest(
        source,
        base_dir=args.manifest.parent,
    )
    if args.checks_out is not None:
        checks_destination = Path(args.checks_out)
        checks_destination.parent.mkdir(parents=True, exist_ok=True)
        checks_destination.write_text(
            json.dumps({"checks": checks}, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    prepared = prepare_research_dashboard_qualification_checks(
        checks,
        base_dir=args.manifest.parent,
    )
    evidence = write_research_dashboard_qualification(
        prepared,
        output_path=args.out,
    )
    status = "passed" if evidence["passed"] else "failed"
    print(
        "research-dashboard-qualification-bundle: "
        f"{status} evidence_id={evidence['evidence_id']} "
        f"checks={len(evidence['checks'])} out={args.out}"
    )
    return 0 if evidence["passed"] else 1


def cmd_research_dashboard_qualification_manifest_template(
    args: argparse.Namespace,
) -> int:
    template = _research_dashboard_qualification_manifest_template(args.artifact_root)
    destination = Path(args.out)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(template, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        "research-dashboard-qualification-manifest-template: "
        f"schema_version={template['schema_version']} out={args.out}"
    )
    return 0


def cmd_release_self_hosted_evidence_audit(args: argparse.Namespace) -> int:
    evidence = write_release_self_hosted_evidence_audit(
        args.artifact_dir,
        expected_commit=getattr(args, "expected_commit", None),
        expected_run_id=getattr(args, "expected_run_id", None),
        output_path=args.out,
        require_parallel_search=args.require_parallel_search,
        require_research_dashboard=args.require_research_dashboard,
    )
    print(
        "release-self-hosted-evidence-audit: "
        f"evidence_id={evidence['evidence_id']} "
        f"files={len(evidence['artifact_files'])} out={args.out}"
    )
    return 0


def cmd_release_self_hosted_evidence_adopt(args: argparse.Namespace) -> int:
    evidence = adopt_release_self_hosted_evidence(
        args.artifact_dir,
        expected_commit=getattr(args, "expected_commit", None),
        expected_run_id=getattr(args, "expected_run_id", None),
        output_dir=args.output_dir,
        adopt_parallel_search=args.adopt_parallel_search,
        adopt_research_dashboard=args.adopt_research_dashboard,
    )
    readiness_out = getattr(args, "readiness_out", None)
    if readiness_out is None:
        readiness_out = Path(args.output_dir) / "release_readiness_status.json"
    readiness = write_release_readiness_status(
        args.output_dir,
        output_path=readiness_out,
    )
    print(
        "release-self-hosted-evidence-adopt: "
        f"evidence_id={evidence['evidence_id']} "
        f"verification_id={evidence['adoption_verification']['evidence_id']} "
        f"readiness_id={readiness['evidence_id']} "
        f"incomplete={','.join(readiness['incomplete_versions']) or '-'} "
        f"files={len(evidence['adopted_files'])} out={args.output_dir}"
    )
    return 0


def cmd_release_self_hosted_evidence_verify_adopted(args: argparse.Namespace) -> int:
    evidence = write_adopted_release_self_hosted_evidence_verification(
        args.evidence_dir,
        expected_commit=getattr(args, "expected_commit", None),
        expected_run_id=getattr(args, "expected_run_id", None),
        output_path=args.out,
        require_parallel_search=args.require_parallel_search,
        require_research_dashboard=args.require_research_dashboard,
    )
    print(
        "release-self-hosted-evidence-verify-adopted: "
        f"evidence_id={evidence['evidence_id']} "
        f"files={len(evidence['verified_files'])} out={args.out}"
    )
    return 0


def cmd_release_readiness_status(args: argparse.Namespace) -> int:
    evidence = write_release_readiness_status(
        args.evidence_dir,
        output_path=args.out,
    )
    status = "passed" if evidence["passed"] else "incomplete"
    print(
        "release-readiness-status: "
        f"{status} evidence_id={evidence['evidence_id']} "
        f"ready={','.join(evidence['ready_versions']) or '-'} "
        f"incomplete={','.join(evidence['incomplete_versions']) or '-'} "
        f"out={args.out}"
    )
    return 0 if evidence["passed"] else 1


def cmd_release_readiness_verify(args: argparse.Namespace) -> int:
    evidence = read_release_readiness_status(
        args.status,
        evidence_dir=args.evidence_dir,
    )
    expected_commit = getattr(args, "expected_commit", None)
    expected_run_id = getattr(args, "expected_run_id", None)
    require_passed = getattr(args, "require_passed", False)
    status = "passed" if evidence["passed"] else "incomplete"
    if require_passed and not evidence["passed"]:
        print(
            "release-readiness-verify: "
            f"{status} evidence_id={evidence['evidence_id']} "
            f"ready={','.join(evidence['ready_versions']) or '-'} "
            f"incomplete={','.join(evidence['incomplete_versions']) or '-'} "
            f"status={args.status}"
        )
        return 1
    stages = {stage["stage"]: stage for stage in evidence["stages"]}
    parallel_adopted = (
        stages["0.6.0"]["adopted_self_hosted_evidence"].get("passed") is True
    )
    research_adopted = (
        stages["0.7.0"]["adopted_self_hosted_evidence"].get("passed") is True
    )
    require_parallel_search = (require_passed and evidence["passed"]) or parallel_adopted
    require_research_dashboard = (
        require_passed and evidence["passed"]
    ) or research_adopted
    if require_parallel_search or require_research_dashboard:
        verify_adopted_release_self_hosted_evidence(
            args.evidence_dir,
            expected_commit=expected_commit,
            expected_run_id=expected_run_id,
            require_parallel_search=require_parallel_search,
            require_research_dashboard=require_research_dashboard,
        )
    print(
        "release-readiness-verify: "
        f"{status} evidence_id={evidence['evidence_id']} "
        f"ready={','.join(evidence['ready_versions']) or '-'} "
        f"incomplete={','.join(evidence['incomplete_versions']) or '-'} "
        f"status={args.status}"
    )
    return 0


def cmd_production_distribution_gate(args: argparse.Namespace) -> int:
    evidence = write_production_distribution_release_gate(
        args.repo_root,
        evidence_dir=args.evidence_dir,
        output_path=args.out,
    )
    status = "passed" if evidence["passed"] else "failed"
    print(
        "production-distribution-gate: "
        f"{status} evidence_id={evidence['evidence_id']} "
        f"rejections={','.join(evidence['rejection_reasons']) or '-'} "
        f"out={args.out}"
    )
    if evidence["passed"] or args.allow_failed:
        return 0
    return 1


def cmd_v1_build_provenance(args: argparse.Namespace) -> int:
    evidence = write_v1_build_provenance(
        args.repo_root,
        output_path=args.out,
    )
    status = "passed" if evidence["passed"] else "failed"
    print(
        "v1-build-provenance: "
        f"{status} evidence_id={evidence['evidence_id']} "
        f"rejections={','.join(evidence['rejection_reasons']) or '-'} "
        f"out={args.out}"
    )
    return 0 if evidence["passed"] else 1


def cmd_v1_upgrade_rollback(args: argparse.Namespace) -> int:
    evidence = write_v1_upgrade_rollback(
        args.repo_root,
        output_path=args.out,
    )
    status = "passed" if evidence["passed"] else "failed"
    print(
        "v1-upgrade-rollback: "
        f"{status} evidence_id={evidence['evidence_id']} "
        f"rejections={','.join(evidence['rejection_reasons']) or '-'} "
        f"out={args.out}"
    )
    return 0 if evidence["passed"] else 1


def cmd_v1_gated_release(args: argparse.Namespace) -> int:
    evidence = write_v1_gated_release(
        args.repo_root,
        output_path=args.out,
    )
    status = "passed" if evidence["passed"] else "failed"
    print(
        "v1-gated-release: "
        f"{status} evidence_id={evidence['evidence_id']} "
        f"rejections={','.join(evidence['rejection_reasons']) or '-'} "
        f"out={args.out}"
    )
    return 0 if evidence["passed"] else 1


def cmd_v1_compatibility_policy(args: argparse.Namespace) -> int:
    evidence = write_v1_compatibility_policy(
        args.repo_root,
        output_path=args.out,
    )
    status = "passed" if evidence["passed"] else "failed"
    print(
        "v1-compatibility-policy: "
        f"{status} evidence_id={evidence['evidence_id']} "
        f"rejections={','.join(evidence['rejection_reasons']) or '-'} "
        f"out={args.out}"
    )
    return 0 if evidence["passed"] else 1


def cmd_v1_observability_redaction_retention(args: argparse.Namespace) -> int:
    evidence = write_v1_observability_redaction_retention(
        args.repo_root,
        output_path=args.out,
    )
    status = "passed" if evidence["passed"] else "failed"
    print(
        "v1-observability-redaction-retention: "
        f"{status} evidence_id={evidence['evidence_id']} "
        f"rejections={','.join(evidence['rejection_reasons']) or '-'} "
        f"out={args.out}"
    )
    return 0 if evidence["passed"] else 1


def cmd_v1_installer_packaging(args: argparse.Namespace) -> int:
    evidence = write_v1_installer_packaging(
        args.repo_root,
        output_path=args.out,
    )
    status = "passed" if evidence["passed"] else "failed"
    print(
        "v1-installer-packaging: "
        f"{status} evidence_id={evidence['evidence_id']} "
        f"rejections={','.join(evidence['rejection_reasons']) or '-'} "
        f"out={args.out}"
    )
    return 0 if evidence["passed"] else 1


def cmd_v1_authenticode_signing(args: argparse.Namespace) -> int:
    evidence = write_v1_authenticode_signing(
        args.repo_root,
        output_path=args.out,
    )
    status = "passed" if evidence["passed"] else "failed"
    print(
        "v1-authenticode-signing: "
        f"{status} evidence_id={evidence['evidence_id']} "
        f"rejections={','.join(evidence['rejection_reasons']) or '-'} "
        f"out={args.out}"
    )
    return 0 if evidence["passed"] else 1


def cmd_v1_webview2_runtime(args: argparse.Namespace) -> int:
    evidence = write_v1_webview2_runtime(
        args.repo_root,
        output_path=args.out,
    )
    status = "passed" if evidence["passed"] else "failed"
    print(
        "v1-webview2-runtime: "
        f"{status} evidence_id={evidence['evidence_id']} "
        f"rejections={','.join(evidence['rejection_reasons']) or '-'} "
        f"out={args.out}"
    )
    return 0 if evidence["passed"] else 1


def cmd_v1_external_asset_setup(args: argparse.Namespace) -> int:
    evidence = write_v1_external_asset_setup(
        args.repo_root,
        output_path=args.out,
    )
    status = "passed" if evidence["passed"] else "failed"
    print(
        "v1-external-asset-setup: "
        f"{status} evidence_id={evidence['evidence_id']} "
        f"rejections={','.join(evidence['rejection_reasons']) or '-'} "
        f"out={args.out}"
    )
    return 0 if evidence["passed"] else 1


def cmd_v1_desktop_settings(args: argparse.Namespace) -> int:
    evidence = write_v1_desktop_settings(
        args.repo_root,
        output_path=args.out,
    )
    status = "passed" if evidence["passed"] else "failed"
    print(
        "v1-desktop-settings: "
        f"{status} evidence_id={evidence['evidence_id']} "
        f"rejections={','.join(evidence['rejection_reasons']) or '-'} "
        f"out={args.out}"
    )
    return 0 if evidence["passed"] else 1


def cmd_lua_load_qualify(args: argparse.Namespace) -> int:
    report = run_lua_load_qualification(
        external_root=args.external_root,
        batch_size=args.batch_size,
        worker_timeout_seconds=args.worker_timeout,
        smoke_limit=args.smoke_limit,
    )
    write_lua_load_qualification(args.out, report)
    coverage = report["coverage"]
    database = report["database_coverage"]
    print(
        "ocgcore-lua-qualify: "
        f"{report['status']} qualification_id={report['qualification_id']} "
        f"scripts={coverage['selected_script_count']}/"
        f"{coverage['official_inventory_count']} "
        f"database={database['runtime_card_coverage_status']}"
    )
    return 0


def cmd_clean_bootstrap_qualify(args: argparse.Namespace) -> int:
    report = run_clean_bootstrap_qualification(work_root=args.work_root)
    write_clean_bootstrap_qualification(args.out, report)
    reproducibility = report["binary_reproducibility"]
    print(
        "ocgcore-clean-bootstrap-qualify: qualified_local "
        f"qualification_id={report['qualification_id']} "
        f"builds={len(report['builds'])} "
        f"binary_hashes={reproducibility['distinct_sha256_count']} "
        f"reproducibility={reproducibility['status']}"
    )
    return 0


__all__ = [
    "cmd_clean_bootstrap_qualify",
    "cmd_japanese_i18n_gate",
    "cmd_lua_load_qualify",
    "cmd_parallel_search_collect",
    "cmd_parallel_search_gate",
    "cmd_parallel_search_records",
    "cmd_production_distribution_gate",
    "cmd_v1_authenticode_signing",
    "cmd_v1_build_provenance",
    "cmd_v1_compatibility_policy",
    "cmd_v1_observability_redaction_retention",
    "cmd_real_deck_qualify",
    "cmd_research_dashboard_qualification",
    "cmd_research_dashboard_qualification_bundle",
    "cmd_research_dashboard_gate",
    "cmd_release_self_hosted_evidence_adopt",
    "cmd_release_self_hosted_evidence_audit",
    "cmd_release_self_hosted_evidence_verify_adopted",
    "cmd_release_readiness_status",
    "cmd_release_readiness_verify",
    "cmd_strategy_interruption_qualify",
    "cmd_v1_desktop_settings",
    "cmd_v1_external_asset_setup",
    "cmd_v1_gated_release",
    "cmd_v1_installer_packaging",
    "cmd_v1_upgrade_rollback",
    "cmd_v1_webview2_runtime",
]
