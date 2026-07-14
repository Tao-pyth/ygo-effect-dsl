from __future__ import annotations

import ctypes
import hashlib
import sqlite3
import threading
from pathlib import Path
from typing import Any, Callable

import pytest

from ygo_effect_dsl.engine.action import Action, ActionKind, Selection
from ygo_effect_dsl.engine.bridge.ocgcore import (
    CARD_SCRIPTS_PROFILE_OFFICIAL,
    CardRecord,
    CardScriptsProvider,
    DuelConfig,
    DuelProcessStatus,
    DuelState,
    FilesystemScriptProvider,
    InMemoryCardDataProvider,
    InMemoryScriptProvider,
    NewCard,
    OcgcoreAssetError,
    OcgcoreBufferError,
    OcgcoreCallbackError,
    OcgcoreCreateError,
    OcgcoreLibrary,
    OcgcoreLuaError,
    OcgcoreMessageDecoder,
    OcgcoreStateError,
    OcgcoreTimeoutError,
    OcgcoreVersionMismatchError,
    Query,
    ResolvedScript,
    SCRIPT_RESOLUTION_SCHEMA_VERSION,
    SQLiteCardDataProvider,
    native_layout,
    resolve_script,
)
from ygo_effect_dsl.engine.bridge.ocgcore.types import OCGDuelOptions
from ygo_effect_dsl.external.ocgcore import OcgcoreBootstrapError, resolve_ocgcore_runtime


class _FakeFunction:
    def __init__(self, implementation: Callable[..., Any]) -> None:
        self.implementation = implementation
        self.argtypes: list[Any] | None = None
        self.restype: Any = None

    def __call__(self, *args: Any) -> Any:
        return self.implementation(*args)


class _FakeNative:
    def __init__(
        self,
        *,
        version: tuple[int, int] = (11, 0),
        creation_status: int = 0,
        process_statuses: list[int] | None = None,
        messages: list[bytes] | None = None,
    ) -> None:
        self.version = version
        self.creation_status = creation_status
        self.process_statuses = list(process_statuses or [DuelProcessStatus.END])
        self.messages = list(messages or [b""])
        self.process_index = -1
        self.destroy_count = 0
        self.responses: list[bytes] = []
        self.options: OCGDuelOptions | None = None
        self._message_buffer = ctypes.create_string_buffer(4096)
        self.OCG_GetVersion = _FakeFunction(self._get_version)
        self.OCG_CreateDuel = _FakeFunction(self._create_duel)
        self.OCG_DestroyDuel = _FakeFunction(self._destroy_duel)
        self.OCG_DuelNewCard = _FakeFunction(lambda *_args: None)
        self.OCG_StartDuel = _FakeFunction(lambda *_args: None)
        self.OCG_DuelProcess = _FakeFunction(self._process)
        self.OCG_DuelGetMessage = _FakeFunction(self._get_message)
        self.OCG_DuelSetResponse = _FakeFunction(self._set_response)
        self.OCG_LoadScript = _FakeFunction(lambda *_args: 1)
        self.OCG_DuelQueryCount = _FakeFunction(lambda *_args: 0)
        self.OCG_DuelQuery = _FakeFunction(self._query)
        self.OCG_DuelQueryLocation = _FakeFunction(self._query)
        self.OCG_DuelQueryField = _FakeFunction(self._query_field)

    def _get_version(self, major: Any, minor: Any) -> None:
        ctypes.cast(major, ctypes.POINTER(ctypes.c_int))[0] = self.version[0]
        ctypes.cast(minor, ctypes.POINTER(ctypes.c_int))[0] = self.version[1]

    def _create_duel(self, output: Any, options: Any) -> int:
        value = 0x1234 if self.creation_status == 0 else 0
        ctypes.cast(output, ctypes.POINTER(ctypes.c_void_p))[0] = value
        if value:
            self.options = ctypes.cast(options, ctypes.POINTER(OCGDuelOptions)).contents
        return self.creation_status

    def _destroy_duel(self, _duel: Any) -> None:
        self.destroy_count += 1

    def _process(self, _duel: Any) -> int:
        self.process_index += 1
        return int(self.process_statuses[self.process_index])

    def _current_message(self) -> bytes:
        index = min(self.process_index, len(self.messages) - 1)
        return self.messages[max(0, index)]

    def _get_message(self, _duel: Any, length: Any) -> int:
        message = self._current_message()
        ctypes.memset(self._message_buffer, 0, ctypes.sizeof(self._message_buffer))
        if message:
            ctypes.memmove(self._message_buffer, message, len(message))
        ctypes.cast(length, ctypes.POINTER(ctypes.c_uint32))[0] = len(message)
        return ctypes.addressof(self._message_buffer)

    def _set_response(self, _duel: Any, pointer: Any, length: int) -> None:
        self.responses.append(ctypes.string_at(pointer, length) if length else b"")

    def _query(self, _duel: Any, length: Any, _query: Any) -> int:
        return self._query_bytes(length, b"query")

    def _query_field(self, _duel: Any, length: Any) -> int:
        return self._query_bytes(length, b"field")

    def _query_bytes(self, length: Any, value: bytes) -> int:
        ctypes.memmove(self._message_buffer, value, len(value))
        ctypes.cast(length, ctypes.POINTER(ctypes.c_uint32))[0] = len(value)
        return ctypes.addressof(self._message_buffer)


def _fake_library(fake: _FakeNative) -> OcgcoreLibrary:
    return OcgcoreLibrary(native=fake, enforce_architecture=False)


def _duel_config() -> DuelConfig:
    return DuelConfig(seed=(1, 2, 3, 4))


def _empty_cards() -> InMemoryCardDataProvider:
    return InMemoryCardDataProvider({})


def _empty_scripts() -> InMemoryScriptProvider:
    return InMemoryScriptProvider({})


def test_native_layout_and_version_are_rejected_before_duel_creation() -> None:
    assert native_layout() == {
        "pointer_width": 8,
        "OCGPlayer": 12,
        "OCGCardData": 64,
        "OCGDuelOptions": 136,
        "OCGNewCardInfo": 24,
        "OCGQueryInfo": 20,
    }


def test_rejected_lua_is_classified_separately_from_missing_asset() -> None:
    fake = _FakeNative()
    fake.OCG_LoadScript = _FakeFunction(lambda *_args: 0)

    with _fake_library(fake) as library:
        with library.create_duel(
            _duel_config(), _empty_cards(), InMemoryScriptProvider({"bad.lua": b"bad"})
        ) as duel:
            with pytest.raises(OcgcoreLuaError) as captured:
                duel.load_script("bad.lua", b"bad")
            assert captured.value.category == "lua_error"
            assert duel.state == DuelState.FAILED
            assert duel.script_load_audit[0]["outcome"] == "rejected"
            assert duel.script_load_audit[0]["source_kind"] == "provided"
    with pytest.raises(OcgcoreVersionMismatchError, match="expected ocgcore API"):
        _fake_library(_FakeNative(version=(10, 0)))


def test_process_state_machine_copies_invalidated_buffers_and_destroys_once() -> None:
    fake = _FakeNative(
        process_statuses=[DuelProcessStatus.CONTINUE, DuelProcessStatus.AWAITING, DuelProcessStatus.END],
        messages=[b"first", b"second", b"ended"],
    )
    library = _fake_library(fake)
    duel = library.create_duel(_duel_config(), _empty_cards(), _empty_scripts())
    assert duel.state == DuelState.DUEL_CREATED
    assert fake.options is not None
    assert fake.options.enableUnsafeLibraries == 0
    fake.options.logHandler(None, b"native diagnostic", 0)
    assert duel.diagnostics[-1].message == "native diagnostic"
    assert duel.diagnostics[-1].context == {"log_type": "error"}

    with pytest.raises(OcgcoreStateError, match="active duel"):
        library.close()
    with pytest.raises(OcgcoreStateError, match="operation is invalid"):
        duel.respond(b"too early")
    with pytest.raises(OcgcoreBufferError, match="exceeds"):
        duel.load_script("oversized.lua", b"x" * (1024 * 1024 + 1))

    duel.start()
    waiting = duel.process()
    assert waiting.status == DuelProcessStatus.AWAITING
    assert waiting.messages == (b"first", b"second")
    assert len(waiting.logs) == 1
    assert waiting.logs[0].message == "native diagnostic"
    assert waiting.logs[0].log_type.name == "ERROR"
    assert duel.state == DuelState.AWAITING_RESPONSE

    request = OcgcoreMessageDecoder().decode_batch(
        bytes.fromhex("0a0000000d000807060504030201"),
        request_id="lifecycle-response",
    ).request
    assert request is not None
    action = Action(
        kind=ActionKind.SELECT_OPTION,
        player=request.player,
        selections=(Selection("choice:1"),),
        request_signature=request.request_signature,
    )
    encoded = duel.respond_action(request, action)
    assert encoded.data == b"\x01\x00\x00\x00"
    assert fake.responses == [encoded.data]
    with pytest.raises(OcgcoreStateError, match="operation is invalid"):
        duel.respond_action(request, action)
    ended = duel.process()
    assert ended.status == DuelProcessStatus.END
    assert ended.messages == (b"ended",)
    assert ended.logs == ()
    assert duel.query(Query(flags=0, controller=0, location=1)) == b"query"
    assert duel.query_field() == b"field"
    with pytest.raises(OcgcoreStateError, match="operation is invalid"):
        duel.start()

    duel.destroy()
    duel.destroy()
    assert fake.destroy_count == 1
    assert duel.state == DuelState.DESTROYED
    with pytest.raises(OcgcoreStateError, match="query is invalid"):
        duel.query_field()
    library.close()


def test_invalid_transition_create_failure_and_step_budget_cleanup() -> None:
    failed_library = _fake_library(_FakeNative(creation_status=2))
    with pytest.raises(OcgcoreCreateError, match="not_created"):
        failed_library.create_duel(_duel_config(), _empty_cards(), _empty_scripts())
    failed_library.close()

    fake = _FakeNative(
        process_statuses=[DuelProcessStatus.CONTINUE] * 3,
        messages=[b""] * 3,
    )
    library = _fake_library(fake)
    with library.create_duel(_duel_config(), _empty_cards(), _empty_scripts()) as duel:
        with pytest.raises(OcgcoreStateError, match="operation is invalid"):
            duel.process()
        duel.start()
        with pytest.raises(OcgcoreTimeoutError, match="max_steps=2"):
            duel.process(max_steps=2, timeout_seconds=1)
        assert duel.state == DuelState.FAILED
    assert fake.destroy_count == 1
    library.close()


def test_thread_affinity_rejects_cross_thread_use() -> None:
    library = _fake_library(_FakeNative())
    duel = library.create_duel(_duel_config(), _empty_cards(), _empty_scripts())
    captured: list[BaseException] = []

    def use_from_other_thread() -> None:
        try:
            duel.query_count(0, 1)
        except BaseException as exc:
            captured.append(exc)

    thread = threading.Thread(target=use_from_other_thread)
    thread.start()
    thread.join()

    assert len(captured) == 1
    assert isinstance(captured[0], OcgcoreStateError)
    duel.destroy()
    library.close()


def test_sqlite_and_filesystem_providers_are_read_only_asset_boundaries(tmp_path: Path) -> None:
    database = tmp_path / "cards.cdb"
    connection = sqlite3.connect(database)
    connection.execute(
        "CREATE TABLE datas (id INTEGER, ot INTEGER, alias INTEGER, setcode INTEGER, "
        "type INTEGER, atk INTEGER, def INTEGER, level INTEGER, race INTEGER, attribute INTEGER)"
    )
    packed_level = 7 | (2 << 16) | (3 << 24)
    connection.execute(
        "INSERT INTO datas VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (123, 0, 0, 0x22220011, 0x10, 2500, 2000, packed_level, 1, 2),
    )
    connection.commit()
    connection.close()

    with SQLiteCardDataProvider(database) as provider:
        database_row = provider.get_database_row(123)
        record = provider.get_card(123)
    assert database_row == {
        "alias": 0,
        "atk": 2500,
        "attribute": 2,
        "def": 2000,
        "id": 123,
        "level": packed_level,
        "race": 1,
        "setcode": 0x22220011,
        "type": 0x10,
    }
    assert record.level == 7
    assert record.lscale == 3
    assert record.rscale == 2
    assert record.setcodes == (0x11, 0x2222)

    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / "c123.lua").write_bytes(b"return 1\n")
    provider = FilesystemScriptProvider(scripts)
    assert provider.get_script("c123.lua") == b"return 1\n"
    with pytest.raises(OcgcoreAssetError):
        provider.get_script("../secret.lua")

    (scripts / "official").mkdir()
    (scripts / "official" / "c456.lua").write_bytes(b"return 2\n")
    card_scripts = CardScriptsProvider(scripts)
    assert card_scripts.get_script("c0.lua") == b""
    assert card_scripts.get_script("c456.lua") == b"return 2\n"


def test_filesystem_script_resolution_is_canonical_and_fail_closed(tmp_path: Path) -> None:
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    exact = scripts / "Exact.lua"
    exact.write_bytes(b"return 1\n")
    outside = tmp_path / "outside.lua"
    outside.write_bytes(b"return 2\n")
    linked = scripts / "linked.lua"
    try:
        linked.symlink_to(outside)
    except OSError:
        symlink_created = False
    else:
        symlink_created = True
    provider = FilesystemScriptProvider(scripts)

    resolved = provider.resolve_script("Exact.lua")
    assert resolved == ResolvedScript(
        requested_name="Exact.lua",
        resolved_path="Exact.lua",
        source_kind="filesystem",
        content=b"return 1\n",
        size=9,
        sha256=hashlib.sha256(b"return 1\n").hexdigest(),
    )
    assert provider.resolve_script("Exact.lua") == resolved
    with pytest.raises(OcgcoreAssetError, match="does not match asset path case"):
        provider.get_script("exact.lua")
    with pytest.raises(OcgcoreAssetError):
        provider.get_script("sub/../Exact.lua")
    with pytest.raises(OcgcoreAssetError):
        provider.get_script("C:/Exact.lua")

    if symlink_created:
        with pytest.raises(OcgcoreAssetError, match="symbolic link"):
            provider.get_script("linked.lua")

    oversized = scripts / "oversized.lua"
    oversized.write_bytes(b"x" * (1024 * 1024 + 1))
    with pytest.raises(OcgcoreAssetError, match="exceeds"):
        provider.get_script("oversized.lua")

    collision_root = tmp_path / "case-collision"
    collision_root.mkdir()
    (collision_root / "Case.lua").write_bytes(b"one")
    collision_provider = FilesystemScriptProvider(collision_root)
    assert collision_provider.get_script("Case.lua") == b"one"
    (collision_root / "case.lua").write_bytes(b"two")
    if len(tuple(collision_root.iterdir())) == 2:
        with pytest.raises(OcgcoreAssetError, match="case-colliding"):
            collision_provider.get_script("Case.lua")

    with pytest.raises(OcgcoreAssetError, match="SHA-256"):
        ResolvedScript(
            requested_name="forged.lua",
            resolved_path="forged.lua",
            source_kind="memory",
            content=b"content",
            size=7,
            sha256="0" * 64,
        )

    class ProbeProvider:
        def __init__(self) -> None:
            self.calls: list[str] = []

        def get_script(self, name: str) -> bytes:
            self.calls.append(name)
            return b"content"

    probe = ProbeProvider()
    with pytest.raises(OcgcoreAssetError):
        resolve_script(probe, "../secret.lua")
    assert probe.calls == []

    class RenamingProvider:
        def resolve_script(self, _name: str) -> ResolvedScript:
            return ResolvedScript.from_bytes(
                requested_name="other.lua",
                resolved_path="other.lua",
                source_kind="memory",
                content=b"content",
            )

        def get_script(self, name: str) -> bytes:
            raise AssertionError(name)

    with pytest.raises(OcgcoreAssetError, match="changed the requested name"):
        resolve_script(RenamingProvider(), "requested.lua")


def test_card_script_resolution_rejects_ambiguous_directory_matches(tmp_path: Path) -> None:
    scripts = tmp_path / "scripts"
    for directory in ("official", "goat", "rush"):
        target = scripts / directory
        target.mkdir(parents=True)
        (target / "c456.lua").write_text(f"return {directory!r}\n", encoding="utf-8")
    (scripts / "rush" / "c789.lua").write_text("return 'rush'\n", encoding="utf-8")

    legacy = CardScriptsProvider(scripts)
    assert legacy.resolve_script("c456.lua").resolved_path == "official/c456.lua"
    assert legacy.resolve_script("c789.lua").resolved_path == "rush/c789.lua"
    with pytest.raises(OcgcoreAssetError, match="ambiguous across allowed roots"):
        CardScriptsProvider(
            scripts, card_directories=("official", "goat")
        ).get_script("c456.lua")

    official = CardScriptsProvider(scripts, card_directories=("official",))
    resolved = official.resolve_script("c456.lua")
    assert resolved.requested_name == "c456.lua"
    assert resolved.resolved_path == "official/c456.lua"
    assert resolved.source_kind == "filesystem"

    strict = CardScriptsProvider(
        scripts,
        profile_id=CARD_SCRIPTS_PROFILE_OFFICIAL,
    )
    with pytest.raises(OcgcoreAssetError, match="outside CardScripts profile"):
        strict.get_script("rush/c789.lua")
    with pytest.raises(OcgcoreAssetError):
        strict.get_script("c789.lua")


def test_duel_records_ordered_script_resolution_audit() -> None:
    fake = _FakeNative()
    scripts = InMemoryScriptProvider(
        {"constant.lua": b"constant", "c123.lua": b"card"}
    )

    with _fake_library(fake) as library:
        with library.create_duel(_duel_config(), _empty_cards(), scripts) as duel:
            duel.load_script_resolution(scripts.resolve_script("constant.lua"))
            assert fake.options is not None
            assert fake.options.scriptReader(None, 0x1234, b"c123.lua") == 1

            audit = duel.script_load_audit
            assert [item["sequence"] for item in audit] == [0, 1]
            assert [item["requested_name"] for item in audit] == [
                "constant.lua",
                "c123.lua",
            ]
            assert all(item["outcome"] == "loaded" for item in audit)
            assert audit[1]["sha256"] == hashlib.sha256(b"card").hexdigest()
            assert audit[1]["resolved_path"] == "c123.lua"
            assert duel.experiment_manifest["lua_script_resolution"] == {
                "schema_version": SCRIPT_RESOLUTION_SCHEMA_VERSION,
                "profile_id": "in-memory-script-provider-v1",
                "loads": list(audit),
            }


def test_script_reader_records_missing_and_rejected_outcomes() -> None:
    missing_native = _FakeNative()
    with _fake_library(missing_native) as library:
        with library.create_duel(
            _duel_config(), _empty_cards(), InMemoryScriptProvider({})
        ) as duel:
            assert missing_native.options is not None
            assert missing_native.options.scriptReader(None, 0x1234, b"missing.lua") == 0
            assert duel.script_load_audit[0]["outcome"] == "missing"
            with pytest.raises(OcgcoreCallbackError) as captured:
                duel.add_card(NewCard(0, 0, 1, 0, 0x1, 0, 0x8))
            assert captured.value.category == "asset_error"

    rejected_native = _FakeNative()
    rejected_native.OCG_LoadScript = _FakeFunction(lambda *_args: 0)
    with _fake_library(rejected_native) as library:
        with library.create_duel(
            _duel_config(),
            _empty_cards(),
            InMemoryScriptProvider({"rejected.lua": b"bad"}),
        ) as duel:
            assert rejected_native.options is not None
            assert rejected_native.options.scriptReader(None, 0x1234, b"rejected.lua") == 0
            assert duel.script_load_audit[0]["outcome"] == "rejected"
            with pytest.raises(OcgcoreCallbackError) as captured:
                duel.add_card(NewCard(0, 0, 1, 0, 0x1, 0, 0x8))
            assert captured.value.category == "lua_error"


def test_nested_script_reader_error_has_priority_over_outer_load_rejection() -> None:
    native = _FakeNative()
    scripts = InMemoryScriptProvider({"outer.lua": b"outer"})
    with _fake_library(native) as library:
        with library.create_duel(_duel_config(), _empty_cards(), scripts) as duel:
            def reject_after_missing(*_args: Any) -> int:
                assert native.options is not None
                assert native.options.scriptReader(None, 0x1234, b"missing.lua") == 0
                return 0

            native.OCG_LoadScript = _FakeFunction(reject_after_missing)
            with pytest.raises(OcgcoreCallbackError) as captured:
                duel.load_script_resolution(scripts.resolve_script("outer.lua"))
            assert captured.value.category == "asset_error"
            assert [item["outcome"] for item in duel.script_load_audit] == [
                "rejected",
                "missing",
            ]


def test_real_core_callbacks_release_setcodes_and_report_missing_assets() -> None:
    try:
        runtime = resolve_ocgcore_runtime()
    except (OcgcoreBootstrapError, OSError) as exc:
        pytest.skip(f"verified local ocgcore runtime is unavailable: {exc}")

    cards = InMemoryCardDataProvider(
        {
            123: CardRecord(
                code=123,
                setcodes=(0x10, 0x20),
                type=0x10,
                level=4,
                attack=1000,
                defense=1000,
            )
        }
    )
    scripts = InMemoryScriptProvider({"c0.lua": b"", "c123.lua": b""})
    with OcgcoreLibrary(runtime) as library:
        duel = library.create_duel(_duel_config(), cards, scripts)
        duel.add_card(NewCard(0, 0, 123, 0, 0x1, 0, 0x8))
        assert duel.state == DuelState.CARDS_LOADED
        assert duel.outstanding_native_allocations == 0
        assert duel.query_count(0, 0x1) == 1
        duel.destroy()
        duel.destroy()

    with OcgcoreLibrary(runtime) as library:
        scripts = InMemoryScriptProvider({"c0.lua": b""})
        with library.create_duel(_duel_config(), _empty_cards(), scripts) as duel:
            with pytest.raises(OcgcoreCallbackError) as captured:
                duel.add_card(NewCard(0, 0, 999, 0, 0x1, 0, 0x8))
            assert captured.value.category == "asset_error"
            assert duel.state == DuelState.FAILED
            assert duel.diagnostics[0].context == {"callback": "DataReader"}

    with OcgcoreLibrary(runtime) as library:
        scripts = InMemoryScriptProvider({"c0.lua": b""})
        with library.create_duel(_duel_config(), cards, scripts) as duel:
            with pytest.raises(OcgcoreCallbackError) as captured:
                duel.add_card(NewCard(0, 0, 123, 0, 0x1, 0, 0x8))
            assert captured.value.category == "asset_error"
            assert captured.value.callback == "ScriptReader"
            assert "c123.lua" in str(captured.value)

    class ExplodingScriptProvider:
        def get_script(self, name: str) -> bytes:
            if name == "c0.lua":
                return b""
            raise RuntimeError("script provider failed")

    with OcgcoreLibrary(runtime) as library:
        with library.create_duel(_duel_config(), cards, ExplodingScriptProvider()) as duel:
            with pytest.raises(OcgcoreCallbackError) as captured:
                duel.add_card(NewCard(0, 0, 123, 0, 0x1, 0, 0x8))
            assert captured.value.category == "core_error"
            assert captured.value.callback == "ScriptReader"
            assert "script provider failed" in str(captured.value)

    with OcgcoreLibrary(runtime) as library:
        with pytest.raises(OcgcoreCallbackError) as captured:
            library.create_duel(_duel_config(), _empty_cards(), _empty_scripts())
        assert captured.value.category == "asset_error"
        scripts = InMemoryScriptProvider({"c0.lua": b""})
        with library.create_duel(_duel_config(), _empty_cards(), scripts):
            pass
