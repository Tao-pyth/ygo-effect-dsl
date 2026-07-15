from __future__ import annotations

from ygo_effect_dsl.external.platform_contract import (
    OCGCORE_PLATFORM_CONTRACT_SCHEMA_VERSION,
    evaluate_ocgcore_platform,
)


def test_windows_x64_python_310_is_supported() -> None:
    result = evaluate_ocgcore_platform(
        system="Windows", machine="AMD64", python_version=(3, 10, 0)
    )
    assert result["schema_version"] == OCGCORE_PLATFORM_CONTRACT_SCHEMA_VERSION
    assert result["supported"] is True
    assert result["diagnostics"] == []


def test_unsupported_platform_has_stable_fail_closed_diagnostics() -> None:
    result = evaluate_ocgcore_platform(
        system="Linux", machine="aarch64", python_version=(3, 9, 18)
    )
    assert result["supported"] is False
    assert {item["code"] for item in result["diagnostics"]} == {
        "unsupported_operating_system",
        "unsupported_architecture",
        "unsupported_python_version",
    }
