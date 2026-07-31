from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import platform
from pathlib import Path
import re
import sys
from typing import Any, Mapping, Sequence

from ygo_effect_dsl import __version__
from ygo_effect_dsl.desktop.bridge import DESKTOP_BRIDGE_CONTRACT_VERSION
from ygo_effect_dsl.engine.canonical import stable_digest, to_canonical_data
from ygo_effect_dsl.engine.information import (
    InformationCanary,
    InformationCanaryRegistry,
    assert_information_artifact_safe,
    audit_information_artifact,
)
from ygo_effect_dsl.external.asset_setup import describe_external_asset_setup
from ygo_effect_dsl.io_atomic import atomic_write_text
from ygo_effect_dsl.project_identity import PROJECT_IDENTITY
from ygo_effect_dsl.storage.policy import storage_policy_document


REDACTED_SUPPORT_BUNDLE_SCHEMA_VERSION = "redacted-support-bundle-v1"
REDACTED_SUPPORT_BUNDLE_MANIFEST_SCHEMA_VERSION = (
    "redacted-support-bundle-manifest-v1"
)
REDACTED_SUPPORT_DIAGNOSTICS_SCHEMA_VERSION = "redacted-support-diagnostics-v1"
REDACTED_SUPPORT_README_SCHEMA_VERSION = "redacted-support-readme-v1"
DEFAULT_SUPPORT_BUNDLE_SIZE_LIMIT_BYTES = 256 * 1024
DEFAULT_PRIVATE_CANARY = "private-support-bundle-canary-v1"

_ABSOLUTE_WINDOWS_PATH = re.compile(r"^[A-Za-z]:[\\/]")
_ABSOLUTE_POSIX_PATH = re.compile(r"^/(Users|home|mnt|var|tmp|private|Volumes)/")
_SENSITIVE_KEY_FRAGMENTS = (
    "card",
    "crash_dump",
    "deck",
    "hand",
    "password",
    "payload",
    "private",
    "raw",
    "secret",
    "seed",
    "stderr",
    "stdout",
    "token",
)
_PATH_KEY_FRAGMENTS = ("path", "root", "directory", "file")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _looks_like_path(value: str) -> bool:
    return bool(_ABSOLUTE_WINDOWS_PATH.match(value) or _ABSOLUTE_POSIX_PATH.match(value))


def _redact_scalar(value: Any, *, canaries: Sequence[str]) -> Any:
    if not isinstance(value, str):
        return value
    redacted = value
    for canary in canaries:
        if canary:
            redacted = redacted.replace(canary, "<private-canary>")
    if _looks_like_path(redacted):
        return "<redacted-path>"
    return redacted


def _redacted_key(kind: str, source_key: str) -> str:
    digest = stable_digest(source_key, prefix="field_")[-12:]
    return f"{kind}_{digest}"


def _redact(value: Any, *, canaries: Sequence[str]) -> Any:
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for key, child in value.items():
            safe_key = str(_redact_scalar(str(key), canaries=canaries))
            lower = safe_key.lower()
            if any(fragment in lower for fragment in _SENSITIVE_KEY_FRAGMENTS):
                result[_redacted_key("redacted_field", safe_key)] = "<redacted>"
            elif any(fragment in lower for fragment in _PATH_KEY_FRAGMENTS):
                result[_redacted_key("redacted_path", safe_key)] = "<redacted-path>"
            else:
                result[safe_key] = _redact(child, canaries=canaries)
        return result
    if isinstance(value, list):
        return [_redact(item, canaries=canaries) for item in value]
    if isinstance(value, tuple):
        return [_redact(item, canaries=canaries) for item in value]
    return _redact_scalar(value, canaries=canaries)


def _load_recent_error(path: str | Path | None, *, canaries: Sequence[str]) -> Any:
    if path is None:
        return []
    source = Path(path)
    try:
        raw = json.loads(source.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [
            {
                "diagnostic_code": "recent_error_json_invalid",
                "message": str(exc),
                "source": "<redacted-path>",
            }
        ]
    return _redact(raw, canaries=canaries)


def build_redacted_support_diagnostics(
    *,
    external_root: str | Path | None = None,
    recent_error_json: str | Path | None = None,
    private_canaries: Sequence[str] = (),
) -> dict[str, Any]:
    canaries = tuple(dict.fromkeys((DEFAULT_PRIVATE_CANARY, *private_canaries)))
    try:
        external_assets = describe_external_asset_setup(external_root=external_root)
    except OSError as exc:
        external_assets = {
            "diagnostic_code": "external_asset_status_unavailable",
            "error_type": type(exc).__name__,
            "ready": False,
            "schema_version": "external-asset-setup-status-v1",
        }
    diagnostics = {
        "automatic_upload": False,
        "bridge": {
            "desktop_bridge_contract": DESKTOP_BRIDGE_CONTRACT_VERSION,
        },
        "diagnostic_code": "support_bundle_generated",
        "external_assets": _redact(external_assets, canaries=canaries),
        "job_context": {
            "recent_errors": _load_recent_error(
                recent_error_json,
                canaries=canaries,
            ),
            "schema_version": "support-bundle-job-context-v1",
        },
        "package": {
            "package_version": __version__,
            "project": PROJECT_IDENTITY.to_dict(),
            "python": platform.python_version(),
            "runtime": platform.system() or "unknown",
        },
        "redaction": {
            "canary_count": len(canaries),
            "hidden_payload_retained": False,
            "policy": "information-access-audit-v2",
            "schema_version": "support-bundle-redaction-policy-v1",
        },
        "schema_version": REDACTED_SUPPORT_DIAGNOSTICS_SCHEMA_VERSION,
        "storage_policy": storage_policy_document(),
        "support_bundle": {
            "retention_days": 30,
            "schema_version": REDACTED_SUPPORT_BUNDLE_SCHEMA_VERSION,
            "size_limit_bytes": DEFAULT_SUPPORT_BUNDLE_SIZE_LIMIT_BYTES,
        },
    }
    return to_canonical_data(diagnostics)


def _registry(private_canaries: Sequence[str]) -> InformationCanaryRegistry:
    canaries = tuple(dict.fromkeys((DEFAULT_PRIVATE_CANARY, *private_canaries)))
    return InformationCanaryRegistry(
        artifact_kind="redacted_support_bundle",
        viewer=0,
        canaries=tuple(
            InformationCanary(
                canary_id=stable_digest(
                    {
                        "artifact_kind": "redacted_support_bundle",
                        "index": index,
                        "value": value,
                    },
                    prefix="canary_",
                ),
                classification="support_bundle_private_input",
                matcher_kind="substring",
                source_path=f"private_canaries[{index}]",
                value=value,
            )
            for index, value in enumerate(canaries)
            if value
        ),
    )


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    atomic_write_text(
        path,
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )


def write_redacted_support_bundle(
    *,
    output_dir: str | Path,
    external_root: str | Path | None = None,
    recent_error_json: str | Path | None = None,
    private_canaries: Sequence[str] = (),
    size_limit_bytes: int = DEFAULT_SUPPORT_BUNDLE_SIZE_LIMIT_BYTES,
) -> dict[str, Any]:
    if size_limit_bytes < 4096:
        raise ValueError("support bundle size limit must be at least 4096 bytes")
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    diagnostics = build_redacted_support_diagnostics(
        external_root=external_root,
        recent_error_json=recent_error_json,
        private_canaries=private_canaries,
    )
    registry = _registry(private_canaries)
    redaction_report = audit_information_artifact(
        diagnostics,
        artifact_kind="redacted_support_bundle",
        registry=registry,
    )
    assert_information_artifact_safe(redaction_report)
    readme = {
        "automatic_upload": False,
        "contents": [
            "Share this bundle only after reviewing it.",
            "It excludes full deck lists, private hands, raw payloads, tokens, absolute personal paths, and crash dumps by default.",
            "Delete local copies after the support request closes unless an incident extension is documented.",
        ],
        "retention_days": 30,
        "schema_version": REDACTED_SUPPORT_README_SCHEMA_VERSION,
    }
    files = {
        "diagnostics.json": diagnostics,
        "redaction-report.json": redaction_report,
        "README.json": readme,
    }
    for name, value in files.items():
        _write_json(destination / name, value)
    file_records = []
    total_bytes = 0
    for name in sorted(files):
        path = destination / name
        size = path.stat().st_size
        total_bytes += size
        file_records.append(
            {
                "name": name,
                "schema_version": files[name]["schema_version"],
                "sha256": _sha256(path),
                "size_bytes": size,
            }
        )
    if total_bytes > size_limit_bytes:
        raise ValueError(
            f"support bundle size {total_bytes} exceeds limit {size_limit_bytes}"
        )
    manifest_identity = {
        "automatic_upload": False,
        "bundle_schema_version": REDACTED_SUPPORT_BUNDLE_SCHEMA_VERSION,
        "files": file_records,
        "redaction_audit_id": redaction_report["audit_id"],
        "retention_policy": {
            "delete_after_support_closure": True,
            "default_days": 30,
            "raw_crash_dumps_included": False,
            "raw_payloads_included": False,
        },
        "schema_version": REDACTED_SUPPORT_BUNDLE_MANIFEST_SCHEMA_VERSION,
        "size_limit_bytes": size_limit_bytes,
        "total_size_bytes": total_bytes,
    }
    manifest = {
        **manifest_identity,
        "bundle_id": stable_digest(manifest_identity, prefix="supportbundle_"),
        "created_at": _now(),
    }
    _write_json(destination / "manifest.json", manifest)
    return manifest
