from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path


def package_source_root() -> Path:
    """Return the import root that contains the active ygo_effect_dsl package."""

    return Path(__file__).resolve().parents[1]


def current_checkout_environment(
    environment: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Build a child-process environment that imports the active checkout first."""

    result = dict(os.environ if environment is None else environment)
    source_root = str(package_source_root())
    existing = result.get("PYTHONPATH", "")
    entries = [entry for entry in existing.split(os.pathsep) if entry]
    normalized_root = os.path.normcase(os.path.abspath(source_root))
    entries = [
        entry
        for entry in entries
        if os.path.normcase(os.path.abspath(entry)) != normalized_root
    ]
    result["PYTHONPATH"] = os.pathsep.join([source_root, *entries])
    return result
