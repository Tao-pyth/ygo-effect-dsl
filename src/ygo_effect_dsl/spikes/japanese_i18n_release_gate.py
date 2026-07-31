from __future__ import annotations

import argparse
from collections.abc import Mapping
import json
from pathlib import Path
from typing import Any

from ygo_effect_dsl.engine.canonical import stable_digest, to_canonical_data
from ygo_effect_dsl.io_atomic import atomic_write_text


JAPANESE_I18N_RELEASE_GATE_SCHEMA_VERSION = "japanese-i18n-release-gate-v1"

DESKTOP_STATIC_ASSETS = (
    Path("src/ygo_effect_dsl/desktop/static/index.html"),
    Path("src/ygo_effect_dsl/desktop/static/app.js"),
    Path("src/ygo_effect_dsl/desktop/static/analytics.js"),
)
RELEASE_FACING_DOCS = (
    Path("README.md"),
    Path("CHANGELOG.md"),
    Path("docs/20_roadmap.md"),
    Path("docs/release/00_versioning.md"),
    Path("docs/spec/00_release_stage_index.md"),
    Path("docs/spec/v0.8.0/00_scope.md"),
    Path("docs/spec/v1.0.0/00_scope.md"),
    Path("docs/spec/v1.0.0/10_production_distribution_contracts.md"),
    Path("docs/spec/v1.0.0/20_work_breakdown_and_acceptance.md"),
    Path("docs/spec/v1.0.0/30_support_matrix.md"),
)


def mojibake_markers() -> tuple[str, ...]:
    return (
        chr(0xFF82) + chr(0xFF77),
        chr(0xFF83) + chr(0x30FB),
        chr(0x7E5D),
        chr(0x7E3A),
        chr(0x8709),
        chr(0x8B0C),
        chr(0x8B41),
        chr(0x8B5B),
        chr(0x8373),
        chr(0x87B3),
        chr(0x9089),
        chr(0x9B06),
        chr(0x9695),
        chr(0x8B80),
        chr(0x7ACA) + chr(0x30FB),
        chr(0x7B28) + chr(0x30FB),
    )


def _read(root: Path, relative: Path) -> str:
    return (root / relative).read_text(encoding="utf-8")


def _contains_halfwidth_katakana(text: str) -> bool:
    return any(0xFF61 <= ord(character) <= 0xFF9F for character in text)


def _mojibake_hits(root: Path, files: tuple[Path, ...]) -> list[dict[str, Any]]:
    markers = mojibake_markers()
    hits: list[dict[str, Any]] = []
    for relative in files:
        text = _read(root, relative)
        file_hits = [
            marker for marker in markers if marker and marker in text
        ]
        if _contains_halfwidth_katakana(text):
            file_hits.append("halfwidth-katakana-range")
        if file_hits:
            hits.append(
                {
                    "file": relative.as_posix(),
                    "markers": sorted(set(file_hits)),
                }
            )
    return hits


def _check(check_id: str, passed: bool, evidence: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "check_id": check_id,
        "evidence": dict(evidence),
        "passed": passed,
    }


def build_japanese_i18n_release_gate(repo_root: str | Path) -> dict[str, Any]:
    root = Path(repo_root)
    html = _read(root, DESKTOP_STATIC_ASSETS[0])
    app_js = _read(root, DESKTOP_STATIC_ASSETS[1])
    analytics_js = _read(root, DESKTOP_STATIC_ASSETS[2])
    scope = _read(root, Path("docs/spec/v0.8.0/00_scope.md"))
    changelog = _read(root, Path("CHANGELOG.md"))
    static_hits = _mojibake_hits(root, DESKTOP_STATIC_ASSETS)
    doc_hits = _mojibake_hits(root, RELEASE_FACING_DOCS)
    checks = [
        _check(
            "desktop-html-lang-ja",
            '<html lang="ja">' in html,
            {"file": DESKTOP_STATIC_ASSETS[0].as_posix(), "expected": "ja"},
        ),
        _check(
            "desktop-static-japanese-copy",
            all(
                text in html
                for text in (
                    "デッキ研究ワークスペース",
                    "デッキカタログ",
                    "探索を実行",
                    "実行観測",
                )
            ),
            {
                "required_copy": [
                    "デッキ研究ワークスペース",
                    "デッキカタログ",
                    "探索を実行",
                    "実行観測",
                ],
            },
        ),
        _check(
            "dynamic-copy-catalogs",
            all(
                text in app_js or text in analytics_js
                for text in (
                    "const UI_TEXT = Object.freeze({",
                    "const ANALYTICS_TEXT = Object.freeze({",
                    'const UI_LOCALE = "ja";',
                    'const ANALYTICS_LOCALE = "ja";',
                )
            ),
            {
                "app_catalog": "UI_TEXT",
                "analytics_catalog": "ANALYTICS_TEXT",
                "locale": "ja",
            },
        ),
        _check(
            "fixture-copy-japanese",
            all(
                text in app_js
                for text in (
                    "短経路 fixture",
                    "長チェーン fixture",
                    "墓地/除外 fixture",
                    "復旧プローブ",
                    "Replay検証をキューへ追加しました。",
                )
            ),
            {
                "fixture_names": [
                    "短経路 fixture",
                    "長チェーン fixture",
                    "墓地/除外 fixture",
                    "復旧プローブ",
                ],
            },
        ),
        _check(
            "analytics-copy-japanese",
            all(
                text in analytics_js
                for text in (
                    "実行",
                    "デッキ",
                    "評価プロファイル",
                    "成否",
                    "分析ページ準備完了",
                    "出力をキューへ投入中",
                )
            ),
            {
                "catalog": "ANALYTICS_TEXT",
                "virtual_table_labels": True,
            },
        ),
        _check(
            "desktop-static-no-mojibake",
            not static_hits,
            {"files": [path.as_posix() for path in DESKTOP_STATIC_ASSETS], "hits": static_hits},
        ),
        _check(
            "release-docs-no-mojibake",
            not doc_hits,
            {"files": [path.as_posix() for path in RELEASE_FACING_DOCS], "hits": doc_hits},
        ),
        _check(
            "scope-non-goals-explicit",
            all(
                text in scope
                for text in (
                    "多言語切替 UI",
                    "英語 locale",
                    "Card text",
                    "Production distribution",
                )
            ),
            {"file": "docs/spec/v0.8.0/00_scope.md"},
        ),
        _check(
            "changelog-release-entry",
            "## 0.8.0 - 2026-07-31" in changelog,
            {"file": "CHANGELOG.md"},
        ),
    ]
    rejection_reasons = [
        check["check_id"] for check in checks if check["passed"] is not True
    ]
    identity = to_canonical_data(
        {
            "checks": checks,
            "passed": not rejection_reasons,
            "rejection_reasons": rejection_reasons,
            "schema_version": JAPANESE_I18N_RELEASE_GATE_SCHEMA_VERSION,
        }
    )
    if not isinstance(identity, dict):
        raise ValueError("Japanese i18n release gate identity is invalid")
    return {
        **identity,
        "evidence_id": stable_digest(identity, prefix="japanesei18ngate_"),
    }


def validate_japanese_i18n_release_gate(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("Japanese i18n release gate must be an object")
    document = to_canonical_data(value)
    if not isinstance(document, dict):
        raise ValueError("Japanese i18n release gate must be an object")
    if set(document) != {
        "checks",
        "evidence_id",
        "passed",
        "rejection_reasons",
        "schema_version",
    }:
        raise ValueError("Japanese i18n release gate keys are invalid")
    if document.get("schema_version") != JAPANESE_I18N_RELEASE_GATE_SCHEMA_VERSION:
        raise ValueError("unsupported Japanese i18n release gate schema_version")
    evidence_id = document.get("evidence_id")
    if not isinstance(evidence_id, str) or not evidence_id.startswith(
        "japanesei18ngate_"
    ):
        raise ValueError("Japanese i18n release gate evidence_id is invalid")
    identity = dict(document)
    identity.pop("evidence_id", None)
    if evidence_id != stable_digest(identity, prefix="japanesei18ngate_"):
        raise ValueError("Japanese i18n release gate evidence_id mismatch")
    checks = document.get("checks")
    if not isinstance(checks, list) or not checks:
        raise ValueError("Japanese i18n release gate checks are invalid")
    rejection_reasons: list[str] = []
    for check in checks:
        if not isinstance(check, Mapping):
            raise ValueError("Japanese i18n release gate check is invalid")
        if set(check) != {"check_id", "evidence", "passed"}:
            raise ValueError("Japanese i18n release gate check keys are invalid")
        if not isinstance(check.get("check_id"), str) or not check["check_id"]:
            raise ValueError("Japanese i18n release gate check_id is invalid")
        if not isinstance(check.get("evidence"), Mapping):
            raise ValueError("Japanese i18n release gate check evidence is invalid")
        if check.get("passed") is True:
            continue
        if check.get("passed") is not False:
            raise ValueError("Japanese i18n release gate check passed is invalid")
        rejection_reasons.append(check["check_id"])
    if document.get("rejection_reasons") != rejection_reasons:
        raise ValueError("Japanese i18n release gate rejection_reasons are inconsistent")
    if document.get("passed") != (not rejection_reasons):
        raise ValueError("Japanese i18n release gate passed is inconsistent")
    return document


def read_japanese_i18n_release_gate(path: str | Path) -> dict[str, Any]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError("Japanese i18n release gate is invalid JSON") from exc
    return validate_japanese_i18n_release_gate(value)


def write_japanese_i18n_release_gate(
    repo_root: str | Path,
    *,
    output_path: str | Path,
) -> dict[str, Any]:
    document = build_japanese_i18n_release_gate(repo_root)
    validate_japanese_i18n_release_gate(document)
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(
        destination,
        json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )
    return document


def main() -> int:
    parser = argparse.ArgumentParser(
        description="evaluate the v0.8 Japanese desktop UI and i18n release gate"
    )
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    evidence = write_japanese_i18n_release_gate(args.repo_root, output_path=args.out)
    print(
        "japanese-i18n-release-gate: "
        f"passed={evidence['passed']} "
        f"rejections={','.join(evidence['rejection_reasons']) or '-'} "
        f"evidence_id={evidence['evidence_id']}"
    )
    return 0 if evidence["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
