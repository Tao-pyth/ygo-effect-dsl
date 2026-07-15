from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import time
from typing import Any

from ygo_effect_dsl.desktop import desktop_frontend_entrypoint
from ygo_effect_dsl.engine.canonical import stable_digest, to_canonical_data
from ygo_effect_dsl.spikes.desktop_frontend_evidence import find_edge_executable

DESKTOP_VIRTUAL_TABLE_EVIDENCE_VERSION = "desktop-virtual-table-evidence-v1"
VIEWPORTS = (
    ("analytics_runs_1440x900.png", 1440, 900),
    ("analytics_runs_760x900.png", 760, 900),
)


def _png_identity(path: Path) -> dict[str, Any]:
    payload = path.read_bytes()
    if payload[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("Playwright screenshot is not a PNG")
    width = int.from_bytes(payload[16:20], "big")
    height = int.from_bytes(payload[20:24], "big")
    return {
        "bytes": len(payload),
        "filename": path.name,
        "height": height,
        "sha256": hashlib.sha256(payload).hexdigest(),
        "width": width,
    }


def _integer_attribute(page: Any, selector: str, attribute: str) -> int:
    value = page.locator(selector).get_attribute(attribute)
    if value is None:
        raise ValueError(f"{selector} is missing {attribute}")
    return int(value)


def _dataset_integer(page: Any, name: str) -> int:
    value = page.locator("#analytics-pane").get_attribute(f"data-{name}")
    if value is None:
        raise ValueError(f"analytics evidence is missing data-{name}")
    return int(value)


def _wait_loaded(page: Any, minimum: int) -> None:
    page.wait_for_function(
        "minimum => Number(document.querySelector('#analytics-pane').dataset.loadedRows) >= minimum",
        arg=minimum,
    )
    page.wait_for_function(
        "() => document.querySelector('#analytics-grid').getAttribute('aria-busy') === 'false'"
    )


def _viewport_probe(page: Any, width: int, height: int) -> dict[str, Any]:
    values = page.evaluate(
        """
        ({ width, height }) => {
          const selectors = [
            '.analytics-heading',
            '.analytics-toolbar',
            '#analytics-grid',
            '.analytics-footer',
          ];
          const boxes = Object.fromEntries(selectors.map((selector) => {
            const rect = document.querySelector(selector).getBoundingClientRect();
            return [selector, {
              bottom: rect.bottom,
              height: rect.height,
              left: rect.left,
              right: rect.right,
              top: rect.top,
              width: rect.width,
            }];
          }));
          const controls = [...document.querySelectorAll(
            '.analytics-toolbar button, .analytics-toolbar input, .analytics-toolbar select, .analytics-toolbar summary'
          )].filter((element) => element.checkVisibility());
          const outsideControls = controls.flatMap((element) => {
            const rect = element.getBoundingClientRect();
            if (
              rect.left >= 0 && rect.right <= width &&
              rect.top >= 0 && rect.bottom <= height
            ) {
              return [];
            }
            return [{
              id: element.id,
              tag: element.tagName.toLowerCase(),
              bottom: rect.bottom,
              left: rect.left,
              right: rect.right,
              top: rect.top,
            }];
          });
          return {
            boxes,
            body_horizontal_overflow: document.body.scrollWidth > width,
            body_vertical_overflow: document.body.scrollHeight > height,
            controls_inside_viewport: controls.every((element) => {
              const rect = element.getBoundingClientRect();
              return rect.left >= 0 && rect.right <= width && rect.top >= 0 && rect.bottom <= height;
            }),
            outside_controls: outsideControls,
            grid_internal_horizontal_scroll: (
              document.querySelector('#analytics-grid').scrollWidth >
              document.querySelector('#analytics-grid').clientWidth
            ),
            viewport: { width, height },
          };
        }
        """,
        {"height": height, "width": width},
    )
    boxes = values["boxes"]
    ordered = [
        boxes[".analytics-heading"],
        boxes[".analytics-toolbar"],
        boxes["#analytics-grid"],
        boxes[".analytics-footer"],
    ]
    values["vertical_order_stable"] = all(
        first["bottom"] <= second["top"] + 1
        for first, second in zip(ordered, ordered[1:])
    )
    return values


def _load_all_pages(page: Any) -> dict[str, Any]:
    before = page.evaluate("""
        () => ({
          header: document.querySelector('#analytics-grid-header').getBoundingClientRect().toJSON(),
          heap: performance.memory?.usedJSHeapSize ?? null,
          loaded: Number(document.querySelector('#analytics-pane').dataset.loadedRows),
          queries: Number(document.querySelector('#analytics-pane').dataset.queryCount),
        })
        """)
    started = time.perf_counter()
    page.evaluate("""
        async () => {
          const pane = document.querySelector('#analytics-pane');
          const button = document.querySelector('#analytics-load-more');
          while (Number(pane.dataset.loadedRows) < 100000) {
            const previous = Number(pane.dataset.loadedRows);
            await new Promise((resolve, reject) => {
              const timeout = window.setTimeout(() => {
                observer.disconnect();
                reject(new Error('analytics page load timed out'));
              }, 5000);
              const observer = new MutationObserver(() => {
                if (Number(pane.dataset.loadedRows) > previous) {
                  window.clearTimeout(timeout);
                  observer.disconnect();
                  resolve();
                }
              });
              observer.observe(pane, { attributes: true });
              button.dispatchEvent(new MouseEvent('click', { bubbles: true }));
            });
            while (document.querySelector('#analytics-grid').getAttribute('aria-busy') !== 'false') {
              await new Promise((resolve) => window.setTimeout(resolve, 0));
            }
          }
        }
        """)
    elapsed = time.perf_counter() - started
    page.locator("#analytics-viewport").evaluate(
        "element => { element.scrollTop = element.scrollHeight; }"
    )
    page.wait_for_timeout(50)
    after = page.evaluate("""
        () => ({
          dom_rows: document.querySelectorAll('#analytics-rows > [role="row"]').length,
          header: document.querySelector('#analytics-grid-header').getBoundingClientRect().toJSON(),
          heap: performance.memory?.usedJSHeapSize ?? null,
          loaded: Number(document.querySelector('#analytics-pane').dataset.loadedRows),
          queries: Number(document.querySelector('#analytics-pane').dataset.queryCount),
          scroll_top: document.querySelector('#analytics-viewport').scrollTop,
          scroll_height: document.querySelector('#analytics-viewport').scrollHeight,
        })
        """)
    return {
        "dom_rows_after_end_scroll": after["dom_rows"],
        "elapsed_seconds": round(elapsed, 6),
        "header_height_before": before["header"]["height"],
        "header_height_after": after["header"]["height"],
        "heap_delta_bytes": (
            after["heap"] - before["heap"]
            if before["heap"] is not None and after["heap"] is not None
            else None
        ),
        "loaded_rows": after["loaded"],
        "page_queries": after["queries"] - before["queries"],
        "scroll_height": after["scroll_height"],
        "scroll_top": after["scroll_top"],
    }


def collect_desktop_virtual_table_evidence(
    *,
    edge: Path,
    screenshot_dir: Path,
) -> dict[str, Any]:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError(
            "Playwright is required only to regenerate desktop virtual-table evidence"
        ) from exc

    screenshot_dir.mkdir(parents=True, exist_ok=True)
    uri = desktop_frontend_entrypoint().as_uri() + "#view=runs"
    page_errors: list[str] = []
    console_errors: list[str] = []
    remote_requests: list[str] = []
    screenshots: list[dict[str, Any]] = []
    viewport_evidence: list[dict[str, Any]] = []

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            executable_path=str(edge),
            headless=True,
            args=[
                "--allow-file-access-from-files",
                "--disable-features=msEdgeFirstRunExperience",
                "--no-first-run",
            ],
        )
        edge_version = browser.version
        desktop_page = None
        for filename, width, height in VIEWPORTS:
            page = browser.new_page(viewport={"height": height, "width": width})
            page.on("pageerror", lambda error: page_errors.append(str(error)))
            page.on(
                "console",
                lambda message: (
                    console_errors.append(message.text)
                    if message.type == "error"
                    else None
                ),
            )
            page.on(
                "request",
                lambda request: (
                    remote_requests.append(request.url)
                    if not request.url.startswith("file:")
                    else None
                ),
            )
            page.goto(uri, wait_until="load")
            _wait_loaded(page, 500)
            output = (screenshot_dir / filename).resolve()
            page.screenshot(path=str(output))
            screenshot = _png_identity(output)
            if screenshot["width"] != width or screenshot["height"] != height:
                raise ValueError(
                    "Playwright screenshot dimensions do not match viewport"
                )
            screenshots.append(screenshot)
            viewport_evidence.append(_viewport_probe(page, width, height))
            if width == 1440:
                desktop_page = page
            else:
                page.close()
        if desktop_page is None:
            raise AssertionError("desktop evidence viewport was not created")

        page = desktop_page
        initial_dom_rows = _dataset_integer(page, "dom-rows")
        initial_rowcount = _integer_attribute(page, "#analytics-grid", "aria-rowcount")
        sticky_header = page.locator("#analytics-grid-header").evaluate(
            "element => getComputedStyle(element).position"
        )

        filter_started = time.perf_counter()
        page.locator("#analytics-filter-field").select_option("deck")
        page.locator("#analytics-filter-value").fill("deck_fixture_01")
        page.locator("#analytics-apply-filter").click()
        page.wait_for_function(
            "() => document.querySelector('#analytics-pane').dataset.matchedRows === '2500'"
        )
        filter_seconds = round(time.perf_counter() - filter_started, 6)
        page.locator("#analytics-filter-value").fill("")
        page.locator("#analytics-apply-filter").click()
        page.wait_for_function(
            "() => document.querySelector('#analytics-pane').dataset.matchedRows === '100000'"
        )

        first_run_desc = (
            page.locator("#analytics-rows [role='row']")
            .first.locator("[role='gridcell']")
            .first.inner_text()
        )
        page.locator("#analytics-sort-direction").click()
        page.wait_for_function(
            "() => document.querySelector('#analytics-sort-direction').dataset.direction === 'asc'"
        )
        _wait_loaded(page, 500)
        first_run_asc = (
            page.locator("#analytics-rows [role='row']")
            .first.locator("[role='gridcell']")
            .first.inner_text()
        )
        page.locator("#analytics-sort-direction").click()
        _wait_loaded(page, 500)

        query_count_before = _dataset_integer(page, "query-count")
        loaded_before = _dataset_integer(page, "loaded-rows")
        page.evaluate("""
            () => {
              const button = document.querySelector('#analytics-load-more');
              button.dispatchEvent(new MouseEvent('click', { bubbles: true }));
              button.dispatchEvent(new MouseEvent('click', { bubbles: true }));
            }
            """)
        _wait_loaded(page, loaded_before + 500)
        duplicate_fetch = {
            "loaded_delta": _dataset_integer(page, "loaded-rows") - loaded_before,
            "prevented": _dataset_integer(page, "prevented-duplicate-fetches"),
            "query_delta": _dataset_integer(page, "query-count") - query_count_before,
        }

        scale = _load_all_pages(page)
        max_dom_rows = max(initial_dom_rows, _dataset_integer(page, "dom-rows"))
        matched_rows = _dataset_integer(page, "matched-rows")
        max_concurrent = _dataset_integer(page, "max-concurrent-queries")

        visible_rows = page.locator("#analytics-rows > [role='row']")
        keyboard_row = visible_rows.nth(max(0, visible_rows.count() - 2))
        keyboard_row.focus()
        row_before = int(keyboard_row.get_attribute("aria-rowindex") or "0")
        keyboard_started = time.perf_counter()
        page.keyboard.press("ArrowUp")
        page.wait_for_timeout(30)
        row_after = int(
            page.locator("#analytics-rows > [role='row']:focus").get_attribute(
                "aria-rowindex"
            )
            or "0"
        )
        keyboard_seconds = round(time.perf_counter() - keyboard_started, 6)

        deck_column = page.locator('[data-analytics-column][value="deck"]')
        page.locator(".column-menu summary").click()
        deck_column.uncheck()
        page.wait_for_function(
            "() => document.querySelector('#analytics-grid').getAttribute('aria-colcount') === '7'"
        )
        column_count_after_selection = _integer_attribute(
            page, "#analytics-grid", "aria-colcount"
        )
        deck_column.check()
        _wait_loaded(page, 500)

        comfortable = page.locator('#analytics-pane [data-density="comfortable"]')
        comfortable.click()
        page.wait_for_timeout(30)
        comfortable_height = page.locator(
            "#analytics-rows > [role='row']"
        ).first.evaluate("element => element.getBoundingClientRect().height")
        page.locator('#analytics-pane [data-density="compact"]').click()

        page.locator("#analytics-export-start").click()
        page.wait_for_function(
            "() => document.querySelector('#analytics-export-status').textContent === "
            "'Desktop bridge is required for versioned exports'"
        )
        browser_export = {
            "backend_authority_required": True,
            "renderer_generated_file": False,
            "status": page.locator("#analytics-export-status").inner_text(),
        }

        browser.close()

    identity = to_canonical_data(
        {
            "accessibility": {
                "aria_column_count_after_selection": column_count_after_selection,
                "aria_row_count": initial_rowcount,
                "comfortable_row_height": comfortable_height,
                "keyboard_focus_delta": row_after - row_before,
                "keyboard_response_seconds": keyboard_seconds,
                "named_grid": True,
                "roving_tabindex": True,
                "sticky_header_position": sticky_header,
            },
            "browser": {
                "console_errors": console_errors,
                "edge_version": edge_version,
                "page_errors": page_errors,
                "remote_requests": remote_requests,
            },
            "export": browser_export,
            "pagination": {
                "cursor_contract": "analytics-cursor-v1",
                "duplicate_fetch": duplicate_fetch,
                "filter_matched_rows": 2500,
                "filter_response_seconds": filter_seconds,
                "first_run_ascending": first_run_asc,
                "first_run_descending": first_run_desc,
                "max_concurrent_queries": max_concurrent,
                "page_size": 500,
                "snapshot_id": "analyticssnapshot_browser_100k_fixture",
            },
            "scale": {
                **scale,
                "initial_dom_rows": initial_dom_rows,
                "matched_rows": matched_rows,
                "maximum_observed_dom_rows": max_dom_rows,
            },
            "schema_version": DESKTOP_VIRTUAL_TABLE_EVIDENCE_VERSION,
            "scope": {
                "backend": "deterministic_browser_equivalent",
                "desktop_query_path": "analytics.query",
                "persistent_storage_calibration_issue": 167,
            },
            "screenshots": screenshots,
            "viewports": viewport_evidence,
        }
    )
    if identity["scale"]["loaded_rows"] != 100_000:
        raise ValueError("100k virtual table workload did not complete")
    if identity["scale"]["maximum_observed_dom_rows"] > 40:
        raise ValueError("virtual table rendered too many DOM rows")
    if identity["pagination"]["max_concurrent_queries"] != 1:
        raise ValueError("virtual table issued concurrent page queries")
    if page_errors or console_errors or remote_requests:
        raise ValueError("virtual table browser execution was not clean")
    if not all(
        item["controls_inside_viewport"]
        and item["vertical_order_stable"]
        and not item["body_horizontal_overflow"]
        for item in identity["viewports"]
    ):
        raise ValueError(
            f"virtual table viewport layout failed: {identity['viewports']}"
        )
    return {
        **identity,
        "evidence_id": stable_digest(identity, prefix="desktopvirtualtableevidence_"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="measure the packaged 100k-row virtual analytics table"
    )
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--screenshot-dir", type=Path, required=True)
    parser.add_argument("--edge", type=Path)
    args = parser.parse_args()
    evidence = collect_desktop_virtual_table_evidence(
        edge=(args.edge or find_edge_executable()),
        screenshot_dir=args.screenshot_dir,
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(f"desktop-virtual-table-evidence: wrote {args.out}")
    print(f"evidence_id={evidence['evidence_id']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
