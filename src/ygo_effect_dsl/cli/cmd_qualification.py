from __future__ import annotations

import argparse

from ygo_effect_dsl.external.clean_bootstrap_qualification import (
    run_clean_bootstrap_qualification,
    write_clean_bootstrap_qualification,
)
from ygo_effect_dsl.engine.bridge.ocgcore.lua_qualification import (
    run_lua_load_qualification,
    write_lua_load_qualification,
)
from ygo_effect_dsl.experiment.qualification import (
    QUALIFICATION_PROFILE_IDS,
    run_external_real_deck_qualification,
)
from ygo_effect_dsl.experiment.cross_validation import (
    run_strategy_interruption_cross_validation,
    write_strategy_interruption_cross_validation,
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
    "cmd_lua_load_qualify",
    "cmd_real_deck_qualify",
    "cmd_strategy_interruption_qualify",
]
