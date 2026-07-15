"""Packaged, backend-independent desktop frontend artifact."""

from __future__ import annotations

import importlib.resources
import json
from pathlib import Path
from typing import Any

DESKTOP_WORKFLOW_CONTRACT_VERSION = "desktop-workflow-v1"
DESKTOP_BRIDGE_CONTRACT_VERSION = "desktop-bridge-v1"


def desktop_frontend_root() -> Path:
    return (Path(__file__).resolve().parent / "static").resolve()


def desktop_frontend_entrypoint() -> Path:
    entrypoint = desktop_frontend_root() / "index.html"
    if not entrypoint.is_file():
        raise FileNotFoundError("packaged desktop frontend entrypoint is missing")
    return entrypoint


def desktop_workflow_contract_document() -> dict[str, Any]:
    resource = importlib.resources.files("ygo_effect_dsl.resources").joinpath(
        "desktop-workflow-contract-v1.json"
    )
    document = json.loads(resource.read_text(encoding="utf-8"))
    if document.get("schema_version") != DESKTOP_WORKFLOW_CONTRACT_VERSION:
        raise ValueError("desktop workflow contract resource version mismatch")
    return document


def desktop_bridge_contract_document() -> dict[str, Any]:
    resource = importlib.resources.files("ygo_effect_dsl.resources").joinpath(
        "desktop-bridge-v1.json"
    )
    document = json.loads(resource.read_text(encoding="utf-8"))
    if document.get("schema_version") != DESKTOP_BRIDGE_CONTRACT_VERSION:
        raise ValueError("desktop bridge contract resource version mismatch")
    return document


__all__ = [
    "DESKTOP_WORKFLOW_CONTRACT_VERSION",
    "DESKTOP_BRIDGE_CONTRACT_VERSION",
    "desktop_bridge_contract_document",
    "desktop_frontend_entrypoint",
    "desktop_frontend_root",
    "desktop_workflow_contract_document",
]
