from __future__ import annotations

import argparse

from ygo_effect_dsl.prototype import (
    build_real_core_route,
    build_prototype_route,
    dump_real_core_stress_report,
    dump_route_document,
    load_prototype_scenario,
    run_real_core_parallel_stress,
    verify_real_core_route,
    verify_prototype_route,
)
from ygo_effect_dsl.route_dsl import load_route_document


def cmd_prototype_run(args: argparse.Namespace) -> int:
    scenario = load_prototype_scenario(args.scenario)
    route = build_prototype_route(scenario)
    dump_route_document(route, args.out)
    print(
        f"prototype-run: ok route_id={route['route_id']} "
        f"events={len(route['replay']['events'])} out={args.out}"
    )
    return 0


def cmd_prototype_verify(args: argparse.Namespace) -> int:
    scenario = load_prototype_scenario(args.scenario)
    route = load_route_document(args.route_file)
    result = verify_prototype_route(scenario, route)
    print(
        f"prototype-verify: ok route_id={result.route_id} "
        f"events={result.event_count} final_state_hash={result.final_state_hash}"
    )
    return 0


def cmd_prototype_real_run(args: argparse.Namespace) -> int:
    route = build_real_core_route(external_root=args.external_root)
    dump_route_document(route, args.out)
    print(
        f"prototype-real-run: ok route_id={route['route_id']} "
        f"events={len(route['replay']['events'])} out={args.out}"
    )
    return 0


def cmd_prototype_real_verify(args: argparse.Namespace) -> int:
    route = load_route_document(args.route_file)
    result = verify_real_core_route(route, external_root=args.external_root)
    print(
        f"prototype-real-verify: ok route_id={result.route_id} "
        f"events={result.event_count} final_state_hash={result.final_state_hash}"
    )
    return 0


def cmd_prototype_real_stress(args: argparse.Namespace) -> int:
    try:
        pool_sizes = tuple(
            int(value.strip()) for value in args.pool_sizes.split(",") if value.strip()
        )
    except ValueError as exc:
        raise ValueError("--pool-sizes must be comma-separated integers") from exc
    report = run_real_core_parallel_stress(
        external_root=args.external_root,
        pool_sizes=pool_sizes,
        task_count=args.tasks,
        include_failure_injection=not args.skip_failure_injection,
    )
    dump_real_core_stress_report(report, args.out)
    print(
        "prototype-real-stress: ok "
        f"report_id={report['semantic_report_id']} "
        f"pools={','.join(str(value) for value in pool_sizes)} "
        f"tasks={args.tasks} out={args.out}"
    )
    return 0
