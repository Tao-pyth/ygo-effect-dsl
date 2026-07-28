"use strict";

const WORKFLOW_VERSION = "desktop-workflow-v1";
const UI_LOCALE = "ja";
const UI_TEXT = Object.freeze({
  analyticsQueryFailed: "分析クエリはfail-closeしました",
  exportRequiresBridge: "version付き出力にはデスクトップブリッジが必要です",
  exportQueueFailed: "出力キューはfail-closeしました",
  exportStatusFailed: "出力状態の確認はfail-closeしました",
  exportCancelFailed: "出力の中止はfail-closeしました",
  bridgeReady: "デスクトップブリッジ準備完了",
  preflightPerRun: "実行ごとに事前検証",
  localDeckCatalog: "ローカルのデスクトップデッキカタログを表示中",
  registered: "登録済み",
  localCatalog: "ローカルカタログ",
  cardPrefix: "カード",
  presentationUnavailable: "表示情報なし",
  terminalPreference: "終端評価",
  defaultTerminalPreference: "既定の終端評価",
  profileCatalogUnavailable: "デスクトップのプロファイルカタログを利用できません。",
  positiveCardCode: "カードコードは正の整数で入力してください。",
  integerWeight: "重みは整数で入力してください。",
  profileLoadFailed: "プロファイルの読み込みはfail-closeしました。",
  profileCloneFailed: "プロファイルの複製はfail-closeしました。",
  profileCloned: "複製したプロファイルを選択しました。",
  ydkRequiresDesktop: "WindowsデスクトップシェルでYDKファイルを選択できます。",
  ydkImportFailed: "YDKの読み込みに失敗しました。",
  ydkRegistered: "YDKをローカルのデスクトップカタログへ登録しました。",
  inlineDeckRequiresBridge: "インラインデッキ登録にはWindowsデスクトップブリッジが必要です。",
  notRegistered: "未登録",
  inlineAddressed: "インラインデッキはデスクトップサービスで内容アドレス化されます。",
  inlineResearchDeck: "インライン研究デッキ",
  bridgeUnavailable: "ブリッジ未接続",
  inlineRegistrationDisabled: "ブラウザプレビューではインライン登録は無効です。",
  deckInputRejected: "デッキ入力を拒否しました",
  deckRegistrationFailed: "デッキ登録に失敗しました",
  inlineRegistered: "インラインデッキをローカルのデスクトップカタログへ登録しました。",
  main: "メイン",
  extra: "エクストラ",
  side: "サイド",
  invalidCardCode: "デッキに正の整数ではないカードコードが含まれています。",
  mainTooSmall: "メインデッキは40枚以上必要です。",
  mainTooLarge: "メインデッキは60枚以下にしてください。",
  extraTooLarge: "エクストラデッキは15枚以下にしてください。",
  sideTooLarge: "サイドデッキは15枚以下にしてください。",
  deckNameRequired: "デッキ名を入力してください。",
  preflightPassed: "事前検証に成功",
  registeredDeckPreflight: "登録済みデッキです。探索前にローカルサービスで再検証します。",
  staleAssetLock: "資産ロックが古い",
  staleAssetDetail: "ローカルソースを再検証するまで探索はブロックされます。",
  readyForPreflight: "事前検証待ち",
  validationBeforeWorker: "workerを開始する前に検証します。",
  assetLockMismatch: "想定された資産ロックがデッキmanifestと一致しません。workerは開始していません。",
  maxNodesInvalid: "max_nodesは1から100,000の範囲で指定してください。workerは開始していません。",
  poolSizeInvalid: "pool_sizeは1から8の範囲で指定してください。workerは開始していません。",
  noWorkerStarted: "workerは開始していません。",
  runningPreflight: "事前検証中",
  composingScenario: "シナリオを構成し、ローカル資産を検証しています。",
  localAssetValidationFailed: "ローカル資産検証はfail-closeしました。",
  scenarioPreflightFailed: "シナリオの事前検証はfail-closeしました。",
  terminalProfileCatalogFailed: "終端評価プロファイルカタログはfail-closeしました。",
  desktopSearchDispatchFailed: "デスクトップ探索のdispatchはfail-closeしました。",
  searchFailed: "探索に失敗しました",
  searchRejected: "探索を拒否しました",
  searchQueueFailed: "探索キューはfail-closeしました。",
  desktopCatalogFailed: "デスクトップカタログはfail-closeしました。",
  settingsBridgeIssue: "設定はデスクトップブリッジ issue #244 で接続されます。",
  queuedPreview: "synthetic preview adapter でキュー済み。実workerは開始していません。",
  previewCheckpoint: "プレビューcheckpoint",
  previewDeterministic: "semantic resultは決定論的なままです。実workerの実行は無効です。",
  syntheticReplayMatched: "synthetic fresh Replayが選択中のRoute IDと一致しました。結果を確認できます。",
  cancellationFailed: "中止はfail-closeしました。",
  cancellationRequested: "中止を要求しました。実行中workerの停止を待っています。",
  cancellationPollingFailed: "中止状態のpollingはfail-closeしました。",
  cancellationToast: "実行中のデスクトップworkerへ中止を要求しました。",
  syntheticJobCanceled: "synthetic jobを中止しました。artifactはcommitされていません。",
  committedRowsEmpty: "このartifactにはcommit済み行がありません。",
  candidatePaths: "候補経路",
  committedCandidateRows: "件のcommit済み候補行",
  topKRoutes: "Top-K経路",
  committedRanking: "commit済みranking",
  previewOnly: "プレビューのみ",
  browserPreview: "ブラウザプレビュー",
  preview: "プレビュー",
  previewRoute: "プレビュー経路",
  noCommittedArtifact: "commit済みdesktop artifactは読み込まれていません。",
  syntheticPreviewResult: "Synthetic preview result",
  realJobArtifactRequired: "実desktop jobは型付きjob artifact serviceから読み込む必要があります。",
  realJobReplayVerified: "実job / Replay検証済み",
  realJobReplayUnverified: "実job / Replay未検証",
  yes: "はい",
  no: "いいえ",
  preference: "評価",
  rule: "ルール",
  unknown: "不明",
  routeAction: "Route action",
  committedRouteEvent: "commit済みRoute event",
  terminalResult: "終端結果",
  bestObservedNotCertified: "best observedです。frontier exhaustionは証明されていません。",
  frontierCertified: "candidate accountingによりfrontier exhaustionを証明済みです。",
  candidate: "候補",
  resultUnavailable: "結果を利用できません",
  notLoaded: "not-loaded",
  blocked: "ブロック",
  unavailable: "利用不可",
  artifactVerificationFailed: "artifact検証に失敗しました",
  failClosedResult: "Fail-closed result",
  rendererDidNotSubstitute: "rendererはfixture値へ置き換えませんでした。",
  committedArtifactsUnavailable: "commit済みartifactを読み込めませんでした。",
  statusUnavailable: "状態を確認できません",
  replayStatusFailed: "Replay検証状態の確認はfail-closeしました。",
  replaySucceeded: "Replay検証に成功しました。",
  replayPollingFailed: "Replay検証pollingはfail-closeしました。",
  replayRequiresCommittedJob: "Replay検証にはcommit済みdesktop jobが必要です。",
  queueing: "キュー投入中",
  replayEnqueueFailed: "Replay検証のキュー投入はfail-closeしました。",
  replayQueued: "Replay検証をキューへ追加しました。",
});

let decks = [
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
  inlineDeckDialog: document.querySelector("#inline-deck-dialog"),
  inlineDeckForm: document.querySelector("#inline-deck-form"),
  inlineDeckName: document.querySelector("#inline-deck-name"),
  inlineMainCards: document.querySelector("#inline-main-cards"),
  inlineExtraCards: document.querySelector("#inline-extra-cards"),
  inlineSideCards: document.querySelector("#inline-side-cards"),
  inlineDeckStatus: document.querySelector("#inline-deck-status"),
  jobDialog: document.querySelector("#job-dialog"),
  cardDialog: document.querySelector("#card-dialog"),
  compareDialog: document.querySelector("#compare-dialog"),
  resultDialog: document.querySelector("#result-dialog"),
  resultEyebrow: document.querySelector("#result-eyebrow"),
  resultRouteId: document.querySelector("#result-route-id"),
  resultSuccess: document.querySelector("#result-success"),
  resultPeak: document.querySelector("#result-peak"),
  resultTerminal: document.querySelector("#result-terminal"),
  resultActions: document.querySelector("#result-actions"),
  resultEvidence: document.querySelector("#result-evidence"),
  resultCoverage: document.querySelector("#result-coverage"),
  resultCandidates: document.querySelector("#result-candidates"),
  resultExplored: document.querySelector("#result-explored"),
  resultCensored: document.querySelector("#result-censored"),
  resultVerificationState: document.querySelector("#result-verification-state"),
  verifyResult: document.querySelector("#verify-result"),
  resultDrilldown: document.querySelector("#result-drilldown"),
  resultDrilldownTitle: document.querySelector("#result-drilldown-title"),
  resultDrilldownSummary: document.querySelector("#result-drilldown-summary"),
  resultTabRanking: document.querySelector("#result-tab-ranking"),
  resultTabCandidates: document.querySelector("#result-tab-candidates"),
  resultDrilldownHead: document.querySelector("#result-drilldown-head"),
  resultDrilldownBody: document.querySelector("#result-drilldown-body"),
  resultRouteLine: document.querySelector("#result-route-line"),
  resultNoteTitle: document.querySelector("#result-note-title"),
  resultNoteDetail: document.querySelector("#result-note-detail"),
  searchForm: document.querySelector("#search-form"),
  searchDeckName: document.querySelector("#search-deck-name"),
  preflightBox: document.querySelector("#preflight-box"),
  queueSearch: document.querySelector("#queue-search"),
  experimentSummary: document.querySelector("#experiment-summary"),
  objective: document.querySelector("#objective"),
  openingHand: document.querySelector("#opening-hand"),
  fixedHandField: document.querySelector("#fixed-hand-field"),
  fixedHandCards: document.querySelector("#fixed-hand-cards"),
  conditionalCardField: document.querySelector("#conditional-card-field"),
  conditionalCardCode: document.querySelector("#conditional-card-code"),
  conditionalMinField: document.querySelector("#conditional-min-field"),
  conditionalMinCount: document.querySelector("#conditional-min-count"),
  conditionalMaxField: document.querySelector("#conditional-max-field"),
  conditionalMaxCount: document.querySelector("#conditional-max-count"),
  conditionalAttemptsField: document.querySelector("#conditional-attempts-field"),
  conditionalMaxAttempts: document.querySelector("#conditional-max-attempts"),
  preferenceProfile: document.querySelector("#preference-profile"),
  profileEditStatus: document.querySelector("#profile-edit-status"),
  preferenceProfileName: document.querySelector("#preference-profile-name"),
  preferenceRuleCard: document.querySelector("#preference-rule-card"),
  preferenceRuleLocation: document.querySelector("#preference-rule-location"),
  preferenceRulePosition: document.querySelector("#preference-rule-position"),
  preferenceRuleWeight: document.querySelector("#preference-rule-weight"),
  cloneProfile: document.querySelector("#clone-profile"),
  interruptionToggle: document.querySelector("#interruption-toggle"),
  interruptionField: document.querySelector("#interruption-card-field"),
  interruptionCode: document.querySelector("#interruption-code"),
  maxNodes: document.querySelector("#max-nodes"),
  maxDepth: document.querySelector("#max-depth"),
  maxSeconds: document.querySelector("#max-seconds"),
  poolSize: document.querySelector("#pool-size"),
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
  workspace: document.querySelector("#workspace"),
  catalogMetrics: document.querySelector("#catalog-metrics"),
  catalogSourceLabel: document.querySelector("#catalog-source-label"),
  catalogPane: document.querySelector(".catalog-pane"),
  detailPane: document.querySelector("#detail-pane"),
  analyticsPane: document.querySelector("#analytics-pane"),
  environmentLabel: document.querySelector("#environment-label"),
  environmentCode: document.querySelector("#environment-code"),
};

let selectedDeck = decks[0];
let preflightValid = false;
let jobTimer = null;
let toastTimer = null;
let currentExperiment = null;
let currentJobId = null;
let currentJobState = null;
let currentReplayJobId = null;
let replayTimer = null;
let currentResultView = null;
let currentResultTab = "ranking";
let preferenceProfilesLoaded = false;

function desktopBridgeAvailable() {
  return Boolean(window.routeLabBridge && window.routeLabBridge.available());
}

async function executeAnalyticsQuery(request) {
  if (!desktopBridgeAvailable()) {
    return window.routeLabAnalytics.syntheticAnalyticsQuery(request);
  }
  const response = await window.routeLabBridge.invoke("analytics.query", { request });
  if (!response.ok) {
    const diagnostic = response.diagnostics[0];
    throw new Error(diagnostic?.message || "Analytics query failed closed");
  }
  return response.result;
}

const analyticsExportJobs = Object.freeze({
  async enqueue(payload) {
    if (!desktopBridgeAvailable()) {
      throw new Error("Desktop bridge is required for versioned exports");
    }
    const response = await window.routeLabBridge.invoke("analytics.export.enqueue", payload);
    if (!response.ok) throw new Error(response.diagnostics[0]?.message || "Export queue failed closed");
    return response.result;
  },
  async status(jobId) {
    const response = await window.routeLabBridge.invoke("job.status", { job_id: jobId });
    if (!response.ok) throw new Error(response.diagnostics[0]?.message || "Export status failed closed");
    return response.result;
  },
  async cancel(jobId) {
    const response = await window.routeLabBridge.invoke("job.cancel", { job_id: jobId });
    if (!response.ok) throw new Error(response.diagnostics[0]?.message || "Export cancellation failed closed");
    return response.result;
  },
});

const analyticsController = window.routeLabAnalytics.createController(
  elements.analyticsPane,
  executeAnalyticsQuery,
  analyticsExportJobs,
);

function markDesktopEnvironment() {
  elements.environmentLabel.textContent = "Desktop bridge ready";
  elements.environmentCode.textContent = "preflight per run";
  elements.catalogSourceLabel.textContent = "Showing the local desktop deck catalog";
}

function bridgeDeck(record) {
  return {
    id: record.deck_id,
    name: record.name,
    hash: record.deck_sha256.slice(0, 8),
    tags: [record.source, record.status],
    main: record.main_count,
    extra: record.extra_count,
    side: record.side_count,
    source: record.source,
    status: "registered",
    statusLabel: "Registered",
    runs: 0,
    success: 0,
    best: 0,
    terminal: 0,
    updated: "Local catalog",
    updatedOrder: 5,
    chart: [["Random", 0], ["Beam", 0], ["MCTS", 0]],
    cards: record.card_counts.slice(0, 30).map((item) => ({
      code: item.card_code,
      name: `Card ${item.card_code}`,
      count: item.count,
      type: "Presentation unavailable",
      attribute: "-",
      stats: "-",
    })),
    recentRuns: [],
  };
}

async function refreshDesktopCatalog() {
  if (!desktopBridgeAvailable()) return;
  markDesktopEnvironment();
  const response = await window.routeLabBridge.invoke("deck.catalog", {});
  if (!response.ok) {
    showToast(response.diagnostics[0]?.message || "Desktop deck catalog failed.");
    return;
  }
  decks = response.result.decks.map(bridgeDeck);
  if (decks.length === 0) {
    selectedDeck = null;
    elements.catalogMetrics.hidden = true;
    elements.detailPane.hidden = true;
    elements.workspace.classList.add("catalog-only");
    renderDecks();
    return;
  }
  selectedDeck = decks[0];
  elements.catalogMetrics.hidden = false;
  elements.detailPane.hidden = false;
  elements.workspace.classList.remove("catalog-only");
  renderDecks();
  updateDetail(selectedDeck);
}

function renderPreferenceProfiles(records) {
  const selected = elements.preferenceProfile.value;
  elements.preferenceProfile.replaceChildren();
  records.forEach((record) => {
    const profile = record.profile || record;
    const option = document.createElement("option");
    option.value = profile.profile_id || "";
    option.textContent = profile.name || profile.profile_id || "Terminal preference";
    elements.preferenceProfile.append(option);
  });
  if (selected && [...elements.preferenceProfile.options].some((option) => option.value === selected)) {
    elements.preferenceProfile.value = selected;
  }
  elements.preferenceProfile.disabled = records.length === 0;
  elements.cloneProfile.disabled = !desktopBridgeAvailable() || records.length === 0;
}

async function refreshPreferenceProfiles() {
  if (!desktopBridgeAvailable()) {
    renderPreferenceProfiles([{ profile: { name: "Default terminal preference", profile_id: "" } }]);
    elements.preferenceProfile.disabled = true;
    return;
  }
  const response = await window.routeLabBridge.invoke("profile.list", {});
  if (!response.ok) {
    showToast(response.diagnostics[0]?.message || "Terminal preference catalog failed.");
    renderPreferenceProfiles([{ profile: { name: "Default terminal preference", profile_id: "" } }]);
    elements.preferenceProfile.disabled = true;
    return;
  }
  renderPreferenceProfiles(response.result.profiles || []);
  preferenceProfilesLoaded = true;
}

async function clonePreferenceProfile() {
  if (!desktopBridgeAvailable() || !elements.preferenceProfile.value) {
    elements.profileEditStatus.textContent = "Desktop profile catalog is unavailable.";
    return;
  }
  const cardCode = Number(elements.preferenceRuleCard.value);
  const weight = Number(elements.preferenceRuleWeight.value);
  if (!Number.isInteger(cardCode) || cardCode < 1) {
    elements.profileEditStatus.textContent = "Card code must be a positive integer.";
    elements.preferenceRuleCard.focus();
    return;
  }
  if (!Number.isInteger(weight)) {
    elements.profileEditStatus.textContent = "Weight must be an integer.";
    elements.preferenceRuleWeight.focus();
    return;
  }
  const current = await window.routeLabBridge.invoke("profile.get", {
    profile_id: elements.preferenceProfile.value,
  });
  if (!current.ok) {
    elements.profileEditStatus.textContent = current.diagnostics[0]?.message || "Profile load failed closed.";
    return;
  }
  const source = current.result.profile.profile;
  const location = elements.preferenceRuleLocation.value;
  const position = elements.preferenceRulePosition.value;
  const rule = {
    card_code: cardCode,
    controller: 0,
    enabled: true,
    location,
    max_count: null,
    min_count: 1,
    position,
    rule_id: `desktop-rule-${cardCode}-${location}-${position}-${Date.now()}`,
    scoring_mode: "once",
    weight,
  };
  const response = await window.routeLabBridge.invoke("profile.clone", {
    name: elements.preferenceProfileName.value.trim() || `${source.name} edited`,
    profile_id: source.profile_id,
    rules: [...source.rules, rule],
  });
  if (!response.ok) {
    elements.profileEditStatus.textContent = response.diagnostics[0]?.message || "Profile clone failed closed.";
    return;
  }
  const profileId = response.result.profile.profile_id;
  await refreshPreferenceProfiles();
  elements.preferenceProfile.value = profileId;
  elements.profileEditStatus.textContent = "Cloned profile selected.";
  invalidatePreflight();
  updateExperimentSummary();
}

async function importDesktopYdk() {
  if (!desktopBridgeAvailable()) {
    showToast("Native YDK file selection is available in the Windows desktop shell.");
    return;
  }
  const response = await window.routeLabBridge.invoke("deck.import_ydk", {});
  if (!response.ok) {
    showToast(response.diagnostics[0]?.message || "YDK import failed.");
    return;
  }
  if (response.result.cancelled) return;
  await refreshDesktopCatalog();
  showToast("YDK registered in the local desktop catalog.");
}

function setInlineDeckStatus(kind, title, detail) {
  elements.inlineDeckStatus.className = `diagnostic ${kind}`;
  elements.inlineDeckStatus.replaceChildren();
  const body = document.createElement("div");
  body.append(textElement("strong", title), textElement("span", detail));
  elements.inlineDeckStatus.append(body);
}

function openInlineDeckDialog() {
  if (!desktopBridgeAvailable()) {
    showToast("Inline deck registration requires the Windows desktop bridge.");
    return;
  }
  elements.inlineDeckForm.reset();
  setInlineDeckStatus(
    "warning",
    "Not registered",
    "Inline decks are content-addressed by the desktop service.",
  );
  elements.inlineDeckDialog.showModal();
}

function inlineDeckPayload() {
  return {
    extra: parseCardCodeList(elements.inlineExtraCards.value),
    main: parseCardCodeList(elements.inlineMainCards.value),
    name: elements.inlineDeckName.value.trim() || "Inline research deck",
    side: parseCardCodeList(elements.inlineSideCards.value),
  };
}

function inlineDeckInputError(payload) {
  const sections = [
    ["main", payload.main],
    ["extra", payload.extra],
    ["side", payload.side],
  ];
  for (const [section, cards] of sections) {
    if (cards.some((card) => !Number.isInteger(card) || card < 1)) {
      return `${section} deck contains a non-positive or non-integer card code.`;
    }
  }
  if (payload.main.length < 40 || payload.main.length > 60) {
    return "main deck must contain 40 to 60 cards.";
  }
  if (payload.extra.length > 15) return "extra deck must contain at most 15 cards.";
  if (payload.side.length > 15) return "side deck must contain at most 15 cards.";
  return null;
}

async function registerInlineDeck() {
  if (!desktopBridgeAvailable()) {
    setInlineDeckStatus("error", "Bridge unavailable", "Inline registration is disabled in browser preview.");
    return;
  }
  const payload = inlineDeckPayload();
  const inputError = inlineDeckInputError(payload);
  if (inputError) {
    setInlineDeckStatus("error", "Deck input rejected", inputError);
    return;
  }
  const response = await window.routeLabBridge.invoke("deck.register_inline", payload);
  if (!response.ok) {
    setInlineDeckStatus(
      "error",
      "Deck registration failed",
      response.diagnostics[0]?.message || "The desktop service rejected this deck.",
    );
    return;
  }
  const deckId = response.result.deck.deck_id;
  await refreshDesktopCatalog();
  selectDeck(deckId);
  elements.inlineDeckDialog.close();
  showToast("Inline deck registered in the local desktop catalog.");
}

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
    if (selectedDeck && deck.id === selectedDeck.id) row.classList.add("is-selected");

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
  } else if (deck.status === "registered") {
    summary.className = "diagnostic warning";
    title.textContent = "Preflight required";
    description.textContent = "DB, Lua scripts, asset lock, and deck shape are checked for each search.";
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
  currentExperiment = null;
  elements.queueSearch.disabled = true;
  elements.preflightBox.className = "preflight-box";
  elements.preflightBox.querySelector("strong").textContent = "Ready for preflight";
  elements.preflightBox.querySelector("span").textContent = "Validation runs before any worker is started.";
}

function selectedStrategy() {
  return document.querySelector('input[name="strategy"]:checked').value;
}

function parseCardCodeList(value) {
  const tokens = value.split(/[,\s]+/).map((item) => item.trim()).filter(Boolean);
  return tokens.map((item) => Number(item));
}

function updateOpeningHandFields() {
  const mode = elements.openingHand.value;
  const fixed = mode === "fixed";
  const conditional = mode === "conditional";
  elements.fixedHandField.hidden = !fixed;
  elements.conditionalCardField.hidden = !conditional;
  elements.conditionalMinField.hidden = !conditional;
  elements.conditionalMaxField.hidden = !conditional;
  elements.conditionalAttemptsField.hidden = !conditional;
}

function openingHandConfiguration() {
  const mode = elements.openingHand.value;
  if (mode === "fixed") {
    return {
      cards: parseCardCodeList(elements.fixedHandCards.value),
      mode: "fixed",
    };
  }
  if (mode === "conditional") {
    const condition = {
      code: Number(elements.conditionalCardCode.value),
      min_count: Number(elements.conditionalMinCount.value || 0),
    };
    if (elements.conditionalMaxCount.value) {
      condition.max_count = Number(elements.conditionalMaxCount.value);
    }
    return {
      conditions: [condition],
      max_attempts: Number(elements.conditionalMaxAttempts.value || 10000),
      mode: "conditional",
      seed: Number(elements.seed.value),
      size: 5,
    };
  }
  return { mode: "random", seed: Number(elements.seed.value), size: 5 };
}

function openingHandInputError() {
  const mode = elements.openingHand.value;
  if (mode === "fixed") {
    const cards = parseCardCodeList(elements.fixedHandCards.value);
    if (!cards.length || cards.some((card) => !Number.isInteger(card) || card < 1)) {
      return "Fixed hand requires one or more positive card codes.";
    }
  }
  if (mode === "conditional") {
    const code = Number(elements.conditionalCardCode.value);
    const minCount = Number(elements.conditionalMinCount.value || 0);
    const maxCount = elements.conditionalMaxCount.value
      ? Number(elements.conditionalMaxCount.value)
      : null;
    const attempts = Number(elements.conditionalMaxAttempts.value || 10000);
    if (!Number.isInteger(code) || code < 1) return "Conditional hand requires a positive card code.";
    if (!Number.isInteger(minCount) || minCount < 0) return "Conditional min count must be zero or greater.";
    if (maxCount !== null && (!Number.isInteger(maxCount) || maxCount < minCount)) {
      return "Conditional max count must be greater than or equal to min count.";
    }
    if (!Number.isInteger(attempts) || attempts < 1 || attempts > 100000) {
      return "Conditional max attempts must be between 1 and 100,000.";
    }
  }
  return null;
}

function updateExperimentSummary() {
  elements.experimentSummary.textContent = `${selectedStrategy()} · seed ${elements.seed.value || "-"} · pool ${elements.poolSize.value || "1"} · ${Number(elements.maxNodes.value || 0).toLocaleString("en-US")} nodes`;
}

function searchConfiguration() {
  return {
    interruption_card_code: elements.interruptionToggle.checked ? Number(elements.interruptionCode.value) : null,
    max_depth: Number(elements.maxDepth.value),
    max_nodes: Number(elements.maxNodes.value),
    max_seconds: Number(elements.maxSeconds.value),
    opening_hand: openingHandConfiguration(),
    pool_size: Number(elements.poolSize.value),
    preference_profile_id: elements.preferenceProfile.value || null,
    scenario_preset_id: elements.objective.value,
    seed: Number(elements.seed.value),
    strategy: selectedStrategy(),
  };
}

async function runPreflight() {
  const title = elements.preflightBox.querySelector("strong");
  const detail = elements.preflightBox.querySelector("span");
  if (!desktopBridgeAvailable() && selectedDeck.status !== "ready") {
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
  if (Number(elements.poolSize.value) < 1 || Number(elements.poolSize.value) > 8) {
    elements.preflightBox.className = "preflight-box is-invalid";
    title.textContent = "Pool size is outside the desktop limit";
    detail.textContent = "pool_size must be between 1 and 8. No worker started.";
    elements.queueSearch.disabled = true;
    return;
  }
  const openingError = openingHandInputError();
  if (openingError) {
    elements.preflightBox.className = "preflight-box is-invalid";
    title.textContent = "Opening hand is invalid";
    detail.textContent = `${openingError} No worker started.`;
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
  if (desktopBridgeAvailable()) {
    elements.queueSearch.disabled = true;
    title.textContent = "Running preflight";
    detail.textContent = "The Python service is validating Experiment 0.4 and pinned local assets.";
    const composed = await window.routeLabBridge.invoke("scenario.compose_search", {
      configuration: searchConfiguration(),
      deck_id: selectedDeck.id,
    });
    if (!composed.ok) {
      elements.preflightBox.className = "preflight-box is-invalid";
      title.textContent = "Configuration failure";
      detail.textContent = composed.diagnostics[0]?.message || "Experiment composition failed.";
      return;
    }
    currentExperiment = composed.result.experiment;
    const checked = await window.routeLabBridge.invoke("scenario.preflight", {
      deck_id: selectedDeck.id,
      experiment: currentExperiment,
    });
    if (!checked.ok || !checked.result.preflight.ok) {
      elements.preflightBox.className = "preflight-box is-invalid";
      title.textContent = "Preflight failed";
      detail.textContent = checked.diagnostics[0]?.message
        || checked.result?.preflight?.diagnostics?.[0]?.message
        || "Local asset validation failed closed.";
      currentExperiment = null;
      return;
    }
  }
  preflightValid = true;
  elements.preflightBox.className = "preflight-box is-valid";
  title.textContent = "Preflight passed";
  detail.textContent = "Fixture manifest, deck shape, strategy, seed, pool policy, and budgets are valid.";
  elements.queueSearch.disabled = false;
}

function openSearch() {
  elements.searchDeckName.textContent = selectedDeck.name;
  if (!preferenceProfilesLoaded) {
    refreshPreferenceProfiles()
      .then(updateExperimentSummary)
      .catch(() => showToast("Terminal preference catalog failed closed."));
  }
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
  window.clearTimeout(jobTimer);
  clearReplayVerificationTimer();
  jobTimer = null;
  currentJobId = null;
  currentJobState = "queued";
  currentReplayJobId = null;
  elements.progress.value = 0;
  elements.progress.textContent = "0%";
  elements.jobTitle.textContent = "Replaying frontier nodes";
  elements.jobNodes.textContent = `0 / ${Number(elements.maxNodes.value).toLocaleString("en-US")}`;
  elements.jobReplays.textContent = "0";
  elements.jobScore.textContent = "0.0";
  elements.jobElapsed.textContent = "0.0s";
  elements.jobLog.textContent = desktopBridgeAvailable()
    ? "Queued in the local SQLite catalog. Waiting for the desktop worker lease."
    : "Queued through synthetic preview adapter. No real worker has started.";
  elements.cancelJob.hidden = false;
  elements.cancelJob.disabled = false;
  elements.viewResult.hidden = true;
}

function finishDesktopJob(snapshot) {
  const state = snapshot.job.state;
  currentJobState = state;
  const checkpoint = snapshot.latest_checkpoint;
  const completed = checkpoint?.completed_units || 0;
  const total = checkpoint?.total_units || Number(elements.maxNodes.value);
  const replayCount = checkpoint?.payload?.replays;
  elements.jobNodes.textContent = `${completed.toLocaleString("en-US")} / ${total.toLocaleString("en-US")}`;
  elements.jobReplays.textContent = Number.isInteger(replayCount)
    ? replayCount.toLocaleString("en-US")
    : "-";
  elements.jobElapsed.textContent = `attempt ${snapshot.job.attempt}/${snapshot.job.max_attempts}`;
  if (checkpoint && total > 0) {
    const percent = Math.min(100, Math.round((completed * 100) / total));
    elements.progress.value = percent;
    elements.progress.textContent = `${percent}%`;
  } else if (state === "running") {
    elements.progress.removeAttribute("value");
  }
  elements.jobTitle.textContent = state === "running" ? "Replaying frontier nodes" : `Search ${state}`;
  elements.jobLog.textContent = snapshot.job.error_message
    || (checkpoint ? `Checkpoint: ${checkpoint.recovery_position}` : `Job state: ${state}`);
  if (state === "succeeded") {
    elements.progress.value = 100;
    elements.progress.textContent = "100%";
    elements.cancelJob.hidden = true;
    elements.viewResult.hidden = false;
    elements.viewResult.focus();
    return true;
  }
  if (["cancelled", "failed", "quarantined"].includes(state)) {
    elements.cancelJob.hidden = true;
    return true;
  }
  return false;
}

async function pollDesktopJob() {
  if (!currentJobId) return;
  const response = await window.routeLabBridge.invoke("job.status", { job_id: currentJobId });
  if (!response.ok) {
    elements.jobLog.textContent = response.diagnostics[0]?.message || "Job status failed closed.";
    return;
  }
  if (!finishDesktopJob(response.result)) {
    jobTimer = window.setTimeout(() => {
      pollDesktopJob().catch(() => {
        elements.jobLog.textContent = "Job status polling failed closed.";
      });
    }, 500);
  }
}

async function startDesktopJob() {
  if (!preflightValid || !currentExperiment) return;
  closeSearch();
  resetJob();
  elements.jobDialog.showModal();
  replaceHash(`view=job&deck=${encodeURIComponent(selectedDeck.id)}`);
  const response = await window.routeLabBridge.invoke("job.enqueue_search", {
    deck_id: selectedDeck.id,
    experiment: currentExperiment,
    idempotency_key: `desktop-${currentExperiment.experiment_id}-${Date.now()}`,
    priority: 0,
  });
  if (!response.ok) {
    elements.jobTitle.textContent = "Search rejected";
    elements.jobLog.textContent = response.diagnostics[0]?.message || "Search queue failed closed.";
    elements.cancelJob.hidden = true;
    return;
  }
  currentJobId = response.result.job.job_id;
  elements.jobLog.textContent = `Queued ${currentJobId}. Waiting for the desktop worker lease.`;
  await pollDesktopJob();
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

async function cancelJob() {
  window.clearInterval(jobTimer);
  window.clearTimeout(jobTimer);
  jobTimer = null;
  if (desktopBridgeAvailable() && currentJobId) {
    if (["succeeded", "cancelled", "failed", "quarantined"].includes(currentJobState)) {
      elements.jobDialog.close();
      return;
    }
    const response = await window.routeLabBridge.invoke("job.cancel", { job_id: currentJobId });
    if (!response.ok) {
      elements.jobLog.textContent = response.diagnostics[0]?.message || "Cancellation failed closed.";
      return;
    }
    const terminal = finishDesktopJob({ ...response.result, latest_checkpoint: null });
    if (!terminal) {
      elements.cancelJob.disabled = true;
      elements.jobLog.textContent = "Cancellation requested. Waiting for the active worker to stop.";
      jobTimer = window.setTimeout(() => {
        pollDesktopJob().catch(() => {
          elements.jobLog.textContent = "Cancellation status polling failed closed.";
        });
      }, 250);
    }
    showToast("Cancellation requested from the active desktop worker.");
    return;
  }
  if (desktopBridgeAvailable()) {
    elements.jobDialog.close();
    replaceHash(`deck=${encodeURIComponent(selectedDeck.id)}`);
    return;
  }
  elements.jobDialog.close();
  replaceHash(`deck=${encodeURIComponent(selectedDeck.id)}`);
  showToast("Synthetic job canceled. No artifact was committed.");
}

function renderResultRows(rows) {
  elements.resultRouteLine.replaceChildren();
  rows.slice(0, 100).forEach((row, index) => {
    const item = document.createElement("li");
    const ordinal = String(index + 1).padStart(2, "0");
    const body = document.createElement("div");
    body.append(textElement("strong", row.title), textElement("small", row.detail));
    item.append(textElement("span", ordinal), body);
    elements.resultRouteLine.append(item);
  });
}

function renderResultEvidence(searchRun) {
  const evidence = searchRun?.candidate_evidence;
  const coverage = searchRun?.coverage;
  const counts = evidence?.candidate_counts;
  if (!counts || !coverage) {
    elements.resultEvidence.hidden = true;
    elements.resultCoverage.textContent = "-";
    elements.resultCandidates.textContent = "0";
    elements.resultExplored.textContent = "0";
    elements.resultCensored.textContent = "0";
    return;
  }
  elements.resultEvidence.hidden = false;
  elements.resultCoverage.textContent = coverage.coverage_status || "best_observed";
  elements.resultCandidates.textContent = String(counts.total ?? evidence.total ?? 0);
  elements.resultExplored.textContent = String(counts.explored ?? 0);
  elements.resultCensored.textContent = String(counts.censored ?? 0);
}

function clearReplayVerificationTimer() {
  window.clearTimeout(replayTimer);
  replayTimer = null;
}

function setResultVerificationState(state, canVerify) {
  elements.resultVerificationState.textContent = state || "unverified";
  elements.verifyResult.hidden = !desktopBridgeAvailable() || !currentJobId;
  elements.verifyResult.disabled = !canVerify;
}

function resultCell(value) {
  const cell = document.createElement("td");
  cell.textContent = value === null || value === undefined || value === "" ? "-" : String(value);
  return cell;
}

function renderResultTable(headers, rows) {
  elements.resultDrilldownHead.replaceChildren();
  elements.resultDrilldownBody.replaceChildren();
  if (!headers.length) {
    return;
  }
  headers.forEach((header) => {
    const cell = document.createElement("th");
    cell.textContent = header;
    elements.resultDrilldownHead.append(cell);
  });
  if (!rows.length) {
    const empty = document.createElement("tr");
    const cell = document.createElement("td");
    cell.colSpan = headers.length;
    cell.textContent = "No committed rows in this artifact.";
    empty.append(cell);
    elements.resultDrilldownBody.append(empty);
    return;
  }
  rows.slice(0, 100).forEach((row) => {
    const item = document.createElement("tr");
    row.forEach((value) => item.append(resultCell(value)));
    elements.resultDrilldownBody.append(item);
  });
}

function renderResultDrilldown(view) {
  currentResultView = view;
  const ranking = view?.search_run?.route_ranking;
  const rankedRoutes = Array.isArray(ranking?.ranked_routes) ? ranking.ranked_routes : [];
  const candidates = Array.isArray(view?.search_run?.candidate_evidence?.candidates)
    ? view.search_run.candidate_evidence.candidates
    : [];
  if (!rankedRoutes.length && !candidates.length) {
    elements.resultDrilldown.hidden = true;
    renderResultTable([], []);
    return;
  }
  elements.resultDrilldown.hidden = false;
  elements.resultTabRanking.setAttribute("aria-selected", currentResultTab === "ranking" ? "true" : "false");
  elements.resultTabCandidates.setAttribute("aria-selected", currentResultTab === "candidates" ? "true" : "false");
  if (currentResultTab === "candidates") {
    elements.resultDrilldownTitle.textContent = "Candidate paths";
    elements.resultDrilldownSummary.textContent = `${candidates.length} committed candidate rows`;
    renderResultTable(
      ["Status", "Depth", "Action", "Prefix", "Parent"],
      candidates.map((candidate) => [
        candidate.status,
        candidate.depth,
        candidate.action_id,
        candidate.prefix_id,
        candidate.parent_prefix_id,
      ]),
    );
    return;
  }
  elements.resultDrilldownTitle.textContent = "Top-K routes";
  elements.resultDrilldownSummary.textContent = ranking?.ranking_id || "committed ranking";
  renderResultTable(
    ["Rank", "Route", "Terminal", "Reliability", "Random", "Actions"],
    rankedRoutes.map((route) => [
      route.rank,
      route.route_id,
      route.terminal_composite_score,
      route.gameplay_reliability,
      route.gameplay_random_event_count,
      route.action_count,
    ]),
  );
}

function renderPreviewResult() {
  clearReplayVerificationTimer();
  currentReplayJobId = null;
  currentResultView = null;
  elements.resultEyebrow.textContent = "Browser preview";
  elements.resultRouteId.textContent = "preview-only";
  elements.resultSuccess.textContent = "Preview";
  elements.resultPeak.textContent = "0";
  elements.resultTerminal.textContent = "0";
  elements.resultActions.textContent = "0";
  setResultVerificationState("preview only", false);
  renderResultEvidence(null);
  elements.resultDrilldown.hidden = true;
  renderResultTable([], []);
  renderResultRows([
    {
      title: "Preview route",
      detail: "No committed desktop artifact loaded.",
    },
  ]);
  elements.resultNoteTitle.textContent = "Synthetic preview result";
  elements.resultNoteDetail.textContent = "Real desktop jobs must load through the typed job artifact service.";
}

function renderVerifiedResult(view) {
  clearReplayVerificationTimer();
  currentReplayJobId = null;
  currentResultTab = "ranking";
  const verificationState = view.result_truth.verification_state || "unverified";
  elements.resultEyebrow.textContent = view.result_truth.verification_state === "verified"
    ? "Real job / replay verified"
    : "Real job / unverified replay";
  elements.resultRouteId.textContent = view.route.route_id;
  elements.resultSuccess.textContent = view.route.success ? "Yes" : "No";
  elements.resultPeak.textContent = String(view.score.peak ?? "-");
  elements.resultTerminal.textContent = String(view.score.terminal_composite ?? "-");
  elements.resultActions.textContent = String(view.route.action_count);
  setResultVerificationState(verificationState, verificationState !== "verified");
  renderResultEvidence(view.search_run);
  renderResultDrilldown(view);
  const preferenceRows = Array.isArray(view.score.preference)
    ? view.score.preference.map((component) => ({
      title: `Preference ${component.rule_id || "rule"}`,
      detail: `${component.match_status || "unknown"} / ${component.applied_value ?? 0}`,
    }))
    : [];
  const actionRows = view.route.actions.length
    ? view.route.actions.map((action) => ({
      title: action.decision_kind || action.action_id || "Route action",
      detail: action.state_hash_after
        ? `state ${action.state_hash_after}`
        : "committed Route event",
    }))
    : [{
      title: view.search_run.termination_reason || "Terminal result",
      detail: view.search_run.best_observed
        ? "Best observed; frontier exhaustion is not certified."
        : "Frontier exhaustion certified by candidate accounting.",
    }];
  const candidateRows = Array.isArray(view.search_run.candidate_evidence?.candidates)
    ? view.search_run.candidate_evidence.candidates.slice(0, 8).map((candidate) => ({
      title: `Candidate ${candidate.action_id || "action"}`,
      detail: `${candidate.status || "unknown"} / depth ${candidate.depth ?? "-"}`,
    }))
    : [];
  const rows = [...preferenceRows, ...actionRows, ...candidateRows];
  renderResultRows(rows);
  elements.resultNoteTitle.textContent = "Committed artifact result";
  elements.resultNoteDetail.textContent = `${view.artifacts.route.schema_version} / ${view.artifact_set_id}`;
}

function renderResultError(message) {
  clearReplayVerificationTimer();
  currentReplayJobId = null;
  currentResultView = null;
  elements.resultEyebrow.textContent = "Result unavailable";
  elements.resultRouteId.textContent = "not-loaded";
  elements.resultSuccess.textContent = "Blocked";
  elements.resultPeak.textContent = "-";
  elements.resultTerminal.textContent = "-";
  elements.resultActions.textContent = "-";
  setResultVerificationState("unavailable", false);
  renderResultEvidence(null);
  elements.resultDrilldown.hidden = true;
  renderResultTable([], []);
  renderResultRows([{ title: "Artifact verification failed", detail: message }]);
  elements.resultNoteTitle.textContent = "Fail-closed result";
  elements.resultNoteDetail.textContent = "The renderer did not substitute a fixture value.";
}

async function openResult() {
  elements.jobDialog.close();
  if (!desktopBridgeAvailable() || !currentJobId) {
    renderPreviewResult();
    elements.resultDialog.showModal();
    replaceHash(`view=result&deck=${encodeURIComponent(selectedDeck.id)}`);
    return;
  }
  const response = await window.routeLabBridge.invoke("job.result", { job_id: currentJobId });
  if (response.ok) {
    renderVerifiedResult(response.result);
  } else {
    renderResultError(response.diagnostics[0]?.message || "Committed artifacts could not be loaded.");
  }
  elements.resultDialog.showModal();
  replaceHash(`view=result&deck=${encodeURIComponent(selectedDeck.id)}`);
}

async function pollReplayVerification() {
  if (!currentReplayJobId) return;
  const response = await window.routeLabBridge.invoke("job.status", { job_id: currentReplayJobId });
  if (!response.ok) {
    setResultVerificationState("status unavailable", Boolean(currentJobId));
    showToast(response.diagnostics[0]?.message || "Replay verification status failed closed.");
    return;
  }
  const state = response.result.job.state;
  if (state === "succeeded") {
    setResultVerificationState("verified", false);
    elements.resultEyebrow.textContent = "Real job / replay verified";
    showToast("Replay verification succeeded.");
    return;
  }
  if (["cancelled", "failed", "quarantined"].includes(state)) {
    setResultVerificationState(state, Boolean(currentJobId));
    showToast(`Replay verification ${state}.`);
    return;
  }
  setResultVerificationState(state, false);
  replayTimer = window.setTimeout(() => {
    pollReplayVerification().catch(() => {
      setResultVerificationState("status unavailable", Boolean(currentJobId));
      showToast("Replay verification polling failed closed.");
    });
  }, 750);
}

async function enqueueReplayVerification() {
  if (!desktopBridgeAvailable() || !currentJobId) {
    setResultVerificationState("preview only", false);
    showToast("Replay verification requires a committed desktop job.");
    return;
  }
  clearReplayVerificationTimer();
  setResultVerificationState("queueing", false);
  const response = await window.routeLabBridge.invoke("job.enqueue_replay_verification", {
    search_job_id: currentJobId,
    idempotency_key: `replay-verification-${currentJobId}`,
    priority: 5,
  });
  if (!response.ok) {
    setResultVerificationState("unavailable", true);
    showToast(response.diagnostics[0]?.message || "Replay verification enqueue failed closed.");
    return;
  }
  currentReplayJobId = response.result.job.job_id;
  setResultVerificationState(response.result.source?.verification_state || response.result.job.state || "queued", false);
  showToast("Replay verification queued.");
  await pollReplayVerification();
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
  showWorkspaceView(view === "runs" ? "runs" : "decks", false);
  if (view === "search") openSearch();
  if (view === "compare") elements.compareDialog.showModal();
}

function setRailCurrent(view) {
  document.querySelectorAll(".rail-item").forEach((button) => {
    const selected = button.dataset.view === view;
    button.classList.toggle("is-active", selected);
    if (selected) button.setAttribute("aria-current", "page");
    else button.removeAttribute("aria-current");
  });
}

function showWorkspaceView(view, updateHash = true) {
  const analyticsActive = view === "runs";
  elements.catalogPane.hidden = analyticsActive;
  elements.detailPane.hidden = analyticsActive;
  elements.analyticsPane.hidden = !analyticsActive;
  elements.workspace.classList.toggle("analytics-active", analyticsActive);
  setRailCurrent(analyticsActive ? "runs" : "decks");
  if (analyticsActive && analyticsController.metrics().query_count === 0) {
    analyticsController.refresh();
  }
  if (updateHash) {
    replaceHash(
      analyticsActive ? "view=runs" : `deck=${encodeURIComponent(selectedDeck?.id || "")}`,
    );
  }
}

elements.filter.addEventListener("input", renderDecks);
elements.sort.addEventListener("change", renderDecks);
document.querySelectorAll("[data-density]").forEach((button) => {
  button.addEventListener("click", () => {
    document.querySelectorAll("[data-density]").forEach((candidate) => {
      const selected = candidate.dataset.density === button.dataset.density;
      candidate.classList.toggle("is-selected", selected);
      candidate.setAttribute("aria-pressed", selected ? "true" : "false");
    });
    document.body.classList.toggle("comfortable", button.dataset.density === "comfortable");
    analyticsController.render();
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
      showWorkspaceView("runs");
      return;
    }
    if (view === "decks") {
      showWorkspaceView("decks");
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
document.querySelector("#run-preflight").addEventListener("click", () => {
  runPreflight().catch(() => {
    invalidatePreflight();
    showToast("Scenario preflight failed closed.");
  });
});
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
  if (desktopBridgeAvailable()) {
    startDesktopJob().catch(() => {
      elements.jobTitle.textContent = "Search failed";
      elements.jobLog.textContent = "Desktop search dispatch failed closed.";
    });
  } else {
    startSyntheticJob();
  }
});
elements.interruptionToggle.addEventListener("change", () => {
  elements.interruptionField.hidden = !elements.interruptionToggle.checked;
  if (elements.interruptionToggle.checked) elements.interruptionCode.focus();
});
elements.openingHand.addEventListener("change", () => {
  updateOpeningHandFields();
  if (elements.openingHand.value === "fixed") elements.fixedHandCards.focus();
  if (elements.openingHand.value === "conditional") elements.conditionalCardCode.focus();
});
elements.cloneProfile.addEventListener("click", () => {
  clonePreferenceProfile().catch(() => {
    elements.profileEditStatus.textContent = "Profile clone failed closed.";
  });
});

elements.cancelJob.addEventListener("click", () => {
  cancelJob().catch(() => showToast("Cancellation failed closed."));
});
elements.viewResult.addEventListener("click", () => {
  openResult().catch(() => {
    renderResultError("Committed artifacts could not be loaded.");
    elements.resultDialog.showModal();
  });
});
elements.verifyResult.addEventListener("click", () => {
  enqueueReplayVerification().catch(() => {
    setResultVerificationState("unavailable", Boolean(currentJobId));
    showToast("Replay verification enqueue failed closed.");
  });
});
elements.resultTabRanking.addEventListener("click", () => {
  currentResultTab = "ranking";
  if (currentResultView) renderResultDrilldown(currentResultView);
});
elements.resultTabCandidates.addEventListener("click", () => {
  currentResultTab = "candidates";
  if (currentResultView) renderResultDrilldown(currentResultView);
});
elements.jobDialog.addEventListener("cancel", (event) => {
  event.preventDefault();
  cancelJob().catch(() => showToast("Cancellation failed closed."));
});
elements.searchDialog.addEventListener("close", () => {
  if (!elements.jobDialog.open) replaceHash(`deck=${encodeURIComponent(selectedDeck.id)}`);
});
elements.inlineDeckDialog.addEventListener("close", () => {
  if (selectedDeck) replaceHash(`deck=${encodeURIComponent(selectedDeck.id)}`);
});
elements.compareDialog.addEventListener("close", () => {
  replaceHash(`deck=${encodeURIComponent(selectedDeck.id)}`);
});
elements.resultDialog.addEventListener("close", () => {
  clearReplayVerificationTimer();
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
document.querySelector("#close-inline-deck").addEventListener("click", () => elements.inlineDeckDialog.close());
document.querySelector("#cancel-inline-deck").addEventListener("click", () => elements.inlineDeckDialog.close());
elements.inlineDeckForm.addEventListener("submit", (event) => {
  event.preventDefault();
  registerInlineDeck().catch(() => {
    setInlineDeckStatus("error", "Deck registration failed", "Desktop bridge registration failed closed.");
  });
});

document.querySelector("#import-deck").addEventListener("click", () => {
  importDesktopYdk().catch(() => showToast("Desktop YDK import failed closed."));
});
document.querySelector("#new-inline").addEventListener("click", () => openInlineDeckDialog());

document.documentElement.dataset.workflowVersion = WORKFLOW_VERSION;
updateOpeningHandFields();
initializeFromHash();
window.addEventListener("routelabbridgeready", () => {
  refreshDesktopCatalog().catch(() => showToast("Desktop catalog failed closed."));
  refreshPreferenceProfiles().catch(() => showToast("Terminal preference catalog failed closed."));
  if (!elements.analyticsPane.hidden) analyticsController.refresh();
});
refreshPreferenceProfiles().catch(() => showToast("Terminal preference catalog failed closed."));
refreshDesktopCatalog().catch(() => showToast("Desktop catalog failed closed."));
