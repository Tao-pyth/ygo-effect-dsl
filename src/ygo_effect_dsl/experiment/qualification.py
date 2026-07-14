from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from ygo_effect_dsl.engine.canonical import (
    canonical_json,
    stable_digest,
    to_canonical_data,
)
from ygo_effect_dsl.engine.search import SEARCH_RUN_RESULT_SCHEMA_VERSION
from ygo_effect_dsl.experiment.schema import load_experiment_document
from ygo_effect_dsl.experiment.scenario import (
    ScenarioPreflightResult,
    preflight_scenario,
)
from ygo_effect_dsl.experiment.verification import read_fresh_replay_verification_report
from ygo_effect_dsl.route_dsl import (
    assert_valid_route_document,
    load_route_document,
)
from ygo_effect_dsl.runtime_imports import current_checkout_environment


REAL_DECK_QUALIFICATION_SCHEMA_VERSION = "real-deck-qualification-index-v1"
QUALIFICATION_PROFILE_IDS = ("short", "long", "grave_banish")
QUALIFICATION_REPETITIONS = 2
LONG_PROFILE_MIN_ACTIONS = 12
ATOMIC_REPLACE_ATTEMPTS = 100


class RealDeckQualificationError(ValueError):
    pass


def _mapping(value: Any, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise RealDeckQualificationError(f"{path} must be a mapping")
    return value


def _sequence(value: Any, path: str) -> Sequence[Any]:
    if not isinstance(value, Sequence) or isinstance(
        value, (str, bytes, bytearray)
    ):
        raise RealDeckQualificationError(f"{path} must be a sequence")
    return value


def _string(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value:
        raise RealDeckQualificationError(f"{path} must be a non-empty string")
    return value


def _sanitized_identifier(value: Any, path: str) -> str:
    observed = _string(value, path)
    if any(character in observed for character in ("/", "\\", ":")) or any(
        ord(character) < 32 for character in observed
    ):
        raise RealDeckQualificationError(
            f"{path} must not contain path separators or control characters"
        )
    return observed


def _integer(value: Any, path: str, *, minimum: int = 0) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < minimum:
        raise RealDeckQualificationError(
            f"{path} must be an integer >= {minimum}"
        )
    return value


def _boolean(value: Any, path: str) -> bool:
    if not isinstance(value, bool):
        raise RealDeckQualificationError(f"{path} must be a boolean")
    return value


def _exact_keys(value: Mapping[str, Any], expected: set[str], path: str) -> None:
    observed = set(value)
    if observed != expected:
        raise RealDeckQualificationError(
            f"{path} fields must be exactly {sorted(expected)}; "
            f"observed {sorted(observed)}"
        )


def _hex_string(value: Any, path: str, *, length: int = 64) -> str:
    observed = _string(value, path)
    if len(observed) != length or any(
        character not in "0123456789abcdef" for character in observed
    ):
        raise RealDeckQualificationError(
            f"{path} must be {length} lowercase hexadecimal characters"
        )
    return observed


def _content_id(value: Any, path: str, *, prefix: str) -> str:
    observed = _string(value, path)
    if not observed.startswith(prefix):
        raise RealDeckQualificationError(f"{path} must start with {prefix!r}")
    _hex_string(observed[len(prefix) :], path)
    return observed


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _require_external_path(path: str | Path, *, repo_root: Path, label: str) -> Path:
    resolved = Path(path).expanduser().resolve()
    if _is_within(resolved, repo_root):
        raise RealDeckQualificationError(
            f"{label} must be outside the repository: {resolved}"
        )
    return resolved


def _validate_qualification_experiment(
    profile_id: str,
    experiment: Mapping[str, Any],
    *,
    experiment_path: Path,
    repo_root: Path,
) -> None:
    if profile_id not in QUALIFICATION_PROFILE_IDS:
        raise RealDeckQualificationError(
            f"unsupported qualification profile {profile_id!r}"
        )
    if experiment.get("schema_version") != "0.4":
        raise RealDeckQualificationError(
            f"{profile_id} requires Experiment schema 0.4"
        )
    deck = _mapping(experiment.get("deck"), f"{profile_id}.deck")
    source = deck.get("source")
    if source not in {"inline", "ydk"}:
        raise RealDeckQualificationError(
            f"{profile_id}.deck.source must be inline or ydk"
        )
    if source == "ydk":
        raw_path = _string(deck.get("path"), f"{profile_id}.deck.path")
        ydk_path = Path(raw_path)
        if not ydk_path.is_absolute():
            ydk_path = experiment_path.parent / ydk_path
        _require_external_path(
            ydk_path,
            repo_root=repo_root,
            label=f"{profile_id} YDK",
        )
    search = _mapping(experiment.get("search"), f"{profile_id}.search")
    if search.get("strategy") != "random_search_v1":
        raise RealDeckQualificationError(
            f"{profile_id} requires random_search_v1"
        )
    runner = experiment.get("runner")
    if isinstance(runner, Mapping) and runner.get("fixture_script_id") is not None:
        raise RealDeckQualificationError(
            f"{profile_id} cannot use runner.fixture_script_id"
        )
    interruption = _mapping(
        experiment.get("interruption"), f"{profile_id}.interruption"
    )
    if interruption.get("mode") != "none" or interruption.get("definitions") != []:
        raise RealDeckQualificationError(
            f"{profile_id} must use interruption mode none until #123 is qualified"
        )


def _initial_zone_counts(route: Mapping[str, Any]) -> dict[str, dict[str, int]]:
    replay = _mapping(route.get("replay"), "route.replay")
    snapshot = _mapping(replay.get("initial_snapshot"), "route.replay.initial_snapshot")
    counts = {
        str(player): {"graveyard": 0, "banished": 0} for player in (0, 1)
    }
    location_names = {0x10: "graveyard", 0x20: "banished"}
    for index, raw_zone in enumerate(
        _sequence(snapshot.get("zones"), "route.replay.initial_snapshot.zones")
    ):
        zone = _mapping(raw_zone, f"route.replay.initial_snapshot.zones[{index}]")
        controller = zone.get("controller")
        location = zone.get("location")
        if controller not in (0, 1) or location not in location_names:
            continue
        cards = _sequence(
            zone.get("cards"),
            f"route.replay.initial_snapshot.zones[{index}].cards",
        )
        counts[str(controller)][location_names[int(location)]] += sum(
            card is not None for card in cards
        )
    return counts


def _checkpoint_zone_counts(checkpoint: Mapping[str, Any]) -> dict[str, dict[str, int]]:
    summary = _mapping(checkpoint.get("board_summary"), "checkpoint.board_summary")
    raw_counts = _mapping(summary.get("zone_counts"), "checkpoint.board_summary.zone_counts")
    return {
        str(player): {
            zone: _integer(
                _mapping(raw_counts.get(str(player)), f"zone_counts.{player}").get(zone),
                f"zone_counts.{player}.{zone}",
            )
            for zone in ("graveyard", "banished")
        }
        for player in (0, 1)
    }


def derive_qualification_witness(
    profile_id: str, route: Mapping[str, Any]
) -> dict[str, Any]:
    replay = _mapping(route.get("replay"), "route.replay")
    events = _sequence(replay.get("events"), "route.replay.events")
    result = _mapping(route.get("result"), "route.result")
    terminal = _mapping(result.get("terminal_board"), "route.result.terminal_board")
    action_count = len(events)

    if profile_id == "short":
        success = _boolean(result.get("success"), "route.result.success")
        stop_reason = _string(
            terminal.get("stop_reason"), "route.result.terminal_board.stop_reason"
        )
        witness = {
            "action_count": action_count,
            "observed": success and stop_reason == "core_end_turn_available",
            "success": success,
            "terminal_stop_reason": stop_reason,
            "witness_type": "short-legal-stop-success-v1",
        }
    elif profile_id == "long":
        checkpoints = [
            _mapping(item, f"route.checkpoints[{index}]")
            for index, item in enumerate(
                _sequence(route.get("checkpoints"), "route.checkpoints")
            )
        ]
        progression: list[dict[str, Any]] = []
        previous: tuple[int, str] | None = None
        for checkpoint in checkpoints:
            coordinate = (
                _integer(checkpoint.get("turn"), "checkpoint.turn", minimum=1),
                _string(checkpoint.get("phase"), "checkpoint.phase"),
            )
            if coordinate != previous:
                progression.append({"phase": coordinate[1], "turn": coordinate[0]})
                previous = coordinate
        witness = {
            "action_count": action_count,
            "checkpoint_count": len(checkpoints),
            "minimum_action_count": LONG_PROFILE_MIN_ACTIONS,
            "observed": (
                action_count >= LONG_PROFILE_MIN_ACTIONS and bool(progression)
            ),
            "turn_phase_progression": progression,
            "witness_type": "long-action-turn-phase-v1",
        }
    elif profile_id == "grave_banish":
        checkpoints = [
            _mapping(item, f"route.checkpoints[{index}]")
            for index, item in enumerate(
                _sequence(route.get("checkpoints"), "route.checkpoints")
            )
        ]
        previous_counts = _initial_zone_counts(route)
        previous_step = -1
        transitions: list[dict[str, Any]] = []
        for checkpoint in checkpoints:
            current_counts = _checkpoint_zone_counts(checkpoint)
            step = _integer(checkpoint.get("step"), "checkpoint.step")
            for player in (0, 1):
                player_key = str(player)
                for zone in ("graveyard", "banished"):
                    before = previous_counts[player_key][zone]
                    after = current_counts[player_key][zone]
                    if before != after:
                        transitions.append(
                            {
                                "after_count": after,
                                "before_count": before,
                                "from_step": previous_step,
                                "player": player,
                                "to_step": step,
                                "zone": zone,
                            }
                        )
            previous_counts = current_counts
            previous_step = step
        witness = {
            "observed": bool(transitions),
            "transitions": transitions,
            "witness_type": "grave-banish-zone-transition-v1",
        }
    else:
        raise RealDeckQualificationError(
            f"unsupported qualification profile {profile_id!r}"
        )

    if not witness["observed"]:
        raise RealDeckQualificationError(
            f"{profile_id} Route did not produce its required core-observed witness"
        )
    return to_canonical_data(witness)


def _run_cli(command: Sequence[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(command),
        cwd=cwd,
        env=current_checkout_environment(),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


def _require_cli_success(
    completed: subprocess.CompletedProcess[str], *, operation: str
) -> None:
    if completed.returncode == 0:
        return
    diagnostic = completed.stderr.strip() or completed.stdout.strip()
    raise RealDeckQualificationError(
        f"{operation} failed with exit code {completed.returncode}: {diagnostic}"
    )


def _artifact_paths(root: Path, profile_id: str, ordinal: int) -> dict[str, Path]:
    run_root = root / profile_id / f"run-{ordinal}"
    run_root.mkdir(parents=True, exist_ok=True)
    return {
        "route": run_root / "best.route.yaml",
        "search": run_root / "search-report.json",
        "verification": run_root / "replay-verification.json",
    }


def _search_summary(
    search_report: Mapping[str, Any],
    *,
    experiment: Mapping[str, Any],
    route: Mapping[str, Any],
    preflight: ScenarioPreflightResult,
) -> dict[str, Any]:
    if search_report.get("schema_version") != SEARCH_RUN_RESULT_SCHEMA_VERSION:
        raise RealDeckQualificationError("qualification requires SearchRun v3")
    expected_digest = stable_digest(experiment, prefix="experiment_")
    if search_report.get("experiment_digest") != expected_digest:
        raise RealDeckQualificationError("SearchRun Experiment digest mismatch")
    if search_report.get("strategy_id") != "random_search_v1":
        raise RealDeckQualificationError("SearchRun strategy must be random_search_v1")
    if search_report.get("preflight") != to_canonical_data(preflight.to_dict()):
        raise RealDeckQualificationError("SearchRun preflight differs from qualification preflight")
    best = _mapping(search_report.get("best_route"), "search_report.best_route")
    if best.get("route_id") != route.get("route_id"):
        raise RealDeckQualificationError("SearchRun best Route ID mismatch")
    return {
        "best_route_id": _content_id(
            best.get("route_id"), "search_report.best_route.route_id", prefix="route_"
        ),
        "nodes": _integer(search_report.get("nodes"), "search_report.nodes", minimum=1),
        "replays": _integer(
            search_report.get("replays"), "search_report.replays", minimum=1
        ),
        "run_id": _content_id(
            search_report.get("run_id"), "search_report.run_id", prefix="searchrun_"
        ),
        "schema_version": SEARCH_RUN_RESULT_SCHEMA_VERSION,
        "strategy_id": "random_search_v1",
        "termination_reason": _string(
            search_report.get("termination_reason"),
            "search_report.termination_reason",
        ),
    }


def _run_record(
    *,
    ordinal: int,
    paths: Mapping[str, Path],
    experiment: Mapping[str, Any],
    preflight: ScenarioPreflightResult,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    route_path = paths["route"]
    search_path = paths["search"]
    verification_path = paths["verification"]
    route = load_route_document(route_path)
    assert_valid_route_document(route)
    if route.get("experiment") != experiment:
        raise RealDeckQualificationError("Route Experiment differs from qualification input")
    try:
        search_report = json.loads(search_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RealDeckQualificationError("SearchRun report is unreadable") from exc
    search = _search_summary(
        _mapping(search_report, "search_report"),
        experiment=experiment,
        route=route,
        preflight=preflight,
    )
    verification = read_fresh_replay_verification_report(verification_path)
    if verification.get("verification_scope") != "general_search":
        raise RealDeckQualificationError("qualification Replay scope must be general_search")
    if verification["experiment"]["digest"] != search_report["experiment_digest"]:
        raise RealDeckQualificationError("SearchRun and Replay Experiment digests differ")
    if verification["route"]["route_id"] != route.get("route_id"):
        raise RealDeckQualificationError("Replay and Route IDs differ")
    terminal = _mapping(
        _mapping(route.get("result"), "route.result").get("terminal_board"),
        "route.result.terminal_board",
    )
    if verification["replay"]["terminal_state_hash"] != terminal.get("state_hash"):
        raise RealDeckQualificationError("Replay terminal State hash mismatch")
    record = {
        "artifacts": {
            "route_sha256": _sha256_file(route_path),
            "search_report_sha256": _sha256_file(search_path),
            "verification_report_sha256": _sha256_file(verification_path),
        },
        "ordinal": ordinal,
        "replay": {
            "event_count": verification["replay"]["event_count"],
            "route_id": verification["route"]["route_id"],
            "terminal_state_hash": verification["replay"]["terminal_state_hash"],
            "verification_id": verification["verification_id"],
        },
        "search": search,
    }
    return to_canonical_data(record), route, search_report, verification


def _profile_record(
    *,
    profile_id: str,
    experiment: Mapping[str, Any],
    preflight: ScenarioPreflightResult,
    runs: Sequence[tuple[dict[str, Any], Mapping[str, Any], Mapping[str, Any], Mapping[str, Any]]],
) -> dict[str, Any]:
    if preflight.manifest is None:
        raise RealDeckQualificationError(f"{profile_id} preflight has no manifest")
    run_records = [item[0] for item in runs]
    route_documents = [item[1] for item in runs]
    verifications = [item[3] for item in runs]
    witnesses = [
        derive_qualification_witness(profile_id, route) for route in route_documents
    ]
    stable_fields = {
        "route_ids": {run["search"]["best_route_id"] for run in run_records},
        "search_run_ids": {run["search"]["run_id"] for run in run_records},
        "terminal_state_hashes": {
            run["replay"]["terminal_state_hash"] for run in run_records
        },
        "witnesses": {canonical_json(witness) for witness in witnesses},
    }
    unstable = [name for name, values in stable_fields.items() if len(values) != 1]
    if unstable:
        raise RealDeckQualificationError(
            f"{profile_id} repeated runs are not reproducible: {', '.join(unstable)}"
        )
    first_verification = verifications[0]
    for verification in verifications[1:]:
        for field in ("runtime", "lua_resolution", "scenario"):
            if verification.get(field) != first_verification.get(field):
                raise RealDeckQualificationError(
                    f"{profile_id} repeated {field} identities differ"
                )
    manifest = preflight.manifest
    return to_canonical_data(
        {
            "deck": {
                "deck_id": manifest.deck_id,
                "deck_sha256": manifest.deck_sha256,
                "source": manifest.deck_source,
                "source_sha256": manifest.source_sha256,
            },
            "experiment": {
                "digest": stable_digest(experiment, prefix="experiment_"),
                "experiment_id": _string(
                    experiment.get("experiment_id"), "experiment.experiment_id"
                ),
                "schema_version": "0.4",
            },
            "lua_resolution": first_verification["lua_resolution"],
            "profile_id": profile_id,
            "reproducibility": {
                "repetitions": len(runs),
                "route_id_stable": True,
                "search_run_id_stable": True,
                "terminal_state_hash_stable": True,
                "witness_stable": True,
            },
            "runs": run_records,
            "runtime": first_verification["runtime"],
            "scenario_manifest_digest": first_verification["scenario"][
                "manifest_digest"
            ],
            "witness": witnesses[0],
        }
    )


def build_real_deck_qualification_index(
    profiles: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    identity = {
        "profiles": [to_canonical_data(profile) for profile in profiles],
        "schema_version": REAL_DECK_QUALIFICATION_SCHEMA_VERSION,
        "status": "qualified",
    }
    document = {
        **identity,
        "qualification_id": stable_digest(identity, prefix="deckqual_"),
    }
    return validate_real_deck_qualification_index(document)


def _validate_witness(profile_id: str, value: Any, path: str) -> None:
    witness = _mapping(value, path)
    if profile_id == "short":
        _exact_keys(
            witness,
            {
                "action_count",
                "observed",
                "success",
                "terminal_stop_reason",
                "witness_type",
            },
            path,
        )
        if witness.get("witness_type") != "short-legal-stop-success-v1":
            raise RealDeckQualificationError(f"{path}.witness_type is unsupported")
        _integer(witness.get("action_count"), f"{path}.action_count", minimum=1)
        if not _boolean(witness.get("success"), f"{path}.success"):
            raise RealDeckQualificationError(f"{path}.success must be true")
        if witness.get("terminal_stop_reason") != "core_end_turn_available":
            raise RealDeckQualificationError(f"{path} has no legal-stop witness")
    elif profile_id == "long":
        _exact_keys(
            witness,
            {
                "action_count",
                "checkpoint_count",
                "minimum_action_count",
                "observed",
                "turn_phase_progression",
                "witness_type",
            },
            path,
        )
        if witness.get("witness_type") != "long-action-turn-phase-v1":
            raise RealDeckQualificationError(f"{path}.witness_type is unsupported")
        action_count = _integer(
            witness.get("action_count"), f"{path}.action_count", minimum=1
        )
        if witness.get("minimum_action_count") != LONG_PROFILE_MIN_ACTIONS:
            raise RealDeckQualificationError(f"{path}.minimum_action_count mismatch")
        if action_count < LONG_PROFILE_MIN_ACTIONS:
            raise RealDeckQualificationError(f"{path} has too few Actions")
        _integer(
            witness.get("checkpoint_count"), f"{path}.checkpoint_count", minimum=1
        )
        progression = _sequence(
            witness.get("turn_phase_progression"), f"{path}.turn_phase_progression"
        )
        if not progression:
            raise RealDeckQualificationError(f"{path} has no turn/phase progression")
        for index, raw_coordinate in enumerate(progression):
            coordinate = _mapping(raw_coordinate, f"{path}.turn_phase_progression[{index}]")
            _exact_keys(coordinate, {"phase", "turn"}, f"{path}.turn_phase_progression[{index}]")
            _string(coordinate.get("phase"), f"{path}.turn_phase_progression[{index}].phase")
            _integer(
                coordinate.get("turn"),
                f"{path}.turn_phase_progression[{index}].turn",
                minimum=1,
            )
    else:
        _exact_keys(
            witness,
            {"observed", "transitions", "witness_type"},
            path,
        )
        if witness.get("witness_type") != "grave-banish-zone-transition-v1":
            raise RealDeckQualificationError(f"{path}.witness_type is unsupported")
        transitions = _sequence(witness.get("transitions"), f"{path}.transitions")
        if not transitions:
            raise RealDeckQualificationError(f"{path} has no zone transition")
        for index, raw_transition in enumerate(transitions):
            transition = _mapping(raw_transition, f"{path}.transitions[{index}]")
            _exact_keys(
                transition,
                {
                    "after_count",
                    "before_count",
                    "from_step",
                    "player",
                    "to_step",
                    "zone",
                },
                f"{path}.transitions[{index}]",
            )
            for field in ("after_count", "before_count", "to_step"):
                _integer(
                    transition.get(field),
                    f"{path}.transitions[{index}].{field}",
                )
            if transition.get("from_step") != -1:
                _integer(
                    transition.get("from_step"),
                    f"{path}.transitions[{index}].from_step",
                )
            if transition.get("player") not in (0, 1):
                raise RealDeckQualificationError(
                    f"{path}.transitions[{index}].player must be 0 or 1"
                )
            if transition.get("zone") not in {"graveyard", "banished"}:
                raise RealDeckQualificationError(
                    f"{path}.transitions[{index}].zone is unsupported"
                )
    if not _boolean(witness.get("observed"), f"{path}.observed"):
        raise RealDeckQualificationError(f"{path}.observed must be true")


def validate_real_deck_qualification_index(value: Any) -> dict[str, Any]:
    document = dict(_mapping(value, "$"))
    _exact_keys(
        document,
        {"profiles", "qualification_id", "schema_version", "status"},
        "$",
    )
    if document.get("schema_version") != REAL_DECK_QUALIFICATION_SCHEMA_VERSION:
        raise RealDeckQualificationError("unsupported qualification index schema")
    if document.get("status") != "qualified":
        raise RealDeckQualificationError("qualification index status must be qualified")
    profiles = _sequence(document.get("profiles"), "$.profiles")
    if len(profiles) != len(QUALIFICATION_PROFILE_IDS):
        raise RealDeckQualificationError("qualification index requires exactly three profiles")
    deck_hashes: set[str] = set()
    observed_profile_ids: list[str] = []
    for index, raw_profile in enumerate(profiles):
        path = f"$.profiles[{index}]"
        profile = _mapping(raw_profile, path)
        _exact_keys(
            profile,
            {
                "deck",
                "experiment",
                "lua_resolution",
                "profile_id",
                "reproducibility",
                "runs",
                "runtime",
                "scenario_manifest_digest",
                "witness",
            },
            path,
        )
        profile_id = _string(profile.get("profile_id"), f"{path}.profile_id")
        observed_profile_ids.append(profile_id)
        if profile_id not in QUALIFICATION_PROFILE_IDS:
            raise RealDeckQualificationError(f"{path}.profile_id is unsupported")

        experiment = _mapping(profile.get("experiment"), f"{path}.experiment")
        _exact_keys(
            experiment,
            {"digest", "experiment_id", "schema_version"},
            f"{path}.experiment",
        )
        _content_id(
            experiment.get("digest"), f"{path}.experiment.digest", prefix="experiment_"
        )
        _sanitized_identifier(
            experiment.get("experiment_id"), f"{path}.experiment.experiment_id"
        )
        if experiment.get("schema_version") != "0.4":
            raise RealDeckQualificationError(f"{path} requires Experiment 0.4")

        deck = _mapping(profile.get("deck"), f"{path}.deck")
        _exact_keys(
            deck,
            {"deck_id", "deck_sha256", "source", "source_sha256"},
            f"{path}.deck",
        )
        _sanitized_identifier(deck.get("deck_id"), f"{path}.deck.deck_id")
        deck_hashes.add(_hex_string(deck.get("deck_sha256"), f"{path}.deck.deck_sha256"))
        if deck.get("source") not in {"inline", "ydk"}:
            raise RealDeckQualificationError(f"{path}.deck.source is unsupported")
        source_sha = deck.get("source_sha256")
        if deck.get("source") == "ydk":
            _hex_string(source_sha, f"{path}.deck.source_sha256")
        elif source_sha is not None:
            raise RealDeckQualificationError(
                f"{path}.deck.source_sha256 is only valid for YDK"
            )

        runtime = _mapping(profile.get("runtime"), f"{path}.runtime")
        _exact_keys(
            runtime,
            {
                "asset_lock_id",
                "core_api",
                "core_binary_sha256",
                "core_lock_id",
                "core_source_commit",
            },
            f"{path}.runtime",
        )
        for field in ("asset_lock_id", "core_api", "core_lock_id"):
            _string(runtime.get(field), f"{path}.runtime.{field}")
        _hex_string(runtime.get("core_binary_sha256"), f"{path}.runtime.core_binary_sha256")
        _hex_string(
            runtime.get("core_source_commit"),
            f"{path}.runtime.core_source_commit",
            length=40,
        )

        lua = _mapping(profile.get("lua_resolution"), f"{path}.lua_resolution")
        _exact_keys(
            lua,
            {"audit_digest", "load_count", "profile_id", "schema_version"},
            f"{path}.lua_resolution",
        )
        _content_id(
            lua.get("audit_digest"),
            f"{path}.lua_resolution.audit_digest",
            prefix="luaresolution_",
        )
        _integer(lua.get("load_count"), f"{path}.lua_resolution.load_count", minimum=1)
        if lua.get("profile_id") != "card-scripts-official-v1":
            raise RealDeckQualificationError(f"{path} requires official CardScripts")
        _integer(lua.get("schema_version"), f"{path}.lua_resolution.schema_version", minimum=1)
        _content_id(
            profile.get("scenario_manifest_digest"),
            f"{path}.scenario_manifest_digest",
            prefix="scenariomanifest_",
        )

        reproducibility = _mapping(
            profile.get("reproducibility"), f"{path}.reproducibility"
        )
        _exact_keys(
            reproducibility,
            {
                "repetitions",
                "route_id_stable",
                "search_run_id_stable",
                "terminal_state_hash_stable",
                "witness_stable",
            },
            f"{path}.reproducibility",
        )
        repetitions = _integer(
            reproducibility.get("repetitions"),
            f"{path}.reproducibility.repetitions",
            minimum=QUALIFICATION_REPETITIONS,
        )
        for field in (
            "route_id_stable",
            "search_run_id_stable",
            "terminal_state_hash_stable",
            "witness_stable",
        ):
            if not _boolean(
                reproducibility.get(field), f"{path}.reproducibility.{field}"
            ):
                raise RealDeckQualificationError(
                    f"{path}.reproducibility.{field} must be true"
                )

        runs = _sequence(profile.get("runs"), f"{path}.runs")
        if len(runs) != repetitions:
            raise RealDeckQualificationError(f"{path}.runs count mismatch")
        route_ids: set[str] = set()
        search_ids: set[str] = set()
        state_ids: set[str] = set()
        for run_index, raw_run in enumerate(runs):
            run_path = f"{path}.runs[{run_index}]"
            run = _mapping(raw_run, run_path)
            _exact_keys(run, {"artifacts", "ordinal", "replay", "search"}, run_path)
            if run.get("ordinal") != run_index + 1:
                raise RealDeckQualificationError(f"{run_path}.ordinal must be sequential")
            artifacts = _mapping(run.get("artifacts"), f"{run_path}.artifacts")
            _exact_keys(
                artifacts,
                {"route_sha256", "search_report_sha256", "verification_report_sha256"},
                f"{run_path}.artifacts",
            )
            for field in artifacts:
                _hex_string(artifacts.get(field), f"{run_path}.artifacts.{field}")
            search = _mapping(run.get("search"), f"{run_path}.search")
            _exact_keys(
                search,
                {
                    "best_route_id",
                    "nodes",
                    "replays",
                    "run_id",
                    "schema_version",
                    "strategy_id",
                    "termination_reason",
                },
                f"{run_path}.search",
            )
            route_ids.add(
                _content_id(
                    search.get("best_route_id"),
                    f"{run_path}.search.best_route_id",
                    prefix="route_",
                )
            )
            search_ids.add(
                _content_id(
                    search.get("run_id"),
                    f"{run_path}.search.run_id",
                    prefix="searchrun_",
                )
            )
            _integer(search.get("nodes"), f"{run_path}.search.nodes", minimum=1)
            _integer(search.get("replays"), f"{run_path}.search.replays", minimum=1)
            if search.get("schema_version") != SEARCH_RUN_RESULT_SCHEMA_VERSION:
                raise RealDeckQualificationError(f"{run_path} requires SearchRun v3")
            if search.get("strategy_id") != "random_search_v1":
                raise RealDeckQualificationError(f"{run_path} requires Random Search")
            _string(
                search.get("termination_reason"), f"{run_path}.search.termination_reason"
            )
            replay = _mapping(run.get("replay"), f"{run_path}.replay")
            _exact_keys(
                replay,
                {
                    "event_count",
                    "route_id",
                    "terminal_state_hash",
                    "verification_id",
                },
                f"{run_path}.replay",
            )
            _integer(replay.get("event_count"), f"{run_path}.replay.event_count", minimum=1)
            replay_route_id = _content_id(
                replay.get("route_id"),
                f"{run_path}.replay.route_id",
                prefix="route_",
            )
            if replay_route_id != search.get("best_route_id"):
                raise RealDeckQualificationError(
                    f"{run_path} Search and Replay Route IDs differ"
                )
            state_ids.add(
                _content_id(
                    replay.get("terminal_state_hash"),
                    f"{run_path}.replay.terminal_state_hash",
                    prefix="state_",
                )
            )
            _content_id(
                replay.get("verification_id"),
                f"{run_path}.replay.verification_id",
                prefix="replayverify_",
            )
        if len(route_ids) != 1 or len(search_ids) != 1 or len(state_ids) != 1:
            raise RealDeckQualificationError(f"{path} repeated run identities differ")
        _validate_witness(profile_id, profile.get("witness"), f"{path}.witness")

    if observed_profile_ids != list(QUALIFICATION_PROFILE_IDS):
        raise RealDeckQualificationError(
            "qualification profiles must be ordered short, long, grave_banish"
        )
    if len(deck_hashes) != len(QUALIFICATION_PROFILE_IDS):
        raise RealDeckQualificationError(
            "qualification profiles require three distinct normalized deck hashes"
        )
    qualification_id = document.pop("qualification_id", None)
    _content_id(qualification_id, "$.qualification_id", prefix="deckqual_")
    if qualification_id != stable_digest(document, prefix="deckqual_"):
        raise RealDeckQualificationError("qualification_id does not match index content")
    return {**to_canonical_data(document), "qualification_id": qualification_id}


def write_real_deck_qualification_index(
    path: str | Path, document: Mapping[str, Any]
) -> None:
    destination = Path(path)
    validated = validate_real_deck_qualification_index(document)
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=destination.parent,
        prefix=f".{destination.name}.",
        suffix=".tmp",
        text=True,
    )
    temporary = Path(temporary_name)
    descriptor_open = True
    try:
        stream = os.fdopen(descriptor, "w", encoding="utf-8", newline="\n")
        descriptor_open = False
        with stream:
            stream.write(canonical_json(validated) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        for attempt in range(ATOMIC_REPLACE_ATTEMPTS):
            try:
                os.replace(temporary, destination)
                break
            except PermissionError:
                if attempt + 1 == ATOMIC_REPLACE_ATTEMPTS:
                    raise
                time.sleep(0.01)
    except BaseException:
        if descriptor_open:
            try:
                os.close(descriptor)
            except OSError:
                pass
        temporary.unlink(missing_ok=True)
        raise


def read_real_deck_qualification_index(path: str | Path) -> dict[str, Any]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RealDeckQualificationError("qualification index is invalid JSON") from exc
    return validate_real_deck_qualification_index(value)


def run_external_real_deck_qualification(
    experiments: Mapping[str, str | Path],
    *,
    artifact_root: str | Path,
    index_out: str | Path,
    external_root: str | Path | None = None,
    repo_root: str | Path | None = None,
    worker_timeout: float = 30.0,
    max_retries: int = 1,
) -> dict[str, Any]:
    if set(experiments) != set(QUALIFICATION_PROFILE_IDS):
        raise RealDeckQualificationError(
            "experiments must contain exactly short, long, grave_banish"
        )
    if worker_timeout <= 0:
        raise RealDeckQualificationError("worker_timeout must be positive")
    if not isinstance(max_retries, int) or max_retries < 0:
        raise RealDeckQualificationError("max_retries must be an integer >= 0")
    repository = Path(repo_root or Path(__file__).parents[3]).resolve()
    artifacts = _require_external_path(
        artifact_root, repo_root=repository, label="artifact root"
    )
    artifacts.mkdir(parents=True, exist_ok=True)

    prepared: list[
        tuple[str, Path, dict[str, Any], ScenarioPreflightResult]
    ] = []
    for profile_id in QUALIFICATION_PROFILE_IDS:
        experiment_path = _require_external_path(
            experiments[profile_id],
            repo_root=repository,
            label=f"{profile_id} Experiment",
        )
        if not experiment_path.is_file():
            raise RealDeckQualificationError(
                f"{profile_id} Experiment does not exist: {experiment_path}"
            )
        experiment = load_experiment_document(experiment_path)
        _validate_qualification_experiment(
            profile_id,
            experiment,
            experiment_path=experiment_path,
            repo_root=repository,
        )
        preflight = preflight_scenario(
            experiment,
            experiment_path=experiment_path,
            external_root=external_root,
        )
        if not preflight.ok or preflight.manifest is None:
            raise RealDeckQualificationError(
                f"{profile_id} scenario preflight failed: "
                f"{canonical_json(preflight.to_dict())}"
            )
        prepared.append((profile_id, experiment_path, experiment, preflight))
    deck_hashes = {
        item[3].manifest.deck_sha256
        for item in prepared
        if item[3].manifest is not None
    }
    if len(deck_hashes) != len(QUALIFICATION_PROFILE_IDS):
        raise RealDeckQualificationError(
            "qualification requires three distinct normalized deck hashes"
        )

    profiles: list[dict[str, Any]] = []
    for profile_id, experiment_path, experiment, preflight in prepared:
        run_results = []
        run_id = "run_qualification_" + hashlib.sha256(
            f"{profile_id}:{stable_digest(experiment)}".encode("utf-8")
        ).hexdigest()
        for ordinal in range(1, QUALIFICATION_REPETITIONS + 1):
            paths = _artifact_paths(artifacts, profile_id, ordinal)
            search_command = [
                sys.executable,
                "-m",
                "ygo_effect_dsl",
                "experiment-search",
                str(experiment_path),
                "--out",
                str(paths["route"]),
                "--search-report",
                str(paths["search"]),
                "--worker-timeout",
                str(worker_timeout),
                "--max-retries",
                str(max_retries),
            ]
            replay_command = [
                sys.executable,
                "-m",
                "ygo_effect_dsl",
                "experiment-replay",
                str(experiment_path),
                str(paths["route"]),
                "--run-id",
                run_id,
                "--verification-report",
                str(paths["verification"]),
            ]
            if external_root is not None:
                search_command.extend(["--external-root", str(external_root)])
                replay_command.extend(["--external-root", str(external_root)])
            _require_cli_success(
                _run_cli(search_command, cwd=repository),
                operation=f"{profile_id} search run {ordinal}",
            )
            _require_cli_success(
                _run_cli(replay_command, cwd=repository),
                operation=f"{profile_id} fresh Replay run {ordinal}",
            )
            run_results.append(
                _run_record(
                    ordinal=ordinal,
                    paths=paths,
                    experiment=experiment,
                    preflight=preflight,
                )
            )
        profiles.append(
            _profile_record(
                profile_id=profile_id,
                experiment=experiment,
                preflight=preflight,
                runs=run_results,
            )
        )
    index = build_real_deck_qualification_index(profiles)
    write_real_deck_qualification_index(index_out, index)
    return index
