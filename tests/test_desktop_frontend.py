from __future__ import annotations

import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import struct

from ygo_effect_dsl.desktop import (
    DESKTOP_BRIDGE_CONTRACT_VERSION,
    DESKTOP_VIRTUAL_TABLE_CONTRACT_VERSION,
    DESKTOP_WORKFLOW_CONTRACT_VERSION,
    desktop_bridge_contract_document,
    desktop_frontend_entrypoint,
    desktop_frontend_root,
    desktop_virtual_table_contract_document,
    desktop_workflow_contract_document,
)
from ygo_effect_dsl.engine.canonical import stable_digest
from ygo_effect_dsl.engine.search.strategy import (
    BEAM_SEARCH_STRATEGY_SCHEMA_VERSION,
    MCTS_STRATEGY_SCHEMA_VERSION,
    RANDOM_SEARCH_STRATEGY_SCHEMA_VERSION,
)
from ygo_effect_dsl.spikes.desktop_frontend_evidence import (
    DESKTOP_FRONTEND_EVIDENCE_SCHEMA_VERSION,
)
from ygo_effect_dsl.spikes.japanese_i18n_release_gate import (
    JAPANESE_I18N_RELEASE_GATE_SCHEMA_VERSION,
    build_japanese_i18n_release_gate,
    validate_japanese_i18n_release_gate,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_ROOT = REPO_ROOT / "docs" / "ui" / "evidence"


class _FrontendParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.ids: set[str] = set()
        self.attrs: list[tuple[str, dict[str, str | None]]] = []

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        values = dict(attrs)
        self.attrs.append((tag, values))
        if identifier := values.get("id"):
            self.ids.add(identifier)


def _assets() -> tuple[str, str, str, str]:
    root = desktop_frontend_root()
    return tuple(
        (root / name).read_text(encoding="utf-8")
        for name in ("index.html", "app.css", "bridge.js", "app.js")
    )


def _static_asset_texts() -> dict[str, str]:
    root = desktop_frontend_root()
    return {
        name: (root / name).read_text(encoding="utf-8")
        for name in ("index.html", "app.css", "bridge.js", "app.js", "analytics.js")
    }


def _mojibake_markers() -> tuple[str, ...]:
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


def _has_halfwidth_katakana(text: str) -> bool:
    return any(0xFF61 <= ord(character) <= 0xFF9F for character in text)


def test_packaged_frontend_and_machine_contract_are_versioned() -> None:
    entrypoint = desktop_frontend_entrypoint()
    contract = desktop_workflow_contract_document()

    assert entrypoint == desktop_frontend_root() / "index.html"
    assert contract["schema_version"] == DESKTOP_WORKFLOW_CONTRACT_VERSION
    assert contract["initial_view"] == "deck_catalog"
    assert contract["authority"] == {
        "card_effect_interpretation": "forbidden",
        "experiment_contract_owner": "python_application_service",
        "fixture_preview_may_execute_workers": False,
        "legality_and_timing": "ocgcore_only",
        "renderer_is_authoritative": False,
    }
    assert contract["search_strategies"] == [
        RANDOM_SEARCH_STRATEGY_SCHEMA_VERSION,
        BEAM_SEARCH_STRATEGY_SCHEMA_VERSION,
        MCTS_STRATEGY_SCHEMA_VERSION,
    ]
    compose_contract = desktop_bridge_contract_document()["methods"][
        "scenario.compose_search"
    ]
    assert "opening_hand" in compose_contract["configuration_fields"]
    assert "pool_size" in compose_contract["configuration_fields"]
    assert "scenario_preset_id" in compose_contract["configuration_fields"]
    assert compose_contract["scenario_presets"] == [
        {
            "evaluator": "real_core_board_count/1",
            "id": "terminal_board_min_monster_v1",
            "objective": "maximize_terminal_board",
            "success_predicate": "real_core_min_monster_count/1",
        }
    ]
    assert compose_contract["parallel_policy"] == {
        "default_pool_size": 1,
        "max_pool_size": 8,
        "schema_version": "parallel-search-policy-v1",
    }
    replay_contract = desktop_bridge_contract_document()["methods"][
        "job.enqueue_replay_verification"
    ]
    assert replay_contract["payload_fields"] == [
        "idempotency_key",
        "priority",
        "search_job_id",
    ]
    assert replay_contract["source"] == "committed_search_job_artifacts"
    assert contract["large_catalog"] == {
        "contract": DESKTOP_VIRTUAL_TABLE_CONTRACT_VERSION,
        "issue": 165,
        "query": "server_cursor_window",
        "status": "implemented_with_browser_scale_evidence",
        "target_rows": 100000,
    }
    virtual_table = desktop_virtual_table_contract_document()
    assert virtual_table["schema_version"] == DESKTOP_VIRTUAL_TABLE_CONTRACT_VERSION
    assert virtual_table["pagination"]["query_contract"] == (
        "analytics-query-contract-v1"
    )


def test_static_html_has_default_deny_csp_and_accessible_workflow() -> None:
    html, _, _, _ = _assets()
    parser = _FrontendParser()
    parser.feed(html)

    csp = next(
        attrs["content"]
        for tag, attrs in parser.attrs
        if tag == "meta" and attrs.get("http-equiv") == "Content-Security-Policy"
    )
    assert csp is not None
    assert "default-src 'none'" in csp
    assert "connect-src 'none'" in csp
    assert "unsafe-inline" not in csp
    assert "unsafe-eval" not in csp
    assert all("style" not in attrs for _, attrs in parser.attrs)
    assert all(
        not any(name.startswith("on") for name in attrs) for _, attrs in parser.attrs
    )
    html_attrs = next(attrs for tag, attrs in parser.attrs if tag == "html")
    assert html_attrs["lang"] == "ja"
    assert "デッキ研究ワークスペース" in html
    assert "デッキカタログ" in html
    assert 'data-view="profiles"' in html
    assert "プロファイル" in html
    assert "探索を実行" in html

    required_ids = {
        "workspace",
        "deck-filter",
        "deck-table-body",
        "deck-settings",
        "deck-settings-dialog",
        "deck-settings-form",
        "deck-display-name",
        "deck-tags",
        "deck-settings-status",
        "inline-deck-dialog",
        "inline-deck-form",
        "inline-deck-name",
        "inline-main-cards",
        "inline-extra-cards",
        "inline-side-cards",
        "inline-deck-status",
        "register-inline-deck",
        "open-search",
        "objective",
        "search-dialog",
        "search-form",
        "run-preflight",
        "queue-search",
        "opening-hand",
        "fixed-hand-cards",
        "conditional-card-code",
        "conditional-min-count",
        "conditional-max-count",
        "conditional-max-attempts",
        "pool-size",
        "preference-profile",
        "edit-profiles",
        "profiles-pane",
        "profile-new",
        "profile-deck-select",
        "profile-include-archived",
        "profile-page-status",
        "deck-profile-list",
        "deck-profile-form",
        "deck-profile-edit-status",
        "deck-profile-name",
        "deck-profile-card",
        "deck-profile-location",
        "deck-profile-position",
        "deck-profile-weight",
        "deck-profile-min-count",
        "deck-profile-max-count",
        "deck-profile-scoring",
        "deck-profile-add-rule",
        "deck-profile-rules",
        "deck-profile-save",
        "deck-profile-archive",
        "job-dialog",
        "cancel-job",
        "view-result",
        "result-dialog",
        "result-route-id",
        "result-route-line",
        "result-evidence",
        "result-coverage",
        "result-candidates",
        "result-explored",
        "result-censored",
        "result-verification-state",
        "result-termination",
        "result-opening-hand",
        "result-peak-board",
        "verify-result",
        "result-drilldown",
        "result-tab-ranking",
        "result-tab-candidates",
        "result-drilldown-head",
        "result-drilldown-body",
        "card-dialog",
        "compare-dialog",
        "analytics-grid",
        "analytics-pane",
        "analytics-viewport",
    }
    assert required_ids <= parser.ids
    assert html.count("<dialog") == 7
    assert 'id="new-inline" type="button" hidden' in html
    assert 'class="help-icon"' in html
    assert "最大スコア盤面" in html
    assert "初期手札" in html
    assert '<script src="app.js" defer></script>' in html
    assert '<script src="bridge.js" defer></script>' in html
    assert '<script src="analytics.js" defer></script>' in html
    assert '<link rel="stylesheet" href="app.css">' in html


def test_desktop_frontend_uses_japanese_copy_and_rejects_mojibake() -> None:
    assets = _static_asset_texts()
    html = assets["index.html"]
    javascript = assets["app.js"]
    analytics = assets["analytics.js"]
    combined = "\n".join(assets.values())

    assert all(marker not in combined for marker in _mojibake_markers())
    assert not _has_halfwidth_katakana(combined)
    assert "UI_LOCALE = \"ja\"" in javascript
    assert "const UI_TEXT = Object.freeze({" in javascript
    assert "ANALYTICS_LOCALE = \"ja\"" in analytics
    assert "const ANALYTICS_TEXT = Object.freeze({" in analytics
    assert "短経路 fixture" in javascript
    assert "長チェーン fixture" in javascript
    assert "墓地/除外 fixture" in javascript
    assert "復旧プローブ" in javascript
    assert "Replay検証をキューへ追加しました。" in javascript
    assert "評価プロファイル" in analytics
    assert "分析ページ準備完了" in analytics
    assert "出力をキューへ投入中" in analytics
    assert "事前検証待ち" in javascript
    assert "デスクトップブリッジ準備完了" in javascript
    assert "Short route fixture" not in combined
    assert "Long chain fixture" not in combined
    assert "Grave / banish fixture" not in combined
    assert "Recovery probe" not in combined


def test_release_facing_0_8_docs_reject_mojibake() -> None:
    release_docs = [
        REPO_ROOT / "README.md",
        REPO_ROOT / "CHANGELOG.md",
        REPO_ROOT / "docs" / "20_roadmap.md",
        REPO_ROOT / "docs" / "release" / "00_versioning.md",
        REPO_ROOT / "docs" / "spec" / "00_release_stage_index.md",
        REPO_ROOT / "docs" / "spec" / "v0.8.0" / "00_scope.md",
    ]
    combined = "\n".join(path.read_text(encoding="utf-8") for path in release_docs)

    assert all(marker not in combined for marker in _mojibake_markers())
    assert not _has_halfwidth_katakana(combined)
    assert "japanese-i18n-release-gate-v1" in combined


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


def test_frontend_has_no_network_or_direct_python_bridge_path() -> None:
    html, css, bridge, javascript = _assets()
    analytics_javascript = (desktop_frontend_root() / "analytics.js").read_text(
        encoding="utf-8"
    )
    combined = "\n".join((html, css, bridge, javascript, analytics_javascript)).lower()

    assert "http://" not in combined
    assert "https://" not in combined
    assert "fetch(" not in javascript
    assert "xmlhttprequest" not in javascript.lower()
    assert "websocket" not in javascript.lower()
    assert "window.pywebview" not in javascript
    assert "window.pywebview.api.invoke" in bridge
    assert '"profile.list"' in bridge
    assert '"profile.clone"' in bridge
    assert '"deck.profile.list"' in bridge
    assert '"deck.profile.create"' in bridge
    assert '"deck.profile.update"' in bridge
    assert '"deck.profile.archive"' in bridge
    assert '"deck.metadata.get"' in bridge
    assert '"deck.metadata.update"' in bridge
    assert '"deck.card_options"' in bridge
    assert '"job.enqueue_replay_verification"' in bridge
    assert '"deck.register_inline"' in bridge
    assert '"deck.register_inline"' in javascript
    assert "inlineDeckPayload" in javascript
    assert "Inline deck registration is connected by issue #244." not in javascript
    assert "refreshPreferenceProfiles" in javascript
    assert "preference_profile_id: elements.preferenceProfile.value || null" in javascript
    assert '"deck.profile.list"' in javascript
    assert '"deck.profile.create"' in javascript
    assert '"deck.profile.update"' in javascript
    assert '"deck.profile.archive"' in javascript
    assert '"deck.metadata.update"' in javascript
    assert '"deck.card_options"' in javascript
    assert '"profile.clone"' not in javascript
    assert "desktop-rule-${cardCode}-${location}-${position}-${Date.now()}" in javascript
    assert "プロファイルを保存しました。" in javascript
    assert "プロファイルをアーカイブしました。" in javascript
    assert "opening_hand: openingHandConfiguration()" in javascript
    assert "scenario_preset_id: elements.objective.value" in javascript
    assert 'value="terminal_board_min_monster_v1"' in html
    assert "デッキ内カードを選択してください。" in javascript
    assert 'id="preference-rule-card"' not in html
    assert 'id="clone-profile"' not in html
    assert '<select id="deck-profile-card">' in html
    assert '<input id="deck-profile-card"' not in html
    assert "fixed-hand-cards" in html
    assert "pool_size:" in javascript
    assert "pool_sizeは1から8の範囲で指定してください。" in javascript
    assert "checkpoint?.payload?.replays" in javascript
    assert "elements.jobReplays.textContent = String(snapshot.job.attempt)" not in javascript
    assert 'value="opening_hand_cohort"' in html
    assert 'value="profile"' in html
    assert 'value="termination"' in html
    assert "opening_hand_cohort" in analytics_javascript
    assert "censor_state" in analytics_javascript
    assert "`replay-verification-${currentJobId}`" in javascript
    assert "Replay検証をキューへ追加しました。" in javascript
    assert "pollReplayVerification" in javascript
    assert "route_ranking" in javascript
    assert "候補経路" in javascript
    assert "result-tab-candidates" in html
    assert "`${UI_TEXT.preference} ${component.rule_id" in javascript
    assert DESKTOP_BRIDGE_CONTRACT_VERSION in bridge
    assert desktop_bridge_contract_document()["security"]["local_rest_api"] is False
    assert "innerHTML" not in javascript
    assert "eval(" not in javascript
    assert "実workerは開始していません" in javascript
    assert "workerは開始していません" in javascript
    assert '"job.result"' in javascript
    assert "candidate_evidence" in javascript
    assert "coverage.coverage_status" in javascript
    assert "renderTerminationSummary" in javascript
    assert "renderOpeningHandSummary" in javascript
    assert "renderPeakBoardSummary" in javascript
    assert "compactId(route.route_id)" in javascript
    sorted_decks_slice = javascript[
        javascript.index("function sortedDecks()"):javascript.index("function renderChart")
    ]
    assert "deck.hash" not in sorted_decks_slice
    assert "candidate accountingによりfrontier exhaustionを証明済みです。" in javascript
    assert "route_fixture_5b7a2c10" not in html
    assert desktop_workflow_contract_document()["integration"]["preview_adapter"] == (
        "synthetic_search_browser_only"
    )


def test_search_button_fails_closed_when_no_deck_is_selected() -> None:
    _, _, _, javascript = _assets()

    assert "noDeckSelected" in javascript
    assert 'document.querySelector("#open-search").disabled = true;' in javascript
    assert 'document.querySelector("#open-search").disabled = false;' in javascript
    open_search = javascript.index("function openSearch()")
    no_selection_guard = javascript.index("if (!selectedDeck)", open_search)
    deck_name_access = javascript.index("elements.searchDeckName.textContent", open_search)
    assert no_selection_guard < deck_name_access


def test_visual_css_preserves_dense_layout_and_accessibility_states() -> None:
    _, css, _, _ = _assets()

    assert "[hidden]" in css
    assert "prefers-reduced-motion: reduce" in css
    assert "forced-colors: active" in css
    assert "min-width: 760px" in css
    assert "min-height: 620px" in css
    assert "linear-gradient" not in css
    assert "radial-gradient" not in css
    assert "letter-spacing: -" not in css
    assert "border-radius: 999" not in css


def test_desktop_cancel_keeps_polling_until_worker_acknowledges() -> None:
    _, _, _, javascript = _assets()

    assert (
        "中止を要求しました。実行中workerの停止を待っています。" in javascript
    )
    assert "中止状態のpollingはfail-closeしました。" in javascript
    assert "elements.cancelJob.disabled = true" in javascript


def test_committed_edge_evidence_and_screenshots_are_content_addressed() -> None:
    evidence_path = EVIDENCE_ROOT / "desktop_frontend.json"
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    identity = {key: value for key, value in evidence.items() if key != "evidence_id"}

    assert evidence["schema_version"] == DESKTOP_FRONTEND_EVIDENCE_SCHEMA_VERSION
    assert evidence["workflow_version"] == DESKTOP_WORKFLOW_CONTRACT_VERSION
    assert evidence["evidence_id"] == stable_digest(
        identity,
        prefix="desktopfrontendevidence_",
    )
    assert evidence["dom"] == {
        "deck_row_count": 4,
        "search_dialog_present": True,
        "workflow_version_present": True,
    }
    assert evidence["security"] == {
        "remote_content": False,
        "runtime_network_access": False,
        "third_party_card_assets": False,
    }

    for screenshot in evidence["screenshots"]:
        path = EVIDENCE_ROOT / screenshot["filename"]
        payload = path.read_bytes()
        width, height = struct.unpack(">II", payload[16:24])
        assert payload[:8] == b"\x89PNG\r\n\x1a\n"
        assert len(payload) == screenshot["bytes"]
        assert hashlib.sha256(payload).hexdigest() == screenshot["sha256"]
        assert width == screenshot["width"]
        assert height == screenshot["height"]
