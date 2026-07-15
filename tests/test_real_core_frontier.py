from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

import pytest

from ygo_effect_dsl.engine.action import Action, ActionKind, Selection
from ygo_effect_dsl.experiment import (
    build_fresh_replay_verification_report,
    load_experiment_document,
    preflight_scenario,
    read_fresh_replay_verification_report,
)
from ygo_effect_dsl.experiment import qualification as qualification_module
from ygo_effect_dsl.external.ocgcore import (
    OcgcoreBootstrapError,
    verify_ocgcore,
    verify_ocgcore_assets,
)
from ygo_effect_dsl.prototype import (
    RealCoreFrontierAdapter,
    RealCoreFrontierWorkerError,
    verify_general_search_route,
)
from ygo_effect_dsl.io_atomic import sha256_file
from ygo_effect_dsl.route_dsl import load_route_document
from ygo_effect_dsl.runtime_imports import current_checkout_environment


ROOT = Path(__file__).parents[1]
EXPERIMENT = ROOT / "examples/experiments/general_search_inline.yaml"


def _runtime_or_skip() -> None:
    try:
        verify_ocgcore()
        verify_ocgcore_assets()
    except (OcgcoreBootstrapError, OSError) as exc:
        pytest.skip(f"pinned local ocgcore runtime/assets are unavailable: {exc}")


def test_fresh_real_core_frontier_replays_prefix_to_a_valid_route() -> None:
    _runtime_or_skip()
    experiment = load_experiment_document(EXPERIMENT)
    preflight = preflight_scenario(experiment, experiment_path=EXPERIMENT)
    assert preflight.ok
    adapter = RealCoreFrontierAdapter(
        experiment_path=EXPERIMENT,
        timeout_seconds=30,
        max_retries=0,
    )

    root = adapter.replay(experiment, ())
    first_pass = next(action for action in root.actions if action.kind == ActionKind.PASS)
    standby = adapter.replay(experiment, (first_pass,))
    second_pass = next(
        action for action in standby.actions if action.kind == ActionKind.PASS
    )
    main_phase = adapter.replay(experiment, (first_pass, second_pass))
    summon = next(
        action for action in main_phase.actions if action.kind == ActionKind.NORMAL_SUMMON
    )
    prefix = [first_pass, second_pass, summon]
    terminal = adapter.replay(experiment, prefix)
    for _ in range(6):
        if terminal.legal_stop:
            break
        next_action = next(
            (action for action in terminal.actions if action.kind == ActionKind.PASS),
            terminal.actions[0],
        )
        prefix.append(next_action)
        terminal = adapter.replay(experiment, prefix)

    assert root.request["request_type"] == "select_chain"
    assert root.state_completeness == "query_api_projection"
    assert main_phase.request["request_type"] == "select_idle_command"
    assert terminal.legal_stop
    assert terminal.success
    assert terminal.route_document is not None
    script_resolution = terminal.route_document["result"]["lua_script_resolution"]
    assert script_resolution["schema_version"] == 1
    assert script_resolution["profile_id"] == "card-scripts-official-v1"
    assert script_resolution["loads"]
    assert all(item["outcome"] == "loaded" for item in script_resolution["loads"])
    assert all("sha256" in item for item in script_resolution["loads"])
    verification = verify_general_search_route(
        terminal.route_document,
        experiment_path=EXPERIMENT,
    )
    assert verification.event_count == len(prefix)
    assert verification.route_id == terminal.route_document["route_id"]
    report = build_fresh_replay_verification_report(
        terminal.route_document,
        run_id="run_real_core_frontier_fixture",
        route_id=verification.route_id,
        event_count=verification.event_count,
        final_state_hash=verification.final_state_hash,
    )
    assert report["scenario"]["deck_source"] == "inline"
    assert report["verification_scope"] == "general_search"
    assert report["scenario"]["deck_sha256"] == preflight.manifest.deck_sha256
    assert report["lua_resolution"]["profile_id"] == "card-scripts-official-v1"
    assert report["lua_resolution"]["load_count"] == len(script_resolution["loads"])


def test_specified_card_activation_opportunity_branches_only_core_candidates() -> None:
    _runtime_or_skip()
    experiment = load_experiment_document(EXPERIMENT)
    experiment["interruption"] = {
        "mode": "specified",
        "definitions": [
            {
                "id": "opening_hand_trigger_all_opportunities",
                "source_card_code": 2511,
                "source_player": 0,
                "source_zone": "hand",
                "response_roles": [],
            }
        ],
    }
    adapter = RealCoreFrontierAdapter(
        experiment_path=EXPERIMENT,
        timeout_seconds=30,
        max_retries=0,
    )

    frontier = adapter.replay(experiment, ())

    taxonomy = frontier.request["interruption_taxonomy"]
    assert len(taxonomy) == 1
    assert taxonomy[0]["status"] == "supported"
    supported_ids = {
        candidate["candidate_id"] for candidate in taxonomy[0]["candidates"]
    }
    activation_ids = {
        selection.candidate_id
        for action in frontier.actions
        if action.kind == ActionKind.ACTIVATE_EFFECT
        for selection in action.selections
    }
    assert supported_ids == activation_ids
    assert {action.kind for action in frontier.actions} == {
        ActionKind.ACTIVATE_EFFECT,
        ActionKind.PASS,
    }
    composition = frontier.request["interruption_composition"]
    opportunities = frontier.request["interruption_opportunities"]
    assert composition["schema_version"] == "multi-interruption-composition-v1"
    assert opportunities["activation_counts"] == {
        "opening_hand_trigger_all_opportunities": 0
    }
    assert len(opportunities["opportunities"]) == 1

    activation = next(
        action
        for action in frontier.actions
        if action.kind == ActionKind.ACTIVATE_EFFECT
    )
    prefix = [activation]
    terminal = adapter.replay(experiment, prefix)
    for _ in range(12):
        if terminal.legal_stop:
            break
        next_action = next(
            (action for action in terminal.actions if action.kind == ActionKind.PASS),
            terminal.actions[0],
        )
        prefix.append(next_action)
        terminal = adapter.replay(experiment, prefix)

    assert terminal.legal_stop
    assert terminal.route_document is not None
    trace = terminal.route_document["presentation"][
        "specified_interruption_trace"
    ]
    assert len(trace) == 1
    assert trace[0]["definition_id"] == "opening_hand_trigger_all_opportunities"
    assert trace[0]["activation"]["action_id"] == activation.action_id
    assert trace[0]["activation"]["candidate_ids"] == list(supported_ids)
    assert trace[0]["composition_id"] == composition["composition_id"]
    assert trace[0]["opportunity_id"] == opportunities["opportunities"][0][
        "opportunity_id"
    ]
    assert trace[0]["prefix_action_ids"] == []
    assert trace[0]["response_steps"] == []
    verify_general_search_route(
        terminal.route_document,
        experiment_path=EXPERIMENT,
    )
    missing_candidate = Action(
        kind=ActionKind.ACTIVATE_EFFECT,
        player=activation.player,
        selections=(
            Selection(
                candidate_id="chain:missing",
                card_ref=activation.selections[0].card_ref,
            ),
        ),
        request_signature=activation.request_signature,
    )
    with pytest.raises(RealCoreFrontierWorkerError) as raised:
        adapter.replay(experiment, (missing_candidate,))
    assert raised.value.failure.disposition.value == "path_failure"
    assert raised.value.failure.recovery.value == "stop_path"
    assert raised.value.failure.context["code"] == "candidate_disappeared"


def test_multiple_specified_sources_keep_all_core_opportunities_in_priority_order(
) -> None:
    _runtime_or_skip()
    experiment = load_experiment_document(EXPERIMENT)
    experiment["deck"]["main"][1] = 23434538
    experiment["scenario"]["opening_hand"]["cards"] = [
        2511,
        23434538,
        27551,
        35699,
        39015,
    ]
    experiment["interruption"] = {
        "mode": "specified",
        "definitions": [
            {
                "id": "cooclock_late",
                "priority": 20,
                "source_card_code": 2511,
                "source_player": 0,
                "source_zone": "hand",
                "response_roles": [],
            },
            {
                "id": "maxx_c_early",
                "priority": 10,
                "source_card_code": 23434538,
                "source_player": 0,
                "source_zone": "hand",
                "response_roles": [],
            },
        ],
    }
    adapter = RealCoreFrontierAdapter(
        experiment_path=EXPERIMENT,
        timeout_seconds=30,
        max_retries=0,
    )

    frontier = adapter.replay(experiment, ())

    opportunities = frontier.request["interruption_opportunities"]
    assert [item["definition_id"] for item in opportunities["opportunities"]] == [
        "maxx_c_early",
        "cooclock_late",
    ]
    assert [
        action.selections[0].card_ref.public_card_id
        for action in frontier.actions
        if action.kind == ActionKind.ACTIVATE_EFFECT
    ] == [23434538, 2511]
    assert frontier.actions[0].kind == ActionKind.PASS
    taxonomy_by_definition = {
        item["definition_id"]: item
        for item in frontier.request["interruption_taxonomy"]
    }
    assert set(taxonomy_by_definition) == {"cooclock_late", "maxx_c_early"}
    assert {
        item["source_card_code"]
        for item in taxonomy_by_definition["cooclock_late"]["candidates"]
    } == {2511}
    assert {
        item["source_card_code"]
        for item in taxonomy_by_definition["maxx_c_early"]["candidates"]
    } == {23434538}


def test_general_search_cli_writes_a_joinable_fresh_replay_report(
    tmp_path: Path,
) -> None:
    _runtime_or_skip()
    route_path = tmp_path / "best.route.yaml"
    search_report_path = tmp_path / "search-report.json"
    verification_path = tmp_path / "replay-verification.json"
    environment = current_checkout_environment()
    common = [sys.executable, "-m", "ygo_effect_dsl"]
    import_probe = subprocess.run(
        [
            sys.executable,
            "-c",
            "import pathlib,ygo_effect_dsl; print(pathlib.Path(ygo_effect_dsl.__file__).resolve())",
        ],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    searched = subprocess.run(
        [
            *common,
            "experiment-search",
            str(EXPERIMENT),
            "--out",
            str(route_path),
            "--search-report",
            str(search_report_path),
        ],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    replayed = subprocess.run(
        [
            *common,
            "experiment-replay",
            str(EXPERIMENT),
            str(route_path),
            "--run-id",
            "run_general_search_cli_fixture",
            "--verification-report",
            str(verification_path),
        ],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert import_probe.returncode == 0, import_probe.stderr
    assert Path(import_probe.stdout.strip()) == (
        ROOT / "src/ygo_effect_dsl/__init__.py"
    ).resolve()
    assert searched.returncode == 0, searched.stdout + searched.stderr
    assert replayed.returncode == 0, replayed.stdout + replayed.stderr
    route = load_route_document(route_path)
    search_report = json.loads(search_report_path.read_text(encoding="utf-8"))
    verification = read_fresh_replay_verification_report(verification_path)
    assert verification["verification_scope"] == "general_search"
    assert verification["experiment"]["digest"] == search_report["experiment_digest"]
    assert verification["route"]["route_id"] == search_report["best_route"]["route_id"]
    assert verification["route"]["route_id"] == route["route_id"]
    assert search_report["status"] == "complete"
    assert search_report["artifact_commit"] == {
        "route_id": route["route_id"],
        "route_sha256": sha256_file(route_path),
        "schema_version": "search-artifact-commit-v1",
        "status": "committed",
    }
    assert verification["scenario"]["deck_source"] == "inline"
    assert verification["lua_resolution"]["profile_id"] == (
        "card-scripts-official-v1"
    )
    experiment = load_experiment_document(EXPERIMENT)
    preflight = preflight_scenario(experiment, experiment_path=EXPERIMENT)
    qualification_run, _, _, _ = qualification_module._run_record(
        ordinal=1,
        paths={
            "route": route_path,
            "search": search_report_path,
            "verification": verification_path,
        },
        experiment=experiment,
        preflight=preflight,
    )
    assert qualification_run["search"]["best_route_id"] == route["route_id"]
    assert qualification_run["replay"]["route_id"] == route["route_id"]
