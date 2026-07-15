from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass
import json
import math
import re
from typing import Any

from ygo_effect_dsl.engine.canonical import to_canonical_data

DESKTOP_BRIDGE_CONTRACT_VERSION = "desktop-bridge-v1"
DESKTOP_BRIDGE_RESPONSE_VERSION = "desktop-bridge-response-v1"
DEFAULT_MAX_REQUEST_BYTES = 256 * 1024
DEFAULT_MAX_RESPONSE_BYTES = 4 * 1024 * 1024

_REQUEST_FIELDS = {"method", "payload", "request_id", "version"}
_REQUEST_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
_PATH_KEYS = {"directory", "file", "file_path", "path", "root", "uri"}


@dataclass(frozen=True)
class DesktopBridgeDiagnostic:
    code: str
    message: str
    path: str = "$"
    severity: str = "error"

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


class DesktopServiceError(ValueError):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        path: str = "$.payload",
        details: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.path = path
        self.details = to_canonical_data(dict(details or {}))


DesktopHandler = Callable[[Mapping[str, Any]], Mapping[str, Any]]


def _json_bytes(value: Any) -> bytes:
    def reject_non_finite(item: Any, path: str) -> None:
        if isinstance(item, float) and not math.isfinite(item):
            raise DesktopServiceError(
                "non_finite_number",
                "bridge payload numbers must be finite",
                path=path,
            )
        if isinstance(item, Mapping):
            for key, child in item.items():
                if not isinstance(key, str):
                    raise DesktopServiceError(
                        "invalid_json_key",
                        "bridge payload object keys must be strings",
                        path=path,
                    )
                reject_non_finite(child, f"{path}.{key}")
        elif isinstance(item, (list, tuple)):
            for index, child in enumerate(item):
                reject_non_finite(child, f"{path}[{index}]")

    reject_non_finite(value, "$")
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise DesktopServiceError(
            "invalid_json_value",
            "bridge payload must contain JSON values only",
        ) from exc


def _reject_renderer_paths(value: Any, path: str = "$.payload") -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            normalized = key.casefold()
            if normalized in _PATH_KEYS or normalized.endswith("_path"):
                raise DesktopServiceError(
                    "renderer_path_forbidden",
                    "renderer requests must use catalog IDs or native file selection",
                    path=f"{path}.{key}",
                )
            _reject_renderer_paths(child, f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            _reject_renderer_paths(child, f"{path}[{index}]")


class DesktopBridge:
    """The only Python object exposed to the renderer.

    pywebview can reflect every public method on ``js_api``. Keeping this object to
    one public method prevents accidental service-object expansion from becoming a
    renderer capability.
    """

    def __init__(
        self,
        handlers: Mapping[str, DesktopHandler],
        *,
        max_request_bytes: int = DEFAULT_MAX_REQUEST_BYTES,
        max_response_bytes: int = DEFAULT_MAX_RESPONSE_BYTES,
    ) -> None:
        if not handlers or any(not callable(handler) for handler in handlers.values()):
            raise ValueError("desktop bridge handlers must be a non-empty callable map")
        if max_request_bytes < 1 or max_response_bytes < 1:
            raise ValueError("desktop bridge byte limits must be positive")
        self._handlers = dict(handlers)
        self._max_request_bytes = max_request_bytes
        self._max_response_bytes = max_response_bytes

    @property
    def methods(self) -> tuple[str, ...]:
        return tuple(sorted(self._handlers))

    def _failure(
        self,
        request_id: str,
        method: str | None,
        diagnostic: DesktopBridgeDiagnostic,
        *,
        details: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        return {
            "details": to_canonical_data(dict(details or {})),
            "diagnostics": [diagnostic.to_dict()],
            "method": method,
            "ok": False,
            "request_id": request_id,
            "result": None,
            "schema_version": DESKTOP_BRIDGE_RESPONSE_VERSION,
        }

    def invoke(self, request: Any) -> dict[str, Any]:
        request_id = "invalid-request"
        method: str | None = None
        try:
            if not isinstance(request, Mapping):
                raise DesktopServiceError(
                    "invalid_request",
                    "bridge request must be an object",
                )
            if set(request) != _REQUEST_FIELDS:
                raise DesktopServiceError(
                    "invalid_request_fields",
                    f"bridge request fields must be exactly {sorted(_REQUEST_FIELDS)}",
                )
            raw_request_id = request.get("request_id")
            if not isinstance(raw_request_id, str) or not _REQUEST_ID.fullmatch(
                raw_request_id
            ):
                raise DesktopServiceError(
                    "invalid_request_id",
                    "request_id must be a 1..128 character bridge token",
                    path="$.request_id",
                )
            request_id = raw_request_id
            if request.get("version") != DESKTOP_BRIDGE_CONTRACT_VERSION:
                raise DesktopServiceError(
                    "bridge_version_mismatch",
                    f"bridge version must be {DESKTOP_BRIDGE_CONTRACT_VERSION}",
                    path="$.version",
                )
            raw_method = request.get("method")
            if not isinstance(raw_method, str):
                raise DesktopServiceError(
                    "invalid_method",
                    "bridge method must be a string",
                    path="$.method",
                )
            method = raw_method
            handler = self._handlers.get(method)
            if handler is None:
                raise DesktopServiceError(
                    "unsupported_method",
                    "bridge method is not allowlisted",
                    path="$.method",
                )
            payload = request.get("payload")
            if not isinstance(payload, Mapping):
                raise DesktopServiceError(
                    "invalid_payload",
                    "bridge payload must be an object",
                    path="$.payload",
                )
            if len(_json_bytes(request)) > self._max_request_bytes:
                raise DesktopServiceError(
                    "request_too_large",
                    f"bridge request exceeds {self._max_request_bytes} bytes",
                )
            _reject_renderer_paths(payload)
            result = handler(to_canonical_data(dict(payload)))
            if not isinstance(result, Mapping):
                raise RuntimeError("desktop service handler returned a non-object")
            response = {
                "details": {},
                "diagnostics": [],
                "method": method,
                "ok": True,
                "request_id": request_id,
                "result": to_canonical_data(dict(result)),
                "schema_version": DESKTOP_BRIDGE_RESPONSE_VERSION,
            }
            if len(_json_bytes(response)) > self._max_response_bytes:
                raise DesktopServiceError(
                    "response_too_large",
                    f"bridge response exceeds {self._max_response_bytes} bytes",
                )
            return response
        except DesktopServiceError as exc:
            return self._failure(
                request_id,
                method,
                DesktopBridgeDiagnostic(exc.code, str(exc), exc.path),
                details=exc.details,
            )
        except (TypeError, ValueError) as exc:
            return self._failure(
                request_id,
                method,
                DesktopBridgeDiagnostic(
                    "invalid_service_request",
                    str(exc),
                    "$.payload",
                ),
            )
        except Exception:
            return self._failure(
                request_id,
                method,
                DesktopBridgeDiagnostic(
                    "service_failure",
                    "desktop application service failed without starting a worker",
                    "$.payload",
                ),
            )


__all__ = [
    "DEFAULT_MAX_REQUEST_BYTES",
    "DEFAULT_MAX_RESPONSE_BYTES",
    "DESKTOP_BRIDGE_CONTRACT_VERSION",
    "DESKTOP_BRIDGE_RESPONSE_VERSION",
    "DesktopBridge",
    "DesktopBridgeDiagnostic",
    "DesktopHandler",
    "DesktopServiceError",
]
