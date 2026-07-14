from __future__ import annotations

from pathlib import Path

import pytest

from ygo_effect_dsl.engine.search import (
    NATIVE_PREFIX_STATE_REUSE_ALLOWED,
    ReplayPrefixCacheEntry,
    ReplayPrefixCacheKey,
)
from ygo_effect_dsl.spikes.ocgcore_snapshot_audit import (
    audit_ocgcore_snapshot_source,
)


def _write_source_fixture(root: Path) -> None:
    files = {
        "ocgapi.h": """
OCGAPI int OCG_CreateDuel(OCG_Duel* out, const OCG_DuelOptions* options);
OCGAPI void OCG_DestroyDuel(OCG_Duel duel);
OCGAPI int OCG_DuelProcess(OCG_Duel duel);
OCGAPI void* OCG_DuelQueryField(OCG_Duel duel, uint32_t* length);
""",
        "ocgapi.cpp": "",
        "ocgapi_types.h": """
typedef void (*OCG_DataReader)(void* payload1);
typedef int (*OCG_ScriptReader)(void* payload2);
typedef void (*OCG_LogHandler)(void* payload3);
""",
        "duel.h": """
field* game_field;
interpreter* lua;
std::unordered_set<card*> cards;
std::vector<uint8_t> buff;
std::vector<uint8_t> query_buffer;
std::deque<duel_message> messages;
RNG::Xoshiro256StarStar random;
""",
        "field.h": """
processor_list units;
std::optional<processor_unit> reserved;
card_vector select_cards;
chain_list select_chains;
chain_array current_chain;
effect_count_map effect_count_code;
""",
        "interpreter.h": """
lua_State* lua_state;
lua_State* current_state;
coroutine_map coroutines;
int32_t call_depth;
""",
        "effect.cpp": "effect* effect::clone() { return pduel->new_effect(); }\n",
        "effect.h": "effect* clone();\n",
        "interpreter.cpp": "int clone_lua_ref(int ref);\n",
        "libeffect.cpp": "LUA_FUNCTION(Clone) {}\n",
        "libgroup.cpp": "LUA_FUNCTION(Clone) {}\n",
    }
    for name, content in files.items():
        (root / name).write_text(content.strip() + "\n", encoding="utf-8")


def test_snapshot_audit_rejects_private_clone_as_duel_snapshot(tmp_path: Path) -> None:
    _write_source_fixture(tmp_path)

    evidence = audit_ocgcore_snapshot_source(
        tmp_path,
        lock_identity={"api": {"major": 11, "minor": 0}, "commit": "fixture"},
    )

    assert evidence["audit_id"].startswith("snapshotaudit_")
    assert evidence["decision"]["adopt_native_mid_duel_state"] is False
    assert evidence["public_api"]["state_transfer_functions"] == []
    assert any(
        item["file"] == "effect.cpp"
        for item in evidence["internal_transfer_matches"]
    )


def test_snapshot_audit_fails_closed_when_public_api_changes(tmp_path: Path) -> None:
    _write_source_fixture(tmp_path)
    header = tmp_path / "ocgapi.h"
    header.write_text(
        header.read_text(encoding="utf-8")
        + "OCGAPI int OCG_SnapshotDuel(OCG_Duel duel, void* out);\n",
        encoding="utf-8",
    )

    with pytest.raises(AssertionError, match="requires re-evaluation"):
        audit_ocgcore_snapshot_source(
            tmp_path,
            lock_identity={"api": {"major": 11, "minor": 0}, "commit": "fixture"},
        )


def test_prefix_cache_rejects_native_handle_reuse() -> None:
    key = ReplayPrefixCacheKey(
        manifest_hash="manifest",
        initial_snapshot_hash="state_initial",
        replay_schema_version="0.3a",
        prefix_length=0,
        prefix_digest="prefix",
    )

    assert NATIVE_PREFIX_STATE_REUSE_ALLOWED is False
    with pytest.raises(ValueError, match="ADR-0009"):
        ReplayPrefixCacheEntry(
            key=key,
            terminal_state_id="state_initial",
            next_request_signature=None,
            core_trace_digest="coretrace",
            artifact_ref="route:fixture",
            state_completeness="exact",
            reuse_mode="native_snapshot",
        )
