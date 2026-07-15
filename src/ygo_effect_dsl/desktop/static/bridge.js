"use strict";

(() => {
  const VERSION = "desktop-bridge-v1";
  const methods = new Set([
    "analytics.compare",
    "analytics.query",
    "card.get",
    "deck.catalog",
    "deck.import_ydk",
    "deck.register_inline",
    "job.cancel",
    "job.enqueue_search",
    "job.status",
    "scenario.compose_search",
    "scenario.preflight",
    "system.describe",
  ]);
  let sequence = 0;
  let ready = Boolean(window.pywebview && window.pywebview.api);

  window.addEventListener("pywebviewready", () => {
    ready = true;
    window.dispatchEvent(new CustomEvent("routelabbridgeready"));
  });

  async function invoke(method, payload = {}) {
    if (!methods.has(method)) throw new Error("Unsupported desktop bridge method");
    if (!ready || !window.pywebview || !window.pywebview.api) {
      throw new Error("Desktop bridge is unavailable in the browser fixture adapter");
    }
    sequence += 1;
    const response = await window.pywebview.api.invoke({
      method,
      payload,
      request_id: `renderer-${sequence}`,
      version: VERSION,
    });
    if (!response || response.schema_version !== "desktop-bridge-response-v1") {
      throw new Error("Desktop bridge response version mismatch");
    }
    return response;
  }

  Object.defineProperty(window, "routeLabBridge", {
    configurable: false,
    enumerable: false,
    value: Object.freeze({
      available: () => ready,
      invoke,
      methods: Object.freeze([...methods]),
      version: VERSION,
    }),
    writable: false,
  });
})();
