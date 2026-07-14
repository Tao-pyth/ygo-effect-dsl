from __future__ import annotations

import argparse
import ctypes
from dataclasses import replace
import json
import os
from pathlib import Path
import sys
import time
from typing import Any, Mapping

from ygo_effect_dsl.engine.bridge.ocgcore.binding import OcgcoreLibrary
from ygo_effect_dsl.engine.bridge.ocgcore.errors import (
    MissingCardDataError,
    OcgcoreLuaError,
)
from ygo_effect_dsl.engine.bridge.ocgcore.lua_qualification import (
    LUA_LOAD_WORKER_SCHEMA_VERSION,
)
from ygo_effect_dsl.engine.bridge.ocgcore.providers import (
    CARD_SCRIPTS_PROFILE_OFFICIAL,
    CardScriptsProvider,
    SQLiteCardDataProvider,
)
from ygo_effect_dsl.engine.bridge.ocgcore.types import CardRecord, DuelConfig, NewCard
from ygo_effect_dsl.engine.canonical import canonical_json, stable_digest, to_canonical_data
from ygo_effect_dsl.external.ocgcore import resolve_ocgcore_assets, resolve_ocgcore_runtime


_DUEL_SEED = (0x140, 0xED0, 0x2025, 0x11)


class _WorkerFailure(RuntimeError):
    def __init__(self, category: str, subject: str) -> None:
        self.category = category
        self.subject = subject
        super().__init__(f"{category}: {subject}")


class _QualificationCardDataProvider:
    def __init__(self, inner: SQLiteCardDataProvider) -> None:
        self.inner = inner
        self.missing_codes: list[int] = []

    def get_card(self, code: int) -> CardRecord:
        try:
            record = self.inner.get_card(code)
        except MissingCardDataError:
            self.missing_codes.append(code)
            return CardRecord(code=code, type=0x10)
        return replace(record, alias=0)


def _peak_rss_bytes() -> int | None:
    if os.name != "nt":
        return None

    class _ProcessMemoryCounters(ctypes.Structure):
        _fields_ = [
            ("cb", ctypes.c_ulong),
            ("PageFaultCount", ctypes.c_ulong),
            ("PeakWorkingSetSize", ctypes.c_size_t),
            ("WorkingSetSize", ctypes.c_size_t),
            ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
            ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
            ("PagefileUsage", ctypes.c_size_t),
            ("PeakPagefileUsage", ctypes.c_size_t),
        ]

    counters = _ProcessMemoryCounters()
    counters.cb = ctypes.sizeof(counters)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    psapi = ctypes.WinDLL("psapi", use_last_error=True)
    kernel32.GetCurrentProcess.restype = ctypes.c_void_p
    psapi.GetProcessMemoryInfo.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(_ProcessMemoryCounters),
        ctypes.c_ulong,
    ]
    psapi.GetProcessMemoryInfo.restype = ctypes.c_int
    if not psapi.GetProcessMemoryInfo(
        kernel32.GetCurrentProcess(),
        ctypes.byref(counters),
        counters.cb,
    ):
        return None
    return int(counters.PeakWorkingSetSize)


def _load_batch(
    payload: Mapping[str, Any],
    *,
    external_root: str | Path | None,
) -> dict[str, Any]:
    raw_codes = payload.get("codes")
    raw_missing = payload.get("expected_missing_database_names")
    if not isinstance(raw_codes, list) or not raw_codes:
        raise _WorkerFailure("worker_protocol", "codes")
    if not isinstance(raw_missing, list):
        raise _WorkerFailure("worker_protocol", "expected_missing_database_names")
    codes: list[int] = []
    for value in raw_codes:
        if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
            raise _WorkerFailure("worker_protocol", "card_code")
        codes.append(value)
    if len(codes) != len(set(codes)):
        raise _WorkerFailure("worker_protocol", "duplicate_card_code")
    expected_names = [f"c{code}.lua" for code in codes]
    expected_missing = set()
    for value in raw_missing:
        if not isinstance(value, str) or value not in expected_names:
            raise _WorkerFailure("worker_protocol", "missing_database_name")
        expected_missing.add(value)

    assets = resolve_ocgcore_assets(external_root=external_root)
    runtime = resolve_ocgcore_runtime(external_root=external_root)
    scripts = CardScriptsProvider(
        assets.scripts_root,
        profile_id=CARD_SCRIPTS_PROFILE_OFFICIAL,
    )
    started = time.perf_counter()
    with SQLiteCardDataProvider(assets.database_path) as database:
        cards = _QualificationCardDataProvider(database)
        with OcgcoreLibrary(runtime) as library:
            with library.create_duel(
                DuelConfig(seed=_DUEL_SEED),
                cards,
                scripts,
            ) as duel:
                if duel.experiment_manifest["enable_unsafe_libraries"] is not False:
                    raise _WorkerFailure("unsafe_libraries", "native_option")
                duel.load_script_resolution(scripts.resolve_script("constant.lua"))
                duel.load_script_resolution(scripts.resolve_script("utility.lua"))
                helper_loads = list(duel.script_load_audit)
                for sequence, (code, name) in enumerate(zip(codes, expected_names, strict=True)):
                    try:
                        duel.add_card(
                            NewCard(
                                team=0,
                                duelist=1,
                                code=code,
                                controller=0,
                                location=0x1,
                                sequence=sequence,
                                position=0x8,
                            )
                        )
                    except Exception as exc:
                        raise _WorkerFailure(type(exc).__name__, name) from exc
                audit = list(duel.script_load_audit)

    observed_missing = {f"c{code}.lua" for code in cards.missing_codes}
    if observed_missing != expected_missing:
        raise _WorkerFailure("asset_identity", "database_missing_set")
    if any(load.get("outcome") != "loaded" for load in audit):
        raise _WorkerFailure("lua_load", "non_loaded_audit_entry")

    card_entries: dict[str, dict[str, Any]] = {}
    dependency_entries: list[dict[str, Any]] = []
    for raw_entry in audit[len(helper_loads) :]:
        entry = dict(raw_entry)
        name = entry.get("requested_name")
        if (
            not isinstance(name, str)
            or not name.startswith("c")
            or not name.endswith(".lua")
            or not name[1:-4].isdigit()
        ):
            raise _WorkerFailure("lua_load", "unexpected_non_card_script")
        if entry.get("resolved_path") != f"official/{name}":
            raise _WorkerFailure("script_resolution", str(name))
        if name in expected_names:
            if name in card_entries:
                raise _WorkerFailure("lua_load", str(name))
            card_entries[name] = entry
        else:
            dependency_entries.append(entry)
    if set(card_entries) != set(expected_names):
        raise _WorkerFailure("lua_load", "incomplete_card_script_set")
    ordered_entries = [card_entries[name] for name in expected_names]
    helper_digest = stable_digest(helper_loads, prefix="luahelpers_")
    card_digest = stable_digest(ordered_entries, prefix="luacardloads_")
    dependency_digest = stable_digest(
        dependency_entries,
        prefix="luadependencyloads_",
    )
    input_digest = stable_digest(expected_names, prefix="luabatchinput_")
    semantic_identity = {
        "card_load_digest": card_digest,
        "dependency_load_digest": dependency_digest,
        "helper_load_digest": helper_digest,
        "input_digest": input_digest,
        "missing_database_names": sorted(observed_missing),
        "profile_id": CARD_SCRIPTS_PROFILE_OFFICIAL,
    }
    return to_canonical_data(
        {
            "batch_id": stable_digest(semantic_identity, prefix="luabatch_"),
            "card_load_digest": card_digest,
            "dependency_load_count": len(dependency_entries),
            "dependency_load_digest": dependency_digest,
            "elapsed_seconds": round(time.perf_counter() - started, 6),
            "enable_unsafe_libraries": False,
            "helper_load_digest": helper_digest,
            "helper_loads": helper_loads,
            "input_count": len(codes),
            "input_digest": input_digest,
            "loaded_expected_count": len(ordered_entries),
            "missing_database_count": len(observed_missing),
            "peak_rss_bytes": _peak_rss_bytes(),
            "schema_version": LUA_LOAD_WORKER_SCHEMA_VERSION,
            "status": "success",
        }
    )


def _negative_probes(
    *,
    external_root: str | Path | None,
) -> dict[str, Any]:
    assets = resolve_ocgcore_assets(external_root=external_root)
    runtime = resolve_ocgcore_runtime(external_root=external_root)
    scripts = CardScriptsProvider(
        assets.scripts_root,
        profile_id=CARD_SCRIPTS_PROFILE_OFFICIAL,
    )
    probes: list[dict[str, Any]] = []
    with SQLiteCardDataProvider(assets.database_path) as cards:
        with OcgcoreLibrary(runtime) as library:
            with library.create_duel(DuelConfig(seed=_DUEL_SEED), cards, scripts) as duel:
                try:
                    duel.load_script(
                        "ygo_effect_dsl_invalid_syntax.lua",
                        b"local = this is not valid Lua(",
                    )
                except OcgcoreLuaError as exc:
                    if exc.category != "lua_error":
                        raise _WorkerFailure("negative_probe", "syntax_error_category")
                    audit = duel.script_load_audit[-1]
                    if audit.get("outcome") != "rejected":
                        raise _WorkerFailure("negative_probe", "syntax_error_outcome")
                else:
                    raise _WorkerFailure("negative_probe", "syntax_error_accepted")
            probes.append(
                {
                    "boundary": "OCG_LoadScript",
                    "case_id": "syntax_error",
                    "classification": "lua_error",
                    "outcome": "rejected",
                }
            )

            with library.create_duel(DuelConfig(seed=_DUEL_SEED), cards, scripts) as duel:
                # This qualification-only call exercises the exact C callback object.
                result = duel._options.scriptReader(None, duel._duel, b"\xff")
                if result != 0 or duel.script_load_audit[-1].get("outcome") != "invalid_encoding":
                    raise _WorkerFailure(
                        "negative_probe",
                        "invalid_callback_name_encoding",
                    )
            probes.append(
                {
                    "boundary": "ScriptReader",
                    "case_id": "invalid_callback_name_encoding",
                    "classification": "asset_error",
                    "outcome": "rejected",
                }
            )

            with library.create_duel(DuelConfig(seed=_DUEL_SEED), cards, scripts) as duel:
                if duel._options.enableUnsafeLibraries != 0:
                    raise _WorkerFailure("negative_probe", "unsafe_native_option")
            try:
                DuelConfig(seed=_DUEL_SEED, enable_unsafe_libraries=True).validate()
            except ValueError:
                pass
            else:
                raise _WorkerFailure("negative_probe", "unsafe_config_accepted")
            probes.append(
                {
                    "boundary": "DuelConfig/OCG_DuelOptions",
                    "case_id": "unsafe_libraries",
                    "classification": "configuration_failure",
                    "outcome": "rejected_and_native_zero",
                }
            )

    return {
        "negative_probes": probes,
        "peak_rss_bytes": _peak_rss_bytes(),
        "schema_version": LUA_LOAD_WORKER_SCHEMA_VERSION,
        "status": "success",
    }


def run_worker(
    payload: Mapping[str, Any],
    *,
    external_root: str | Path | None,
) -> dict[str, Any]:
    if payload.get("schema_version") != LUA_LOAD_WORKER_SCHEMA_VERSION:
        raise _WorkerFailure("worker_protocol", "schema_version")
    operation = payload.get("operation")
    if operation == "load_batch":
        return _load_batch(payload, external_root=external_root)
    if operation == "negative_probes":
        return _negative_probes(external_root=external_root)
    raise _WorkerFailure("worker_protocol", "operation")


def main() -> int:
    parser = argparse.ArgumentParser(prog="ygo-effect-dsl-lua-qualification-worker")
    parser.add_argument("--external-root")
    args = parser.parse_args()
    payload = json.loads(sys.stdin.read())
    if not isinstance(payload, dict):
        raise _WorkerFailure("worker_protocol", "input")
    print(canonical_json(run_worker(payload, external_root=args.external_root)))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except _WorkerFailure as exc:
        print(
            canonical_json(
                {
                    "failure": {
                        "category": exc.category,
                        "subject": exc.subject,
                    },
                    "schema_version": LUA_LOAD_WORKER_SCHEMA_VERSION,
                    "status": "failure",
                }
            )
        )
        raise SystemExit(1) from None
    except Exception as exc:
        print(
            canonical_json(
                {
                    "failure": {
                        "category": type(exc).__name__,
                        "subject": "worker",
                    },
                    "schema_version": LUA_LOAD_WORKER_SCHEMA_VERSION,
                    "status": "failure",
                }
            )
        )
        raise SystemExit(1) from None
