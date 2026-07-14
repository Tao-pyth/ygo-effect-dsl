from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from pathlib import Path

import pytest

from ygo_effect_dsl.cli import cmd_experiment as experiment_commands
from ygo_effect_dsl.engine.action import Action, ActionKind
from ygo_effect_dsl.engine.search import SearchFrontier
from ygo_effect_dsl.experiment import (
    FRESH_REPLAY_VERIFICATION_SCHEMA_VERSION,
    build_fresh_replay_verification_report,
    read_fresh_replay_verification_report,
    validate_fresh_replay_verification_report,
    write_fresh_replay_verification_report,
)
from ygo_effect_dsl.prototype import frontier as frontier_module
import ygo_effect_dsl.experiment.verification as verification_module


ROOT = Path(__file__).parents[1]
ROUTE_ID = "route_" + "f" * 64
STATE_ID = "state_" + "1" * 64
MANIFEST_ID = "manifest_" + "2" * 64


def _route() -> dict:
    return {
        "experiment": {
            "experiment_id": "verification_fixture",
            "schema_version": "0.4",
            "search": {"strategy": "random_search_v1"},
        },
        "replay": {
            "events": [{"step": 0}, {"step": 1}],
            "manifest": {
                "environment": {
                    "assets": {"lock_id": "assets_fixture"},
                    "core": {
                        "api": "11.0",
                        "binary_sha256": "a" * 64,
                        "lock_id": "core_fixture",
                        "source_commit": "b" * 40,
                    },
                    "scenario_manifest": {
                        "asset_lock_id": "assets_fixture",
                        "deck_id": "deck_fixture",
                        "deck_sha256": "c" * 64,
                        "deck_source": "ydk",
                        "opening_hand": [1, 2, 3, 4, 5],
                        "schema_version": "scenario-manifest-v1",
                        "sections": {"main": [1, 2, 3], "extra": [], "side": []},
                        "source_sha256": "d" * 64,
                    },
                },
                "manifest_hash": MANIFEST_ID,
                "schema_version": "ygo-replay-manifest-v1",
            },
        },
        "result": {
            "lua_script_resolution": {
                "loads": [
                    {
                        "outcome": "loaded",
                        "requested_name": "c1.lua",
                        "sha256": "e" * 64,
                    }
                ],
                "profile_id": "card-scripts-official-v1",
                "schema_version": 1,
            },
            "terminal_board": {"state_hash": STATE_ID},
        },
        "route_id": ROUTE_ID,
    }


def _report(route: dict | None = None) -> dict:
    return build_fresh_replay_verification_report(
        route or _route(),
        run_id="run_fixture",
        route_id=ROUTE_ID,
        event_count=2,
        final_state_hash=STATE_ID,
    )


def test_report_links_sanitized_content_identities_without_deck_contents() -> None:
    report = _report()

    assert report["schema_version"] == FRESH_REPLAY_VERIFICATION_SCHEMA_VERSION
    assert report["verification_id"].startswith("replayverify_")
    assert report["verification_scope"] == "general_search"
    assert report["experiment"]["digest"].startswith("experiment_")
    assert report["scenario"] == {
        "asset_lock_id": "assets_fixture",
        "deck_id": "deck_fixture",
        "deck_sha256": "c" * 64,
        "deck_source": "ydk",
        "manifest_digest": report["scenario"]["manifest_digest"],
        "schema_version": "scenario-manifest-v1",
        "source_sha256": "d" * 64,
    }
    assert "sections" not in report["scenario"]
    assert "opening_hand" not in report["scenario"]
    assert report["lua_resolution"]["profile_id"] == "card-scripts-official-v1"
    assert report["lua_resolution"]["load_count"] == 1


def test_report_round_trip_is_atomic_and_content_addressed(tmp_path) -> None:
    path = tmp_path / "nested" / "verification.json"
    report = _report()

    write_fresh_replay_verification_report(path, report)

    assert read_fresh_replay_verification_report(path) == report
    assert not list(path.parent.glob(f".{path.name}.*.tmp"))


def test_atomic_writer_supports_concurrent_windows_writers(tmp_path) -> None:
    path = tmp_path / "verification.json"
    reports = [
        build_fresh_replay_verification_report(
            _route(),
            run_id=f"run_concurrent_{index}",
            route_id=ROUTE_ID,
            event_count=2,
            final_state_hash=STATE_ID,
        )
        for index in range(24)
    ]

    with ThreadPoolExecutor(max_workers=8) as executor:
        list(
            executor.map(
                lambda report: write_fresh_replay_verification_report(path, report),
                reports,
            )
        )

    assert read_fresh_replay_verification_report(path) in reports
    assert not list(path.parent.glob(f".{path.name}.*.tmp"))


def test_atomic_writer_preserves_destination_and_cleans_temp_on_replace_failure(
    tmp_path, monkeypatch
) -> None:
    path = tmp_path / "verification.json"
    path.write_text("preserved\n", encoding="utf-8")

    def _fail_replace(*_args, **_kwargs):
        raise OSError("replace failed")

    monkeypatch.setattr(verification_module.os, "replace", _fail_replace)

    with pytest.raises(OSError, match="replace failed"):
        write_fresh_replay_verification_report(path, _report())

    assert path.read_text(encoding="utf-8") == "preserved\n"
    assert not list(path.parent.glob(f".{path.name}.*.tmp"))


def test_atomic_writer_retries_transient_windows_replace_conflicts(
    tmp_path, monkeypatch
) -> None:
    path = tmp_path / "verification.json"
    replace = verification_module.os.replace
    attempts = 0

    def _flaky_replace(source, destination):
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise PermissionError("transient conflict")
        replace(source, destination)

    monkeypatch.setattr(verification_module.os, "replace", _flaky_replace)

    write_fresh_replay_verification_report(path, _report())

    assert attempts == 3
    assert read_fresh_replay_verification_report(path) == _report()
    assert not list(path.parent.glob(f".{path.name}.*.tmp"))


def test_atomic_writer_exhausts_windows_retry_without_destroying_destination(
    tmp_path, monkeypatch
) -> None:
    path = tmp_path / "verification.json"
    path.write_text("preserved\n", encoding="utf-8")
    attempts = 0

    def _deny_replace(*_args, **_kwargs):
        nonlocal attempts
        attempts += 1
        raise PermissionError("persistent conflict")

    monkeypatch.setattr(verification_module, "ATOMIC_REPLACE_ATTEMPTS", 3)
    monkeypatch.setattr(verification_module.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(verification_module.os, "replace", _deny_replace)

    with pytest.raises(PermissionError, match="persistent conflict"):
        write_fresh_replay_verification_report(path, _report())

    assert attempts == 3
    assert path.read_text(encoding="utf-8") == "preserved\n"
    assert not list(path.parent.glob(f".{path.name}.*.tmp"))


def test_report_rejects_content_id_tampering() -> None:
    report = _report()
    report["route"]["route_id"] = "route_" + "0" * 64

    with pytest.raises(ValueError, match="verification_id"):
        validate_fresh_replay_verification_report(report)


def test_report_rejects_unknown_fields_before_content_id_validation() -> None:
    report = _report()
    report["unexpected"] = True

    with pytest.raises(ValueError, match="fields must be exactly"):
        validate_fresh_replay_verification_report(report)


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"route_id": "route_other"}, "Route ID"),
        ({"event_count": 3}, "event count"),
        ({"final_state_hash": "state_other"}, "State hash"),
    ],
)
def test_report_rejects_verification_result_divergence(overrides, message) -> None:
    arguments = {
        "run_id": "run_fixture",
        "route_id": ROUTE_ID,
        "event_count": 2,
        "final_state_hash": STATE_ID,
        **overrides,
    }

    with pytest.raises(ValueError, match=message):
        build_fresh_replay_verification_report(_route(), **arguments)


def test_report_rejects_unsuccessful_lua_resolution_outcomes() -> None:
    route = deepcopy(_route())
    route["result"]["lua_script_resolution"]["loads"][0]["outcome"] = "missing"

    with pytest.raises(ValueError, match="successful Lua load outcomes"):
        _report(route)


@pytest.mark.parametrize(
    ("section", "version", "message"),
    [
        ("scenario", "scenario-manifest-v2", "scenario manifest schema"),
        ("lua", 2, "Lua resolution schema"),
    ],
)
def test_report_builder_rejects_unknown_nested_versions(
    section, version, message
) -> None:
    route = deepcopy(_route())
    if section == "scenario":
        route["replay"]["manifest"]["environment"]["scenario_manifest"][
            "schema_version"
        ] = version
    else:
        route["result"]["lua_script_resolution"]["schema_version"] = version

    with pytest.raises(ValueError, match=message):
        _report(route)


@pytest.mark.parametrize(
    ("difference", "message"),
    [
        ("missing_ydk_source", "YDK verification requires"),
        ("asset_lock", "asset lock IDs must match"),
        ("missing_lua", "requires scenario and Lua identities"),
        ("lua_profile", "card-scripts-official-v1"),
    ],
)
def test_report_validator_rejects_cross_field_inconsistency(
    difference, message
) -> None:
    report = _report()
    if difference == "missing_ydk_source":
        report["scenario"]["source_sha256"] = None
    elif difference == "asset_lock":
        report["runtime"]["asset_lock_id"] = "other-assets"
    elif difference == "missing_lua":
        report["lua_resolution"] = None
    else:
        report["lua_resolution"]["profile_id"] = "card-scripts-custom"

    with pytest.raises(ValueError, match=message):
        validate_fresh_replay_verification_report(report)


def test_cli_replay_failure_does_not_write_a_success_report(
    tmp_path, monkeypatch
) -> None:
    destination = tmp_path / "verification.json"

    def _fail(*_args, **_kwargs):
        raise ValueError("fresh Replay diverged")

    monkeypatch.setattr(experiment_commands, "verify_real_core_route", _fail)
    args = argparse.Namespace(
        experiment_file=(
            ROOT / "examples/experiments/real_core_effect_veiler.yaml"
        ),
        route_file=(
            ROOT / "examples/prototype/real_core_effect_veiler.route.yaml"
        ),
        external_root=None,
        run_id="run_failure_fixture",
        verification_report=destination,
    )

    with pytest.raises(ValueError, match="fresh Replay diverged"):
        experiment_commands.cmd_experiment_replay(args)

    assert not destination.exists()


def _install_fresh_route(monkeypatch, fresh) -> None:
    class _FreshRouteAdapter:
        def __init__(self, **_kwargs) -> None:
            pass

        def replay(self, _experiment, _actions) -> SearchFrontier:
            return SearchFrontier(
                state_id="state_fixture",
                state_completeness="query_api_projection",
                request={"request_signature": "req_fixture"},
                actions=(),
                score=0,
                peak_score=0,
                success=False,
                legal_stop=True,
                legal_stop_reason="core_end_turn_available",
                route_document=fresh,
            )

    monkeypatch.setattr(frontier_module, "RealCoreFrontierAdapter", _FreshRouteAdapter)


def test_fresh_replay_rejects_a_changed_ydk_source_identity(monkeypatch) -> None:
    action = Action(
        kind=ActionKind.PASS,
        player=0,
        selections=(),
        request_signature="req_fixture",
    )
    recorded = {
        "experiment": {"experiment_id": "ydk_source_fixture", "schema_version": "0.4"},
        "replay": {
            "events": [{"action": action.to_dict()}],
            "manifest": {
                "environment": {
                    "scenario_manifest": {"source_sha256": "a" * 64}
                }
            },
        },
        "result": {"terminal_board": {"state_hash": "state_fixture"}},
        "route_id": "route_fixture",
    }
    fresh = deepcopy(recorded)
    fresh["replay"]["manifest"]["environment"]["scenario_manifest"][
        "source_sha256"
    ] = "b" * 64

    _install_fresh_route(monkeypatch, fresh)

    with pytest.raises(ValueError, match="differs from fresh worker Replay"):
        frontier_module.verify_general_search_route(recorded)


@pytest.mark.parametrize("difference", ["request", "state", "lua"])
def test_fresh_replay_rejects_request_state_or_lua_divergence(
    monkeypatch, difference
) -> None:
    action = Action(
        kind=ActionKind.PASS,
        player=0,
        selections=(),
        request_signature="req_fixture",
    )
    recorded = {
        "experiment": {"experiment_id": "divergence_fixture", "schema_version": "0.4"},
        "replay": {"events": [{"action": action.to_dict()}]},
        "result": {
            "lua_script_resolution": {
                "profile_id": "card-scripts-official-v1"
            },
            "terminal_board": {"state_hash": "state_recorded"},
        },
        "route_id": "route_fixture",
    }
    fresh = deepcopy(recorded)
    if difference == "request":
        fresh["replay"]["events"][0]["action"]["request_signature"] = "req_changed"
    elif difference == "state":
        fresh["result"]["terminal_board"]["state_hash"] = "state_changed"
    else:
        fresh["result"]["lua_script_resolution"]["profile_id"] = (
            "card-scripts-changed"
        )
    _install_fresh_route(monkeypatch, fresh)

    with pytest.raises(ValueError, match="differs from fresh worker Replay"):
        frontier_module.verify_general_search_route(recorded)
