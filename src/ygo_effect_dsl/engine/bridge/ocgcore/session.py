from __future__ import annotations

import ctypes
import threading
import time
from typing import Any, Mapping

from ygo_effect_dsl.engine.bridge.ocgcore.binding import OcgcoreLibrary
from ygo_effect_dsl.engine.bridge.ocgcore.errors import (
    MissingCardDataError,
    MissingScriptError,
    OcgcoreAssetError,
    OcgcoreBridgeError,
    OcgcoreBufferError,
    OcgcoreCallbackError,
    OcgcoreCreateError,
    OcgcoreLuaError,
    OcgcoreStateError,
    OcgcoreTimeoutError,
)
from ygo_effect_dsl.engine.bridge.ocgcore.providers import (
    MAX_SCRIPT_BYTES,
    SCRIPT_RESOLUTION_SCHEMA_VERSION,
    CardDataProvider,
    ResolvedScript,
    ScriptProvider,
    resolve_script,
)
from ygo_effect_dsl.engine.bridge.ocgcore.types import (
    MAX_NATIVE_BUFFER_BYTES,
    MAX_RESPONSE_BYTES,
    CardRecord,
    CoreLog,
    DataReader,
    DataReaderDone,
    Diagnostic,
    DuelConfig,
    DuelCreationStatus,
    DuelProcessStatus,
    DuelState,
    LogHandler,
    LogType,
    NewCard,
    OCGCardData,
    OCGDuelOptions,
    ProcessBatch,
    Query,
    ScriptReader,
)


class OcgcoreDuel:
    """One-thread, one-duel owner for the ocgcore C API."""

    def __init__(
        self,
        library: OcgcoreLibrary,
        config: DuelConfig,
        card_data: CardDataProvider,
        scripts: ScriptProvider,
    ) -> None:
        config.validate()
        self.library = library
        self.config = config
        self.card_data = card_data
        self.scripts = scripts
        self.state = DuelState.VERSION_CHECKED
        self.history: list[DuelState] = [self.state]
        self._owner_thread = threading.get_ident()
        self._callback_depth = 0
        self._callback_errors: list[OcgcoreCallbackError] = []
        self._diagnostics: list[Diagnostic] = []
        self._pending_logs: list[CoreLog] = []
        self._next_log_sequence = 0
        self._script_load_audit: list[dict[str, Any]] = []
        self._next_script_load_sequence = 0
        self._script_resolution_profile_id = str(
            getattr(scripts, "script_resolution_profile_id", "custom-script-provider-v1")
        )
        self._setcode_allocations: dict[int, Any] = {}
        self._destroyed_native = False
        self._registered_with_library = False
        self._duel = ctypes.c_void_p()
        self._data_reader = DataReader(self._on_data_reader)
        self._script_reader = ScriptReader(self._on_script_reader)
        self._log_handler = LogHandler(self._on_log)
        self._data_reader_done = DataReaderDone(self._on_data_reader_done)
        self._options = self._build_options()
        status = self.library.native.OCG_CreateDuel(
            ctypes.byref(self._duel), ctypes.byref(self._options)
        )
        if status != DuelCreationStatus.SUCCESS or not self._duel.value:
            if self._duel.value:
                self.library.native.OCG_DestroyDuel(self._duel)
                self._destroyed_native = True
            self._transition(DuelState.FAILED)
            self._release_python_owners()
            raise OcgcoreCreateError(
                f"OCG_CreateDuel failed with status={status} ({self._creation_status_name(status)})"
            )
        self.library._session_opened()
        self._registered_with_library = True
        self._transition(DuelState.DUEL_CREATED)
        try:
            self._raise_callback_error()
        except BaseException:
            self.destroy()
            raise

    @staticmethod
    def _creation_status_name(value: int) -> str:
        try:
            return DuelCreationStatus(value).name.lower()
        except ValueError:
            return "unknown"

    def _build_options(self) -> OCGDuelOptions:
        options = OCGDuelOptions()
        options.seed = (ctypes.c_uint64 * 4)(*self.config.seed)
        options.flags = self.config.flags
        options.team1 = self.config.team1.to_native()
        options.team2 = self.config.team2.to_native()
        options.cardReader = self._data_reader
        options.scriptReader = self._script_reader
        options.logHandler = self._log_handler
        options.cardReaderDone = self._data_reader_done
        options.enableUnsafeLibraries = 0
        return options

    def _transition(self, state: DuelState) -> None:
        self.state = state
        self.history.append(state)

    def _assert_owner(self) -> None:
        if threading.get_ident() != self._owner_thread:
            raise OcgcoreStateError("ocgcore duel may only be used by its owner thread")
        if self._callback_depth:
            raise OcgcoreStateError("public ocgcore calls are forbidden while a callback is active")

    def _require(self, *states: DuelState) -> None:
        self._assert_owner()
        if self.state not in states:
            allowed = ", ".join(state.value for state in states)
            raise OcgcoreStateError(
                f"operation is invalid in state {self.state.value}; expected one of: {allowed}"
            )

    @property
    def diagnostics(self) -> tuple[Diagnostic, ...]:
        return tuple(self._diagnostics)

    @property
    def outstanding_native_allocations(self) -> int:
        return len(self._setcode_allocations)

    @property
    def experiment_manifest(self) -> dict[str, Any]:
        return {
            "ocgcore_api": {
                "major": self.library.api_version[0],
                "minor": self.library.api_version[1],
            },
            "enable_unsafe_libraries": False,
            "seed": list(self.config.seed),
            "flags": self.config.flags,
            "lua_script_resolution": self.script_resolution_manifest,
        }

    @property
    def script_load_audit(self) -> tuple[dict[str, Any], ...]:
        return tuple(
            dict(item)
            for item in sorted(
                self._script_load_audit,
                key=lambda item: int(item["sequence"]),
            )
        )

    @property
    def script_resolution_manifest(self) -> dict[str, Any]:
        return {
            "schema_version": SCRIPT_RESOLUTION_SCHEMA_VERSION,
            "profile_id": self._script_resolution_profile_id,
            "loads": list(self.script_load_audit),
        }

    def _begin_script_load(self) -> int:
        sequence = self._next_script_load_sequence
        self._next_script_load_sequence += 1
        return sequence

    def _record_script_load(
        self,
        *,
        sequence: int,
        requested_name: str,
        outcome: str,
        resolution: ResolvedScript | None = None,
        error: str | None = None,
    ) -> None:
        entry: dict[str, Any] = {
            "sequence": sequence,
            "requested_name": requested_name,
            "outcome": outcome,
        }
        if resolution is not None:
            metadata = resolution.audit_dict()
            metadata.pop("requested_name", None)
            entry.update(metadata)
        if error is not None:
            entry["error"] = error
        self._script_load_audit.append(entry)

    def _capture_callback_error(
        self, callback: str, exc: BaseException, *, category: str = "core_error"
    ) -> None:
        error = OcgcoreCallbackError(callback, str(exc), cause_category=category)
        self._callback_errors.append(error)
        self._diagnostics.append(
            Diagnostic(
                severity="error",
                category=error.category,
                message=str(error),
                context={"callback": callback},
            )
        )

    def _callback_enter(self, name: str) -> bool:
        if threading.get_ident() != self._owner_thread:
            self._capture_callback_error(
                name, OcgcoreStateError("callback ran on a non-owner thread")
            )
            return False
        self._callback_depth += 1
        return True

    def _callback_exit(self) -> None:
        self._callback_depth = max(0, self._callback_depth - 1)

    def _on_data_reader(
        self,
        _payload: int | None,
        code: int,
        data: ctypes.POINTER(OCGCardData),
    ) -> None:
        if not self._callback_enter("DataReader"):
            return
        try:
            if not data:
                raise OcgcoreBufferError("DataReader received a null OCG_CardData pointer")
            record = self.card_data.get_card(code)
            record.validate()
            self._write_card_data(data.contents, record)
            if record.setcodes:
                allocation = (ctypes.c_uint16 * (len(record.setcodes) + 1))(
                    *record.setcodes, 0
                )
                data.contents.setcodes = ctypes.cast(
                    allocation, ctypes.POINTER(ctypes.c_uint16)
                )
                self._setcode_allocations[ctypes.addressof(data.contents)] = allocation
        except MissingCardDataError as exc:
            self._capture_callback_error("DataReader", exc, category="asset_error")
        except OcgcoreAssetError as exc:
            self._capture_callback_error("DataReader", exc, category="asset_error")
        except BaseException as exc:
            self._capture_callback_error("DataReader", exc)
        finally:
            self._callback_exit()

    @staticmethod
    def _write_card_data(native: OCGCardData, record: CardRecord) -> None:
        native.code = record.code
        native.alias = record.alias
        native.type = record.type
        native.level = record.level
        native.attribute = record.attribute
        native.race = record.race
        native.attack = record.attack
        native.defense = record.defense
        native.lscale = record.lscale
        native.rscale = record.rscale
        native.link_marker = record.link_marker

    def _on_data_reader_done(
        self, _payload: int | None, data: ctypes.POINTER(OCGCardData)
    ) -> None:
        if not self._callback_enter("DataReaderDone"):
            return
        try:
            if not data:
                raise OcgcoreBufferError("DataReaderDone received a null OCG_CardData pointer")
            self._setcode_allocations.pop(ctypes.addressof(data.contents), None)
        except BaseException as exc:
            self._capture_callback_error("DataReaderDone", exc)
        finally:
            self._callback_exit()

    def _on_script_reader(
        self,
        _payload: int | None,
        duel: int | None,
        raw_name: bytes | None,
    ) -> int:
        if not self._callback_enter("ScriptReader"):
            return 0
        sequence = self._begin_script_load()
        name = "<null>"
        resolution: ResolvedScript | None = None
        try:
            if not raw_name:
                raise MissingScriptError("<null>")
            name = raw_name.decode("utf-8", errors="strict")
            resolution = resolve_script(self.scripts, name)
            result = self.library.native.OCG_LoadScript(
                duel,
                resolution.content,
                resolution.size,
                name.encode("utf-8"),
            )
            if result <= 0:
                raise OcgcoreLuaError(f"OCG_LoadScript rejected {name!r}")
            self._record_script_load(
                sequence=sequence,
                requested_name=name,
                outcome="loaded",
                resolution=resolution,
            )
            return 1
        except MissingScriptError as exc:
            self._record_script_load(
                sequence=sequence,
                requested_name=name,
                outcome="missing",
                resolution=resolution,
                error=str(exc),
            )
            self._capture_callback_error("ScriptReader", exc, category="asset_error")
        except OcgcoreLuaError as exc:
            self._record_script_load(
                sequence=sequence,
                requested_name=name,
                outcome="rejected",
                resolution=resolution,
                error=str(exc),
            )
            self._capture_callback_error("ScriptReader", exc, category="lua_error")
        except OcgcoreAssetError as exc:
            self._record_script_load(
                sequence=sequence,
                requested_name=name,
                outcome="asset_error",
                resolution=resolution,
                error=str(exc),
            )
            self._capture_callback_error("ScriptReader", exc, category="asset_error")
        except UnicodeError as exc:
            self._record_script_load(
                sequence=sequence,
                requested_name="<invalid-utf8>",
                outcome="invalid_encoding",
                error=str(exc),
            )
            self._capture_callback_error("ScriptReader", exc, category="asset_error")
        except BaseException as exc:
            self._record_script_load(
                sequence=sequence,
                requested_name=name,
                outcome="provider_error",
                resolution=resolution,
                error=str(exc),
            )
            self._capture_callback_error("ScriptReader", exc)
        finally:
            self._callback_exit()
        return 0

    def _on_log(
        self,
        _payload: int | None,
        raw_message: bytes | None,
        raw_type: int,
    ) -> None:
        if not self._callback_enter("LogHandler"):
            return
        try:
            message = (raw_message or b"").decode("utf-8", errors="replace")
            try:
                log_type = LogType(raw_type)
            except ValueError:
                log_type = LogType.UNDEFINED
            severity = {
                LogType.ERROR: "error",
                LogType.FROM_SCRIPT: "warning",
                LogType.FOR_DEBUG: "debug",
                LogType.UNDEFINED: "warning",
            }[log_type]
            self._pending_logs.append(
                CoreLog(
                    sequence=self._next_log_sequence,
                    log_type=log_type,
                    message=message,
                )
            )
            self._next_log_sequence += 1
            self._diagnostics.append(
                Diagnostic(
                    severity=severity,
                    category="core_log",
                    message=message,
                    context={"log_type": log_type.name.lower()},
                )
            )
        except BaseException as exc:
            self._capture_callback_error("LogHandler", exc)
        finally:
            self._callback_exit()

    def _raise_callback_error(self) -> None:
        if not self._callback_errors:
            return
        error = self._callback_errors.pop(0)
        if self.state not in {DuelState.DESTROYED, DuelState.FAILED}:
            self._transition(DuelState.FAILED)
        raise error

    def add_card(self, card: NewCard) -> None:
        self._require(DuelState.DUEL_CREATED, DuelState.CARDS_LOADED)
        native = card.to_native()
        self.library.native.OCG_DuelNewCard(self._duel, ctypes.byref(native))
        self._raise_callback_error()
        if self.state == DuelState.DUEL_CREATED:
            self._transition(DuelState.CARDS_LOADED)

    def load_script(self, name: str, script: bytes) -> None:
        if len(script) > MAX_SCRIPT_BYTES:
            raise OcgcoreBufferError(
                f"Lua script {name!r} exceeds {MAX_SCRIPT_BYTES} bytes"
            )
        resolution = ResolvedScript.from_bytes(
            requested_name=name,
            resolved_path=name,
            source_kind="provided",
            content=script,
        )
        self.load_script_resolution(resolution)

    def load_script_resolution(self, resolution: ResolvedScript) -> None:
        self._require(DuelState.DUEL_CREATED, DuelState.CARDS_LOADED)
        if resolution.size > MAX_SCRIPT_BYTES:
            raise OcgcoreBufferError(
                f"Lua script {resolution.requested_name!r} exceeds {MAX_SCRIPT_BYTES} bytes"
            )
        sequence = self._begin_script_load()
        result = self.library.native.OCG_LoadScript(
            self._duel,
            resolution.content,
            resolution.size,
            resolution.requested_name.encode("utf-8"),
        )
        if result <= 0:
            error = f"OCG_LoadScript rejected {resolution.requested_name!r}"
            self._record_script_load(
                sequence=sequence,
                requested_name=resolution.requested_name,
                outcome="rejected",
                resolution=resolution,
                error=error,
            )
            if self._callback_errors:
                self._raise_callback_error()
            self._transition(DuelState.FAILED)
            raise OcgcoreLuaError(error)
        self._record_script_load(
            sequence=sequence,
            requested_name=resolution.requested_name,
            outcome="loaded",
            resolution=resolution,
        )
        self._raise_callback_error()

    def capture_card_instance_scan(self, *, scan_nonce: str) -> tuple[CoreLog, ...]:
        """Run the private card-instance scan at an awaiting Request boundary."""

        self._require(DuelState.AWAITING_RESPONSE)
        if not scan_nonce or not scan_nonce.replace("_", "").isalnum():
            raise ValueError("scan_nonce must contain only letters, numbers, and underscores")
        script = (
            f'YGO_EFFECT_DSL_CARD_INSTANCE_SCAN_V2("{scan_nonce}")\n'.encode(
                "ascii"
            )
        )
        name = f"ygo_effect_dsl_card_instance_scan_{scan_nonce}.lua"
        result = self.library.native.OCG_LoadScript(
            self._duel, script, len(script), name.encode("utf-8")
        )
        if result <= 0:
            self._transition(DuelState.FAILED)
            raise OcgcoreLuaError(
                f"OCG_LoadScript rejected card-instance scan {scan_nonce!r}"
            )
        self._raise_callback_error()
        return self._drain_logs()

    def start(self) -> None:
        self._require(DuelState.DUEL_CREATED, DuelState.CARDS_LOADED)
        self.library.native.OCG_StartDuel(self._duel)
        self._raise_callback_error()
        self._transition(DuelState.STARTED)

    @staticmethod
    def _copy_buffer(pointer: int | None, length: int, label: str) -> bytes:
        if length > MAX_NATIVE_BUFFER_BYTES:
            raise OcgcoreBufferError(
                f"{label} length {length} exceeds {MAX_NATIVE_BUFFER_BYTES} bytes"
            )
        if length == 0:
            return b""
        if not pointer:
            raise OcgcoreBufferError(f"{label} returned null with non-zero length {length}")
        return ctypes.string_at(pointer, length)

    def _get_message(self) -> bytes:
        length = ctypes.c_uint32()
        pointer = self.library.native.OCG_DuelGetMessage(
            self._duel, ctypes.byref(length)
        )
        return self._copy_buffer(pointer, length.value, "message")

    def process(
        self, *, max_steps: int = 1000, timeout_seconds: float = 1.0
    ) -> ProcessBatch:
        self._require(DuelState.STARTED, DuelState.PROCESSING)
        if max_steps <= 0:
            raise ValueError("max_steps must be positive")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        started = time.perf_counter()
        deadline = started + timeout_seconds
        messages: list[bytes] = []
        self._transition(DuelState.PROCESSING)
        for step in range(1, max_steps + 1):
            raw_status = self.library.native.OCG_DuelProcess(self._duel)
            self._raise_callback_error()
            try:
                status = DuelProcessStatus(raw_status)
            except ValueError as exc:
                self._transition(DuelState.FAILED)
                raise OcgcoreBridgeError(f"unknown OCG_DuelProcess status {raw_status}") from exc
            message = self._get_message()
            if message:
                messages.append(message)
            elapsed = time.perf_counter() - started
            if time.perf_counter() > deadline:
                self._transition(DuelState.FAILED)
                raise OcgcoreTimeoutError(
                    f"ocgcore process exceeded {timeout_seconds:.3f}s after {step} step(s)"
                )
            if status == DuelProcessStatus.AWAITING:
                self._transition(DuelState.AWAITING_RESPONSE)
                return ProcessBatch(
                    status,
                    tuple(messages),
                    step,
                    elapsed,
                    self._drain_logs(),
                )
            if status == DuelProcessStatus.END:
                self._transition(DuelState.ENDED)
                return ProcessBatch(
                    status,
                    tuple(messages),
                    step,
                    elapsed,
                    self._drain_logs(),
                )
        self._transition(DuelState.FAILED)
        raise OcgcoreTimeoutError(f"ocgcore process exceeded max_steps={max_steps}")

    def _drain_logs(self) -> tuple[CoreLog, ...]:
        logs = tuple(self._pending_logs)
        self._pending_logs.clear()
        return logs

    def respond(self, response: bytes) -> None:
        self._require(DuelState.AWAITING_RESPONSE)
        if len(response) > MAX_RESPONSE_BYTES:
            raise OcgcoreBufferError(
                f"response length {len(response)} exceeds {MAX_RESPONSE_BYTES} bytes"
            )
        buffer = ctypes.create_string_buffer(response) if response else None
        pointer = ctypes.cast(buffer, ctypes.c_void_p) if buffer is not None else None
        self.library.native.OCG_DuelSetResponse(self._duel, pointer, len(response))
        self._raise_callback_error()
        self._transition(DuelState.PROCESSING)

    def respond_action(self, request: Any, action: Any, encoder: Any | None = None) -> Any:
        if encoder is None:
            from ygo_effect_dsl.engine.bridge.ocgcore.protocol import ActionResponseEncoder

            encoder = ActionResponseEncoder(self.library.api_version)
        encoded = encoder.encode(request, action)
        self.respond(encoded.data)
        return encoded

    def capture_snapshot(
        self,
        *,
        pending_request: Any | None,
        environment: dict[str, Any],
        locations: Any = None,
        display_metadata: dict[str, Any] | None = None,
        information_mode: str = "complete_information",
        sampling_reference: Mapping[str, Any] | None = None,
    ) -> Any:
        from ygo_effect_dsl.engine.bridge.ocgcore.state import (
            LOCATION_ORDER,
            OcgcoreStateAdapter,
        )

        return OcgcoreStateAdapter().capture(
            self,
            pending_request=pending_request,
            environment=environment,
            locations=LOCATION_ORDER if locations is None else locations,
            display_metadata=display_metadata,
            information_mode=information_mode,
            sampling_reference=sampling_reference,
        )

    def _query_buffer(self, function_name: str, query: Query | None = None) -> bytes:
        self._assert_usable_for_query()
        length = ctypes.c_uint32()
        function = getattr(self.library.native, function_name)
        if query is None:
            pointer = function(self._duel, ctypes.byref(length))
        else:
            native = query.to_native()
            pointer = function(self._duel, ctypes.byref(length), ctypes.byref(native))
        self._raise_callback_error()
        return self._copy_buffer(pointer, length.value, function_name)

    def query(self, query: Query) -> bytes:
        return self._query_buffer("OCG_DuelQuery", query)

    def query_location(self, query: Query) -> bytes:
        return self._query_buffer("OCG_DuelQueryLocation", query)

    def query_field(self) -> bytes:
        return self._query_buffer("OCG_DuelQueryField")

    def query_count(self, team: int, location: int) -> int:
        self._assert_usable_for_query()
        return int(self.library.native.OCG_DuelQueryCount(self._duel, team, location))

    def _assert_usable_for_query(self) -> None:
        self._assert_owner()
        if self.state in {DuelState.FAILED, DuelState.DESTROYED}:
            raise OcgcoreStateError(f"query is invalid in state {self.state.value}")

    def destroy(self) -> None:
        if self.state == DuelState.DESTROYED:
            return
        self._assert_owner()
        if self._duel.value and not self._destroyed_native:
            self.library.native.OCG_DestroyDuel(self._duel)
            self._destroyed_native = True
        self._duel = ctypes.c_void_p()
        self._setcode_allocations.clear()
        self._pending_logs.clear()
        if self._registered_with_library:
            self.library._session_closed()
            self._registered_with_library = False
        self._transition(DuelState.DESTROYED)
        self._release_python_owners()

    def _release_python_owners(self) -> None:
        self._options = None
        self._data_reader = None
        self._script_reader = None
        self._log_handler = None
        self._data_reader_done = None

    def __enter__(self) -> "OcgcoreDuel":
        return self

    def __exit__(self, _type: object, _value: object, _traceback: object) -> None:
        self.destroy()
