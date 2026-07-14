from __future__ import annotations

from ygo_effect_dsl.engine.bridge.errors import BridgeError


class OcgcoreBridgeError(BridgeError):
    """Base error for the native ocgcore boundary."""

    category = "core_error"


class OcgcoreArchitectureError(OcgcoreBridgeError):
    category = "version_mismatch"


class OcgcoreVersionMismatchError(OcgcoreBridgeError):
    category = "version_mismatch"


class OcgcoreStateError(OcgcoreBridgeError):
    category = "invalid_state"


class OcgcoreCreateError(OcgcoreBridgeError):
    category = "core_error"


class OcgcoreCallbackError(OcgcoreBridgeError):
    category = "core_error"

    def __init__(self, callback: str, message: str, *, cause_category: str = "core_error") -> None:
        super().__init__(f"{callback}: {message}")
        self.callback = callback
        self.message = message
        self.category = cause_category


class OcgcoreTimeoutError(OcgcoreBridgeError):
    category = "timeout"


class OcgcoreBufferError(OcgcoreBridgeError):
    category = "invalid_message"


class OcgcoreSnapshotError(OcgcoreBridgeError):
    category = "core_error"


class OcgcoreAssetError(OcgcoreBridgeError):
    category = "asset_error"


class OcgcoreLuaError(OcgcoreBridgeError):
    category = "lua_error"


class OcgcoreWorkerError(OcgcoreBridgeError):
    category = "worker_error"


class OcgcoreWorkerTimeoutError(OcgcoreWorkerError):
    category = "worker_timeout"

    def __init__(self, timeout_seconds: float) -> None:
        self.timeout_seconds = timeout_seconds
        super().__init__(
            f"ocgcore worker exceeded deadline {timeout_seconds:.3f}s"
        )


class OcgcoreWorkerCrashError(OcgcoreWorkerError):
    category = "worker_crash"

    def __init__(self, returncode: int, diagnostic: str) -> None:
        self.returncode = returncode
        self.diagnostic = diagnostic
        super().__init__(
            f"ocgcore worker exited with code {returncode}: "
            f"{diagnostic or 'no diagnostic output'}"
        )


class OcgcoreWorkerProtocolError(OcgcoreWorkerError):
    category = "worker_protocol"


class MissingCardDataError(OcgcoreAssetError):
    def __init__(self, code: int) -> None:
        super().__init__(f"missing card data for code {code}")
        self.code = code


class MissingScriptError(OcgcoreAssetError):
    def __init__(self, name: str) -> None:
        super().__init__(f"missing Lua script {name!r}")
        self.name = name
