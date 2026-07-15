from __future__ import annotations

import json
from pathlib import Path

import pytest

from ygo_effect_dsl.engine.action import ActionKind
from ygo_effect_dsl.experiment import load_experiment_document
from ygo_effect_dsl.external.ocgcore import (
    OcgcoreBootstrapError,
    verify_ocgcore,
    verify_ocgcore_assets,
)
from ygo_effect_dsl.prototype import (
    RealCoreFrontierAdapter,
    RealCorePlayerViewAdapter,
)


ROOT = Path(__file__).parents[1]
EXPERIMENT = ROOT / "examples/experiments/general_search_inline.yaml"


def _runtime_or_skip() -> None:
    try:
        verify_ocgcore()
        verify_ocgcore_assets()
    except (OcgcoreBootstrapError, OSError) as exc:
        pytest.skip(f"pinned local ocgcore runtime/assets are unavailable: {exc}")


def _source_route() -> dict:
    experiment = load_experiment_document(EXPERIMENT)
    adapter = RealCoreFrontierAdapter(
        experiment_path=EXPERIMENT,
        timeout_seconds=30,
        max_retries=0,
    )
    prefix = []
    frontier = adapter.replay(experiment, prefix)
    for preferred_kind in (ActionKind.PASS, ActionKind.PASS, ActionKind.NORMAL_SUMMON):
        action = next(value for value in frontier.actions if value.kind == preferred_kind)
        prefix.append(action)
        frontier = adapter.replay(experiment, prefix)
    for _ in range(6):
        if frontier.legal_stop:
            break
        action = next(
            (value for value in frontier.actions if value.kind == ActionKind.PASS),
            frontier.actions[0],
        )
        prefix.append(action)
        frontier = adapter.replay(experiment, prefix)
    assert frontier.legal_stop
    assert frontier.route_document is not None
    return dict(frontier.route_document)


def test_real_core_player_view_is_fresh_replay_verified_for_both_viewers() -> None:
    _runtime_or_skip()
    source_route = _source_route()
    adapter = RealCorePlayerViewAdapter(
        experiment_path=EXPERIMENT,
        timeout_seconds=30,
        max_retries=0,
    )

    viewer0_first = adapter.project(source_route, viewer=0)
    viewer0_second = adapter.project(source_route, viewer=0)
    viewer1 = adapter.project(source_route, viewer=1)

    assert viewer0_first.player_view == viewer0_second.player_view
    assert viewer0_first.verification == viewer0_second.verification
    assert viewer0_first.player_view["player_view_id"] != viewer1.player_view[
        "player_view_id"
    ]
    assert len(viewer0_first.player_view["events"]) == len(
        source_route["replay"]["events"]
    )
    public_json = json.dumps(viewer0_first.player_view, sort_keys=True)
    assert source_route["route_id"] not in public_json
    assert source_route["result"]["terminal_board"]["state_hash"] not in public_json
    assert source_route["route_id"] == viewer0_first.private_lineage[
        "source_route_id"
    ]
