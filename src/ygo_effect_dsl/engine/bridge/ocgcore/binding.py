from __future__ import annotations

import ctypes
import os
import platform
from pathlib import Path
from typing import Any

from ygo_effect_dsl.engine.bridge.ocgcore.errors import (
    OcgcoreArchitectureError,
    OcgcoreStateError,
    OcgcoreVersionMismatchError,
)
from ygo_effect_dsl.engine.bridge.ocgcore.types import (
    API_VERSION,
    OCGDuelOptions,
    OCGNewCardInfo,
    OCGQueryInfo,
    LibraryState,
    validate_native_layout,
)


class OcgcoreLibrary:
    """Validated C API 11.0 library handle, intended to live inside one worker."""

    def __init__(
        self,
        runtime: str | Path | None = None,
        *,
        expected_api: tuple[int, int] = API_VERSION,
        native: Any | None = None,
        enforce_architecture: bool = True,
    ) -> None:
        self.state = LibraryState.DISCOVERED
        self.runtime = Path(runtime).resolve() if runtime is not None else None
        self.expected_api = expected_api
        self._active_sessions = 0
        self._owns_native = native is None
        validate_native_layout()
        if enforce_architecture:
            self._validate_architecture()
        if native is None:
            if self.runtime is None or not self.runtime.is_file():
                raise OcgcoreArchitectureError(f"ocgcore runtime is missing: {self.runtime}")
            native = ctypes.CDLL(str(self.runtime))
        self._native = native
        self._configure_functions()
        self.api_version = self._get_version()
        if self.api_version != expected_api:
            self._unload()
            raise OcgcoreVersionMismatchError(
                f"expected ocgcore API {expected_api[0]}.{expected_api[1]}, "
                f"got {self.api_version[0]}.{self.api_version[1]}"
            )
        self.state = LibraryState.VERSION_CHECKED

    @staticmethod
    def _validate_architecture() -> None:
        if os.name != "nt" or platform.machine().upper() not in {"AMD64", "X86_64"}:
            raise OcgcoreArchitectureError("the frozen native contract supports Windows x64 only")

    def _configure_functions(self) -> None:
        signatures = {
            "OCG_GetVersion": (
                [ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int)],
                None,
            ),
            "OCG_CreateDuel": (
                [ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(OCGDuelOptions)],
                ctypes.c_int,
            ),
            "OCG_DestroyDuel": ([ctypes.c_void_p], None),
            "OCG_DuelNewCard": (
                [ctypes.c_void_p, ctypes.POINTER(OCGNewCardInfo)],
                None,
            ),
            "OCG_StartDuel": ([ctypes.c_void_p], None),
            "OCG_DuelProcess": ([ctypes.c_void_p], ctypes.c_int),
            "OCG_DuelGetMessage": (
                [ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint32)],
                ctypes.c_void_p,
            ),
            "OCG_DuelSetResponse": (
                [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint32],
                None,
            ),
            "OCG_LoadScript": (
                [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_uint32, ctypes.c_char_p],
                ctypes.c_int,
            ),
            "OCG_DuelQueryCount": (
                [ctypes.c_void_p, ctypes.c_uint8, ctypes.c_uint32],
                ctypes.c_uint32,
            ),
            "OCG_DuelQuery": (
                [ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint32), ctypes.POINTER(OCGQueryInfo)],
                ctypes.c_void_p,
            ),
            "OCG_DuelQueryLocation": (
                [ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint32), ctypes.POINTER(OCGQueryInfo)],
                ctypes.c_void_p,
            ),
            "OCG_DuelQueryField": (
                [ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint32)],
                ctypes.c_void_p,
            ),
        }
        for name, (argument_types, result_type) in signatures.items():
            try:
                function = getattr(self._native, name)
            except AttributeError as exc:
                raise OcgcoreArchitectureError(f"ocgcore export is missing: {name}") from exc
            function.argtypes = argument_types
            function.restype = result_type

    def _get_version(self) -> tuple[int, int]:
        major = ctypes.c_int()
        minor = ctypes.c_int()
        self._native.OCG_GetVersion(ctypes.byref(major), ctypes.byref(minor))
        return major.value, minor.value

    @property
    def native(self) -> Any:
        if self.state != LibraryState.VERSION_CHECKED:
            raise OcgcoreStateError(f"ocgcore library is not available in state {self.state.value}")
        return self._native

    def create_duel(self, *args: Any, **kwargs: Any) -> Any:
        from ygo_effect_dsl.engine.bridge.ocgcore.session import OcgcoreDuel

        if self.state != LibraryState.VERSION_CHECKED:
            raise OcgcoreStateError(f"cannot create duel in library state {self.state.value}")
        return OcgcoreDuel(self, *args, **kwargs)

    def _session_opened(self) -> None:
        self._active_sessions += 1

    def _session_closed(self) -> None:
        if self._active_sessions <= 0:
            raise OcgcoreStateError("ocgcore session accounting underflow")
        self._active_sessions -= 1

    def _unload(self) -> None:
        if self._native is None:
            return
        if self._owns_native and os.name == "nt":
            free_library = ctypes.WinDLL("kernel32", use_last_error=True).FreeLibrary
            free_library.argtypes = [ctypes.c_void_p]
            free_library.restype = ctypes.c_int
            handle = self._native._handle
            if free_library(handle) == 0:
                raise OcgcoreArchitectureError(f"FreeLibrary failed for {self.runtime}")
            self._native._handle = 0
        self._native = None

    def close(self) -> None:
        if self.state == LibraryState.CLOSED:
            return
        if self._active_sessions:
            raise OcgcoreStateError(
                f"cannot close ocgcore library with {self._active_sessions} active duel(s)"
            )
        self._unload()
        self.state = LibraryState.CLOSED

    def __enter__(self) -> "OcgcoreLibrary":
        return self

    def __exit__(self, _type: object, _value: object, _traceback: object) -> None:
        self.close()
