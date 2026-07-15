"use strict";

(function initializeAnalyticsModule() {
  const PAGE_SIZE = 500;
  const OVERSCAN_ROWS = 6;
  const FIXTURE_ROW_COUNT = 100000;
  const VALUE_SCHEMA = "analytics-query-value-v1";

  const columns = Object.freeze([
    { field: "run", label: "Run", width: "minmax(180px, 1.5fr)" },
    { field: "deck", label: "Deck", width: "minmax(150px, 1.2fr)" },
    { field: "strategy", label: "Strategy", width: "minmax(120px, 1fr)" },
    { field: "success", label: "Outcome", width: "100px" },
    { field: "score", label: "Score", width: "84px" },
    { field: "action_count", label: "Actions", width: "84px" },
    { field: "status", label: "Status", width: "110px" },
    { field: "time", label: "Observed", width: "170px" },
  ]);

  function analyticsValue(value) {
    if (value === "") {
      return { schema_version: VALUE_SCHEMA, state: "empty", value: "" };
    }
    return { schema_version: VALUE_SCHEMA, state: "value", value };
  }

  function fixtureScalar(field, index) {
    const strategy = ["random_search_v1", "beam_search_v1", "mcts_v1"][index % 3];
    const status = ["complete", "complete", "partial", "quarantined"][index % 4];
    const values = {
      run: `searchrun_fixture_${String(index).padStart(6, "0")}`,
      deck: `deck_fixture_${String(index % 40).padStart(2, "0")}`,
      strategy,
      success: index % 5 !== 0,
      score: index / 10,
      action_count: index + 1,
      status,
      time: new Date(Date.UTC(2026, 0, 1) + index * 1000).toISOString(),
    };
    return values[field];
  }

  function fixtureMatches(index, filters) {
    return filters.every((filter) => {
      if (filter.operator !== "eq") return false;
      return fixtureScalar(filter.field, index) === filter.value;
    });
  }

  function fixtureRow(index, fields) {
    const values = {};
    for (const field of fields) values[field] = analyticsValue(fixtureScalar(field, index));
    return {
      row_id: `analyticsrow_fixture_${String(index).padStart(6, "0")}`,
      schema_version: "analytics-query-row-v1",
      values,
    };
  }

  async function syntheticAnalyticsQuery(request) {
    await Promise.resolve();
    const offset = request.cursor ? Number(request.cursor.replace("fixture_", "")) : 0;
    if (!Number.isInteger(offset) || offset < 0) throw new Error("Synthetic cursor is invalid");
    const direction = request.sort[0]?.direction || "asc";
    const selected = [];
    let matched = 0;
    for (let position = 0; position < FIXTURE_ROW_COUNT; position += 1) {
      const index = direction === "desc" ? FIXTURE_ROW_COUNT - position - 1 : position;
      if (!fixtureMatches(index, request.filters)) continue;
      if (matched >= offset && selected.length < request.limit) {
        selected.push(fixtureRow(index, request.fields));
      }
      matched += 1;
    }
    const nextOffset = offset + selected.length;
    return {
      matched_rows: matched,
      next_cursor: nextOffset < matched ? `fixture_${nextOffset}` : null,
      request_fingerprint: "analyticsquery_browser_fixture",
      rows: selected,
      scanned_rows: FIXTURE_ROW_COUNT,
      schema_version: "analytics-query-response-v1",
      snapshot_id: "analyticssnapshot_browser_100k_fixture",
    };
  }

  function stateText(value) {
    if (!value || typeof value !== "object") return "[missing]";
    if (value.state !== "value" && value.state !== "empty") {
      return `[${String(value.state || "unknown").replaceAll("_", " ")}]`;
    }
    if (value.state === "empty") return "[empty]";
    if (typeof value.value === "boolean") return value.value ? "Success" : "Failure";
    if (Array.isArray(value.value)) return value.value.join(", ");
    return String(value.value);
  }

  function formatCell(field, value) {
    const text = stateText(value);
    if (value?.state !== "value") return text;
    if (field === "score" && typeof value.value === "number") return value.value.toFixed(1);
    if (field === "time") return text.replace("T", " ").replace(".000Z", "Z");
    return text;
  }

  class AnalyticsVirtualGrid {
    constructor(root, query) {
      this.root = root;
      this.query = query;
      this.grid = root.querySelector("#analytics-grid");
      this.viewport = root.querySelector("#analytics-viewport");
      this.header = root.querySelector("#analytics-grid-header");
      this.rowsLayer = root.querySelector("#analytics-rows");
      this.spacer = root.querySelector("#analytics-spacer");
      this.status = root.querySelector("#analytics-status");
      this.empty = root.querySelector("#analytics-empty");
      this.error = root.querySelector("#analytics-error");
      this.loaded = root.querySelector("#analytics-loaded");
      this.matched = root.querySelector("#analytics-matched");
      this.snapshot = root.querySelector("#analytics-snapshot");
      this.loadMore = root.querySelector("#analytics-load-more");
      this.filterField = root.querySelector("#analytics-filter-field");
      this.filterValue = root.querySelector("#analytics-filter-value");
      this.applyFilter = root.querySelector("#analytics-apply-filter");
      this.sortField = root.querySelector("#analytics-sort-field");
      this.sortDirection = root.querySelector("#analytics-sort-direction");
      this.columnInputs = [...root.querySelectorAll("[data-analytics-column]")];
      this.rows = [];
      this.rowIds = new Set();
      this.nextCursor = null;
      this.matchedRows = 0;
      this.snapshotId = null;
      this.activeIndex = 0;
      this.generation = 0;
      this.inFlight = null;
      this.queryCount = 0;
      this.maxConcurrentQueries = 0;
      this.concurrentQueries = 0;
      this.preventedDuplicateFetches = 0;
      this.renderFrame = null;
      this.bind();
      this.renderHeader();
      this.render();
    }

    bind() {
      this.viewport.addEventListener("scroll", () => {
        if (this.renderFrame !== null) return;
        this.renderFrame = window.requestAnimationFrame(() => {
          this.renderFrame = null;
          this.renderRows();
        });
      });
      this.viewport.addEventListener("keydown", (event) => {
        if (event.target !== this.viewport || event.key !== "ArrowDown" || this.rows.length === 0) return;
        event.preventDefault();
        this.focusRow(this.activeIndex);
      });
      this.applyFilter.addEventListener("click", () => this.refresh());
      this.filterValue.addEventListener("keydown", (event) => {
        if (event.key === "Enter") this.refresh();
      });
      this.sortField.addEventListener("change", () => this.refresh());
      this.sortDirection.addEventListener("click", () => {
        const direction = this.sortDirection.dataset.direction === "desc" ? "asc" : "desc";
        this.sortDirection.dataset.direction = direction;
        this.sortDirection.textContent = direction === "desc" ? "↓" : "↑";
        this.sortDirection.setAttribute("aria-label", `Sort ${direction}ending`);
        this.refresh();
      });
      this.loadMore.addEventListener("click", () => this.loadNext());
      for (const input of this.columnInputs) {
        input.addEventListener("change", () => {
          if (this.visibleColumns().length === 0) {
            input.checked = true;
            return;
          }
          this.refresh();
        });
      }
    }

    visibleColumns() {
      const selected = new Set(
        this.columnInputs.filter((input) => input.checked).map((input) => input.value),
      );
      return columns.filter((column) => selected.has(column.field));
    }

    template() {
      return this.visibleColumns().map((column) => column.width).join(" ");
    }

    renderHeader() {
      this.header.replaceChildren();
      this.header.style.gridTemplateColumns = this.template();
      for (const column of this.visibleColumns()) {
        const cell = document.createElement("div");
        cell.setAttribute("role", "columnheader");
        cell.textContent = column.label;
        this.header.append(cell);
      }
      this.grid.setAttribute("aria-colcount", String(this.visibleColumns().length));
    }

    request(cursor) {
      const filterValue = this.filterValue.value.trim();
      const filters = filterValue
        ? [{ field: this.filterField.value, operator: "eq", value: filterValue }]
        : [];
      return {
        cursor,
        fields: this.visibleColumns().map((column) => column.field),
        filters,
        limit: PAGE_SIZE,
        schema_version: "analytics-query-request-v1",
        snapshot_id: this.snapshotId,
        sort: [{ direction: this.sortDirection.dataset.direction, field: this.sortField.value }],
      };
    }

    async refresh() {
      this.generation += 1;
      const generation = this.generation;
      this.rows = [];
      this.rowIds.clear();
      this.nextCursor = null;
      this.matchedRows = 0;
      this.snapshotId = null;
      this.activeIndex = 0;
      this.viewport.scrollTop = 0;
      this.renderHeader();
      this.render();
      if (this.inFlight) {
        this.preventedDuplicateFetches += 1;
        const previous = this.inFlight;
        return previous.finally(() => {
          if (generation === this.generation) return this.loadNext(generation);
          return null;
        });
      }
      return this.loadNext(generation);
    }

    async loadNext(generation = this.generation) {
      if (this.inFlight) {
        this.preventedDuplicateFetches += 1;
        return this.inFlight;
      }
      if (this.rows.length > 0 && !this.nextCursor) return null;
      const request = this.request(this.nextCursor);
      this.setBusy(true);
      this.queryCount += 1;
      this.concurrentQueries += 1;
      this.maxConcurrentQueries = Math.max(this.maxConcurrentQueries, this.concurrentQueries);
      this.inFlight = this.query(request)
        .then((response) => {
          if (generation !== this.generation) return;
          if (response.schema_version !== "analytics-query-response-v1") {
            throw new Error("Analytics response version mismatch");
          }
          if (this.snapshotId && this.snapshotId !== response.snapshot_id) {
            throw new Error("Analytics cursor changed immutable snapshot");
          }
          this.snapshotId = response.snapshot_id;
          for (const row of response.rows) {
            if (this.rowIds.has(row.row_id)) throw new Error("Analytics page repeated a row ID");
            this.rowIds.add(row.row_id);
            this.rows.push(row);
          }
          this.nextCursor = response.next_cursor;
          this.matchedRows = response.matched_rows;
          this.error.hidden = true;
          this.render();
        })
        .catch((error) => {
          if (generation !== this.generation) return;
          this.error.hidden = false;
          this.error.textContent = error instanceof Error ? error.message : "Analytics query failed closed";
          this.render();
        })
        .finally(() => {
          this.concurrentQueries -= 1;
          this.inFlight = null;
          this.setBusy(false);
          this.render();
        });
      return this.inFlight;
    }

    setBusy(busy) {
      this.grid.setAttribute("aria-busy", busy ? "true" : "false");
      this.loadMore.disabled = busy;
      if (busy) this.empty.hidden = true;
      this.status.textContent = busy ? "Loading analytics page" : "Analytics page ready";
    }

    rowHeight() {
      return document.body.classList.contains("comfortable") ? 48 : 40;
    }

    render() {
      this.loaded.textContent = this.rows.length.toLocaleString("en-US");
      this.matched.textContent = this.matchedRows.toLocaleString("en-US");
      this.snapshot.textContent = this.snapshotId ? this.snapshotId.slice(0, 28) : "No snapshot";
      this.grid.setAttribute("aria-rowcount", String(this.matchedRows + 1));
      this.empty.hidden = this.rows.length !== 0 || Boolean(this.inFlight) || !this.error.hidden;
      this.loadMore.hidden = !this.nextCursor;
      this.spacer.style.height = `${this.rows.length * this.rowHeight()}px`;
      this.renderRows();
    }

    renderRows() {
      const height = this.viewport.clientHeight || 360;
      const rowHeight = this.rowHeight();
      const start = Math.max(0, Math.floor(this.viewport.scrollTop / rowHeight) - OVERSCAN_ROWS);
      const count = Math.ceil(height / rowHeight) + OVERSCAN_ROWS * 2;
      const end = Math.min(this.rows.length, start + count);
      this.rowsLayer.replaceChildren();
      this.rowsLayer.style.gridTemplateColumns = this.template();
      for (let index = start; index < end; index += 1) {
        const row = document.createElement("div");
        row.className = "virtual-grid-row";
        row.dataset.rowIndex = String(index);
        row.setAttribute("role", "row");
        row.setAttribute("aria-rowindex", String(index + 2));
        row.tabIndex = index === this.activeIndex ? 0 : -1;
        row.style.height = `${rowHeight}px`;
        row.style.transform = `translateY(${index * rowHeight}px)`;
        row.style.gridTemplateColumns = this.template();
        for (const column of this.visibleColumns()) {
          const cell = document.createElement("div");
          const value = this.rows[index].values[column.field];
          cell.setAttribute("role", "gridcell");
          cell.dataset.state = value?.state || "missing";
          cell.textContent = formatCell(column.field, value);
          row.append(cell);
        }
        row.addEventListener("focus", () => {
          this.activeIndex = index;
        });
        row.addEventListener("keydown", (event) => this.handleRowKey(event, index));
        this.rowsLayer.append(row);
      }
      this.syncMetrics();
    }

    handleRowKey(event, index) {
      const page = Math.max(1, Math.floor(this.viewport.clientHeight / this.rowHeight()) - 1);
      const targets = {
        ArrowDown: index + 1,
        ArrowUp: index - 1,
        End: this.rows.length - 1,
        Home: 0,
        PageDown: index + page,
        PageUp: index - page,
      };
      if (!(event.key in targets)) return;
      event.preventDefault();
      this.focusRow(Math.max(0, Math.min(this.rows.length - 1, targets[event.key])));
    }

    focusRow(index) {
      if (this.rows.length === 0) return;
      this.activeIndex = index;
      const rowHeight = this.rowHeight();
      const top = index * rowHeight;
      if (top < this.viewport.scrollTop) this.viewport.scrollTop = top;
      if (top + rowHeight > this.viewport.scrollTop + this.viewport.clientHeight) {
        this.viewport.scrollTop = top - this.viewport.clientHeight + rowHeight;
      }
      this.renderRows();
      window.requestAnimationFrame(() => {
        this.rowsLayer.querySelector(`[data-row-index="${index}"]`)?.focus();
      });
    }

    metrics() {
      return {
        dom_rows: this.rowsLayer.childElementCount,
        loaded_rows: this.rows.length,
        matched_rows: this.matchedRows,
        max_concurrent_queries: this.maxConcurrentQueries,
        prevented_duplicate_fetches: this.preventedDuplicateFetches,
        query_count: this.queryCount,
        snapshot_id: this.snapshotId,
      };
    }

    syncMetrics() {
      const metrics = this.metrics();
      for (const [key, value] of Object.entries(metrics)) {
        const datasetKey = key.replace(/_([a-z])/g, (_match, letter) => letter.toUpperCase());
        if (value !== null) this.root.dataset[datasetKey] = String(value);
      }
    }
  }

  function createController(root, query) {
    return new AnalyticsVirtualGrid(root, query);
  }

  Object.defineProperty(window, "routeLabAnalytics", {
    configurable: false,
    enumerable: false,
    value: Object.freeze({ createController, syntheticAnalyticsQuery }),
    writable: false,
  });
})();
