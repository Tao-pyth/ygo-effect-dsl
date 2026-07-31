from __future__ import annotations

from pathlib import Path
from typing import Any

from ygo_effect_dsl.external.ocgcore import (
    OcgcoreBootstrapError,
    OcgcoreLayout,
    load_ocgcore_asset_lock,
    load_ocgcore_lock,
    verify_ocgcore,
    verify_ocgcore_assets,
)


EXTERNAL_ASSET_SETUP_STATUS_SCHEMA_VERSION = "external-asset-setup-status-v1"


def external_asset_setup_guidance() -> dict[str, Any]:
    return {
        "commands": [
            "python -m ygo_effect_dsl ocgcore-doctor",
            "python -m ygo_effect_dsl ocgcore-bootstrap",
            "python -m ygo_effect_dsl ocgcore-assets-bootstrap",
            "python -m ygo_effect_dsl ocgcore-verify",
            "python -m ygo_effect_dsl ocgcore-assets-verify",
        ],
        "offline_verification_commands": [
            "python -m ygo_effect_dsl ocgcore-bootstrap --offline",
            "python -m ygo_effect_dsl ocgcore-assets-bootstrap --offline",
            "python -m ygo_effect_dsl ocgcore-verify",
            "python -m ygo_effect_dsl ocgcore-assets-verify",
        ],
        "policy": {
            "bundle_in_release_artifacts": False,
            "runtime_network_access": False,
            "scrape_card_data": False,
            "silent_download_at_runtime": False,
            "system_wide_install": False,
        },
        "summary": (
            "Use a user-owned external asset cache, verify pinned commits and "
            "SHA-256 hashes, and keep ocgcore/CardScripts/BabelCDB out of release artifacts."
        ),
    }


def describe_external_asset_setup(
    *,
    external_root: str | Path | None = None,
) -> dict[str, Any]:
    core_lock = load_ocgcore_lock()
    asset_lock = load_ocgcore_asset_lock()
    layout = OcgcoreLayout.create(core_lock, external_root)
    core_check = _check(
        "ocgcore_runtime_verified",
        lambda: verify_ocgcore(external_root=external_root),
    )
    asset_check = _check(
        "card_scripts_and_database_verified",
        lambda: verify_ocgcore_assets(external_root=external_root),
    )
    card_assets_ready = asset_check["passed"]
    runtime_ready = core_check["passed"]
    return {
        "asset_lock_id": asset_lock.lock_id,
        "checks": [core_check, asset_check],
        "core_lock_id": core_lock.lock_id,
        "dependent_features": {
            "card_names": "enabled" if card_assets_ready else "blocked",
            "deck_card_options": "enabled" if card_assets_ready else "blocked",
            "search_jobs": "enabled" if runtime_ready and card_assets_ready else "blocked",
        },
        "external_root": str(layout.external_root),
        "guidance": external_asset_setup_guidance(),
        "ready": runtime_ready and card_assets_ready,
        "schema_version": EXTERNAL_ASSET_SETUP_STATUS_SCHEMA_VERSION,
    }


def _check(check_id: str, verifier: Any) -> dict[str, Any]:
    try:
        result = verifier()
    except OcgcoreBootstrapError as exc:
        return {
            "diagnostic": exc.diagnostic(),
            "id": check_id,
            "passed": False,
            "reason": exc.code,
        }
    return {
        "id": check_id,
        "lock_id": result.get("lock_id") or result.get("asset_lock_id"),
        "passed": True,
        "reason": "verified",
    }


__all__ = [
    "EXTERNAL_ASSET_SETUP_STATUS_SCHEMA_VERSION",
    "describe_external_asset_setup",
    "external_asset_setup_guidance",
]
