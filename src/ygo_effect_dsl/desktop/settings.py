from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from ygo_effect_dsl.engine.canonical import to_canonical_data
from ygo_effect_dsl.io_atomic import atomic_write_text


DESKTOP_SETTINGS_SCHEMA_VERSION = "desktop-settings-v1"
DESKTOP_SETTINGS_RESPONSE_SCHEMA_VERSION = "desktop-settings-response-v1"

_TOP_LEVEL_FIELDS = {
    "display",
    "external_asset_root",
    "privacy",
    "recovery",
    "schema_version",
    "storage",
    "updates",
}
_DISPLAY_FIELDS = {"density", "reduced_motion", "theme"}
_PRIVACY_FIELDS = {
    "include_local_paths_in_support_bundle",
    "redact_card_names",
    "redact_user_text",
}
_RECOVERY_FIELDS = {"safe_mode"}
_STORAGE_FIELDS = {"cache_limit_mb", "retention_days"}
_UPDATES_FIELDS = {"automatic_downloads", "channel"}


def default_desktop_settings(
    *, external_asset_root: str | Path | None = None
) -> dict[str, Any]:
    return {
        "display": {
            "density": "compact",
            "reduced_motion": False,
            "theme": "system",
        },
        "external_asset_root": _optional_path_text(external_asset_root),
        "privacy": {
            "include_local_paths_in_support_bundle": False,
            "redact_card_names": True,
            "redact_user_text": True,
        },
        "recovery": {"safe_mode": False},
        "schema_version": DESKTOP_SETTINGS_SCHEMA_VERSION,
        "storage": {
            "cache_limit_mb": 512,
            "retention_days": 30,
        },
        "updates": {
            "automatic_downloads": False,
            "channel": "manual",
        },
    }


def validate_desktop_settings(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("デスクトップ設定はJSONオブジェクトである必要があります")
    document = to_canonical_data(dict(value))
    if not isinstance(document, dict):
        raise ValueError("デスクトップ設定はJSONオブジェクトである必要があります")
    if set(document) != _TOP_LEVEL_FIELDS:
        raise ValueError("デスクトップ設定の項目が不正です")
    if document.get("schema_version") != DESKTOP_SETTINGS_SCHEMA_VERSION:
        raise ValueError("デスクトップ設定のschema_versionは明示的な移行が必要です")
    external_root = document["external_asset_root"]
    if external_root is not None and (
        not isinstance(external_root, str) or not external_root.strip()
    ):
        raise ValueError("外部資産rootは空でない文字列またはnullである必要があります")
    _validate_display(document["display"])
    _validate_privacy(document["privacy"])
    _validate_recovery(document["recovery"])
    _validate_storage(document["storage"])
    _validate_updates(document["updates"])
    return document


def _validate_display(value: Any) -> None:
    if not isinstance(value, Mapping) or set(value) != _DISPLAY_FIELDS:
        raise ValueError("表示設定の項目が不正です")
    if value["density"] not in {"compact", "comfortable"}:
        raise ValueError("表示密度はcompactまたはcomfortableである必要があります")
    if value["theme"] not in {"system", "light", "dark"}:
        raise ValueError("表示テーマはsystem/light/darkのいずれかです")
    if not isinstance(value["reduced_motion"], bool):
        raise ValueError("reduced_motionは真偽値である必要があります")


def _validate_privacy(value: Any) -> None:
    if not isinstance(value, Mapping) or set(value) != _PRIVACY_FIELDS:
        raise ValueError("プライバシー設定の項目が不正です")
    for key in _PRIVACY_FIELDS:
        if not isinstance(value[key], bool):
            raise ValueError("プライバシー設定は真偽値である必要があります")


def _validate_recovery(value: Any) -> None:
    if not isinstance(value, Mapping) or set(value) != _RECOVERY_FIELDS:
        raise ValueError("リカバリ設定の項目が不正です")
    if not isinstance(value["safe_mode"], bool):
        raise ValueError("safe_modeは真偽値である必要があります")


def _validate_storage(value: Any) -> None:
    if not isinstance(value, Mapping) or set(value) != _STORAGE_FIELDS:
        raise ValueError("保存設定の項目が不正です")
    if (
        not isinstance(value["retention_days"], int)
        or not 1 <= value["retention_days"] <= 365
    ):
        raise ValueError("保持日数は1から365の整数である必要があります")
    if (
        not isinstance(value["cache_limit_mb"], int)
        or not 64 <= value["cache_limit_mb"] <= 65536
    ):
        raise ValueError("cache_limit_mbは64から65536の整数である必要があります")


def _validate_updates(value: Any) -> None:
    if not isinstance(value, Mapping) or set(value) != _UPDATES_FIELDS:
        raise ValueError("更新設定の項目が不正です")
    if value["channel"] != "manual":
        raise ValueError("v1.0.0ではmanual更新チャネルだけがサポートされます")
    if value["automatic_downloads"] is not False:
        raise ValueError("v1.0.0設定は自動ダウンロードを許可しません")


def _optional_path_text(value: str | Path | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


class DesktopSettingsStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def read(self) -> dict[str, Any]:
        if not self.path.exists():
            return default_desktop_settings()
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError("デスクトップ設定ファイルを読み込めません") from exc
        return validate_desktop_settings(value)

    def write(self, settings: Mapping[str, Any]) -> dict[str, Any]:
        document = validate_desktop_settings(settings)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_text(
            self.path,
            json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        )
        return document

    def reset(
        self,
        *,
        external_asset_root: str | Path | None = None,
        safe_mode: bool = False,
    ) -> dict[str, Any]:
        document = default_desktop_settings(external_asset_root=external_asset_root)
        document["recovery"]["safe_mode"] = safe_mode
        return self.write(document)


__all__ = [
    "DESKTOP_SETTINGS_RESPONSE_SCHEMA_VERSION",
    "DESKTOP_SETTINGS_SCHEMA_VERSION",
    "DesktopSettingsStore",
    "default_desktop_settings",
    "validate_desktop_settings",
]
