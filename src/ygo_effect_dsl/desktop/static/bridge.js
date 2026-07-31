"use strict";

(() => {
  const VERSION = "desktop-bridge-v1";
  const methods = new Set([
    "analytics.compare",
    "analytics.export.enqueue",
    "analytics.query",
    "card.get",
    "deck.card_options",
    "deck.catalog",
    "deck.import_ydk",
    "deck.metadata.get",
    "deck.metadata.update",
    "deck.profile.archive",
    "deck.profile.create",
    "deck.profile.get",
    "deck.profile.list",
    "deck.profile.update",
    "deck.register_inline",
    "job.cancel",
    "job.enqueue_replay_verification",
    "job.enqueue_search",
    "job.result",
    "job.status",
    "profile.clone",
    "profile.get",
    "profile.list",
    "scenario.compose_search",
    "scenario.preflight",
    "settings.get",
    "settings.reset",
    "settings.update",
    "system.describe",
    "system.external_asset_status",
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
