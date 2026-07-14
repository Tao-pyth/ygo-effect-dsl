from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
import json
import platform
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import time
from typing import Any

from ygo_effect_dsl import __version__
from ygo_effect_dsl.engine.bridge.ocgcore.errors import (
    MissingCardDataError,
    MissingScriptError,
    OcgcoreAssetError,
)
from ygo_effect_dsl.engine.bridge.ocgcore.providers import (
    CARD_SCRIPTS_PROFILE_OFFICIAL,
    CardScriptsProvider,
    SQLiteCardDataProvider,
)
from ygo_effect_dsl.engine.canonical import canonical_json, stable_digest, to_canonical_data
from ygo_effect_dsl.external.ocgcore import (
    OcgcoreAssets,
    resolve_ocgcore_assets,
    verify_ocgcore,
)
from ygo_effect_dsl.io_atomic import atomic_write_text
from ygo_effect_dsl.runtime_imports import current_checkout_environment


LUA_LOAD_QUALIFICATION_SCHEMA_VERSION = "ocgcore-lua-load-qualification-v1"
LUA_LOAD_WORKER_SCHEMA_VERSION = "ocgcore-lua-load-worker-v1"
DEFAULT_BATCH_SIZE = 2048
DEFAULT_WORKER_TIMEOUT_SECONDS = 300.0
_CARD_SCRIPT_PATTERN = re.compile(r"c([0-9]+)\.lua\Z")
_FORBIDDEN_PATH_FIELDS = frozenset(
    {"database_path", "runtime_path", "scripts_root", "source_path"}
)


class LuaLoadQualificationError(ValueError):
    """The pinned Lua corpus could not be qualified without ambiguity."""


def _positive_integer(value: Any, path: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise LuaLoadQualificationError(f"{path} must be an integer >= 1")
    return value


def _non_negative_integer(value: Any, path: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise LuaLoadQualificationError(f"{path} must be a non-negative integer")
    return value


def _mapping(value: Any, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise LuaLoadQualificationError(f"{path} must be a mapping")
    return value


def _list(value: Any, path: str) -> list[Any]:
    if not isinstance(value, list):
        raise LuaLoadQualificationError(f"{path} must be a list")
    return value


def _string(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value:
        raise LuaLoadQualificationError(f"{path} must be a non-empty string")
    return value


def _reject_private_paths(value: Any, path: str = "$") -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            field = str(key)
            if field in _FORBIDDEN_PATH_FIELDS:
                raise LuaLoadQualificationError(
                    f"{path}.{field} is forbidden in sanitized qualification evidence"
                )
            _reject_private_paths(item, f"{path}.{field}")
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _reject_private_paths(item, f"{path}[{index}]")


def _assert_relative_script_path(value: Any, path: str) -> str:
    text = _string(value, path)
    relative = PurePosixPath(text)
    if relative.is_absolute() or any(part in {"", ".", ".."} for part in relative.parts):
        raise LuaLoadQualificationError(f"{path} must be a canonical relative path")
    if relative.as_posix() != text or ":" in text:
        raise LuaLoadQualificationError(f"{path} must be a canonical relative path")
    return text


def _official_inventory(scripts_root: Path) -> tuple[tuple[str, int], ...]:
    official = scripts_root / "official"
    if not official.is_dir():
        raise LuaLoadQualificationError("CardScripts official directory is missing")
    inventory: list[tuple[str, int]] = []
    unexpected: list[str] = []
    for entry in official.iterdir():
        if entry.suffix.lower() != ".lua":
            continue
        match = _CARD_SCRIPT_PATTERN.fullmatch(entry.name)
        if match is None:
            unexpected.append(entry.name)
            continue
        inventory.append((entry.name, int(match.group(1))))
    if unexpected:
        raise LuaLoadQualificationError(
            "official CardScripts contains non-card Lua files: "
            + ", ".join(sorted(unexpected))
        )
    inventory.sort(key=lambda item: (item[1], item[0]))
    names = [name for name, _code in inventory]
    codes = [code for _name, code in inventory]
    if not inventory:
        raise LuaLoadQualificationError("official CardScripts inventory is empty")
    if len(names) != len(set(names)) or len(codes) != len(set(codes)):
        raise LuaLoadQualificationError("official CardScripts inventory is not unique")
    return tuple(inventory)


def _resolution_pass(
    provider: CardScriptsProvider,
    names: Sequence[str],
) -> tuple[list[dict[str, Any]], float]:
    started = time.perf_counter()
    entries = [provider.resolve_script(name).audit_dict() for name in names]
    return entries, round(time.perf_counter() - started, 6)


def _resolution_qualification(
    scripts_root: Path,
    names: Sequence[str],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    cached_provider = CardScriptsProvider(
        scripts_root,
        profile_id=CARD_SCRIPTS_PROFILE_OFFICIAL,
    )
    cold_entries, cold_seconds = _resolution_pass(cached_provider, names)
    warm_entries, warm_seconds = _resolution_pass(cached_provider, names)
    fresh_entries, fresh_seconds = _resolution_pass(
        CardScriptsProvider(
            scripts_root,
            profile_id=CARD_SCRIPTS_PROFILE_OFFICIAL,
        ),
        names,
    )
    digests = [
        stable_digest(entries, prefix="luaresolution_")
        for entries in (cold_entries, warm_entries, fresh_entries)
    ]
    if len(set(digests)) != 1 or cold_entries != warm_entries or cold_entries != fresh_entries:
        raise LuaLoadQualificationError(
            "cold, warm, and fresh script resolution are not semantically identical"
        )
    return (
        {
            "cache_policy": "process-local-directory-identity-v1",
            "cold_seconds": cold_seconds,
            "fresh_seconds": fresh_seconds,
            "persistent_index": False,
            "persistent_index_policy": "disabled-to-preserve-live-path-identity-checks",
            "resolution_digest": digests[0],
            "semantic_invariance": True,
            "warm_seconds": warm_seconds,
        },
        cold_entries,
    )


def _database_coverage(
    database_path: Path,
    inventory: Sequence[tuple[str, int]],
) -> dict[str, Any]:
    missing_names: list[str] = []
    alias_count = 0
    with SQLiteCardDataProvider(database_path) as cards:
        for name, code in inventory:
            try:
                record = cards.get_card(code)
            except MissingCardDataError:
                missing_names.append(name)
                continue
            if record.alias:
                alias_count += 1
    total = len(inventory)
    missing_count = len(missing_names)
    return {
        "alias_suppressed_for_corpus_count": alias_count,
        "database_backed_script_count": total - missing_count,
        "fail_close_policy": "scenario-preflight-rejects-missing-card-data",
        "missing_database_script_count": missing_count,
        "missing_database_script_names": missing_names,
        "missing_database_set_digest": stable_digest(
            missing_names,
            prefix="luadbmissing_",
        ),
        "runtime_card_coverage_status": (
            "complete" if not missing_names else "partial_fail_closed"
        ),
    }


def _strict_resolver_probes(scripts_root: Path) -> list[dict[str, Any]]:
    provider = CardScriptsProvider(
        scripts_root,
        profile_id=CARD_SCRIPTS_PROFILE_OFFICIAL,
    )
    cases: tuple[tuple[str, str, type[BaseException]], ...] = (
        ("path_traversal", "../constant.lua", MissingScriptError),
        ("case_mismatch", "Constant.lua", OcgcoreAssetError),
        ("missing_script", "__ygo_effect_dsl_missing__.lua", MissingScriptError),
    )
    probes: list[dict[str, Any]] = []
    for case_id, name, expected in cases:
        try:
            provider.resolve_script(name)
        except expected:
            probes.append(
                {
                    "boundary": "strict_filesystem_resolver",
                    "case_id": case_id,
                    "classification": "asset_error",
                    "outcome": "rejected",
                }
            )
        except Exception as exc:
            raise LuaLoadQualificationError(
                f"resolver probe {case_id!r} raised {type(exc).__name__}"
            ) from exc
        else:
            raise LuaLoadQualificationError(
                f"resolver probe {case_id!r} did not fail closed"
            )
    probes.append(
        {
            "boundary": "strict_filesystem_resolver",
            "case_id": "duplicate_resolution",
            "classification": "asset_error",
            "evidence": ["tests/test_ocgcore_lifecycle.py"],
            "outcome": "verified_by_contract_test",
        }
    )
    return probes


def _invoke_worker(
    payload: Mapping[str, Any],
    *,
    external_root: str | Path | None,
    timeout_seconds: float,
) -> dict[str, Any]:
    command = [
        sys.executable,
        "-m",
        "ygo_effect_dsl.engine.bridge.ocgcore._lua_qualification_worker",
    ]
    if external_root is not None:
        command.extend(["--external-root", str(external_root)])
    try:
        completed = subprocess.run(
            command,
            input=canonical_json(payload),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=current_checkout_environment(),
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise LuaLoadQualificationError(
            f"Lua qualification worker exceeded {timeout_seconds:g} seconds"
        ) from exc
    stdout = completed.stdout.strip()
    try:
        result = json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise LuaLoadQualificationError(
            "Lua qualification worker returned invalid JSON"
        ) from exc
    if not isinstance(result, dict):
        raise LuaLoadQualificationError("Lua qualification worker result must be a mapping")
    if completed.returncode != 0 or result.get("status") != "success":
        failure = result.get("failure")
        if isinstance(failure, Mapping):
            category = failure.get("category", "worker_failure")
            subject = failure.get("subject", "unknown")
            raise LuaLoadQualificationError(
                f"Lua qualification worker failed: {category} at {subject}"
            )
        raise LuaLoadQualificationError("Lua qualification worker failed")
    if result.get("schema_version") != LUA_LOAD_WORKER_SCHEMA_VERSION:
        raise LuaLoadQualificationError("unsupported Lua qualification worker schema")
    return result


def _sanitized_core_identity(core: Mapping[str, Any]) -> dict[str, Any]:
    source = _mapping(core.get("source"), "core.source")
    build = _mapping(core.get("build"), "core.build")
    binary = _mapping(build.get("binary"), "core.build.binary")
    api = _mapping(build.get("api"), "core.build.api")
    return {
        "api": {"major": api.get("major"), "minor": api.get("minor")},
        "binary_sha256": binary.get("sha256"),
        "binary_size": binary.get("size"),
        "lock_id": core.get("lock_id"),
        "source_commit": source.get("commit"),
        "source_tree": source.get("tree"),
    }


def _sanitized_asset_identity(assets: OcgcoreAssets) -> dict[str, Any]:
    manifest = _mapping(assets.manifest, "assets.manifest")
    repositories = _mapping(manifest.get("repositories"), "assets.repositories")
    scripts = _mapping(repositories.get("card_scripts"), "assets.card_scripts")
    database = _mapping(repositories.get("card_database"), "assets.card_database")
    return {
        "asset_lock_id": manifest.get("asset_lock_id"),
        "card_database": {
            "commit": database.get("commit"),
            "tree": database.get("tree"),
        },
        "card_scripts": {
            "commit": scripts.get("commit"),
            "tree": scripts.get("tree"),
        },
        "core_lock_id": manifest.get("core_lock_id"),
        "runtime_network_access": False,
    }


def run_lua_load_qualification(
    *,
    external_root: str | Path | None = None,
    batch_size: int = DEFAULT_BATCH_SIZE,
    worker_timeout_seconds: float = DEFAULT_WORKER_TIMEOUT_SECONDS,
    smoke_limit: int | None = None,
) -> dict[str, Any]:
    _positive_integer(batch_size, "batch_size")
    if worker_timeout_seconds <= 0:
        raise LuaLoadQualificationError("worker_timeout_seconds must be positive")
    if smoke_limit is not None:
        _positive_integer(smoke_limit, "smoke_limit")

    core = verify_ocgcore(external_root=external_root)
    assets = resolve_ocgcore_assets(external_root=external_root)
    inventory = _official_inventory(assets.scripts_root)
    selected = inventory if smoke_limit is None else inventory[:smoke_limit]
    if not selected:
        raise LuaLoadQualificationError("Lua qualification selected no card scripts")
    selected_names = [name for name, _code in selected]
    resolution, resolution_entries = _resolution_qualification(
        assets.scripts_root,
        selected_names,
    )
    inventory_digest = stable_digest(resolution_entries, prefix="luainventory_")
    database = _database_coverage(assets.database_path, inventory)
    missing_names = set(database["missing_database_script_names"])

    worker_results: list[dict[str, Any]] = []
    for offset in range(0, len(selected), batch_size):
        batch = selected[offset : offset + batch_size]
        payload = {
            "codes": [code for _name, code in batch],
            "expected_missing_database_names": [
                name for name, _code in batch if name in missing_names
            ],
            "operation": "load_batch",
            "schema_version": LUA_LOAD_WORKER_SCHEMA_VERSION,
        }
        result = _invoke_worker(
            payload,
            external_root=external_root,
            timeout_seconds=worker_timeout_seconds,
        )
        if result.get("input_count") != len(batch):
            raise LuaLoadQualificationError("worker input count does not match its batch")
        expected_digest = stable_digest(selected_names[offset : offset + len(batch)], prefix="luabatchinput_")
        if result.get("input_digest") != expected_digest:
            raise LuaLoadQualificationError("worker input digest does not match its batch")
        worker_results.append(result)

    helper_digests = {str(result.get("helper_load_digest")) for result in worker_results}
    if len(helper_digests) != 1:
        raise LuaLoadQualificationError("fresh workers observed different helper load order")
    loaded_count = sum(int(result["loaded_expected_count"]) for result in worker_results)
    if loaded_count != len(selected):
        raise LuaLoadQualificationError("native workers did not load every selected card script")

    native_probes = _invoke_worker(
        {
            "operation": "negative_probes",
            "schema_version": LUA_LOAD_WORKER_SCHEMA_VERSION,
        },
        external_root=external_root,
        timeout_seconds=worker_timeout_seconds,
    )
    negative_probes = [
        *_strict_resolver_probes(assets.scripts_root),
        *_list(native_probes.get("negative_probes"), "worker.negative_probes"),
    ]
    coverage_status = "complete" if len(selected) == len(inventory) else "partial"
    batch_summaries = [
        {
            "batch_id": result["batch_id"],
            "card_load_digest": result["card_load_digest"],
            "dependency_load_count": result["dependency_load_count"],
            "dependency_load_digest": result["dependency_load_digest"],
            "elapsed_seconds": result["elapsed_seconds"],
            "input_count": result["input_count"],
            "input_digest": result["input_digest"],
            "loaded_expected_count": result["loaded_expected_count"],
            "missing_database_count": result["missing_database_count"],
            "peak_rss_bytes": result["peak_rss_bytes"],
        }
        for result in worker_results
    ]
    measured_rss = [
        int(result["peak_rss_bytes"])
        for result in worker_results
        if isinstance(result.get("peak_rss_bytes"), int)
    ]
    report: dict[str, Any] = {
        "assets": _sanitized_asset_identity(assets),
        "coverage": {
            "coverage_status": coverage_status,
            "official_inventory_count": len(inventory),
            "selected_script_count": len(selected),
            "selected_script_digest": inventory_digest,
            "selected_script_total_bytes": sum(
                int(entry["size"]) for entry in resolution_entries
            ),
        },
        "database_coverage": database,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "host": {
            "machine": platform.machine(),
            "operating_system": platform.system(),
            "python": platform.python_version(),
        },
        "native_load": {
            "batch_count": len(worker_results),
            "batch_size": batch_size,
            "batches": batch_summaries,
            "card_data_mode": "pinned-database-alias-suppressed-with-minimal-missing-record",
            "enable_unsafe_libraries": False,
            "failure_count": 0,
            "fresh_duel_per_batch": True,
            "helper_load_digest": next(iter(helper_digests)),
            "helper_loads": worker_results[0]["helper_loads"],
            "loaded_script_count": loaded_count,
            "max_worker_peak_rss_bytes": max(measured_rss) if measured_rss else None,
            "script_resolution_profile_id": CARD_SCRIPTS_PROFILE_OFFICIAL,
            "total_worker_elapsed_seconds": round(
                sum(float(result["elapsed_seconds"]) for result in worker_results),
                6,
            ),
            "worker_isolation": "fresh-process-per-batch",
        },
        "negative_probes": negative_probes,
        "package_version": __version__,
        "qualification_id": "",
        "resolution": resolution,
        "runtime": _sanitized_core_identity(core),
        "schema_version": LUA_LOAD_QUALIFICATION_SCHEMA_VERSION,
        "status": "qualified" if coverage_status == "complete" else "smoke_only",
    }
    report["qualification_id"] = stable_digest(
        {key: value for key, value in report.items() if key != "qualification_id"},
        prefix="luaqualification_",
    )
    return validate_lua_load_qualification(report)


def validate_lua_load_qualification(value: Any) -> dict[str, Any]:
    document = dict(_mapping(value, "$"))
    if document.get("schema_version") != LUA_LOAD_QUALIFICATION_SCHEMA_VERSION:
        raise LuaLoadQualificationError("unsupported Lua load qualification schema")
    if document.get("status") not in {"qualified", "smoke_only"}:
        raise LuaLoadQualificationError("invalid Lua load qualification status")
    _reject_private_paths(document)

    coverage = _mapping(document.get("coverage"), "$.coverage")
    total = _positive_integer(
        coverage.get("official_inventory_count"),
        "$.coverage.official_inventory_count",
    )
    selected = _positive_integer(
        coverage.get("selected_script_count"),
        "$.coverage.selected_script_count",
    )
    if selected > total:
        raise LuaLoadQualificationError("selected script count exceeds inventory")
    expected_coverage = "complete" if selected == total else "partial"
    if coverage.get("coverage_status") != expected_coverage:
        raise LuaLoadQualificationError("coverage status does not match selected scripts")
    expected_status = "qualified" if expected_coverage == "complete" else "smoke_only"
    if document.get("status") != expected_status:
        raise LuaLoadQualificationError("qualification status does not match coverage")

    database = _mapping(document.get("database_coverage"), "$.database_coverage")
    backed = _non_negative_integer(
        database.get("database_backed_script_count"),
        "$.database_coverage.database_backed_script_count",
    )
    missing = _non_negative_integer(
        database.get("missing_database_script_count"),
        "$.database_coverage.missing_database_script_count",
    )
    missing_names = _list(
        database.get("missing_database_script_names"),
        "$.database_coverage.missing_database_script_names",
    )
    if backed + missing != total or len(missing_names) != missing:
        raise LuaLoadQualificationError("database coverage counts do not match inventory")
    for index, name in enumerate(missing_names):
        if _CARD_SCRIPT_PATTERN.fullmatch(_string(name, f"missing_names[{index}]")) is None:
            raise LuaLoadQualificationError("database coverage contains an invalid script name")
    expected_database_status = "complete" if missing == 0 else "partial_fail_closed"
    if database.get("missing_database_set_digest") != stable_digest(
        missing_names,
        prefix="luadbmissing_",
    ):
        raise LuaLoadQualificationError("database missing set digest is inconsistent")
    if database.get("runtime_card_coverage_status") != expected_database_status:
        raise LuaLoadQualificationError("database coverage status is inconsistent")
    if database.get("fail_close_policy") != "scenario-preflight-rejects-missing-card-data":
        raise LuaLoadQualificationError("database coverage must fail closed")

    resolution = _mapping(document.get("resolution"), "$.resolution")
    if resolution.get("semantic_invariance") is not True:
        raise LuaLoadQualificationError("resolver semantic invariance is not verified")
    if resolution.get("persistent_index") is not False:
        raise LuaLoadQualificationError("persistent script indexes are outside this contract")

    native = _mapping(document.get("native_load"), "$.native_load")
    if native.get("enable_unsafe_libraries") is not False:
        raise LuaLoadQualificationError("unsafe Lua libraries must remain disabled")
    if native.get("fresh_duel_per_batch") is not True:
        raise LuaLoadQualificationError("native qualification requires fresh batch duels")
    if _non_negative_integer(native.get("failure_count"), "$.native_load.failure_count") != 0:
        raise LuaLoadQualificationError("native Lua load failures are not qualified")
    if _positive_integer(
        native.get("loaded_script_count"), "$.native_load.loaded_script_count"
    ) != selected:
        raise LuaLoadQualificationError("native loaded count does not match selection")
    helper_loads = _list(native.get("helper_loads"), "$.native_load.helper_loads")
    if not helper_loads:
        raise LuaLoadQualificationError("native qualification has no helper load audit")
    for index, raw_load in enumerate(helper_loads):
        load = _mapping(raw_load, f"$.native_load.helper_loads[{index}]")
        if load.get("outcome") != "loaded":
            raise LuaLoadQualificationError("helper load audit contains a failure")
        _assert_relative_script_path(
            load.get("resolved_path"),
            f"$.native_load.helper_loads[{index}].resolved_path",
        )
    if native.get("helper_load_digest") != stable_digest(
        helper_loads,
        prefix="luahelpers_",
    ):
        raise LuaLoadQualificationError("helper load digest is inconsistent")
    batches = _list(native.get("batches"), "$.native_load.batches")
    if len(batches) != _positive_integer(
        native.get("batch_count"), "$.native_load.batch_count"
    ):
        raise LuaLoadQualificationError("native batch count is inconsistent")
    batch_input_total = 0
    batch_loaded_total = 0
    for index, batch in enumerate(batches):
        batch_value = _mapping(batch, f"$.native_load.batches[{index}]")
        input_count = _positive_integer(
            batch_value.get("input_count"),
            f"$.native_load.batches[{index}].input_count",
        )
        loaded_count = _positive_integer(
            batch_value.get("loaded_expected_count"),
            f"$.native_load.batches[{index}].loaded_expected_count",
        )
        if loaded_count != input_count:
            raise LuaLoadQualificationError(
                "native batch did not load every input script"
            )
        _non_negative_integer(
            batch_value.get("dependency_load_count"),
            f"$.native_load.batches[{index}].dependency_load_count",
        )
        _non_negative_integer(
            batch_value.get("missing_database_count"),
            f"$.native_load.batches[{index}].missing_database_count",
        )
        batch_input_total += input_count
        batch_loaded_total += loaded_count
    if batch_input_total != selected or batch_loaded_total != selected:
        raise LuaLoadQualificationError("native batch loaded counts are inconsistent")

    probes = _list(document.get("negative_probes"), "$.negative_probes")
    required_probes = {
        "case_mismatch",
        "duplicate_resolution",
        "invalid_callback_name_encoding",
        "missing_script",
        "path_traversal",
        "syntax_error",
        "unsafe_libraries",
    }
    observed_probes = {
        _string(_mapping(probe, "negative_probe").get("case_id"), "negative_probe.case_id")
        for probe in probes
    }
    if not required_probes.issubset(observed_probes):
        raise LuaLoadQualificationError("qualification is missing required negative probes")

    qualification_id = document.pop("qualification_id", None)
    expected_id = stable_digest(document, prefix="luaqualification_")
    if qualification_id != expected_id:
        raise LuaLoadQualificationError("Lua qualification ID is not canonical")
    return {
        **to_canonical_data(document),
        "qualification_id": qualification_id,
    }


def write_lua_load_qualification(
    path: str | Path,
    qualification: Mapping[str, Any],
) -> None:
    validated = validate_lua_load_qualification(qualification)
    atomic_write_text(path, canonical_json(validated) + "\n")


def read_lua_load_qualification(path: str | Path) -> dict[str, Any]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise LuaLoadQualificationError("Lua qualification is invalid JSON") from exc
    return validate_lua_load_qualification(value)


__all__ = [
    "DEFAULT_BATCH_SIZE",
    "DEFAULT_WORKER_TIMEOUT_SECONDS",
    "LUA_LOAD_QUALIFICATION_SCHEMA_VERSION",
    "LUA_LOAD_WORKER_SCHEMA_VERSION",
    "LuaLoadQualificationError",
    "read_lua_load_qualification",
    "run_lua_load_qualification",
    "validate_lua_load_qualification",
    "write_lua_load_qualification",
]
