from __future__ import annotations

import platform
import sys
from collections.abc import Sequence
from typing import Any


OCGCORE_PLATFORM_CONTRACT_SCHEMA_VERSION = "ocgcore-platform-contract-v1"
SUPPORTED_MACHINES = frozenset({"AMD64", "X86_64"})
MINIMUM_PYTHON = (3, 10)


def evaluate_ocgcore_platform(
    *,
    system: str | None = None,
    machine: str | None = None,
    python_version: Sequence[int] | None = None,
) -> dict[str, Any]:
    observed_system = system or platform.system()
    observed_machine = (machine or platform.machine()).upper()
    observed_python = tuple(python_version or sys.version_info[:3])
    diagnostics: list[dict[str, str]] = []
    if observed_system != "Windows":
        diagnostics.append(
            {
                "code": "unsupported_operating_system",
                "message": "the frozen real-core contract supports Windows only",
            }
        )
    if observed_machine not in SUPPORTED_MACHINES:
        diagnostics.append(
            {
                "code": "unsupported_architecture",
                "message": "the frozen real-core contract supports x64 only",
            }
        )
    if observed_python[:2] < MINIMUM_PYTHON:
        diagnostics.append(
            {
                "code": "unsupported_python_version",
                "message": "the real-core worker requires Python 3.10 or newer",
            }
        )
    return {
        "classification": "supported" if not diagnostics else "unsupported",
        "diagnostics": diagnostics,
        "machine": observed_machine,
        "python": ".".join(str(value) for value in observed_python[:3]),
        "schema_version": OCGCORE_PLATFORM_CONTRACT_SCHEMA_VERSION,
        "system": observed_system,
        "supported": not diagnostics,
    }
