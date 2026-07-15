from __future__ import annotations

import hashlib
import json
from pathlib import Path
import struct

from ygo_effect_dsl.desktop import (
    DESKTOP_VIRTUAL_TABLE_CONTRACT_VERSION,
    desktop_frontend_root,
    desktop_virtual_table_contract_document,
)
from ygo_effect_dsl.engine.canonical import stable_digest
from ygo_effect_dsl.spikes.desktop_virtual_table_evidence import (
    DESKTOP_VIRTUAL_TABLE_EVIDENCE_VERSION,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_ROOT = REPO_ROOT / "docs" / "ui" / "evidence"


def test_virtual_table_contract_is_versioned_and_fail_closed() -> None:
    contract = desktop_virtual_table_contract_document()

    assert contract["schema_version"] == DESKTOP_VIRTUAL_TABLE_CONTRACT_VERSION
    assert contract["pagination"] == {
        "cursor_contract": "analytics-cursor-v1",
        "immutable_snapshot": True,
        "page_size": 500,
        "query_contract": "analytics-query-contract-v1",
        "request_schema": "analytics-query-request-v1",
        "response_schema": "analytics-query-response-v1",
    }
    assert contract["rendering"] == {
        "compact_row_height": 40,
        "comfortable_row_height": 48,
        "mode": "viewport_row_window",
        "overscan_rows": 6,
        "stable_row_height": True,
        "target_rows": 100000,
    }
    assert set(contract["failure_policy"].values()) == {
        "fail_closed",
        "suppress_duplicate",
    }


def test_virtual_table_uses_cursor_query_and_bounded_dom_window() -> None:
    script = (desktop_frontend_root() / "analytics.js").read_text(encoding="utf-8")

    assert "const PAGE_SIZE = 500;" in script
    assert "const OVERSCAN_ROWS = 6;" in script
    assert 'schema_version: "analytics-query-request-v1"' in script
    assert 'response.schema_version !== "analytics-query-response-v1"' in script
    assert "this.snapshotId !== response.snapshot_id" in script
    assert "this.rowIds.has(row.row_id)" in script
    assert "this.rowsLayer.replaceChildren()" in script
    assert "this.preventedDuplicateFetches += 1" in script
    assert "fetch(" not in script
    assert "XMLHttpRequest" not in script
    assert "window.pywebview" not in script


def test_virtual_table_keyboard_and_accessibility_contract_is_explicit() -> None:
    root = desktop_frontend_root()
    script = (root / "analytics.js").read_text(encoding="utf-8")
    html = (root / "index.html").read_text(encoding="utf-8")
    css = (root / "app.css").read_text(encoding="utf-8")

    for key in ("ArrowDown", "ArrowUp", "End", "Home", "PageDown", "PageUp"):
        assert key in script
    for attribute in ("aria-colcount", "aria-rowcount", "aria-rowindex"):
        assert attribute in script or attribute in html
    assert 'role="grid"' in html
    assert 'aria-label="Run observations"' in html
    assert "position: sticky" in css
    assert "forced-colors: active" in css


def test_committed_100k_virtual_table_evidence_is_content_addressed() -> None:
    evidence = json.loads(
        (EVIDENCE_ROOT / "desktop_virtual_table.json").read_text(encoding="utf-8")
    )
    identity = {key: value for key, value in evidence.items() if key != "evidence_id"}

    assert evidence["schema_version"] == DESKTOP_VIRTUAL_TABLE_EVIDENCE_VERSION
    assert evidence["scope"] == {
        "backend": "deterministic_browser_equivalent",
        "desktop_query_path": "analytics.query",
        "persistent_storage_calibration_issue": 167,
    }
    assert evidence["evidence_id"] == stable_digest(
        identity,
        prefix="desktopvirtualtableevidence_",
    )
    assert evidence["scale"]["loaded_rows"] == 100000
    assert evidence["scale"]["matched_rows"] == 100000
    assert evidence["scale"]["maximum_observed_dom_rows"] <= 40
    assert evidence["scale"]["dom_rows_after_end_scroll"] <= 40
    assert (
        evidence["scale"]["header_height_before"]
        == evidence["scale"]["header_height_after"]
    )
    assert evidence["pagination"]["max_concurrent_queries"] == 1
    assert evidence["pagination"]["duplicate_fetch"] == {
        "loaded_delta": 500,
        "prevented": 1,
        "query_delta": 1,
    }
    assert evidence["accessibility"]["aria_row_count"] == 100001
    assert evidence["accessibility"]["keyboard_focus_delta"] == -1
    assert evidence["accessibility"]["sticky_header_position"] == "sticky"
    assert all(
        not viewport["body_horizontal_overflow"] for viewport in evidence["viewports"]
    )
    assert all(
        viewport["controls_inside_viewport"] for viewport in evidence["viewports"]
    )
    assert all(viewport["vertical_order_stable"] for viewport in evidence["viewports"])
    assert evidence["browser"]["console_errors"] == []
    assert evidence["browser"]["page_errors"] == []
    assert evidence["browser"]["remote_requests"] == []

    for screenshot in evidence["screenshots"]:
        payload = (EVIDENCE_ROOT / screenshot["filename"]).read_bytes()
        width, height = struct.unpack(">II", payload[16:24])
        assert payload[:8] == b"\x89PNG\r\n\x1a\n"
        assert len(payload) == screenshot["bytes"]
        assert hashlib.sha256(payload).hexdigest() == screenshot["sha256"]
        assert (width, height) == (screenshot["width"], screenshot["height"])
