from __future__ import annotations

import json
import os
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
from ygo_effect_dsl.engine.bridge.ocgcore.providers import (
    SCRIPT_RESOLUTION_SCHEMA_VERSION,
)
from ygo_effect_dsl.engine.replay import REPLAY_MANIFEST_SCHEMA_VERSION
from ygo_effect_dsl.experiment.scenario import SCENARIO_MANIFEST_SCHEMA_VERSION


FRESH_REPLAY_VERIFICATION_SCHEMA_VERSION = "fresh-replay-verification-v1"
FRESH_REPLAY_VERIFICATION_SCOPES = {"general_search", "scripted_real_core"}
ATOMIC_REPLACE_ATTEMPTS = 100


def _mapping(value: Any, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{path} must be a mapping")
    return value


def _string(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{path} must be a non-empty string")
    return value


def _optional_string(value: Any, path: str) -> str | None:
    if value is None:
        return None
    return _string(value, path)


def _integer(value: Any, path: str, *, minimum: int = 0) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < minimum:
        raise ValueError(f"{path} must be an integer >= {minimum}")
    return value


def _exact_keys(value: Mapping[str, Any], expected: set[str], path: str) -> None:
    observed = set(value)
    if observed != expected:
        raise ValueError(
            f"{path} fields must be exactly {sorted(expected)}; "
            f"observed {sorted(observed)}"
        )


def _hex_string(value: Any, path: str, *, length: int) -> str:
    observed = _string(value, path)
    if len(observed) != length or any(
        character not in "0123456789abcdef" for character in observed
    ):
        raise ValueError(f"{path} must be {length} lowercase hexadecimal characters")
    return observed


def _content_id(value: Any, path: str, *, prefix: str) -> str:
    observed = _string(value, path)
    digest = observed.removeprefix(prefix)
    if not observed.startswith(prefix):
        raise ValueError(f"{path} must start with {prefix!r}")
    _hex_string(digest, path, length=64)
    return observed


def build_fresh_replay_verification_report(
    route_document: Mapping[str, Any],
    *,
    run_id: str,
    route_id: str,
    event_count: int,
    final_state_hash: str,
) -> dict[str, Any]:
    _string(run_id, "run_id")
    verified_route_id = _string(route_id, "route_id")
    verified_state_hash = _string(final_state_hash, "final_state_hash")
    _integer(event_count, "event_count", minimum=1)
    recorded_route_id = _string(route_document.get("route_id"), "$.route_id")
    if recorded_route_id != verified_route_id:
        raise ValueError("verified Route ID does not match the Route document")

    experiment = _mapping(route_document.get("experiment"), "$.experiment")
    search = experiment.get("search")
    verification_scope = (
        "general_search"
        if experiment.get("schema_version") == "0.4"
        and isinstance(search, Mapping)
        and search.get("strategy") == "random_search_v1"
        else "scripted_real_core"
    )
    replay = _mapping(route_document.get("replay"), "$.replay")
    events = replay.get("events")
    if not isinstance(events, Sequence) or isinstance(events, (str, bytes, bytearray)):
        raise ValueError("$.replay.events must be a sequence")
    if len(events) != event_count:
        raise ValueError("verified event count does not match the Route document")
    result = _mapping(route_document.get("result"), "$.result")
    terminal = _mapping(result.get("terminal_board"), "$.result.terminal_board")
    recorded_state_hash = _string(
        terminal.get("state_hash"), "$.result.terminal_board.state_hash"
    )
    if recorded_state_hash != verified_state_hash:
        raise ValueError("verified terminal State hash does not match the Route document")

    manifest = _mapping(replay.get("manifest"), "$.replay.manifest")
    environment = _mapping(manifest.get("environment"), "$.replay.manifest.environment")
    core = _mapping(environment.get("core"), "$.replay.manifest.environment.core")
    assets = _mapping(environment.get("assets"), "$.replay.manifest.environment.assets")

    scenario_report = None
    scenario = environment.get("scenario_manifest")
    if scenario is not None:
        scenario_manifest = _mapping(
            scenario, "$.replay.manifest.environment.scenario_manifest"
        )
        scenario_report = {
            "asset_lock_id": _string(
                scenario_manifest.get("asset_lock_id"),
                "$.replay.manifest.environment.scenario_manifest.asset_lock_id",
            ),
            "deck_id": _string(
                scenario_manifest.get("deck_id"),
                "$.replay.manifest.environment.scenario_manifest.deck_id",
            ),
            "deck_sha256": _string(
                scenario_manifest.get("deck_sha256"),
                "$.replay.manifest.environment.scenario_manifest.deck_sha256",
            ),
            "deck_source": _string(
                scenario_manifest.get("deck_source"),
                "$.replay.manifest.environment.scenario_manifest.deck_source",
            ),
            "manifest_digest": stable_digest(
                scenario_manifest, prefix="scenariomanifest_"
            ),
            "schema_version": _string(
                scenario_manifest.get("schema_version"),
                "$.replay.manifest.environment.scenario_manifest.schema_version",
            ),
            "source_sha256": _optional_string(
                scenario_manifest.get("source_sha256"),
                "$.replay.manifest.environment.scenario_manifest.source_sha256",
            ),
        }

    lua_report = None
    lua_resolution = result.get("lua_script_resolution")
    if lua_resolution is not None:
        lua_manifest = _mapping(
            lua_resolution, "$.result.lua_script_resolution"
        )
        loads = lua_manifest.get("loads")
        if not isinstance(loads, list):
            raise ValueError("$.result.lua_script_resolution.loads must be a list")
        if any(
            not isinstance(item, Mapping) or item.get("outcome") != "loaded"
            for item in loads
        ):
            raise ValueError("fresh Replay report requires successful Lua load outcomes")
        lua_report = {
            "audit_digest": stable_digest(lua_manifest, prefix="luaresolution_"),
            "load_count": len(loads),
            "profile_id": _string(
                lua_manifest.get("profile_id"),
                "$.result.lua_script_resolution.profile_id",
            ),
            "schema_version": _integer(
                lua_manifest.get("schema_version"),
                "$.result.lua_script_resolution.schema_version",
                minimum=1,
            ),
        }

    identity = to_canonical_data(
        {
            "experiment": {
                "digest": stable_digest(experiment, prefix="experiment_"),
                "experiment_id": _string(
                    experiment.get("experiment_id"), "$.experiment.experiment_id"
                ),
                "schema_version": _string(
                    experiment.get("schema_version"), "$.experiment.schema_version"
                ),
            },
            "lua_resolution": lua_report,
            "replay": {
                "event_count": event_count,
                "manifest_hash": _string(
                    manifest.get("manifest_hash"), "$.replay.manifest.manifest_hash"
                ),
                "manifest_schema_version": _string(
                    manifest.get("schema_version"),
                    "$.replay.manifest.schema_version",
                ),
                "terminal_state_hash": verified_state_hash,
            },
            "route": {
                "route_document_digest": stable_digest(
                    route_document, prefix="routedoc_"
                ),
                "route_id": recorded_route_id,
            },
            "run_id": run_id,
            "runtime": {
                "asset_lock_id": _string(
                    assets.get("lock_id"), "$.replay.manifest.environment.assets.lock_id"
                ),
                "core_api": _string(
                    core.get("api"), "$.replay.manifest.environment.core.api"
                ),
                "core_binary_sha256": _string(
                    core.get("binary_sha256"),
                    "$.replay.manifest.environment.core.binary_sha256",
                ),
                "core_lock_id": _string(
                    core.get("lock_id"), "$.replay.manifest.environment.core.lock_id"
                ),
                "core_source_commit": _string(
                    core.get("source_commit"),
                    "$.replay.manifest.environment.core.source_commit",
                ),
            },
            "scenario": scenario_report,
            "schema_version": FRESH_REPLAY_VERIFICATION_SCHEMA_VERSION,
            "status": "verified",
            "verification_scope": verification_scope,
        }
    )
    report = {
        **identity,
        "verification_id": stable_digest(identity, prefix="replayverify_"),
    }
    return validate_fresh_replay_verification_report(report)


def validate_fresh_replay_verification_report(value: Any) -> dict[str, Any]:
    report = dict(_mapping(value, "$"))
    _exact_keys(
        report,
        {
            "experiment",
            "lua_resolution",
            "replay",
            "route",
            "run_id",
            "runtime",
            "scenario",
            "schema_version",
            "status",
            "verification_id",
            "verification_scope",
        },
        "$",
    )
    if report.get("schema_version") != FRESH_REPLAY_VERIFICATION_SCHEMA_VERSION:
        raise ValueError("unsupported fresh Replay verification schema")
    if report.get("status") != "verified":
        raise ValueError("fresh Replay verification status must be 'verified'")
    verification_scope = report.get("verification_scope")
    if verification_scope not in FRESH_REPLAY_VERIFICATION_SCOPES:
        raise ValueError("fresh Replay verification scope is unsupported")
    run_id = _string(report.get("run_id"), "$.run_id")
    if not run_id.startswith("run_") or len(run_id) <= 4:
        raise ValueError("$.run_id must start with 'run_' and include an identifier")

    experiment = _mapping(report.get("experiment"), "$.experiment")
    _exact_keys(
        experiment,
        {"digest", "experiment_id", "schema_version"},
        "$.experiment",
    )
    _content_id(
        experiment.get("digest"), "$.experiment.digest", prefix="experiment_"
    )
    _string(experiment.get("experiment_id"), "$.experiment.experiment_id")
    _string(experiment.get("schema_version"), "$.experiment.schema_version")

    replay = _mapping(report.get("replay"), "$.replay")
    _exact_keys(
        replay,
        {
            "event_count",
            "manifest_hash",
            "manifest_schema_version",
            "terminal_state_hash",
        },
        "$.replay",
    )
    _integer(replay.get("event_count"), "$.replay.event_count", minimum=1)
    _content_id(
        replay.get("manifest_hash"), "$.replay.manifest_hash", prefix="manifest_"
    )
    if replay.get("manifest_schema_version") != REPLAY_MANIFEST_SCHEMA_VERSION:
        raise ValueError("unsupported Replay manifest schema in verification report")
    _content_id(
        replay.get("terminal_state_hash"),
        "$.replay.terminal_state_hash",
        prefix="state_",
    )

    route = _mapping(report.get("route"), "$.route")
    _exact_keys(route, {"route_document_digest", "route_id"}, "$.route")
    _content_id(
        route.get("route_document_digest"),
        "$.route.route_document_digest",
        prefix="routedoc_",
    )
    _content_id(route.get("route_id"), "$.route.route_id", prefix="route_")

    runtime = _mapping(report.get("runtime"), "$.runtime")
    _exact_keys(
        runtime,
        {
            "asset_lock_id",
            "core_api",
            "core_binary_sha256",
            "core_lock_id",
            "core_source_commit",
        },
        "$.runtime",
    )
    for field in ("asset_lock_id", "core_api", "core_lock_id"):
        _string(runtime.get(field), f"$.runtime.{field}")
    _hex_string(
        runtime.get("core_binary_sha256"),
        "$.runtime.core_binary_sha256",
        length=64,
    )
    _hex_string(
        runtime.get("core_source_commit"),
        "$.runtime.core_source_commit",
        length=40,
    )

    scenario = report.get("scenario")
    if scenario is not None:
        scenario_manifest = _mapping(scenario, "$.scenario")
        _exact_keys(
            scenario_manifest,
            {
                "asset_lock_id",
                "deck_id",
                "deck_sha256",
                "deck_source",
                "manifest_digest",
                "schema_version",
                "source_sha256",
            },
            "$.scenario",
        )
        for field in ("asset_lock_id", "deck_id"):
            _string(scenario_manifest.get(field), f"$.scenario.{field}")
        _hex_string(
            scenario_manifest.get("deck_sha256"),
            "$.scenario.deck_sha256",
            length=64,
        )
        _content_id(
            scenario_manifest.get("manifest_digest"),
            "$.scenario.manifest_digest",
            prefix="scenariomanifest_",
        )
        if scenario_manifest.get("deck_source") not in {"fixed", "inline", "ydk"}:
            raise ValueError("$.scenario.deck_source is unsupported")
        if scenario_manifest.get("schema_version") != SCENARIO_MANIFEST_SCHEMA_VERSION:
            raise ValueError("unsupported scenario manifest schema in verification report")
        source_sha256 = _optional_string(
            scenario_manifest.get("source_sha256"), "$.scenario.source_sha256"
        )
        if source_sha256 is not None:
            _hex_string(source_sha256, "$.scenario.source_sha256", length=64)

    lua_resolution = report.get("lua_resolution")
    if lua_resolution is not None:
        lua_manifest = _mapping(lua_resolution, "$.lua_resolution")
        _exact_keys(
            lua_manifest,
            {"audit_digest", "load_count", "profile_id", "schema_version"},
            "$.lua_resolution",
        )
        _content_id(
            lua_manifest.get("audit_digest"),
            "$.lua_resolution.audit_digest",
            prefix="luaresolution_",
        )
        _integer(
            lua_manifest.get("load_count"),
            "$.lua_resolution.load_count",
            minimum=1,
        )
        _string(lua_manifest.get("profile_id"), "$.lua_resolution.profile_id")
        if lua_manifest.get("schema_version") != SCRIPT_RESOLUTION_SCHEMA_VERSION:
            raise ValueError("unsupported Lua resolution schema in verification report")

    experiment_schema = experiment.get("schema_version")
    if verification_scope == "general_search":
        if experiment_schema != "0.4":
            raise ValueError("general_search verification requires Experiment 0.4")
        if scenario is None or lua_resolution is None:
            raise ValueError(
                "general_search verification requires scenario and Lua identities"
            )
        lua_manifest = _mapping(lua_resolution, "$.lua_resolution")
        if lua_manifest.get("profile_id") != "card-scripts-official-v1":
            raise ValueError(
                "general_search verification requires card-scripts-official-v1"
            )
    else:
        if experiment_schema not in {"0.3a", "0.3b"}:
            raise ValueError(
                "scripted_real_core verification requires Experiment 0.3a or 0.3b"
            )
        if scenario is not None or lua_resolution is not None:
            raise ValueError(
                "scripted_real_core verification cannot mix General Search identities"
            )

    if scenario is not None:
        scenario_manifest = _mapping(scenario, "$.scenario")
        runtime_manifest = _mapping(report.get("runtime"), "$.runtime")
        if scenario_manifest.get("asset_lock_id") != runtime_manifest.get(
            "asset_lock_id"
        ):
            raise ValueError("scenario and runtime asset lock IDs must match")
        deck_source = scenario_manifest.get("deck_source")
        source_sha256 = scenario_manifest.get("source_sha256")
        if deck_source == "ydk" and source_sha256 is None:
            raise ValueError("YDK verification requires source_sha256")
        if deck_source != "ydk" and source_sha256 is not None:
            raise ValueError("only YDK verification may include source_sha256")

    verification_id = report.pop("verification_id", None)
    _content_id(verification_id, "$.verification_id", prefix="replayverify_")
    if verification_id != stable_digest(report, prefix="replayverify_"):
        raise ValueError("fresh Replay verification_id does not match its content")
    return {**to_canonical_data(report), "verification_id": verification_id}


def write_fresh_replay_verification_report(
    path: str | Path, report: Mapping[str, Any]
) -> None:
    destination = Path(path)
    validated = validate_fresh_replay_verification_report(report)
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


def read_fresh_replay_verification_report(path: str | Path) -> dict[str, Any]:
    source = Path(path)
    try:
        value = json.loads(source.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError("fresh Replay verification report is invalid JSON") from exc
    return validate_fresh_replay_verification_report(value)
