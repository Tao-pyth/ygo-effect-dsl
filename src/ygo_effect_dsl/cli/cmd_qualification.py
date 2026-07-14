from __future__ import annotations

import argparse

from ygo_effect_dsl.experiment.qualification import (
    QUALIFICATION_PROFILE_IDS,
    run_external_real_deck_qualification,
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
