from __future__ import annotations

import argparse
from collections.abc import Mapping
from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import uuid

from ygo_effect_dsl.experiment import (
    assert_experiment_matches_route,
    build_fresh_replay_verification_report,
    dump_experiment_document,
    load_experiment_document,
    migrate_experiment_v03a_to_v03b,
    resolve_experiment_overrides,
    preflight_scenario,
    validate_experiment,
    write_fresh_replay_verification_report,
)
from ygo_effect_dsl.reporting import write_markdown_report
from ygo_effect_dsl.prototype import (
    RealCoreFrontierAdapter,
    RealCorePlayerViewAdapter,
    RealCorePlayerViewWorkerError,
    build_real_core_route,
    dump_route_document,
    verify_real_core_route,
)
from ygo_effect_dsl.engine.canonical import canonical_json, stable_digest
from ygo_effect_dsl.engine.failures import FailureRecord, classify_failure
from ygo_effect_dsl.engine.information import (
    InformationArtifactLeakError,
    InformationCanaryRegistry,
    assert_information_artifact_safe,
    audit_information_artifact,
)
from ygo_effect_dsl.engine.search import (
    SEARCH_ARTIFACT_COMMIT_SCHEMA_VERSION,
    SEARCH_RUN_FAILURE_SCHEMA_VERSION,
    SEARCH_RUN_REPORT_SCHEMA_VERSION,
    SearchBudget,
    SearchExecutor,
    strategy_from_experiment,
)
from ygo_effect_dsl.io_atomic import atomic_write_text, sha256_file
from ygo_effect_dsl.prototype.frontier import verify_general_search_route
from ygo_effect_dsl.route_dsl import (
    assert_valid_route_document,
    load_route_document,
)
from ygo_effect_dsl.storage import (
    RawLogRecord,
    RunCatalog,
    RunRecord,
    RunStatus,
    write_raw_log,
)


PLAYER_VIEW_PUBLICATION_AUDIT_SCHEMA_VERSION = "player-view-publication-audit-v1"
PLAYER_VIEW_PUBLICATION_FAILURE_SCHEMA_VERSION = "player-view-publication-failure-v1"


def _search_artifact_commit(
    status: str,
    *,
    route_id: str | None = None,
    route_sha256: str | None = None,
) -> dict[str, object]:
    return {
        "route_id": route_id,
        "route_sha256": route_sha256,
        "schema_version": SEARCH_ARTIFACT_COMMIT_SCHEMA_VERSION,
        "status": status,
    }


def _write_search_report(path: str | Path, report: Mapping[str, object]) -> None:
    atomic_write_text(path, canonical_json(report) + "\n")


def _worker_evidence(adapter: object) -> dict[str, object]:
    return {
        "quarantined_attempt_ids": list(
            getattr(adapter, "quarantined_attempt_ids", ())
        ),
        "worker_attempts": list(getattr(adapter, "worker_attempts", ())),
        "worker_invocations": int(getattr(adapter, "worker_invocations", 0)),
        "worker_retries": int(getattr(adapter, "worker_retries", 0)),
    }


def _execution_failure_report(
    *,
    adapter: object,
    error: BaseException,
    preflight: Mapping[str, object],
    status: str | None = None,
) -> dict[str, object]:
    carried = getattr(error, "failure", None)
    failure = carried if isinstance(carried, FailureRecord) else classify_failure(error)
    failure_status = status or (
        "worker_failure"
        if failure.category.startswith("worker_") or failure.category == "callback_error"
        else "execution_failure"
    )
    return {
        "artifact_commit": _search_artifact_commit("not_published"),
        "failure": failure.to_dict(),
        "preflight": preflight,
        "schema_version": SEARCH_RUN_FAILURE_SCHEMA_VERSION,
        "status": failure_status,
        **_worker_evidence(adapter),
    }


def cmd_validate_experiment(args: argparse.Namespace) -> int:
    experiment = load_experiment_document(args.experiment_file)
    issues = validate_experiment(experiment)
    if issues:
        print(f"validate-experiment: failed issues={len(issues)}")
        for issue in issues:
            print(f"  - {issue}")
        return 1
    print(
        "validate-experiment: ok "
        f"experiment_id={experiment['experiment_id']}"
    )
    return 0


def cmd_migrate_experiment(args: argparse.Namespace) -> int:
    sampling_reference = None
    if args.sampling_reference_json is not None:
        sampling_reference = json.loads(args.sampling_reference_json)
        if not isinstance(sampling_reference, Mapping):
            raise ValueError("--sampling-reference-json must decode to an object")
    experiment = load_experiment_document(args.experiment_file)
    migrated = migrate_experiment_v03a_to_v03b(
        experiment,
        deck_order=args.deck_order,
        opening_hand=args.opening_hand,
        sampling_reference=sampling_reference,
    )
    dump_experiment_document(migrated, args.out)
    print(
        "experiment-migrate: ok "
        f"experiment_id={migrated['experiment_id']} "
        f"policy_id={migrated['information_policy']['policy_id']} out={args.out}"
    )
    return 0


def _resolved_experiment(args: argparse.Namespace) -> dict[str, object]:
    experiment = load_experiment_document(args.experiment_file)
    return resolve_experiment_overrides(
        experiment,
        max_nodes=getattr(args, "max_nodes", None),
        max_seconds=getattr(args, "max_seconds", None),
        evaluator_id=getattr(args, "evaluator_id", None),
        evaluator_version=getattr(args, "evaluator_version", None),
        interruption_mode=getattr(args, "interruption_mode", None),
    )


def _runner_adapter(experiment: Mapping[str, object]) -> str:
    runner = experiment.get("runner")
    if not isinstance(runner, Mapping):
        raise ValueError("Experiment runner must be a mapping")
    adapter = runner.get("adapter")
    if not isinstance(adapter, str) or not adapter:
        raise ValueError("Experiment runner.adapter must be a non-empty string")
    return adapter


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _run_id(value: str | None) -> str:
    if value is None:
        return f"run_{uuid.uuid4().hex}"
    if not value.startswith("run_") or len(value) <= 4:
        raise ValueError("run_id must start with 'run_' and include an identifier")
    return value


def cmd_experiment_run(args: argparse.Namespace) -> int:
    experiment = _resolved_experiment(args)
    adapter = _runner_adapter(experiment)
    if adapter != "real_core_prototype":
        raise ValueError(f"unsupported Experiment runner adapter {adapter!r}")
    run_id = _run_id(args.run_id)
    started_at = _now()
    catalog = RunCatalog(args.catalog) if args.catalog else None
    if catalog is not None:
        catalog.create_run(
            RunRecord(
                run_id=run_id,
                experiment_id=str(experiment["experiment_id"]),
                status=RunStatus.RUNNING,
                started_at=started_at,
            )
        )
    raw_records = [
        RawLogRecord(
            run_id,
            0,
            "run_started",
            {"experiment_id": experiment["experiment_id"]},
        )
    ]
    try:
        route = build_real_core_route(
            external_root=args.external_root,
            experiment=experiment,
        )
        dump_route_document(route, args.out)
        finished_at = _now()
        if catalog is not None:
            catalog.add_route(
                route_id=str(route["route_id"]),
                run_id=run_id,
                route_path=str(args.out),
                state_hash=str(route["result"]["terminal_board"]["state_hash"]),
            )
            catalog.finish_run(
                run_id,
                status=RunStatus.COMPLETE,
                finished_at=finished_at,
            )
        raw_records.append(
            RawLogRecord(
                run_id,
                1,
                "run_completed",
                {
                    "event_count": len(route["replay"]["events"]),
                    "route_id": route["route_id"],
                },
            )
        )
    except Exception as exc:
        if catalog is not None:
            catalog.finish_run(
                run_id,
                status=RunStatus.FAILED,
                finished_at=_now(),
                error_summary=f"{type(exc).__name__}: {exc}",
            )
        raw_records.append(
            RawLogRecord(
                run_id,
                1,
                "run_failed",
                {"error_type": type(exc).__name__, "message": str(exc)},
            )
        )
        if args.raw_log:
            write_raw_log(args.raw_log, raw_records)
        raise
    if args.raw_log:
        write_raw_log(args.raw_log, raw_records)
    print(
        f"experiment-run: ok run_id={run_id} experiment_id={experiment['experiment_id']} "
        f"route_id={route['route_id']} events={len(route['replay']['events'])} "
        f"out={args.out}"
    )
    return 0


def cmd_experiment_search(args: argparse.Namespace) -> int:
    experiment = _resolved_experiment(args)
    route_path = Path(args.out)
    report_path = Path(args.search_report)
    if route_path.resolve() == report_path.resolve():
        raise ValueError("--out and --search-report must use different paths")
    preflight = preflight_scenario(
        experiment,
        experiment_path=args.experiment_file,
        external_root=args.external_root,
    )
    if not preflight.ok:
        _write_search_report(
            report_path,
            {
                "artifact_commit": _search_artifact_commit("not_published"),
                "preflight": preflight.to_dict(),
                "schema_version": SEARCH_RUN_FAILURE_SCHEMA_VERSION,
                "status": "configuration_failure",
            },
        )
        raise ValueError("scenario preflight failed: " + canonical_json(preflight.to_dict()))
    adapter = RealCoreFrontierAdapter(
        external_root=args.external_root,
        experiment_path=args.experiment_file,
        timeout_seconds=args.worker_timeout,
        max_retries=args.max_retries,
    )
    try:
        result = SearchExecutor(
            adapter,
            strategy_from_experiment(experiment),
            SearchBudget.from_experiment(experiment),
        ).run(experiment)
    except Exception as exc:
        _write_search_report(
            report_path,
            _execution_failure_report(
                adapter=adapter,
                error=exc,
                preflight=preflight.to_dict(),
            ),
        )
        raise
    report = {
        **result.to_dict(),
        "artifact_commit": _search_artifact_commit("not_published"),
        "preflight": preflight.to_dict(),
        "report_schema_version": SEARCH_RUN_REPORT_SCHEMA_VERSION,
        "status": "no_route" if result.best_route is None else "publishing",
        **_worker_evidence(adapter),
    }
    if result.best_route is None:
        _write_search_report(report_path, report)
        raise ValueError(
            f"search produced no legal Route before {result.termination_reason}; "
            f"report={args.search_report}"
        )
    try:
        dump_route_document(result.best_route.route_document, route_path)
    except Exception as exc:
        _write_search_report(
            report_path,
            _execution_failure_report(
                adapter=adapter,
                error=exc,
                preflight=preflight.to_dict(),
                status="artifact_failure",
            ),
        )
        raise
    report["artifact_commit"] = _search_artifact_commit(
        "committed",
        route_id=result.best_route.route_id,
        route_sha256=sha256_file(route_path),
    )
    report["status"] = "complete"
    _write_search_report(report_path, report)
    print(
        f"experiment-search: ok experiment_id={experiment['experiment_id']} "
        f"run_id={result.run_id} route_id={result.best_route.route_id} "
        f"nodes={result.nodes} replays={result.replays} out={args.out} "
        f"report={args.search_report}"
    )
    return 0


def cmd_experiment_replay(args: argparse.Namespace) -> int:
    experiment = _resolved_experiment(args)
    run_id = _run_id(args.run_id)
    route = load_route_document(args.route_file)
    assert_experiment_matches_route(experiment, route)
    if experiment.get("search", {}).get("strategy") == "random_search_v1":
        result = verify_general_search_route(
            route,
            external_root=args.external_root,
            experiment_path=args.experiment_file,
            timeout_seconds=getattr(args, "worker_timeout", 30.0),
        )
    else:
        result = verify_real_core_route(route, external_root=args.external_root)
    verification_report_path = getattr(args, "verification_report", None)
    if verification_report_path is not None:
        report = build_fresh_replay_verification_report(
            route,
            run_id=run_id,
            route_id=result.route_id,
            event_count=result.event_count,
            final_state_hash=result.final_state_hash,
        )
        write_fresh_replay_verification_report(verification_report_path, report)
    report_suffix = (
        f" verification_report={verification_report_path}"
        if verification_report_path is not None
        else ""
    )
    print(
        f"experiment-replay: ok run_id={run_id} experiment_id={experiment['experiment_id']} "
        f"route_id={result.route_id} events={result.event_count} "
        f"final_state_hash={result.final_state_hash}{report_suffix}"
    )
    return 0


def _player_view_failure_report(
    *,
    status: str,
    failure_code: str,
    failed_audit: Mapping[str, object] | None = None,
) -> dict[str, object]:
    report: dict[str, object] = {
        "artifact_commit": {"status": "not_published"},
        "failure_code": failure_code,
        "schema_version": PLAYER_VIEW_PUBLICATION_FAILURE_SCHEMA_VERSION,
        "status": status,
    }
    if failed_audit is not None:
        report["failed_audit"] = dict(failed_audit)
    return report


def cmd_experiment_player_view(args: argparse.Namespace) -> int:
    output_paths = {
        "audit_report": Path(args.audit_report),
        "out": Path(args.out),
        "private_lineage": Path(args.private_lineage),
        "verification_report": Path(args.verification_report),
    }
    resolved_paths = [path.resolve() for path in output_paths.values()]
    if len(resolved_paths) != len(set(resolved_paths)):
        raise ValueError("PlayerView output paths must be distinct")
    experiment = _resolved_experiment(args)
    route = load_route_document(args.route_file)
    assert_experiment_matches_route(experiment, route)
    adapter = RealCorePlayerViewAdapter(
        external_root=args.external_root,
        experiment_path=args.experiment_file,
        timeout_seconds=args.worker_timeout,
        max_retries=args.max_retries,
    )
    try:
        result = adapter.project(route, viewer=args.viewer)
    except InformationArtifactLeakError as exc:
        failure_report = _player_view_failure_report(
            status="audit_failure",
            failure_code="information_leak_detected",
            failed_audit=exc.report,
        )
        atomic_write_text(
            output_paths["audit_report"], canonical_json(failure_report) + "\n"
        )
        raise ValueError("PlayerView publication blocked by information audit") from None
    except RealCorePlayerViewWorkerError as exc:
        failure_report = _player_view_failure_report(
            status="worker_failure",
            failure_code=exc.code,
        )
        atomic_write_text(
            output_paths["audit_report"], canonical_json(failure_report) + "\n"
        )
        raise ValueError(
            f"PlayerView generation failed with safe code {exc.code!r}"
        ) from None
    registry = InformationCanaryRegistry.from_private_dict(
        result.private_canary_registry
    )
    try:
        player_view_audit = audit_information_artifact(
            result.player_view,
            artifact_kind="player_view_replay",
            registry=registry,
        )
        assert_information_artifact_safe(player_view_audit)
        if canonical_json(player_view_audit) != canonical_json(
            result.information_audit
        ):
            raise ValueError("worker and CLI PlayerView audits differ")
        verification_audit = audit_information_artifact(
            result.verification,
            artifact_kind="player_view_verification",
            registry=registry.for_artifact_kind("player_view_verification"),
        )
        assert_information_artifact_safe(verification_audit)
        publication_identity = {
            "artifact_audits": [player_view_audit, verification_audit],
            "artifact_commit": {
                "player_view_id": result.player_view["player_view_id"],
                "status": "committed",
            },
            "schema_version": PLAYER_VIEW_PUBLICATION_AUDIT_SCHEMA_VERSION,
            "status": "passed",
            "viewer": args.viewer,
        }
        publication_report = {
            "publication_audit_id": stable_digest(
                publication_identity, prefix="playerviewpublicationaudit_"
            ),
            **publication_identity,
        }
        report_safety = audit_information_artifact(
            publication_report,
            artifact_kind="player_view_audit_report",
            registry=registry.for_artifact_kind("player_view_audit_report"),
        )
        assert_information_artifact_safe(report_safety)
    except InformationArtifactLeakError as exc:
        failure_report = _player_view_failure_report(
            status="audit_failure",
            failure_code="information_leak_detected",
            failed_audit=exc.report,
        )
        failure_safety = audit_information_artifact(
            failure_report,
            artifact_kind="player_view_failure_report",
            registry=registry.for_artifact_kind("player_view_failure_report"),
        )
        assert_information_artifact_safe(failure_safety)
        atomic_write_text(
            output_paths["audit_report"], canonical_json(failure_report) + "\n"
        )
        raise ValueError("PlayerView publication blocked by information audit") from None
    private_lineage_text = canonical_json(result.private_lineage) + "\n"
    verification_text = canonical_json(result.verification) + "\n"
    audit_text = canonical_json(publication_report) + "\n"
    player_view_text = canonical_json(result.player_view) + "\n"
    atomic_write_text(output_paths["private_lineage"], private_lineage_text)
    atomic_write_text(output_paths["verification_report"], verification_text)
    atomic_write_text(output_paths["audit_report"], audit_text)
    atomic_write_text(output_paths["out"], player_view_text)
    print(
        "experiment-player-view: ok "
        f"player_view_id={result.player_view['player_view_id']} "
        f"viewer={args.viewer} events={len(result.player_view['events'])} "
        f"audit_id={player_view_audit['audit_id']}"
    )
    return 0


def cmd_experiment_inspect(args: argparse.Namespace) -> int:
    experiment = _resolved_experiment(args)
    route = load_route_document(args.route_file)
    assert_valid_route_document(route)
    assert_experiment_matches_route(experiment, route)
    result = route["result"]
    peak = result["peak_board"]
    terminal = result["terminal_board"]
    print(
        f"experiment-inspect: ok experiment_id={experiment['experiment_id']} "
        f"route_id={route['route_id']} success={str(result['success']).lower()} "
        f"peak_score={peak['score']} terminal_score={terminal['score']} "
        f"events={len(route['replay']['events'])}"
    )
    return 0


def cmd_experiment_interrupt(args: argparse.Namespace) -> int:
    experiment = load_experiment_document(args.experiment_file)
    derived = deepcopy(experiment)
    interruption = derived["interruption"]
    definitions = [] if args.replace else list(interruption["definitions"])
    definitions.append({"id": args.interruption_id})
    interruption["mode"] = args.mode
    interruption["definitions"] = definitions
    derived["experiment_id"] = args.experiment_id or (
        f"{experiment['experiment_id']}__{args.interruption_id}"
    )
    dump_experiment_document(derived, args.out)
    print(
        f"experiment-interrupt: ok experiment_id={derived['experiment_id']} "
        f"mode={args.mode} definitions={len(definitions)} out={args.out}"
    )
    return 0


def cmd_experiment_report(args: argparse.Namespace) -> int:
    experiment = _resolved_experiment(args)
    route = load_route_document(args.route_file)
    assert_valid_route_document(route)
    assert_experiment_matches_route(experiment, route)
    write_markdown_report(route["experiment"], route, args.out)
    print(
        f"experiment-report: ok experiment_id={experiment['experiment_id']} "
        f"route_id={route['route_id']} format=markdown out={args.out}"
    )
    return 0
