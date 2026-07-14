from __future__ import annotations

import subprocess
from copy import deepcopy
from pathlib import Path

import pytest

from ygo_effect_dsl.cli.cmd_qualification import _profile_inputs
from ygo_effect_dsl.engine.canonical import stable_digest, to_canonical_data
from ygo_effect_dsl.engine.search import SEARCH_RUN_RESULT_SCHEMA_VERSION
from ygo_effect_dsl.experiment import (
    ScenarioManifest,
    ScenarioPreflightResult,
    dump_experiment_document,
    load_experiment_document,
)
from ygo_effect_dsl.experiment import qualification as qualification_module
from ygo_effect_dsl.experiment.qualification import (
    REAL_DECK_QUALIFICATION_SCHEMA_VERSION,
    RealDeckQualificationError,
    build_real_deck_qualification_index,
    derive_qualification_witness,
    read_real_deck_qualification_index,
    run_external_real_deck_qualification,
    validate_real_deck_qualification_index,
    write_real_deck_qualification_index,
)


ROOT = Path(__file__).parents[1]
BASE_EXPERIMENT = ROOT / "examples/experiments/general_search_inline.yaml"
PROFILE_HEX = {"short": "1", "long": "2", "grave_banish": "3"}


def _id(prefix: str, character: str) -> str:
    return prefix + character * 64


def _witness(profile_id: str) -> dict:
    if profile_id == "short":
        return {
            "action_count": 3,
            "observed": True,
            "success": True,
            "terminal_stop_reason": "core_end_turn_available",
            "witness_type": "short-legal-stop-success-v1",
        }
    if profile_id == "long":
        return {
            "action_count": 12,
            "checkpoint_count": 12,
            "minimum_action_count": 12,
            "observed": True,
            "turn_phase_progression": [
                {"phase": "main1", "turn": 1},
                {"phase": "main1", "turn": 2},
            ],
            "witness_type": "long-action-turn-phase-v1",
        }
    return {
        "observed": True,
        "transitions": [
            {
                "after_count": 1,
                "before_count": 0,
                "from_step": -1,
                "player": 0,
                "to_step": 0,
                "zone": "graveyard",
            }
        ],
        "witness_type": "grave-banish-zone-transition-v1",
    }


def _run(profile_id: str, ordinal: int) -> dict:
    character = PROFILE_HEX[profile_id]
    route_id = _id("route_", character)
    return {
        "artifacts": {
            "route_sha256": str(ordinal) * 64,
            "search_report_sha256": chr(ord("3") + ordinal) * 64,
            "verification_report_sha256": chr(ord("5") + ordinal) * 64,
        },
        "ordinal": ordinal,
        "replay": {
            "event_count": 12 if profile_id == "long" else 3,
            "route_id": route_id,
            "terminal_state_hash": _id("state_", character),
            "verification_id": _id("replayverify_", str(ordinal + 6)),
        },
        "search": {
            "best_route_id": route_id,
            "nodes": 20,
            "replays": 20,
            "run_id": _id("searchrun_", character),
            "schema_version": SEARCH_RUN_RESULT_SCHEMA_VERSION,
            "strategy_id": "random_search_v1",
            "termination_reason": "max_nodes",
        },
    }


def _profile(profile_id: str) -> dict:
    character = PROFILE_HEX[profile_id]
    return {
        "deck": {
            "deck_id": f"external_{profile_id}",
            "deck_sha256": character * 64,
            "source": "inline",
            "source_sha256": None,
        },
        "experiment": {
            "digest": _id("experiment_", character),
            "experiment_id": f"qualification_{profile_id}",
            "schema_version": "0.4",
        },
        "lua_resolution": {
            "audit_digest": _id("luaresolution_", character),
            "load_count": 41,
            "profile_id": "card-scripts-official-v1",
            "schema_version": 1,
        },
        "profile_id": profile_id,
        "reproducibility": {
            "repetitions": 2,
            "route_id_stable": True,
            "search_run_id_stable": True,
            "terminal_state_hash_stable": True,
            "witness_stable": True,
        },
        "runs": [_run(profile_id, 1), _run(profile_id, 2)],
        "runtime": {
            "asset_lock_id": "ocgcore-assets-20250420",
            "core_api": "11.0",
            "core_binary_sha256": "a" * 64,
            "core_lock_id": "ocgcore-v11.0-windows-x64",
            "core_source_commit": "b" * 40,
        },
        "scenario_manifest_digest": _id("scenariomanifest_", character),
        "witness": _witness(profile_id),
    }


def _profiles() -> list[dict]:
    return [_profile(profile_id) for profile_id in ("short", "long", "grave_banish")]


def test_qualification_index_round_trips_without_raw_deck_or_path_fields(
    tmp_path: Path,
) -> None:
    index = build_real_deck_qualification_index(_profiles())
    path = tmp_path / "qualification-index.json"

    write_real_deck_qualification_index(path, index)
    loaded = read_real_deck_qualification_index(path)

    assert loaded == index
    assert loaded["schema_version"] == REAL_DECK_QUALIFICATION_SCHEMA_VERSION
    assert loaded["qualification_id"].startswith("deckqual_")
    serialized = path.read_text(encoding="utf-8")
    assert '"path"' not in serialized
    assert '"main"' not in serialized
    assert '"opening_hand"' not in serialized


def test_qualification_index_requires_distinct_decks_and_fixed_profile_order() -> None:
    duplicate = _profiles()
    duplicate[1]["deck"]["deck_sha256"] = duplicate[0]["deck"]["deck_sha256"]
    with pytest.raises(RealDeckQualificationError, match="distinct normalized deck"):
        build_real_deck_qualification_index(duplicate)

    reordered = _profiles()
    reordered.reverse()
    with pytest.raises(RealDeckQualificationError, match="must be ordered"):
        build_real_deck_qualification_index(reordered)


def test_qualification_index_rejects_route_join_and_content_id_tampering() -> None:
    profiles = _profiles()
    profiles[0]["runs"][0]["replay"]["route_id"] = _id("route_", "f")
    with pytest.raises(RealDeckQualificationError, match="Route IDs differ"):
        build_real_deck_qualification_index(profiles)

    index = build_real_deck_qualification_index(_profiles())
    index["profiles"][0]["runtime"]["core_api"] = "other"
    with pytest.raises(RealDeckQualificationError, match="qualification_id"):
        validate_real_deck_qualification_index(index)


def test_qualification_index_rejects_path_like_identifiers() -> None:
    profiles = _profiles()
    profiles[0]["deck"]["deck_id"] = "C:\\private\\deck.ydk"

    with pytest.raises(RealDeckQualificationError, match="path separators"):
        build_real_deck_qualification_index(profiles)


def _short_route() -> dict:
    return {
        "replay": {"events": [{"action": {}}]},
        "result": {
            "success": True,
            "terminal_board": {"stop_reason": "core_end_turn_available"},
        },
    }


def _long_route(actions: int = 12) -> dict:
    return {
        "checkpoints": [
            {
                "board_summary": {},
                "phase": "main1",
                "step": index,
                "turn": 1 if index < actions - 1 else 2,
            }
            for index in range(actions)
        ],
        "replay": {"events": [{"action": {}} for _ in range(actions)]},
        "result": {"terminal_board": {}},
    }


def _grave_route(*, moved: bool = True) -> dict:
    return {
        "checkpoints": [
            {
                "board_summary": {
                    "zone_counts": {
                        "0": {
                            "banished": 0,
                            "graveyard": 1 if moved else 0,
                        },
                        "1": {"banished": 0, "graveyard": 0},
                    }
                },
                "step": 0,
            }
        ],
        "replay": {
            "events": [{"action": {}}],
            "initial_snapshot": {
                "zones": [
                    {"cards": [], "controller": 0, "location": 0x10},
                    {"cards": [], "controller": 0, "location": 0x20},
                    {"cards": [], "controller": 1, "location": 0x10},
                    {"cards": [], "controller": 1, "location": 0x20},
                ]
            },
        },
        "result": {"terminal_board": {}},
    }


def test_witnesses_are_derived_only_from_route_observations() -> None:
    short = derive_qualification_witness("short", _short_route())
    long = derive_qualification_witness("long", _long_route())
    grave = derive_qualification_witness("grave_banish", _grave_route())

    assert short["success"] is True
    assert long["action_count"] == 12
    assert long["turn_phase_progression"][-1]["turn"] == 2
    assert grave["transitions"][0]["zone"] == "graveyard"
    assert "card" not in grave["transitions"][0]


@pytest.mark.parametrize(
    ("profile_id", "route", "message"),
    [
        (
            "short",
            {
                "replay": {"events": [{}]},
                "result": {
                    "success": False,
                    "terminal_board": {"stop_reason": "core_end_turn_available"},
                },
            },
            "required core-observed witness",
        ),
        ("long", _long_route(11), "required core-observed witness"),
        ("grave_banish", _grave_route(moved=False), "required core-observed witness"),
    ],
)
def test_missing_profile_witnesses_fail_closed(profile_id, route, message) -> None:
    with pytest.raises(RealDeckQualificationError, match=message):
        derive_qualification_witness(profile_id, route)


def test_input_contract_rejects_fixture_scripts_and_unqualified_interruptions(
    tmp_path: Path,
) -> None:
    experiment = load_experiment_document(BASE_EXPERIMENT)
    experiment_path = tmp_path / "experiment.yaml"
    experiment["runner"] = {"fixture_script_id": "custom_fixture"}
    with pytest.raises(RealDeckQualificationError, match="fixture_script_id"):
        qualification_module._validate_qualification_experiment(
            "short",
            experiment,
            experiment_path=experiment_path,
            repo_root=ROOT,
        )

    experiment.pop("runner")
    experiment["interruption"] = {
        "definitions": [{"id": "unsupported"}],
        "mode": "specified",
    }
    with pytest.raises(RealDeckQualificationError, match="#123"):
        qualification_module._validate_qualification_experiment(
            "grave_banish",
            experiment,
            experiment_path=experiment_path,
            repo_root=ROOT,
        )


def test_input_contract_rejects_a_repository_internal_ydk(tmp_path: Path) -> None:
    experiment = load_experiment_document(BASE_EXPERIMENT)
    experiment["deck"] = {
        "id": "internal",
        "path": str(ROOT / "internal.ydk"),
        "source": "ydk",
    }
    with pytest.raises(RealDeckQualificationError, match="YDK must be outside"):
        qualification_module._validate_qualification_experiment(
            "short",
            experiment,
            experiment_path=tmp_path / "experiment.yaml",
            repo_root=ROOT,
        )


def test_cli_profile_parser_requires_exactly_three_unique_profiles() -> None:
    parsed = _profile_inputs(
        ["grave_banish=c.yaml", "short=a.yaml", "long=b.yaml"]
    )
    assert list(parsed) == ["short", "long", "grave_banish"]

    with pytest.raises(ValueError, match="exactly"):
        _profile_inputs(["short=a.yaml"])
    with pytest.raises(ValueError, match="duplicate"):
        _profile_inputs(
            ["short=a.yaml", "short=b.yaml", "long=c.yaml", "grave_banish=d.yaml"]
        )


def test_search_preflight_join_normalizes_tuple_sections() -> None:
    experiment = load_experiment_document(BASE_EXPERIMENT)
    preflight = ScenarioPreflightResult((), _manifest("short"))
    route_id = _id("route_", "1")
    search_report = {
        "best_route": {"route_id": route_id},
        "experiment_digest": stable_digest(experiment, prefix="experiment_"),
        "nodes": 1,
        "preflight": to_canonical_data(preflight.to_dict()),
        "replays": 1,
        "run_id": _id("searchrun_", "1"),
        "schema_version": SEARCH_RUN_RESULT_SCHEMA_VERSION,
        "strategy_id": "random_search_v1",
        "termination_reason": "max_nodes",
    }

    summary = qualification_module._search_summary(
        search_report,
        experiment=experiment,
        route={"route_id": route_id},
        preflight=preflight,
    )

    assert summary["best_route_id"] == route_id


def _manifest(profile_id: str) -> ScenarioManifest:
    character = PROFILE_HEX[profile_id]
    return ScenarioManifest(
        experiment_schema_version="0.4",
        deck_id=f"external_{profile_id}",
        deck_source="inline",
        deck_sha256=character * 64,
        source_sha256=None,
        sections={"main": tuple(range(1, 41)), "extra": (), "side": ()},
        opening_hand=(1, 2, 3, 4, 5),
        opening_hand_mode="fixed",
        opening_hand_seed=None,
        interruption_source_codes=(),
        asset_lock_id="ocgcore-assets-20250420",
        asset_lock_sha256="c" * 64,
        card_database_commit="d" * 40,
        card_scripts_commit="e" * 40,
    )


def _fake_route(profile_id: str) -> dict:
    if profile_id == "short":
        return _short_route()
    if profile_id == "long":
        return _long_route()
    return _grave_route()


def _external_experiments(tmp_path: Path) -> dict[str, Path]:
    source = load_experiment_document(BASE_EXPERIMENT)
    experiments: dict[str, Path] = {}
    for profile_id in ("short", "long", "grave_banish"):
        document = deepcopy(source)
        document["experiment_id"] = f"qualification_{profile_id}"
        document["deck"]["id"] = f"external_{profile_id}"
        path = tmp_path / f"{profile_id}.yaml"
        dump_experiment_document(document, path)
        experiments[profile_id] = path
    return experiments


def test_harness_runs_two_search_and_replay_passes_per_external_profile(
    tmp_path: Path, monkeypatch
) -> None:
    experiments = _external_experiments(tmp_path)

    def _preflight(experiment, **_kwargs):
        profile_id = str(experiment["experiment_id"]).removeprefix("qualification_")
        return ScenarioPreflightResult((), _manifest(profile_id))

    commands: list[list[str]] = []

    def _run_cli(command, *, cwd):
        assert cwd == ROOT
        commands.append(list(command))
        return subprocess.CompletedProcess(command, 0, "ok", "")

    def _run_record(*, ordinal, paths, experiment, preflight):
        profile_id = str(experiment["experiment_id"]).removeprefix("qualification_")
        character = PROFILE_HEX[profile_id]
        route = _fake_route(profile_id)
        run = _run(profile_id, ordinal)
        verification = {
            "lua_resolution": {
                "audit_digest": _id("luaresolution_", character),
                "load_count": 41,
                "profile_id": "card-scripts-official-v1",
                "schema_version": 1,
            },
            "runtime": {
                "asset_lock_id": "ocgcore-assets-20250420",
                "core_api": "11.0",
                "core_binary_sha256": "a" * 64,
                "core_lock_id": "ocgcore-v11.0-windows-x64",
                "core_source_commit": "b" * 40,
            },
            "scenario": {
                "manifest_digest": _id("scenariomanifest_", character)
            },
        }
        return run, route, {}, verification

    monkeypatch.setattr(qualification_module, "preflight_scenario", _preflight)
    monkeypatch.setattr(qualification_module, "_run_cli", _run_cli)
    monkeypatch.setattr(qualification_module, "_run_record", _run_record)
    index_path = tmp_path / "sanitized-index.json"

    index = run_external_real_deck_qualification(
        experiments,
        artifact_root=tmp_path / "raw-artifacts",
        index_out=index_path,
        repo_root=ROOT,
    )

    assert len(commands) == 12
    assert sum("experiment-search" in command for command in commands) == 6
    assert sum("experiment-replay" in command for command in commands) == 6
    assert read_real_deck_qualification_index(index_path) == index
    assert [profile["profile_id"] for profile in index["profiles"]] == [
        "short",
        "long",
        "grave_banish",
    ]


def test_harness_does_not_publish_index_when_repeated_runs_diverge(
    tmp_path: Path, monkeypatch
) -> None:
    experiments = _external_experiments(tmp_path)

    monkeypatch.setattr(
        qualification_module,
        "preflight_scenario",
        lambda experiment, **_kwargs: ScenarioPreflightResult(
            (),
            _manifest(
                str(experiment["experiment_id"]).removeprefix("qualification_")
            ),
        ),
    )
    monkeypatch.setattr(
        qualification_module,
        "_run_cli",
        lambda command, *, cwd: subprocess.CompletedProcess(command, 0, "", ""),
    )

    def _divergent_run(*, ordinal, paths, experiment, preflight):
        profile_id = str(experiment["experiment_id"]).removeprefix("qualification_")
        run = _run(profile_id, ordinal)
        if profile_id == "long" and ordinal == 2:
            run["search"]["run_id"] = _id("searchrun_", "f")
        character = PROFILE_HEX[profile_id]
        return (
            run,
            _fake_route(profile_id),
            {},
            {
                "lua_resolution": {
                    "audit_digest": _id("luaresolution_", character),
                    "load_count": 41,
                    "profile_id": "card-scripts-official-v1",
                    "schema_version": 1,
                },
                "runtime": {
                    "asset_lock_id": "ocgcore-assets-20250420",
                    "core_api": "11.0",
                    "core_binary_sha256": "a" * 64,
                    "core_lock_id": "ocgcore-v11.0-windows-x64",
                    "core_source_commit": "b" * 40,
                },
                "scenario": {
                    "manifest_digest": _id("scenariomanifest_", character)
                },
            },
        )

    monkeypatch.setattr(qualification_module, "_run_record", _divergent_run)
    index_path = tmp_path / "must-not-exist.json"

    with pytest.raises(RealDeckQualificationError, match="not reproducible"):
        run_external_real_deck_qualification(
            experiments,
            artifact_root=tmp_path / "raw-artifacts",
            index_out=index_path,
            repo_root=ROOT,
        )

    assert not index_path.exists()


def test_harness_replay_divergence_does_not_publish_an_index(
    tmp_path: Path, monkeypatch
) -> None:
    experiments = _external_experiments(tmp_path)
    monkeypatch.setattr(
        qualification_module,
        "preflight_scenario",
        lambda experiment, **_kwargs: ScenarioPreflightResult(
            (),
            _manifest(
                str(experiment["experiment_id"]).removeprefix("qualification_")
            ),
        ),
    )

    def _run_cli(command, *, cwd):
        if "experiment-replay" in command:
            return subprocess.CompletedProcess(
                command, 2, "", "General Search Route differs from fresh worker Replay"
            )
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(qualification_module, "_run_cli", _run_cli)
    index_path = tmp_path / "must-not-exist.json"

    with pytest.raises(RealDeckQualificationError, match="fresh Replay run 1 failed"):
        run_external_real_deck_qualification(
            experiments,
            artifact_root=tmp_path / "raw-artifacts",
            index_out=index_path,
            repo_root=ROOT,
        )

    assert not index_path.exists()
