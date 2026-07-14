from __future__ import annotations

import ctypes
import sqlite3
import threading
from pathlib import Path
from typing import Any, Callable

import pytest

from ygo_effect_dsl.engine.action import Action, ActionKind, Selection
from ygo_effect_dsl.engine.bridge.ocgcore import (
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
    SQLiteCardDataProvider,
    native_layout,
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
