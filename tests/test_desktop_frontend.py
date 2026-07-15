from __future__ import annotations

import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import struct

from ygo_effect_dsl.desktop import (
    DESKTOP_BRIDGE_CONTRACT_VERSION,
    DESKTOP_WORKFLOW_CONTRACT_VERSION,
    desktop_bridge_contract_document,
    desktop_frontend_entrypoint,
    desktop_frontend_root,
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
    assert contract["large_catalog"] == {
        "issue": 165,
        "query": "server_cursor_window",
        "status": "virtualization_release_gate",
        "target_rows": 100000,
    }


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

    required_ids = {
        "workspace",
        "deck-filter",
        "deck-table-body",
        "open-search",
        "search-dialog",
        "search-form",
        "run-preflight",
        "queue-search",
        "job-dialog",
        "cancel-job",
        "view-result",
        "result-dialog",
        "card-dialog",
        "compare-dialog",
    }
    assert required_ids <= parser.ids
    assert html.count("<dialog") == 5
    assert '<script src="app.js" defer></script>' in html
    assert '<script src="bridge.js" defer></script>' in html
    assert '<link rel="stylesheet" href="app.css">' in html


def test_frontend_has_no_network_or_direct_python_bridge_path() -> None:
    html, css, bridge, javascript = _assets()
    combined = "\n".join((html, css, bridge, javascript)).lower()

    assert "http://" not in combined
    assert "https://" not in combined
    assert "fetch(" not in javascript
    assert "xmlhttprequest" not in javascript.lower()
    assert "websocket" not in javascript.lower()
    assert "window.pywebview" not in javascript
    assert "window.pywebview.api.invoke" in bridge
    assert DESKTOP_BRIDGE_CONTRACT_VERSION in bridge
    assert desktop_bridge_contract_document()["security"]["local_rest_api"] is False
    assert "innerHTML" not in javascript
    assert "eval(" not in javascript
    assert "No real worker has started" in javascript
    assert "No worker started" in javascript
    assert desktop_workflow_contract_document()["integration"]["preview_adapter"] == (
        "synthetic_search_browser_only"
    )


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
        "Cancellation requested. Waiting for the active worker to stop." in javascript
    )
    assert "Cancellation status polling failed closed." in javascript
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
