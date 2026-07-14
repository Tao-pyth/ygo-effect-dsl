from __future__ import annotations

import argparse
from collections.abc import Mapping
from copy import deepcopy
from datetime import datetime, timezone
import json
import uuid

from ygo_effect_dsl.experiment import (
    assert_experiment_matches_route,
    dump_experiment_document,
    load_experiment_document,
    migrate_experiment_v03a_to_v03b,
    resolve_experiment_overrides,
    validate_experiment,
)
from ygo_effect_dsl.reporting import write_markdown_report
from ygo_effect_dsl.prototype import (
    build_real_core_route,
    dump_route_document,
    verify_real_core_route,
)
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


def cmd_experiment_replay(args: argparse.Namespace) -> int:
    experiment = _resolved_experiment(args)
    run_id = _run_id(args.run_id)
    route = load_route_document(args.route_file)
    assert_experiment_matches_route(experiment, route)
    result = verify_real_core_route(route, external_root=args.external_root)
    print(
        f"experiment-replay: ok run_id={run_id} experiment_id={experiment['experiment_id']} "
        f"route_id={result.route_id} events={result.event_count} "
        f"final_state_hash={result.final_state_hash}"
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
