from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

import pytest

from ygo_effect_dsl.engine.bridge.ocgcore import lua_qualification as qualification
from ygo_effect_dsl.engine.bridge.ocgcore.lua_qualification import (
    LUA_LOAD_QUALIFICATION_SCHEMA_VERSION,
    LuaLoadQualificationError,
    read_lua_load_qualification,
    run_lua_load_qualification,
    validate_lua_load_qualification,
    write_lua_load_qualification,
)
from ygo_effect_dsl.external.ocgcore import (
    OcgcoreBootstrapError,
    resolve_ocgcore_assets,
    resolve_ocgcore_runtime,
)


REPO_ROOT = Path(__file__).parents[1]
EVIDENCE = REPO_ROOT / "docs" / "ocgcore" / "evidence" / "lua_load_qualification.json"


def test_official_inventory_and_resolver_cache_are_canonical(tmp_path: Path) -> None:
    scripts = tmp_path / "CardScripts"
    official = scripts / "official"
    official.mkdir(parents=True)
    (scripts / "constant.lua").write_text("return 1\n", encoding="utf-8")
    (scripts / "utility.lua").write_text("return 2\n", encoding="utf-8")
    (official / "c10.lua").write_text("return 10\n", encoding="utf-8")
    (official / "c2.lua").write_text("return 2\n", encoding="utf-8")

    inventory = qualification._official_inventory(scripts)
    assert inventory == (("c2.lua", 2), ("c10.lua", 10))

    result, entries = qualification._resolution_qualification(
        scripts,
        [name for name, _code in inventory],
    )
    assert result["semantic_invariance"] is True
    assert result["persistent_index"] is False
    assert [entry["resolved_path"] for entry in entries] == [
        "official/c2.lua",
        "official/c10.lua",
    ]

    (official / "not-a-card.lua").write_text("return 3\n", encoding="utf-8")
    with pytest.raises(LuaLoadQualificationError, match="non-card Lua"):
        qualification._official_inventory(scripts)


def test_local_real_core_lua_qualification_smoke_round_trips(tmp_path: Path) -> None:
    try:
        resolve_ocgcore_runtime()
        resolve_ocgcore_assets()
    except (OcgcoreBootstrapError, OSError) as exc:
        pytest.skip(f"verified local ocgcore assets are unavailable: {exc}")

    report = run_lua_load_qualification(smoke_limit=2, batch_size=2)

    assert report["schema_version"] == LUA_LOAD_QUALIFICATION_SCHEMA_VERSION
    assert report["status"] == "smoke_only"
    assert report["coverage"]["selected_script_count"] == 2
    assert report["coverage"]["official_inventory_count"] == 12702
    assert report["native_load"]["loaded_script_count"] == 2
    assert report["native_load"]["failure_count"] == 0
    assert report["native_load"]["enable_unsafe_libraries"] is False
    assert report["database_coverage"]["missing_database_script_count"] == 120
    assert {probe["case_id"] for probe in report["negative_probes"]} >= {
        "invalid_callback_name_encoding",
        "syntax_error",
        "unsafe_libraries",
    }

    destination = tmp_path / "lua-qualification.json"
    write_lua_load_qualification(destination, report)
    assert read_lua_load_qualification(destination) == report

    tampered = deepcopy(report)
    tampered["native_load"]["enable_unsafe_libraries"] = True
    with pytest.raises(LuaLoadQualificationError, match="unsafe Lua libraries"):
        validate_lua_load_qualification(tampered)

    tampered_digest = deepcopy(report)
    tampered_digest["database_coverage"]["missing_database_set_digest"] = (
        "luadbmissing_tampered"
    )
    with pytest.raises(LuaLoadQualificationError, match="missing set digest"):
        validate_lua_load_qualification(tampered_digest)


def test_committed_full_lua_qualification_is_canonical() -> None:
    if not EVIDENCE.is_file():
        pytest.skip("full Lua qualification evidence has not been generated yet")
    report = read_lua_load_qualification(EVIDENCE)

    assert report["status"] == "qualified"
    assert report["coverage"]["coverage_status"] == "complete"
    assert report["coverage"]["selected_script_count"] == 12702
    assert report["native_load"]["loaded_script_count"] == 12702
    assert report["native_load"]["failure_count"] == 0
    assert report["database_coverage"]["database_backed_script_count"] == 12582
    assert report["database_coverage"]["missing_database_script_count"] == 120
    assert json.loads(EVIDENCE.read_text(encoding="utf-8")) == report
