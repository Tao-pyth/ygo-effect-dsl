"use strict";

const WORKFLOW_VERSION = "desktop-workflow-v1";

const decks = [
  {
    id: "short-route",
    name: "Short route fixture",
    hash: "a72f91c8",
    tags: ["qualified", "short", "baseline"],
    main: 40,
    extra: 15,
    side: 0,
    source: "inline",
    status: "ready",
    statusLabel: "Ready",
    runs: 4280,
    success: 84.2,
    best: 18.6,
    terminal: 14.1,
    updated: "12 min ago",
    updatedOrder: 4,
    chart: [
      ["Random", 84.2],
      ["Beam", 88.7],
      ["MCTS", 86.1],
    ],
    cards: [
      { code: 10000, name: "Synthetic Relay Alpha", count: 3, type: "Effect", attribute: "Light", stats: "1800 / 1200" },
      { code: 10001, name: "Synthetic Relay Beta", count: 3, type: "Quick-Play", attribute: "-", stats: "-" },
      { code: 10002, name: "Synthetic Relay Gate", count: 2, type: "Trap", attribute: "-", stats: "-" },
    ],
    recentRuns: [
      ["Random · seed 42017", "Success · score 18.6", "02:14"],
      ["Beam · seed 912", "Success · score 19.2", "Yesterday"],
      ["MCTS · seed 6601", "Budget reached · score 17.4", "Yesterday"],
    ],
  },
  {
    id: "long-chain",
    name: "Long chain fixture",
    hash: "88d14be2",
    tags: ["qualified", "chain", "long"],
    main: 44,
    extra: 15,
    side: 6,
    source: "ydk",
    status: "ready",
    statusLabel: "Ready",
    runs: 3650,
    success: 71.8,
    best: 22.4,
    terminal: 17.9,
    updated: "1 hr ago",
    updatedOrder: 3,
    chart: [
      ["Random", 71.8],
      ["Beam", 77.4],
      ["MCTS", 79.1],
    ],
    cards: [
      { code: 11000, name: "Synthetic Chain Node", count: 3, type: "Effect", attribute: "Dark", stats: "1600 / 1000" },
      { code: 11001, name: "Synthetic Chain Link", count: 2, type: "Continuous", attribute: "-", stats: "-" },
      { code: 11002, name: "Synthetic Chain Guard", count: 3, type: "Counter", attribute: "-", stats: "-" },
    ],
    recentRuns: [
      ["MCTS · seed 773", "Success · score 22.4", "03:05"],
      ["Beam · seed 114", "Success · score 21.7", "Yesterday"],
      ["Random · seed 801", "Max nodes · score 18.9", "2 days ago"],
    ],
  },
  {
    id: "grave-banish",
    name: "Grave / banish fixture",
    hash: "d3196af4",
    tags: ["qualified", "graveyard", "banish"],
    main: 42,
    extra: 12,
    side: 0,
    source: "inline",
    status: "ready",
    statusLabel: "Ready",
    runs: 3180,
    success: 66.5,
    best: 20.8,
    terminal: 13.6,
    updated: "Yesterday",
    updatedOrder: 2,
    chart: [
      ["Random", 66.5],
      ["Beam", 70.2],
      ["MCTS", 72.8],
    ],
    cards: [
      { code: 12000, name: "Synthetic Archive Unit", count: 3, type: "Effect", attribute: "Earth", stats: "1400 / 1800" },
      { code: 12001, name: "Synthetic Exile Path", count: 3, type: "Normal", attribute: "-", stats: "-" },
      { code: 12002, name: "Synthetic Return Trace", count: 2, type: "Trap", attribute: "-", stats: "-" },
    ],
    recentRuns: [
      ["Beam · seed 234", "Success · score 20.8", "Yesterday"],
      ["Random · seed 120", "Legal stop · score 16.2", "2 days ago"],
      ["MCTS · seed 990", "Success · score 19.7", "2 days ago"],
    ],
  },
  {
    id: "recovery-probe",
    name: "Recovery probe",
    hash: "f741e3a0",
    tags: ["recovery", "interrupted", "review"],
    main: 40,
    extra: 15,
    side: 3,
    source: "ydk",
    status: "stale",
    statusLabel: "Stale lock",
    runs: 1370,
    success: 42.1,
    best: 13.4,
    terminal: 8.2,
    updated: "4 days ago",
    updatedOrder: 1,
    chart: [
      ["Random", 42.1],
      ["Beam", 48.6],
      ["MCTS", 50.4],
    ],
    cards: [
      { code: 13000, name: "Synthetic Recovery Unit", count: 3, type: "Effect", attribute: "Water", stats: "1200 / 2000" },
      { code: 13001, name: "Synthetic Recovery Plan", count: 2, type: "Normal", attribute: "-", stats: "-" },
      { code: 13002, name: "Synthetic Interrupt Trace", count: 3, type: "Trap", attribute: "-", stats: "-" },
    ],
    recentRuns: [
      ["Random · seed 184", "Configuration failure", "4 days ago"],
      ["Beam · seed 725", "Path failure · score 9.1", "5 days ago"],
      ["MCTS · seed 402", "Success · score 13.4", "5 days ago"],
    ],
  },
];

const elements = {
  tableBody: document.querySelector("#deck-table-body"),
  empty: document.querySelector("#empty-state"),
  count: document.querySelector("#visible-count"),
  filter: document.querySelector("#deck-filter"),
  sort: document.querySelector("#deck-sort"),
  detailTitle: document.querySelector("#detail-title"),
  detailHash: document.querySelector("#detail-hash"),
  detailStatus: document.querySelector("#detail-status"),
  mainCount: document.querySelector("#main-count"),
  extraCount: document.querySelector("#extra-count"),
  sideCount: document.querySelector("#side-count"),
  sourceKind: document.querySelector("#source-kind"),
  detailSuccess: document.querySelector("#detail-success"),
  detailPeak: document.querySelector("#detail-peak"),
  detailTerminal: document.querySelector("#detail-terminal"),
  chart: document.querySelector("#bar-chart"),
  cards: document.querySelector("#card-list"),
  runs: document.querySelector("#run-list"),
  preflightSummary: document.querySelector("#preflight-summary"),
  searchDialog: document.querySelector("#search-dialog"),
  jobDialog: document.querySelector("#job-dialog"),
  cardDialog: document.querySelector("#card-dialog"),
  compareDialog: document.querySelector("#compare-dialog"),
  resultDialog: document.querySelector("#result-dialog"),
  searchForm: document.querySelector("#search-form"),
  searchDeckName: document.querySelector("#search-deck-name"),
  preflightBox: document.querySelector("#preflight-box"),
  queueSearch: document.querySelector("#queue-search"),
  experimentSummary: document.querySelector("#experiment-summary"),
  interruptionToggle: document.querySelector("#interruption-toggle"),
  interruptionField: document.querySelector("#interruption-card-field"),
  interruptionCode: document.querySelector("#interruption-code"),
  maxNodes: document.querySelector("#max-nodes"),
  seed: document.querySelector("#seed"),
  progress: document.querySelector("#job-progress"),
  jobTitle: document.querySelector("#job-title"),
  jobNodes: document.querySelector("#job-nodes"),
  jobReplays: document.querySelector("#job-replays"),
  jobScore: document.querySelector("#job-score"),
  jobElapsed: document.querySelector("#job-elapsed"),
  jobLog: document.querySelector("#job-log"),
  cancelJob: document.querySelector("#cancel-job"),
  viewResult: document.querySelector("#view-result"),
  toast: document.querySelector("#toast"),
};

let selectedDeck = decks[0];
let preflightValid = false;
let jobTimer = null;
let toastTimer = null;

function textElement(tag, text, className = "") {
  const element = document.createElement(tag);
  element.textContent = text;
  if (className) element.className = className;
  return element;
}

function statusClass(deck) {
  return deck.status === "ready" ? "success" : "warning";
}

function sortedDecks() {
  const query = elements.filter.value.trim().toLowerCase();
  const filtered = decks.filter((deck) => {
    const haystack = [deck.name, deck.hash, ...deck.tags].join(" ").toLowerCase();
    return haystack.includes(query);
  });
  const mode = elements.sort.value;
  return filtered.sort((left, right) => {
    if (mode === "name") return left.name.localeCompare(right.name);
    if (mode === "runs") return right.runs - left.runs;
    if (mode === "success") return right.success - left.success;
    return right.updatedOrder - left.updatedOrder;
  });
}

function renderDecks() {
  const visible = sortedDecks();
  elements.tableBody.replaceChildren();
  elements.count.textContent = String(visible.length);
  elements.empty.hidden = visible.length !== 0;
  for (const deck of visible) {
    const row = document.createElement("tr");
    row.dataset.deckId = deck.id;
    if (deck.id === selectedDeck.id) row.classList.add("is-selected");

    const nameCell = document.createElement("td");
    const nameButton = document.createElement("button");
    nameButton.type = "button";
    nameButton.className = "deck-name-button";
    nameButton.append(textElement("strong", deck.name), textElement("span", deck.hash));
    nameButton.addEventListener("click", () => selectDeck(deck.id));
    nameCell.append(nameButton);
    row.append(nameCell);

    row.append(textElement("td", `${deck.main + deck.extra + deck.side}`));
    const statusCell = document.createElement("td");
    statusCell.append(textElement("span", deck.statusLabel, `status-chip ${statusClass(deck)}`));
    row.append(statusCell);
    row.append(textElement("td", deck.runs.toLocaleString("en-US")));
    row.append(textElement("td", `${deck.success.toFixed(1)}%`));
    row.append(textElement("td", deck.best.toFixed(1)));
    row.append(textElement("td", deck.updated));
    elements.tableBody.append(row);
  }
}

function renderChart(deck) {
  elements.chart.replaceChildren();
  for (const [label, value] of deck.chart) {
    const row = document.createElement("div");
    row.className = "bar-row";
    const progress = document.createElement("progress");
    progress.max = 100;
    progress.value = value;
    progress.setAttribute("aria-label", `${label} success ${value.toFixed(1)} percent`);
    row.append(textElement("span", label), progress, textElement("strong", `${value.toFixed(1)}%`));
    elements.chart.append(row);
  }
}

function renderCards(deck) {
  elements.cards.replaceChildren();
  for (const card of deck.cards) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "card-button";
    const identity = document.createElement("span");
    identity.append(textElement("strong", card.name), textElement("small", `Code ${card.code} · ${card.type}`));
    button.append(identity, textElement("b", `×${card.count}`));
    button.addEventListener("click", () => openCard(card));
    elements.cards.append(button);
  }
}

function renderRuns(deck) {
  elements.runs.replaceChildren();
  for (const [identity, outcome, when] of deck.recentRuns) {
    const item = document.createElement("li");
    const body = document.createElement("div");
    body.append(textElement("strong", identity), textElement("small", outcome));
    item.append(body, textElement("small", when));
    elements.runs.append(item);
  }
}

function updateDetail(deck) {
  elements.detailTitle.textContent = deck.name;
  elements.detailHash.textContent = deck.hash;
  elements.detailStatus.textContent = deck.statusLabel;
  elements.detailStatus.className = `status-chip ${statusClass(deck)}`;
  elements.mainCount.textContent = String(deck.main);
  elements.extraCount.textContent = String(deck.extra);
  elements.sideCount.textContent = String(deck.side);
  elements.sourceKind.textContent = deck.source;
  elements.detailSuccess.textContent = `${deck.success.toFixed(1)}%`;
  elements.detailPeak.textContent = deck.best.toFixed(1);
  elements.detailTerminal.textContent = deck.terminal.toFixed(1);
  renderChart(deck);
  renderCards(deck);
  renderRuns(deck);

  const summary = elements.preflightSummary;
  const title = summary.querySelector("strong");
  const description = summary.querySelector("span");
  if (deck.status === "ready") {
    summary.className = "diagnostic success";
    title.textContent = "Preflight passed";
    description.textContent = "DB, Lua scripts, asset lock, and deck shape verified.";
  } else {
    summary.className = "diagnostic warning";
    title.textContent = "Asset lock is stale";
    description.textContent = "Search remains blocked until the local source is revalidated.";
  }
}

function replaceHash(value) {
  if (window.history && window.history.replaceState) {
    window.history.replaceState(null, "", `#${value}`);
  }
}

function selectDeck(id) {
  const deck = decks.find((candidate) => candidate.id === id);
  if (!deck) return;
  selectedDeck = deck;
  renderDecks();
  updateDetail(deck);
  replaceHash(`deck=${encodeURIComponent(deck.id)}`);
}

function activateTab(tabName) {
  const tabs = ["overview", "cards", "runs"];
  for (const name of tabs) {
    const button = document.querySelector(`#tab-${name}`);
    const panel = document.querySelector(`#panel-${name}`);
    const active = name === tabName;
    button.setAttribute("aria-selected", active ? "true" : "false");
    panel.hidden = !active;
  }
}

function showToast(message) {
  window.clearTimeout(toastTimer);
  elements.toast.textContent = message;
  elements.toast.hidden = false;
  toastTimer = window.setTimeout(() => {
    elements.toast.hidden = true;
  }, 2600);
}

function invalidatePreflight() {
  preflightValid = false;
  elements.queueSearch.disabled = true;
  elements.preflightBox.className = "preflight-box";
  elements.preflightBox.querySelector("strong").textContent = "Ready for preflight";
  elements.preflightBox.querySelector("span").textContent = "Validation runs before any worker is started.";
}

function selectedStrategy() {
  return document.querySelector('input[name="strategy"]:checked').value;
}

function updateExperimentSummary() {
  elements.experimentSummary.textContent = `${selectedStrategy()} · seed ${elements.seed.value || "-"} · ${Number(elements.maxNodes.value || 0).toLocaleString("en-US")} nodes`;
}

function runPreflight() {
  const title = elements.preflightBox.querySelector("strong");
  const detail = elements.preflightBox.querySelector("span");
  if (selectedDeck.status !== "ready") {
    elements.preflightBox.className = "preflight-box is-invalid";
    title.textContent = "Configuration failure";
    detail.textContent = "Expected asset lock does not match this deck manifest. No worker started.";
    elements.queueSearch.disabled = true;
    return;
  }
  if (Number(elements.maxNodes.value) < 1 || Number(elements.maxNodes.value) > 100000) {
    elements.preflightBox.className = "preflight-box is-invalid";
    title.textContent = "Budget is outside the MVP limit";
    detail.textContent = "max_nodes must be between 1 and 100,000. No worker started.";
    elements.queueSearch.disabled = true;
    return;
  }
  if (elements.interruptionToggle.checked && !elements.interruptionCode.value) {
    elements.preflightBox.className = "preflight-box is-invalid";
    title.textContent = "Interruption card is required";
    detail.textContent = "Specify a positive card code. No effect or timing is inferred.";
    elements.queueSearch.disabled = true;
    return;
  }
  preflightValid = true;
  elements.preflightBox.className = "preflight-box is-valid";
  title.textContent = "Preflight passed";
  detail.textContent = "Fixture manifest, deck shape, strategy, seed, and budgets are valid.";
  elements.queueSearch.disabled = false;
}

function openSearch() {
  elements.searchDeckName.textContent = selectedDeck.name;
  invalidatePreflight();
  updateExperimentSummary();
  elements.searchDialog.showModal();
  replaceHash(`view=search&deck=${encodeURIComponent(selectedDeck.id)}`);
}

function closeSearch() {
  elements.searchDialog.close();
  replaceHash(`deck=${encodeURIComponent(selectedDeck.id)}`);
}

function resetJob() {
  window.clearInterval(jobTimer);
  jobTimer = null;
  elements.progress.value = 0;
  elements.progress.textContent = "0%";
  elements.jobTitle.textContent = "Replaying frontier nodes";
  elements.jobNodes.textContent = `0 / ${Number(elements.maxNodes.value).toLocaleString("en-US")}`;
  elements.jobReplays.textContent = "0";
  elements.jobScore.textContent = "0.0";
  elements.jobElapsed.textContent = "0.0s";
  elements.jobLog.textContent = "Queued through synthetic preview adapter. No real worker has started.";
  elements.cancelJob.hidden = false;
  elements.viewResult.hidden = true;
}

function startSyntheticJob() {
  if (!preflightValid) return;
  closeSearch();
  resetJob();
  elements.jobDialog.showModal();
  replaceHash(`view=job&deck=${encodeURIComponent(selectedDeck.id)}`);
  const steps = [8, 23, 41, 64, 82, 100];
  let index = 0;
  const maxNodes = Number(elements.maxNodes.value);
  jobTimer = window.setInterval(() => {
    const percent = steps[index];
    const nodes = Math.round((maxNodes * percent) / 100);
    elements.progress.value = percent;
    elements.progress.textContent = `${percent}%`;
    elements.jobNodes.textContent = `${nodes.toLocaleString("en-US")} / ${maxNodes.toLocaleString("en-US")}`;
    elements.jobReplays.textContent = Math.max(1, Math.round(nodes * 0.72)).toLocaleString("en-US");
    elements.jobScore.textContent = (18.6 * (percent / 100)).toFixed(1);
    elements.jobElapsed.textContent = `${(index * 0.7 + 0.6).toFixed(1)}s`;
    elements.jobLog.textContent = `Preview checkpoint ${index + 1}/${steps.length}: semantic result remains deterministic; real worker execution is disabled.`;
    index += 1;
    if (index === steps.length) {
      window.clearInterval(jobTimer);
      jobTimer = null;
      elements.jobTitle.textContent = "Best route verified";
      elements.jobLog.textContent = "Synthetic fresh Replay matched the selected Route identity. Ready to inspect result.";
      elements.cancelJob.hidden = true;
      elements.viewResult.hidden = false;
      elements.viewResult.focus();
    }
  }, 360);
}

function cancelJob() {
  window.clearInterval(jobTimer);
  jobTimer = null;
  elements.jobDialog.close();
  replaceHash(`deck=${encodeURIComponent(selectedDeck.id)}`);
  showToast("Synthetic job canceled. No artifact was committed.");
}

function openResult() {
  elements.jobDialog.close();
  elements.resultDialog.showModal();
  replaceHash(`view=result&deck=${encodeURIComponent(selectedDeck.id)}`);
}

function openCard(card) {
  document.querySelector("#card-code").textContent = `Code ${card.code}`;
  document.querySelector("#card-title").textContent = card.name;
  const metadata = document.querySelector("#card-metadata");
  metadata.replaceChildren();
  for (const [label, value] of [["Type", card.type], ["Attribute", card.attribute], ["ATK / DEF", card.stats], ["Locale", "en"]]) {
    const group = document.createElement("div");
    group.append(textElement("dt", label), textElement("dd", value));
    metadata.append(group);
  }
  elements.cardDialog.showModal();
}

function initializeFromHash() {
  const params = new URLSearchParams(window.location.hash.slice(1));
  const deckId = params.get("deck");
  if (deckId && decks.some((deck) => deck.id === deckId)) {
    selectedDeck = decks.find((deck) => deck.id === deckId);
  }
  renderDecks();
  updateDetail(selectedDeck);
  const view = params.get("view");
  if (view === "search") openSearch();
  if (view === "compare") elements.compareDialog.showModal();
}

elements.filter.addEventListener("input", renderDecks);
elements.sort.addEventListener("change", renderDecks);
document.querySelectorAll("[data-density]").forEach((button) => {
  button.addEventListener("click", () => {
    document.querySelectorAll("[data-density]").forEach((candidate) => {
      const selected = candidate === button;
      candidate.classList.toggle("is-selected", selected);
      candidate.setAttribute("aria-pressed", selected ? "true" : "false");
    });
    document.body.classList.toggle("comfortable", button.dataset.density === "comfortable");
  });
});

document.querySelectorAll("[role='tab']").forEach((tab) => {
  tab.addEventListener("click", () => activateTab(tab.id.replace("tab-", "")));
  tab.addEventListener("keydown", (event) => {
    if (!['ArrowLeft', 'ArrowRight'].includes(event.key)) return;
    const tabs = [...document.querySelectorAll("[role='tab']")];
    const direction = event.key === 'ArrowRight' ? 1 : -1;
    const index = (tabs.indexOf(tab) + direction + tabs.length) % tabs.length;
    event.preventDefault();
    tabs[index].focus();
  });
});

document.querySelectorAll(".rail-item").forEach((button) => {
  button.addEventListener("click", () => {
    const view = button.dataset.view;
    if (view === "compare") {
      elements.compareDialog.showModal();
      replaceHash(`view=compare&deck=${encodeURIComponent(selectedDeck.id)}`);
      return;
    }
    if (view === "runs") {
      activateTab("runs");
      showToast("Recent runs opened for the selected deck.");
      return;
    }
    if (view === "decks") {
      activateTab("overview");
      document.querySelector("#workspace").focus({ preventScroll: true });
      return;
    }
    showToast("Settings are connected by desktop bridge issue #244.");
  });
});

document.querySelector("#open-search").addEventListener("click", openSearch);
document.querySelector("#close-search").addEventListener("click", closeSearch);
document.querySelector("#cancel-search").addEventListener("click", closeSearch);
document.querySelector("#run-preflight").addEventListener("click", runPreflight);
elements.searchForm.addEventListener("input", () => {
  invalidatePreflight();
  updateExperimentSummary();
});
elements.searchForm.addEventListener("change", () => {
  invalidatePreflight();
  updateExperimentSummary();
});
elements.searchForm.addEventListener("submit", (event) => {
  event.preventDefault();
  startSyntheticJob();
});
elements.interruptionToggle.addEventListener("change", () => {
  elements.interruptionField.hidden = !elements.interruptionToggle.checked;
  if (elements.interruptionToggle.checked) elements.interruptionCode.focus();
});

elements.cancelJob.addEventListener("click", cancelJob);
elements.viewResult.addEventListener("click", openResult);
elements.jobDialog.addEventListener("cancel", (event) => {
  event.preventDefault();
  cancelJob();
});
elements.searchDialog.addEventListener("close", () => {
  if (!elements.jobDialog.open) replaceHash(`deck=${encodeURIComponent(selectedDeck.id)}`);
});
elements.compareDialog.addEventListener("close", () => {
  replaceHash(`deck=${encodeURIComponent(selectedDeck.id)}`);
});
elements.resultDialog.addEventListener("close", () => {
  replaceHash(`deck=${encodeURIComponent(selectedDeck.id)}`);
});
document.querySelector("#close-card").addEventListener("click", () => elements.cardDialog.close());
document.querySelector("#close-compare").addEventListener("click", () => {
  elements.compareDialog.close();
  replaceHash(`deck=${encodeURIComponent(selectedDeck.id)}`);
});
document.querySelector("#close-result").addEventListener("click", () => {
  elements.resultDialog.close();
  replaceHash(`deck=${encodeURIComponent(selectedDeck.id)}`);
});

document.querySelector("#import-deck").addEventListener("click", () => showToast("Native YDK file selection is connected by issue #244."));
document.querySelector("#new-inline").addEventListener("click", () => showToast("Inline deck registration is connected by issue #244."));

document.documentElement.dataset.workflowVersion = WORKFLOW_VERSION;
initializeFromHash();
