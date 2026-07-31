from __future__ import annotations

from pathlib import Path

from ygo_effect_dsl.spikes.japanese_i18n_release_gate import (
    JAPANESE_I18N_RELEASE_GATE_SCHEMA_VERSION,
    build_japanese_i18n_release_gate,
    validate_japanese_i18n_release_gate,
)


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_japanese_i18n_release_gate_passes_current_sources() -> None:
    evidence = build_japanese_i18n_release_gate(REPO_ROOT)
    validated = validate_japanese_i18n_release_gate(evidence)

    assert validated["schema_version"] == JAPANESE_I18N_RELEASE_GATE_SCHEMA_VERSION
    assert validated["passed"] is True
    assert validated["rejection_reasons"] == []
    assert [check["check_id"] for check in validated["checks"]] == [
        "desktop-html-lang-ja",
        "desktop-static-japanese-copy",
        "dynamic-copy-catalogs",
        "fixture-copy-japanese",
        "analytics-copy-japanese",
        "desktop-static-no-mojibake",
        "release-docs-no-mojibake",
        "scope-non-goals-explicit",
        "changelog-release-entry",
    ]


def test_japanese_i18n_release_gate_rejects_mojibake_fixture_copy(
    tmp_path: Path,
) -> None:
    for source in (
        "src/ygo_effect_dsl/desktop/static/index.html",
        "src/ygo_effect_dsl/desktop/static/app.js",
        "src/ygo_effect_dsl/desktop/static/analytics.js",
        "README.md",
        "CHANGELOG.md",
        "docs/20_roadmap.md",
        "docs/release/00_versioning.md",
        "docs/spec/00_release_stage_index.md",
        "docs/spec/v0.8.0/00_scope.md",
    ):
        destination = tmp_path / source
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text((REPO_ROOT / source).read_text(encoding="utf-8"), encoding="utf-8")

    app_path = tmp_path / "src/ygo_effect_dsl/desktop/static/app.js"
    app_path.write_text(
        app_path.read_text(encoding="utf-8").replace("短経路 fixture", "短経路 ﾂｷ fixture"),
        encoding="utf-8",
    )

    evidence = build_japanese_i18n_release_gate(tmp_path)

    assert evidence["passed"] is False
    assert "desktop-static-no-mojibake" in evidence["rejection_reasons"]
