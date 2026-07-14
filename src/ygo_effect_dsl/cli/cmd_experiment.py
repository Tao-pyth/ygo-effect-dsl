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
    build_real_core_route,
    dump_route_document,
    verify_real_core_route,
)
from ygo_effect_dsl.engine.canonical import canonical_json
from ygo_effect_dsl.engine.search import SearchBudget, SearchExecutor, strategy_from_experiment
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
    preflight = preflight_scenario(
        experiment,
        experiment_path=args.experiment_file,
        external_root=args.external_root,
    )
    if not preflight.ok:
        report_path = Path(args.search_report)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(
            canonical_json(
                {
                    "preflight": preflight.to_dict(),
                    "schema_version": "search-run-failure-v1",
                    "status": "configuration_failure",
                }
            )
            + "\n",
            encoding="utf-8",
        )
        raise ValueError("scenario preflight failed: " + canonical_json(preflight.to_dict()))
    adapter = RealCoreFrontierAdapter(
        external_root=args.external_root,
        experiment_path=args.experiment_file,
        timeout_seconds=args.worker_timeout,
        max_retries=args.max_retries,
    )
    result = SearchExecutor(
        adapter,
        strategy_from_experiment(experiment),
        SearchBudget.from_experiment(experiment),
    ).run(experiment)
    report = {
        **result.to_dict(),
        "preflight": preflight.to_dict(),
        "worker_invocations": adapter.worker_invocations,
        "worker_retries": adapter.worker_retries,
    }
    report_path = Path(args.search_report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(canonical_json(report) + "\n", encoding="utf-8")
    if result.best_route is None:
        raise ValueError(
            f"search produced no legal Route before {result.termination_reason}; "
            f"report={args.search_report}"
        )
    dump_route_document(result.best_route.route_document, args.out)
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
