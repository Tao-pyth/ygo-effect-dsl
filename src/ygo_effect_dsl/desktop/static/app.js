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
  profileCatalogUnavailable: "デッキ別プロファイルカタログを利用できません。",
  profilePageNoDeck: "デッキを選択してください。",
  profilePageNoCards: "このデッキには選択可能な日本語カード名がありません。",
  profilePageDeckRequired: "先に対象デッキを選択してください。",
  profileNameRequired: "プロファイル名を入力してください。",
  profileCardRequired: "デッキ内カードを選択してください。",
  integerWeight: "重みは整数で入力してください。",
  integerMinCount: "最小枚数は1以上の整数で入力してください。",
  integerMaxCount: "最大枚数は空欄、または最小枚数以上の整数で入力してください。",
  profileLoadFailed: "プロファイルの読み込みはfail-closeしました。",
  profileSaveFailed: "プロファイル保存はfail-closeしました。",
  profileSaved: "プロファイルを保存しました。",
  profileArchived: "プロファイルをアーカイブしました。",
  profileArchiveFailed: "プロファイルのアーカイブはfail-closeしました。",
  profileRuleAdded: "終端評価ルールを追加しました。",
  profileRuleRemoved: "終端評価ルールを削除しました。",
  deckCardOptionsFailed: "デッキ内カード候補の読み込みはfail-closeしました。",
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
  readyDeckVerified: "DB、Luaスクリプト、資産ロック、デッキ形状を確認済みです。",
  preflightRequired: "事前検証が必要",
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
  externalAssetSetupRequired: "外部資産セットアップが必要",
  externalAssetSetupReady: "外部資産検証済み",
  settingsLoadFailed: "設定の読み込みはfail-closeしました。",
  settingsSaved: "設定を保存しました。外部資産rootの変更は次回起動で有効です。",
  settingsSaveFailed: "設定の保存はfail-closeしました。",
  settingsReset: "設定をresetしました。",
  scenarioPreflightFailed: "シナリオの事前検証はfail-closeしました。",
  terminalProfileCatalogFailed: "終端評価プロファイルカタログはfail-closeしました。",
  desktopSearchDispatchFailed: "デスクトップ探索のdispatchはfail-closeしました。",
  searchFailed: "探索に失敗しました",
  searchRejected: "探索を拒否しました",
  searchQueueFailed: "探索キューはfail-closeしました。",
  jobStatusFailed: "ジョブ状態の確認はfail-closeしました。",
  jobPollingFailed: "ジョブ状態のpollingはfail-closeしました。",
  desktopCatalogFailed: "デスクトップカタログはfail-closeしました。",
  noDeckSelected: "デッキが選択されていません。YDKを読み込むか、インラインデッキを登録してください。",
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
  syntheticPreviewResult: "Synthetic preview 結果",
  realJobArtifactRequired: "実desktop jobは型付きjob artifact serviceから読み込む必要があります。",
  realJobReplayVerified: "実job / Replay検証済み",
  realJobReplayUnverified: "実job / Replay未検証",
  yes: "はい",
  no: "いいえ",
  preference: "評価",
  rule: "ルール",
  unknown: "不明",
  routeAction: "Routeアクション",
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
  failClosedResult: "Fail-closed 結果",
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
  configurationFailure: "設定エラー",
  desktopDeckRejected: "デスクトップサービスがこのデッキを拒否しました。",
  fixedHandInvalid: "固定初手には正のカードコードを1件以上指定してください。",
  conditionalMinInvalid: "条件付き初手の最小枚数は0以上の整数で指定してください。",
  conditionalMaxInvalid: "条件付き初手の最大枚数は最小枚数以上の整数で指定してください。",
  conditionalAttemptsInvalid: "条件付き初手の最大試行回数は1から100,000の範囲で指定してください。",
  experimentSummaryNodes: "nodes",
  budgetOutsideMvp: "予算がMVP上限を超えています",
  poolOutsideDesktop: "Poolサイズがデスクトップ上限を超えています",
  openingHandInvalid: "初手条件が不正です",
  interruptionCardRequired: "妨害カードが必要です",
  specifyPositiveNoInference: "正のカードコードを指定してください。効果やtimingは推測しません。",
  experimentCompositionFailed: "Experiment構成に失敗しました。",
  preflightFailed: "事前検証に失敗",
  preflightValidDetail: "fixture manifest、デッキ形状、戦略、seed、pool policy、予算は有効です。",
  replayingFrontierNodes: "frontier nodeをReplay中",
  searchState: "探索状態",
  jobState: "ジョブ状態",
  queuedJob: "キュー投入済み",
  waitingDesktopWorker: "デスクトップworker leaseを待っています。",
  bestRouteVerified: "最良経路を検証済み",
  committedArtifactResult: "commit済みartifact結果",
  codePrefix: "コード",
  typeLabel: "種別",
  attributeLabel: "属性",
  atkDefLabel: "ATK / DEF",
  localeLabel: "言語",
  deckSettingsSaved: "デッキ設定を保存しました。",
  deckSettingsFailed: "デッキ設定の保存はfail-closeしました。",
  deckNameAndTags: "デッキ名とタグ",
  unnamedCard: "カード名未構成",
  internalIdHidden: "内部IDは詳細表示に移動しました。",
  routeBudgetUnknown: "ノード予算はartifactから確認できません。",
  noPeakBoard: "最大スコア盤面はartifactから復元できません。",
  localeValue: "ja",
});

let decks = [
  {
    id: "short-route",
    name: "短経路 fixture",
    hash: "a72f91c8",
    tags: ["検証済み", "短経路", "基準"],
    main: 40,
    extra: 15,
    side: 0,
    source: "inline",
    status: "ready",
    statusLabel: "準備完了",
    runs: 4280,
    success: 84.2,
    best: 18.6,
    terminal: 14.1,
    updated: "12分前",
    updatedOrder: 4,
    chart: [
      ["Random", 84.2],
      ["Beam", 88.7],
      ["MCTS", 86.1],
    ],
    cards: [
      { code: 10000, name: "Synthetic Relay Alpha", count: 3, type: "効果", attribute: "光", stats: "1800 / 1200" },
      { code: 10001, name: "Synthetic Relay Beta", count: 3, type: "速攻魔法", attribute: "-", stats: "-" },
      { code: 10002, name: "Synthetic Relay Gate", count: 2, type: "罠", attribute: "-", stats: "-" },
    ],
    recentRuns: [
      ["Random · seed 42017", "成功 · score 18.6", "02:14"],
      ["Beam · seed 912", "成功 · score 19.2", "昨日"],
      ["MCTS · seed 6601", "予算到達 · score 17.4", "昨日"],
    ],
  },
  {
    id: "long-chain",
    name: "長チェーン fixture",
    hash: "88d14be2",
    tags: ["検証済み", "チェーン", "長経路"],
    main: 44,
    extra: 15,
    side: 6,
    source: "ydk",
    status: "ready",
    statusLabel: "準備完了",
    runs: 3650,
    success: 71.8,
    best: 22.4,
    terminal: 17.9,
    updated: "1時間前",
    updatedOrder: 3,
    chart: [
      ["Random", 71.8],
      ["Beam", 77.4],
      ["MCTS", 79.1],
    ],
    cards: [
      { code: 11000, name: "Synthetic Chain Node", count: 3, type: "効果", attribute: "闇", stats: "1600 / 1000" },
      { code: 11001, name: "Synthetic Chain Link", count: 2, type: "永続", attribute: "-", stats: "-" },
      { code: 11002, name: "Synthetic Chain Guard", count: 3, type: "カウンター", attribute: "-", stats: "-" },
    ],
    recentRuns: [
      ["MCTS · seed 773", "成功 · score 22.4", "03:05"],
      ["Beam · seed 114", "成功 · score 21.7", "昨日"],
      ["Random · seed 801", "最大ノード到達 · score 18.9", "2日前"],
    ],
  },
  {
    id: "grave-banish",
    name: "墓地/除外 fixture",
    hash: "d3196af4",
    tags: ["検証済み", "墓地", "除外"],
    main: 42,
    extra: 12,
    side: 0,
    source: "inline",
    status: "ready",
    statusLabel: "準備完了",
    runs: 3180,
    success: 66.5,
    best: 20.8,
    terminal: 13.6,
    updated: "昨日",
    updatedOrder: 2,
    chart: [
      ["Random", 66.5],
      ["Beam", 70.2],
      ["MCTS", 72.8],
    ],
    cards: [
      { code: 12000, name: "Synthetic Archive Unit", count: 3, type: "効果", attribute: "地", stats: "1400 / 1800" },
      { code: 12001, name: "Synthetic Exile Path", count: 3, type: "通常", attribute: "-", stats: "-" },
      { code: 12002, name: "Synthetic Return Trace", count: 2, type: "罠", attribute: "-", stats: "-" },
    ],
    recentRuns: [
      ["Beam · seed 234", "成功 · score 20.8", "昨日"],
      ["Random · seed 120", "合法停止 · score 16.2", "2日前"],
      ["MCTS · seed 990", "成功 · score 19.7", "2日前"],
    ],
  },
  {
    id: "recovery-probe",
    name: "復旧プローブ",
    hash: "f741e3a0",
    tags: ["復旧", "妨害あり", "要確認"],
    main: 40,
    extra: 15,
    side: 3,
    source: "ydk",
    status: "stale",
    statusLabel: "古いロック",
    runs: 1370,
    success: 42.1,
    best: 13.4,
    terminal: 8.2,
    updated: "4日前",
    updatedOrder: 1,
    chart: [
      ["Random", 42.1],
      ["Beam", 48.6],
      ["MCTS", 50.4],
    ],
    cards: [
      { code: 13000, name: "Synthetic Recovery Unit", count: 3, type: "効果", attribute: "水", stats: "1200 / 2000" },
      { code: 13001, name: "Synthetic Recovery Plan", count: 2, type: "通常", attribute: "-", stats: "-" },
      { code: 13002, name: "Synthetic Interrupt Trace", count: 3, type: "罠", attribute: "-", stats: "-" },
    ],
    recentRuns: [
      ["Random · seed 184", "設定エラー", "4日前"],
      ["Beam · seed 725", "経路エラー · score 9.1", "5日前"],
      ["MCTS · seed 402", "成功 · score 13.4", "5日前"],
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
  deckSettings: document.querySelector("#deck-settings"),
  deckSettingsDialog: document.querySelector("#deck-settings-dialog"),
  deckSettingsForm: document.querySelector("#deck-settings-form"),
  deckDisplayName: document.querySelector("#deck-display-name"),
  deckTags: document.querySelector("#deck-tags"),
  deckSettingsStatus: document.querySelector("#deck-settings-status"),
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
  resultTermination: document.querySelector("#result-termination"),
  resultOpeningHand: document.querySelector("#result-opening-hand"),
  resultPeakBoard: document.querySelector("#result-peak-board"),
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
  editProfiles: document.querySelector("#edit-profiles"),
  profilesPane: document.querySelector("#profiles-pane"),
  settingsPane: document.querySelector("#settings-pane"),
  settingsForm: document.querySelector("#settings-form"),
  settingsStatus: document.querySelector("#settings-status"),
  settingsExternalRoot: document.querySelector("#settings-external-root"),
  settingsUpdateChannel: document.querySelector("#settings-update-channel"),
  settingsAutoDownloads: document.querySelector("#settings-auto-downloads"),
  settingsAssetsReady: document.querySelector("#settings-assets-ready"),
  settingsRuntimeStatus: document.querySelector("#settings-runtime-status"),
  settingsFilePath: document.querySelector("#settings-file-path"),
  settingsRetentionDays: document.querySelector("#settings-retention-days"),
  settingsCacheLimit: document.querySelector("#settings-cache-limit"),
  settingsRedactPaths: document.querySelector("#settings-redact-paths"),
  settingsRedactUserText: document.querySelector("#settings-redact-user-text"),
  settingsRedactCardNames: document.querySelector("#settings-redact-card-names"),
  settingsDataRoot: document.querySelector("#settings-data-root"),
  settingsBackupRoot: document.querySelector("#settings-backup-root"),
  settingsDensity: document.querySelector("#settings-density"),
  settingsTheme: document.querySelector("#settings-theme"),
  settingsReducedMotion: document.querySelector("#settings-reduced-motion"),
  settingsSafeMode: document.querySelector("#settings-safe-mode"),
  settingsReset: document.querySelector("#settings-reset"),
  settingsSafeReset: document.querySelector("#settings-safe-reset"),
  profileNew: document.querySelector("#profile-new"),
  profileDeckSelect: document.querySelector("#profile-deck-select"),
  profileIncludeArchived: document.querySelector("#profile-include-archived"),
  profilePageStatus: document.querySelector("#profile-page-status"),
  deckProfileList: document.querySelector("#deck-profile-list"),
  deckProfileForm: document.querySelector("#deck-profile-form"),
  deckProfileEditStatus: document.querySelector("#deck-profile-edit-status"),
  profileDetailTitle: document.querySelector("#profile-detail-title"),
  deckProfileName: document.querySelector("#deck-profile-name"),
  deckProfileCard: document.querySelector("#deck-profile-card"),
  deckProfileLocation: document.querySelector("#deck-profile-location"),
  deckProfilePosition: document.querySelector("#deck-profile-position"),
  deckProfileWeight: document.querySelector("#deck-profile-weight"),
  deckProfileMinCount: document.querySelector("#deck-profile-min-count"),
  deckProfileMaxCount: document.querySelector("#deck-profile-max-count"),
  deckProfileScoring: document.querySelector("#deck-profile-scoring"),
  deckProfileAddRule: document.querySelector("#deck-profile-add-rule"),
  deckProfileRules: document.querySelector("#deck-profile-rules"),
  deckProfileSave: document.querySelector("#deck-profile-save"),
  deckProfileArchive: document.querySelector("#deck-profile-archive"),
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
let currentDesktopSettings = null;
let preferenceProfilesLoaded = false;
const profilePageState = {
  cardOptions: [],
  deckId: selectedDeck?.id || "",
  profiles: [],
  rules: [],
  selectedDeckProfileId: "",
};

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
    throw new Error(diagnostic?.message || UI_TEXT.analyticsQueryFailed);
  }
  return response.result;
}

const analyticsExportJobs = Object.freeze({
  async enqueue(payload) {
    if (!desktopBridgeAvailable()) {
      throw new Error(UI_TEXT.exportRequiresBridge);
    }
    const response = await window.routeLabBridge.invoke("analytics.export.enqueue", payload);
    if (!response.ok) throw new Error(response.diagnostics[0]?.message || UI_TEXT.exportQueueFailed);
    return response.result;
  },
  async status(jobId) {
    const response = await window.routeLabBridge.invoke("job.status", { job_id: jobId });
    if (!response.ok) throw new Error(response.diagnostics[0]?.message || UI_TEXT.exportStatusFailed);
    return response.result;
  },
  async cancel(jobId) {
    const response = await window.routeLabBridge.invoke("job.cancel", { job_id: jobId });
    if (!response.ok) throw new Error(response.diagnostics[0]?.message || UI_TEXT.exportCancelFailed);
    return response.result;
  },
});

const analyticsController = window.routeLabAnalytics.createController(
  elements.analyticsPane,
  executeAnalyticsQuery,
  analyticsExportJobs,
);

function markDesktopEnvironment() {
  elements.environmentLabel.textContent = UI_TEXT.bridgeReady;
  elements.environmentCode.textContent = UI_TEXT.preflightPerRun;
  elements.catalogSourceLabel.textContent = UI_TEXT.localDeckCatalog;
}

async function refreshExternalAssetStatus() {
  if (!desktopBridgeAvailable()) return;
  const response = await window.routeLabBridge.invoke("system.external_asset_status", {});
  if (!response.ok) return;
  const status = response.result;
  elements.environmentCode.textContent = status.ready
    ? UI_TEXT.externalAssetSetupReady
    : UI_TEXT.externalAssetSetupRequired;
}

function applySettingsToForm(payload) {
  const settings = payload.settings;
  currentDesktopSettings = settings;
  elements.settingsExternalRoot.value = settings.external_asset_root || "";
  elements.settingsUpdateChannel.value = settings.updates.channel;
  elements.settingsAutoDownloads.checked = settings.updates.automatic_downloads;
  elements.settingsRetentionDays.value = String(settings.storage.retention_days);
  elements.settingsCacheLimit.value = String(settings.storage.cache_limit_mb);
  elements.settingsRedactPaths.checked = !settings.privacy.include_local_paths_in_support_bundle;
  elements.settingsRedactUserText.checked = settings.privacy.redact_user_text;
  elements.settingsRedactCardNames.checked = settings.privacy.redact_card_names;
  elements.settingsDensity.value = settings.display.density;
  elements.settingsTheme.value = settings.display.theme;
  elements.settingsReducedMotion.checked = settings.display.reduced_motion;
  elements.settingsSafeMode.checked = settings.recovery.safe_mode;
  elements.settingsAssetsReady.textContent = payload.external_assets?.ready
    ? UI_TEXT.externalAssetSetupReady
    : UI_TEXT.externalAssetSetupRequired;
  elements.settingsRuntimeStatus.textContent = payload.runtime?.webview2 || "-";
  elements.settingsFilePath.textContent = payload.storage_locations?.settings_file || "-";
  elements.settingsDataRoot.textContent = payload.storage_locations?.data_root || "-";
  elements.settingsBackupRoot.textContent = payload.storage_locations?.backup_export_root || "-";
  document.body.classList.toggle("comfortable", settings.display.density === "comfortable");
}

function collectSettingsFromForm() {
  const base = currentDesktopSettings || {
    schema_version: "desktop-settings-v1",
    external_asset_root: null,
    updates: { automatic_downloads: false, channel: "manual" },
    storage: { cache_limit_mb: 512, retention_days: 30 },
    privacy: {
      include_local_paths_in_support_bundle: false,
      redact_card_names: true,
      redact_user_text: true,
    },
    display: { density: "compact", reduced_motion: false, theme: "system" },
    recovery: { safe_mode: false },
  };
  return {
    ...base,
    display: {
      density: elements.settingsDensity.value,
      reduced_motion: elements.settingsReducedMotion.checked,
      theme: elements.settingsTheme.value,
    },
    external_asset_root: elements.settingsExternalRoot.value.trim() || null,
    privacy: {
      include_local_paths_in_support_bundle: !elements.settingsRedactPaths.checked,
      redact_card_names: elements.settingsRedactCardNames.checked,
      redact_user_text: elements.settingsRedactUserText.checked,
    },
    recovery: { safe_mode: elements.settingsSafeMode.checked },
    storage: {
      cache_limit_mb: Number(elements.settingsCacheLimit.value),
      retention_days: Number(elements.settingsRetentionDays.value),
    },
    updates: {
      automatic_downloads: false,
      channel: elements.settingsUpdateChannel.value,
    },
  };
}

async function refreshSettings() {
  if (!desktopBridgeAvailable()) {
    elements.settingsStatus.textContent = UI_TEXT.bridgeUnavailable;
    return;
  }
  const response = await window.routeLabBridge.invoke("settings.get", {});
  if (!response.ok) {
    elements.settingsStatus.textContent = response.diagnostics[0]?.message || UI_TEXT.settingsLoadFailed;
    return;
  }
  applySettingsToForm(response.result);
  elements.settingsStatus.textContent = UI_TEXT.externalAssetSetupReady;
}

async function saveDesktopSettings(event) {
  event.preventDefault();
  const response = await window.routeLabBridge.invoke("settings.update", {
    settings: collectSettingsFromForm(),
  });
  if (!response.ok) {
    elements.settingsStatus.textContent = response.diagnostics[0]?.message || UI_TEXT.settingsSaveFailed;
    return;
  }
  await refreshSettings();
  elements.settingsStatus.textContent = UI_TEXT.settingsSaved;
}

async function resetDesktopSettings(safeMode) {
  const response = await window.routeLabBridge.invoke("settings.reset", { safe_mode: safeMode });
  if (!response.ok) {
    elements.settingsStatus.textContent = response.diagnostics[0]?.message || UI_TEXT.settingsSaveFailed;
    return;
  }
  await refreshSettings();
  elements.settingsStatus.textContent = UI_TEXT.settingsReset;
}

function bridgeDeck(record) {
  const metadata = record.metadata || {};
  return {
    id: record.deck_id,
    canonicalName: record.canonical_name || record.name,
    name: metadata.display_name || record.name,
    hash: record.deck_sha256.slice(0, 8),
    tags: Array.isArray(record.tags) ? record.tags : [record.source, record.status],
    main: record.main_count,
    extra: record.extra_count,
    side: record.side_count,
    source: record.source,
    status: "registered",
    statusLabel: UI_TEXT.registered,
    runs: 0,
    success: 0,
    best: 0,
    terminal: 0,
    updated: UI_TEXT.localCatalog,
    updatedOrder: 5,
    chart: [["Random", 0], ["Beam", 0], ["MCTS", 0]],
    cards: record.card_counts.slice(0, 30).map((item) => ({
      code: item.card_code,
      name: item.name_ja || UI_TEXT.unnamedCard,
      count: item.count,
      type: item.name_ja ? UI_TEXT.localeValue : UI_TEXT.presentationUnavailable,
      attribute: "-",
      stats: "-",
    })),
    recentRuns: [],
  };
}

async function refreshDesktopCatalog() {
  if (!desktopBridgeAvailable()) return;
  markDesktopEnvironment();
  await refreshExternalAssetStatus();
  const selectedId = selectedDeck?.id || "";
  const response = await window.routeLabBridge.invoke("deck.catalog", {});
  if (!response.ok) {
    showToast(response.diagnostics[0]?.message || UI_TEXT.desktopCatalogFailed);
    return;
  }
  decks = response.result.decks.map(bridgeDeck);
  if (decks.length === 0) {
    selectedDeck = null;
    elements.catalogMetrics.hidden = true;
    elements.detailPane.hidden = true;
    document.querySelector("#open-search").disabled = true;
    elements.workspace.classList.add("catalog-only");
    renderDecks();
    renderProfileDeckOptions();
    return;
  }
  selectedDeck = decks.find((deck) => deck.id === selectedId) || decks[0];
  profilePageState.deckId = selectedDeck.id;
  preferenceProfilesLoaded = false;
  elements.catalogMetrics.hidden = false;
  elements.detailPane.hidden = false;
  document.querySelector("#open-search").disabled = false;
  elements.workspace.classList.remove("catalog-only");
  renderDecks();
  updateDetail(selectedDeck);
  renderProfileDeckOptions();
  if (!elements.profilesPane.hidden) {
    await refreshDeckProfiles();
  }
}

function renderPreferenceProfiles(records) {
  const selected = elements.preferenceProfile.value;
  elements.preferenceProfile.replaceChildren();
  const defaultOption = document.createElement("option");
  defaultOption.value = "";
  defaultOption.textContent = UI_TEXT.defaultTerminalPreference;
  elements.preferenceProfile.append(defaultOption);
  records.forEach((record) => {
    const option = document.createElement("option");
    option.value = record.deck_profile_id || "";
    option.textContent = record.display_name || UI_TEXT.terminalPreference;
    elements.preferenceProfile.append(option);
  });
  if (selected && [...elements.preferenceProfile.options].some((option) => option.value === selected)) {
    elements.preferenceProfile.value = selected;
  }
  elements.preferenceProfile.disabled = !selectedDeck;
}

async function refreshPreferenceProfiles() {
  if (!desktopBridgeAvailable() || !selectedDeck) {
    renderPreferenceProfiles([]);
    elements.preferenceProfile.disabled = true;
    return;
  }
  const response = await window.routeLabBridge.invoke("deck.profile.list", {
    deck_id: selectedDeck.id,
    include_archived: false,
  });
  if (!response.ok) {
    showToast(response.diagnostics[0]?.message || UI_TEXT.terminalProfileCatalogFailed);
    renderPreferenceProfiles([]);
    elements.preferenceProfile.disabled = true;
    return;
  }
  renderPreferenceProfiles(response.result.profiles || []);
  preferenceProfilesLoaded = true;
}

function renderProfileDeckOptions() {
  const selected = profilePageState.deckId || selectedDeck?.id || "";
  elements.profileDeckSelect.replaceChildren();
  decks.forEach((deck) => {
    const option = document.createElement("option");
    option.value = deck.id;
    option.textContent = deck.name;
    elements.profileDeckSelect.append(option);
  });
  if (selected && [...elements.profileDeckSelect.options].some((option) => option.value === selected)) {
    elements.profileDeckSelect.value = selected;
    profilePageState.deckId = selected;
  } else {
    profilePageState.deckId = elements.profileDeckSelect.value || "";
  }
}

function currentProfileRecord() {
  return profilePageState.profiles.find((profile) => profile.deck_profile_id === profilePageState.selectedDeckProfileId) || null;
}

function renderDeckProfileList() {
  elements.deckProfileList.replaceChildren();
  if (profilePageState.profiles.length === 0) {
    elements.deckProfileList.append(textElement("span", "このデッキのプロファイルはありません。"));
    return;
  }
  profilePageState.profiles.forEach((profile) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "deck-profile-item";
    if (profile.deck_profile_id === profilePageState.selectedDeckProfileId) button.classList.add("is-selected");
    const state = profile.state === "archived" ? "アーカイブ済み" : `rev ${profile.revision}`;
    button.append(textElement("strong", profile.display_name), textElement("small", state));
    button.addEventListener("click", () => selectDeckProfile(profile.deck_profile_id));
    elements.deckProfileList.append(button);
  });
}

function renderDeckCardOptions() {
  elements.deckProfileCard.replaceChildren();
  const placeholder = document.createElement("option");
  placeholder.value = "";
  placeholder.textContent = "デッキ内カードを選択";
  elements.deckProfileCard.append(placeholder);
  profilePageState.cardOptions.forEach((item) => {
    const option = document.createElement("option");
    option.value = String(item.card_code);
    option.disabled = !item.selectable;
    option.textContent = item.selectable
      ? `${item.name_ja} ×${item.count}`
      : `日本語名なし (${item.card_code})`;
    elements.deckProfileCard.append(option);
  });
  const cardSelectionDisabled = profilePageState.cardOptions.every((item) => !item.selectable);
  elements.deckProfileCard.disabled = cardSelectionDisabled;
  elements.deckProfileAddRule.disabled = cardSelectionDisabled;
}

function cardOptionName(cardCode) {
  const option = profilePageState.cardOptions.find((item) => item.card_code === cardCode);
  return option?.name_ja || `${UI_TEXT.cardPrefix} ${cardCode}`;
}

function renderProfileRules() {
  elements.deckProfileRules.replaceChildren();
  if (profilePageState.rules.length === 0) {
    elements.deckProfileRules.append(textElement("span", "ルールは未追加です。"));
    return;
  }
  profilePageState.rules.forEach((rule, index) => {
    const row = document.createElement("div");
    row.className = "profile-rule-row";
    row.append(
      textElement("strong", cardOptionName(rule.card_code)),
      textElement("span", rule.location),
      textElement("span", rule.position),
      textElement("span", `重み ${rule.weight}`),
      textElement("span", `${rule.min_count}-${rule.max_count ?? "上限なし"}`),
    );
    const remove = document.createElement("button");
    remove.type = "button";
    remove.className = "button secondary";
    remove.textContent = "削除";
    remove.addEventListener("click", () => {
      profilePageState.rules.splice(index, 1);
      renderProfileRules();
      elements.deckProfileEditStatus.textContent = UI_TEXT.profileRuleRemoved;
    });
    row.append(remove);
    elements.deckProfileRules.append(row);
  });
}

function resetProfileEditor() {
  const current = currentProfileRecord();
  elements.deckProfileName.value = current?.display_name || "";
  elements.profileDetailTitle.textContent = current ? "終端評価ルールを編集" : "終端評価ルールを新規作成";
  elements.deckProfileArchive.disabled = !current || current.state === "archived";
  elements.deckProfileSave.disabled = !profilePageState.deckId || current?.state === "archived";
  profilePageState.rules = current?.active_profile?.rules ? [...current.active_profile.rules] : [];
  renderProfileRules();
}

function selectDeckProfile(deckProfileId) {
  profilePageState.selectedDeckProfileId = deckProfileId;
  renderDeckProfileList();
  resetProfileEditor();
}

async function refreshDeckCardOptions() {
  profilePageState.cardOptions = [];
  renderDeckCardOptions();
  if (!desktopBridgeAvailable() || !profilePageState.deckId) {
    return;
  }
  const response = await window.routeLabBridge.invoke("deck.card_options", {
    deck_id: profilePageState.deckId,
  });
  if (!response.ok) {
    elements.deckProfileEditStatus.textContent = response.diagnostics[0]?.message || UI_TEXT.deckCardOptionsFailed;
    elements.profilePageStatus.textContent = UI_TEXT.profilePageNoCards;
    renderDeckCardOptions();
    return;
  }
  profilePageState.cardOptions = response.result.items || [];
  renderDeckCardOptions();
}

async function refreshDeckProfiles() {
  renderProfileDeckOptions();
  if (!desktopBridgeAvailable() || !profilePageState.deckId) {
    profilePageState.profiles = [];
    profilePageState.selectedDeckProfileId = "";
    elements.profilePageStatus.textContent = UI_TEXT.profilePageDeckRequired;
    renderDeckProfileList();
    resetProfileEditor();
    return;
  }
  const response = await window.routeLabBridge.invoke("deck.profile.list", {
    deck_id: profilePageState.deckId,
    include_archived: elements.profileIncludeArchived.checked,
  });
  if (!response.ok) {
    elements.profilePageStatus.textContent = response.diagnostics[0]?.message || UI_TEXT.profileCatalogUnavailable;
    profilePageState.profiles = [];
    profilePageState.selectedDeckProfileId = "";
  } else {
    profilePageState.profiles = response.result.profiles || [];
    if (!profilePageState.profiles.some((profile) => profile.deck_profile_id === profilePageState.selectedDeckProfileId)) {
      profilePageState.selectedDeckProfileId = profilePageState.profiles[0]?.deck_profile_id || "";
    }
    elements.profilePageStatus.textContent = `${profilePageState.profiles.length} 件`;
  }
  renderDeckProfileList();
  await refreshDeckCardOptions();
  resetProfileEditor();
}

function addProfileRule() {
  const cardCode = Number(elements.deckProfileCard.value);
  const weight = Number(elements.deckProfileWeight.value);
  const minCount = Number(elements.deckProfileMinCount.value);
  const maxValue = elements.deckProfileMaxCount.value.trim();
  const maxCount = maxValue ? Number(maxValue) : null;
  if (!Number.isInteger(cardCode) || cardCode < 1) {
    elements.deckProfileEditStatus.textContent = UI_TEXT.profileCardRequired;
    elements.deckProfileCard.focus();
    return;
  }
  if (!Number.isInteger(weight)) {
    elements.deckProfileEditStatus.textContent = UI_TEXT.integerWeight;
    elements.deckProfileWeight.focus();
    return;
  }
  if (!Number.isInteger(minCount) || minCount < 1) {
    elements.deckProfileEditStatus.textContent = UI_TEXT.integerMinCount;
    elements.deckProfileMinCount.focus();
    return;
  }
  if (maxCount !== null && (!Number.isInteger(maxCount) || maxCount < minCount)) {
    elements.deckProfileEditStatus.textContent = UI_TEXT.integerMaxCount;
    elements.deckProfileMaxCount.focus();
    return;
  }
  const location = elements.deckProfileLocation.value;
  const position = elements.deckProfilePosition.value;
  const rule = {
    card_code: cardCode,
    controller: 0,
    enabled: true,
    location,
    max_count: maxCount,
    min_count: minCount,
    position,
    rule_id: `desktop-rule-${cardCode}-${location}-${position}-${Date.now()}`,
    scoring_mode: elements.deckProfileScoring.value,
    weight,
  };
  profilePageState.rules.push(rule);
  renderProfileRules();
  elements.deckProfileEditStatus.textContent = UI_TEXT.profileRuleAdded;
}

async function saveDeckProfile(event) {
  event.preventDefault();
  if (!desktopBridgeAvailable() || !profilePageState.deckId) {
    elements.deckProfileEditStatus.textContent = UI_TEXT.profilePageDeckRequired;
    return;
  }
  const displayName = elements.deckProfileName.value.trim();
  if (!displayName) {
    elements.deckProfileEditStatus.textContent = UI_TEXT.profileNameRequired;
    elements.deckProfileName.focus();
    return;
  }
  const current = currentProfileRecord();
  const method = current ? "deck.profile.update" : "deck.profile.create";
  const payload = current
    ? { deck_profile_id: current.deck_profile_id, display_name: displayName, rules: profilePageState.rules }
    : { deck_id: profilePageState.deckId, display_name: displayName, rules: profilePageState.rules };
  const response = await window.routeLabBridge.invoke(method, payload);
  if (!response.ok) {
    elements.deckProfileEditStatus.textContent = response.diagnostics[0]?.message || UI_TEXT.profileSaveFailed;
    return;
  }
  profilePageState.selectedDeckProfileId = response.result.profile.deck_profile_id;
  elements.deckProfileEditStatus.textContent = UI_TEXT.profileSaved;
  await refreshDeckProfiles();
  await refreshPreferenceProfiles();
  invalidatePreflight();
  updateExperimentSummary();
}

async function archiveDeckProfile() {
  const current = currentProfileRecord();
  if (!desktopBridgeAvailable() || !current) return;
  const response = await window.routeLabBridge.invoke("deck.profile.archive", {
    deck_profile_id: current.deck_profile_id,
  });
  if (!response.ok) {
    elements.deckProfileEditStatus.textContent = response.diagnostics[0]?.message || UI_TEXT.profileArchiveFailed;
    return;
  }
  profilePageState.selectedDeckProfileId = "";
  elements.deckProfileEditStatus.textContent = UI_TEXT.profileArchived;
  await refreshDeckProfiles();
  await refreshPreferenceProfiles();
  invalidatePreflight();
  updateExperimentSummary();
}

async function importDesktopYdk() {
  if (!desktopBridgeAvailable()) {
    showToast(UI_TEXT.ydkRequiresDesktop);
    return;
  }
  const response = await window.routeLabBridge.invoke("deck.import_ydk", {});
  if (!response.ok) {
    showToast(response.diagnostics[0]?.message || UI_TEXT.ydkImportFailed);
    return;
  }
  if (response.result.cancelled) return;
  await refreshDesktopCatalog();
  showToast(UI_TEXT.ydkRegistered);
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
    showToast(UI_TEXT.inlineDeckRequiresBridge);
    return;
  }
  elements.inlineDeckForm.reset();
  setInlineDeckStatus(
    "warning",
    UI_TEXT.notRegistered,
    UI_TEXT.inlineAddressed,
  );
  elements.inlineDeckDialog.showModal();
}

function inlineDeckPayload() {
  return {
    extra: parseCardCodeList(elements.inlineExtraCards.value),
    main: parseCardCodeList(elements.inlineMainCards.value),
    name: elements.inlineDeckName.value.trim() || UI_TEXT.inlineResearchDeck,
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
      return `${UI_TEXT[section]}: ${UI_TEXT.invalidCardCode}`;
    }
  }
  if (payload.main.length < 40 || payload.main.length > 60) {
    return payload.main.length < 40 ? UI_TEXT.mainTooSmall : UI_TEXT.mainTooLarge;
  }
  if (payload.extra.length > 15) return UI_TEXT.extraTooLarge;
  if (payload.side.length > 15) return UI_TEXT.sideTooLarge;
  return null;
}

async function registerInlineDeck() {
  if (!desktopBridgeAvailable()) {
    setInlineDeckStatus("error", UI_TEXT.bridgeUnavailable, UI_TEXT.inlineRegistrationDisabled);
    return;
  }
  const payload = inlineDeckPayload();
  const inputError = inlineDeckInputError(payload);
  if (inputError) {
    setInlineDeckStatus("error", UI_TEXT.deckInputRejected, inputError);
    return;
  }
  const response = await window.routeLabBridge.invoke("deck.register_inline", payload);
  if (!response.ok) {
    setInlineDeckStatus(
      "error",
      UI_TEXT.deckRegistrationFailed,
      response.diagnostics[0]?.message || UI_TEXT.desktopDeckRejected,
    );
    return;
  }
  const deckId = response.result.deck.deck_id;
  await refreshDesktopCatalog();
  selectDeck(deckId);
  elements.inlineDeckDialog.close();
  showToast(UI_TEXT.inlineRegistered);
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
    const haystack = [deck.name, deck.canonicalName || "", ...deck.tags].join(" ").toLowerCase();
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
    nameButton.append(textElement("strong", deck.name), textElement("span", deck.tags.join(" / ")));
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
  elements.detailHash.title = UI_TEXT.internalIdHidden;
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
    title.textContent = UI_TEXT.preflightPassed;
    description.textContent = UI_TEXT.readyDeckVerified;
  } else if (deck.status === "registered") {
    summary.className = "diagnostic warning";
    title.textContent = UI_TEXT.preflightRequired;
    description.textContent = UI_TEXT.registeredDeckPreflight;
  } else {
    summary.className = "diagnostic warning";
    title.textContent = UI_TEXT.staleAssetLock;
    description.textContent = UI_TEXT.staleAssetDetail;
  }
}

function setDeckSettingsStatus(kind, title, detail) {
  elements.deckSettingsStatus.className = `diagnostic ${kind}`;
  elements.deckSettingsStatus.replaceChildren();
  const body = document.createElement("div");
  body.append(textElement("strong", title), textElement("span", detail));
  elements.deckSettingsStatus.append(body);
}

function openDeckSettings() {
  if (!selectedDeck) {
    showToast(UI_TEXT.noDeckSelected);
    return;
  }
  elements.deckDisplayName.value = selectedDeck.name;
  elements.deckTags.value = selectedDeck.tags.join(", ");
  setDeckSettingsStatus("warning", UI_TEXT.deckNameAndTags, "保存しても内部IDと過去の証跡は変わりません。");
  elements.deckSettingsDialog.showModal();
}

function deckSettingsPayload() {
  return {
    deck_id: selectedDeck.id,
    display_name: elements.deckDisplayName.value.trim(),
    tags: elements.deckTags.value
      .split(",")
      .map((tag) => tag.trim())
      .filter(Boolean),
  };
}

async function saveDeckSettings(event) {
  event.preventDefault();
  if (!desktopBridgeAvailable() || !selectedDeck) {
    setDeckSettingsStatus("error", UI_TEXT.bridgeUnavailable, UI_TEXT.deckSettingsFailed);
    return;
  }
  const payload = deckSettingsPayload();
  if (!payload.display_name) {
    elements.deckDisplayName.focus();
    setDeckSettingsStatus("error", UI_TEXT.deckInputRejected, UI_TEXT.deckNameRequired);
    return;
  }
  const response = await window.routeLabBridge.invoke("deck.metadata.update", payload);
  if (!response.ok) {
    setDeckSettingsStatus("error", UI_TEXT.deckInputRejected, response.diagnostics[0]?.message || UI_TEXT.deckSettingsFailed);
    return;
  }
  await refreshDesktopCatalog();
  elements.deckSettingsDialog.close();
  showToast(UI_TEXT.deckSettingsSaved);
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
  profilePageState.deckId = deck.id;
  profilePageState.selectedDeckProfileId = "";
  preferenceProfilesLoaded = false;
  document.querySelector("#open-search").disabled = false;
  renderDecks();
  updateDetail(deck);
  renderProfileDeckOptions();
  if (!elements.profilesPane.hidden) {
    refreshDeckProfiles().catch(() => showToast(UI_TEXT.profileCatalogUnavailable));
  }
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
  elements.preflightBox.querySelector("strong").textContent = UI_TEXT.readyForPreflight;
  elements.preflightBox.querySelector("span").textContent = UI_TEXT.validationBeforeWorker;
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
      return UI_TEXT.fixedHandInvalid;
    }
  }
  if (mode === "conditional") {
    const code = Number(elements.conditionalCardCode.value);
    const minCount = Number(elements.conditionalMinCount.value || 0);
    const maxCount = elements.conditionalMaxCount.value
      ? Number(elements.conditionalMaxCount.value)
      : null;
    const attempts = Number(elements.conditionalMaxAttempts.value || 10000);
    if (!Number.isInteger(code) || code < 1) return UI_TEXT.invalidCardCode;
    if (!Number.isInteger(minCount) || minCount < 0) return UI_TEXT.conditionalMinInvalid;
    if (maxCount !== null && (!Number.isInteger(maxCount) || maxCount < minCount)) {
      return UI_TEXT.conditionalMaxInvalid;
    }
    if (!Number.isInteger(attempts) || attempts < 1 || attempts > 100000) {
      return UI_TEXT.conditionalAttemptsInvalid;
    }
  }
  return null;
}

function updateExperimentSummary() {
  elements.experimentSummary.textContent = `${selectedStrategy()} · seed ${elements.seed.value || "-"} · pool ${elements.poolSize.value || "1"} · ${Number(elements.maxNodes.value || 0).toLocaleString("en-US")} ${UI_TEXT.experimentSummaryNodes}`;
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
    title.textContent = UI_TEXT.configurationFailure;
    detail.textContent = UI_TEXT.assetLockMismatch;
    elements.queueSearch.disabled = true;
    return;
  }
  if (Number(elements.maxNodes.value) < 1 || Number(elements.maxNodes.value) > 100000) {
    elements.preflightBox.className = "preflight-box is-invalid";
    title.textContent = UI_TEXT.budgetOutsideMvp;
    detail.textContent = UI_TEXT.maxNodesInvalid;
    elements.queueSearch.disabled = true;
    return;
  }
  if (Number(elements.poolSize.value) < 1 || Number(elements.poolSize.value) > 8) {
    elements.preflightBox.className = "preflight-box is-invalid";
    title.textContent = UI_TEXT.poolOutsideDesktop;
    detail.textContent = UI_TEXT.poolSizeInvalid;
    elements.queueSearch.disabled = true;
    return;
  }
  const openingError = openingHandInputError();
  if (openingError) {
    elements.preflightBox.className = "preflight-box is-invalid";
    title.textContent = UI_TEXT.openingHandInvalid;
    detail.textContent = `${openingError} ${UI_TEXT.noWorkerStarted}`;
    elements.queueSearch.disabled = true;
    return;
  }
  if (elements.interruptionToggle.checked && !elements.interruptionCode.value) {
    elements.preflightBox.className = "preflight-box is-invalid";
    title.textContent = UI_TEXT.interruptionCardRequired;
    detail.textContent = UI_TEXT.specifyPositiveNoInference;
    elements.queueSearch.disabled = true;
    return;
  }
  if (desktopBridgeAvailable()) {
    elements.queueSearch.disabled = true;
    title.textContent = UI_TEXT.runningPreflight;
    detail.textContent = UI_TEXT.composingScenario;
    const composed = await window.routeLabBridge.invoke("scenario.compose_search", {
      configuration: searchConfiguration(),
      deck_id: selectedDeck.id,
    });
    if (!composed.ok) {
      elements.preflightBox.className = "preflight-box is-invalid";
      title.textContent = UI_TEXT.configurationFailure;
      detail.textContent = composed.diagnostics[0]?.message || UI_TEXT.experimentCompositionFailed;
      return;
    }
    currentExperiment = composed.result.experiment;
    const checked = await window.routeLabBridge.invoke("scenario.preflight", {
      deck_id: selectedDeck.id,
      experiment: currentExperiment,
    });
    if (!checked.ok || !checked.result.preflight.ok) {
      elements.preflightBox.className = "preflight-box is-invalid";
      title.textContent = UI_TEXT.preflightFailed;
      detail.textContent = checked.diagnostics[0]?.message
        || checked.result?.preflight?.diagnostics?.[0]?.message
        || UI_TEXT.localAssetValidationFailed;
      currentExperiment = null;
      return;
    }
  }
  preflightValid = true;
  elements.preflightBox.className = "preflight-box is-valid";
  title.textContent = UI_TEXT.preflightPassed;
  detail.textContent = UI_TEXT.preflightValidDetail;
  elements.queueSearch.disabled = false;
}

function openSearch() {
  if (!selectedDeck) {
    showToast(UI_TEXT.noDeckSelected);
    return;
  }
  elements.searchDeckName.textContent = selectedDeck.name;
  if (!preferenceProfilesLoaded) {
    refreshPreferenceProfiles()
      .then(updateExperimentSummary)
      .catch(() => showToast(UI_TEXT.terminalProfileCatalogFailed));
  }
  invalidatePreflight();
  updateExperimentSummary();
  elements.searchDialog.showModal();
  replaceHash(`view=search&deck=${encodeURIComponent(selectedDeck.id)}`);
}

function openProfilePageForSelectedDeck() {
  if (!selectedDeck) {
    showToast(UI_TEXT.noDeckSelected);
    return;
  }
  profilePageState.deckId = selectedDeck.id;
  profilePageState.selectedDeckProfileId = elements.preferenceProfile.value || "";
  elements.searchDialog.close();
  showWorkspaceView("profiles");
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
  elements.jobTitle.textContent = UI_TEXT.replayingFrontierNodes;
  elements.jobNodes.textContent = `0 / ${Number(elements.maxNodes.value).toLocaleString("en-US")}`;
  elements.jobReplays.textContent = "0";
  elements.jobScore.textContent = "0.0";
  elements.jobElapsed.textContent = "0.0s";
  elements.jobLog.textContent = desktopBridgeAvailable()
    ? `${UI_TEXT.queuedJob}: ${UI_TEXT.waitingDesktopWorker}`
    : UI_TEXT.queuedPreview;
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
  elements.jobTitle.textContent = state === "running" ? UI_TEXT.replayingFrontierNodes : `${UI_TEXT.searchState}: ${state}`;
  elements.jobLog.textContent = snapshot.job.error_message
    || (checkpoint ? `Checkpoint: ${checkpoint.recovery_position}` : `${UI_TEXT.jobState}: ${state}`);
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
    elements.jobLog.textContent = response.diagnostics[0]?.message || UI_TEXT.jobStatusFailed;
    return;
  }
  if (!finishDesktopJob(response.result)) {
    jobTimer = window.setTimeout(() => {
      pollDesktopJob().catch(() => {
        elements.jobLog.textContent = UI_TEXT.jobPollingFailed;
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
    elements.jobTitle.textContent = UI_TEXT.searchRejected;
    elements.jobLog.textContent = response.diagnostics[0]?.message || UI_TEXT.searchQueueFailed;
    elements.cancelJob.hidden = true;
    return;
  }
  currentJobId = response.result.job.job_id;
  elements.jobLog.textContent = `${UI_TEXT.queuedJob} ${currentJobId}. ${UI_TEXT.waitingDesktopWorker}`;
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
    elements.jobLog.textContent = `${UI_TEXT.previewCheckpoint} ${index + 1}/${steps.length}: ${UI_TEXT.previewDeterministic}`;
    index += 1;
    if (index === steps.length) {
      window.clearInterval(jobTimer);
      jobTimer = null;
      elements.jobTitle.textContent = UI_TEXT.bestRouteVerified;
      elements.jobLog.textContent = UI_TEXT.syntheticReplayMatched;
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
      elements.jobLog.textContent = response.diagnostics[0]?.message || UI_TEXT.cancellationFailed;
      return;
    }
    const terminal = finishDesktopJob({ ...response.result, latest_checkpoint: null });
    if (!terminal) {
      elements.cancelJob.disabled = true;
      elements.jobLog.textContent = UI_TEXT.cancellationRequested;
      jobTimer = window.setTimeout(() => {
        pollDesktopJob().catch(() => {
          elements.jobLog.textContent = UI_TEXT.cancellationPollingFailed;
        });
      }, 250);
    }
    showToast(UI_TEXT.cancellationToast);
    return;
  }
  if (desktopBridgeAvailable()) {
    elements.jobDialog.close();
    replaceHash(`deck=${encodeURIComponent(selectedDeck.id)}`);
    return;
  }
  elements.jobDialog.close();
  replaceHash(`deck=${encodeURIComponent(selectedDeck.id)}`);
  showToast(UI_TEXT.syntheticJobCanceled);
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

function compactId(value) {
  if (!value) return "-";
  const text = String(value);
  const marker = text.indexOf("_");
  return marker >= 0 ? `${text.slice(0, marker)}_${text.slice(marker + 1, marker + 9)}...` : text;
}

function terminationLabel(reason) {
  return {
    frontier_exhausted: "探索候補を使い切りました",
    goal_reached: "成功条件に到達しました",
    max_depth: "最大深さに到達しました",
    max_nodes: "最大ノード数に到達しました",
    max_seconds: "最大秒数に到達しました",
    failed: "探索に失敗しました",
  }[reason] || reason || "停止理由不明";
}

function cardName(card) {
  return card?.name_ja || (card?.card_code ? `${UI_TEXT.codePrefix} ${card.card_code}` : UI_TEXT.unnamedCard);
}

function renderTerminationSummary(view) {
  if (!view?.search_run) {
    elements.resultTermination.textContent = "結果artifactを読み込むと停止理由を表示します。";
    return;
  }
  const budget = view.search_run.budget || {};
  const nodes = view.search_run.nodes ?? "-";
  const maxNodes = budget.max_nodes ?? UI_TEXT.routeBudgetUnknown;
  const reason = terminationLabel(view.search_run.termination_reason);
  const coverage = view.search_run.best_observed ? "観測上の最良で、全探索の証明ではありません。" : "frontier exhaustion を証明済みです。";
  elements.resultTermination.textContent = `${reason}。ノード消費 ${nodes} / ${maxNodes}。${coverage}`;
}

function renderOpeningHandSummary(opening) {
  if (!opening) {
    elements.resultOpeningHand.textContent = "初期手札情報がありません。";
    return;
  }
  const mode = opening.mode || "unknown";
  const cards = Array.isArray(opening.cards) ? opening.cards.map(cardName).join(" / ") : "";
  const base = `mode: ${mode}${opening.seed !== null && opening.seed !== undefined ? ` / seed: ${opening.seed}` : ""}${opening.size ? ` / ${opening.size}枚` : ""}`;
  elements.resultOpeningHand.textContent = cards ? `${base} / ${cards}` : `${base} / ${opening.message || "カード内容は未解決です。"}`;
}

function renderPeakBoardSummary(snapshot) {
  elements.resultPeakBoard.replaceChildren();
  if (!snapshot?.available) {
    elements.resultPeakBoard.textContent = snapshot?.message || UI_TEXT.noPeakBoard;
    return;
  }
  const summary = textElement("p", `score ${snapshot.score ?? "-"} / state ${compactId(snapshot.state_hash)}`);
  elements.resultPeakBoard.append(summary);
  const cards = Array.isArray(snapshot.cards) ? snapshot.cards : [];
  if (!cards.length) {
    elements.resultPeakBoard.append(textElement("p", "公開カードは記録されていません。"));
    return;
  }
  const list = document.createElement("ul");
  cards.slice(0, 20).forEach((card) => {
    const zone = [card.location, card.slot !== undefined ? `slot ${card.slot}` : ""].filter(Boolean).join(" / ");
    const item = document.createElement("li");
    item.textContent = `${cardName(card)}${zone ? ` (${zone})` : ""}`;
    list.append(item);
  });
  elements.resultPeakBoard.append(list);
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
    cell.textContent = UI_TEXT.committedRowsEmpty;
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
    elements.resultDrilldownTitle.textContent = UI_TEXT.candidatePaths;
    elements.resultDrilldownSummary.textContent = `${candidates.length}${UI_TEXT.committedCandidateRows}`;
    renderResultTable(
      ["状態", "深さ", "Action", "Prefix", "Parent"],
      candidates.map((candidate) => [
        candidate.status,
        candidate.depth,
        compactId(candidate.action_id),
        compactId(candidate.prefix_id),
        compactId(candidate.parent_prefix_id),
      ]),
    );
    return;
  }
  elements.resultDrilldownTitle.textContent = UI_TEXT.topKRoutes;
  elements.resultDrilldownSummary.textContent = ranking?.ranking_id || UI_TEXT.committedRanking;
  renderResultTable(
    ["順位", "経路", "終端", "信頼性", "Random", "手数"],
    rankedRoutes.map((route) => [
      route.rank,
      compactId(route.route_id),
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
  elements.resultEyebrow.textContent = UI_TEXT.browserPreview;
  elements.resultRouteId.textContent = "preview-only";
  elements.resultSuccess.textContent = UI_TEXT.preview;
  elements.resultPeak.textContent = "0";
  elements.resultTerminal.textContent = "0";
  elements.resultActions.textContent = "0";
  setResultVerificationState(UI_TEXT.previewOnly, false);
  renderResultEvidence(null);
  elements.resultDrilldown.hidden = true;
  renderResultTable([], []);
  renderResultRows([
    {
      title: UI_TEXT.previewRoute,
      detail: UI_TEXT.noCommittedArtifact,
    },
  ]);
  renderTerminationSummary(null);
  renderOpeningHandSummary(null);
  renderPeakBoardSummary(null);
  elements.resultNoteTitle.textContent = UI_TEXT.syntheticPreviewResult;
  elements.resultNoteDetail.textContent = UI_TEXT.realJobArtifactRequired;
}

function renderVerifiedResult(view) {
  clearReplayVerificationTimer();
  currentReplayJobId = null;
  currentResultTab = "ranking";
  const verificationState = view.result_truth.verification_state || "unverified";
  elements.resultEyebrow.textContent = view.result_truth.verification_state === "verified"
    ? UI_TEXT.realJobReplayVerified
    : UI_TEXT.realJobReplayUnverified;
  elements.resultRouteId.textContent = view.route.route_id;
  elements.resultSuccess.textContent = view.route.success ? UI_TEXT.yes : UI_TEXT.no;
  elements.resultPeak.textContent = String(view.score.peak ?? "-");
  elements.resultTerminal.textContent = String(view.score.terminal_composite ?? "-");
  elements.resultActions.textContent = String(view.route.action_count);
  setResultVerificationState(verificationState, verificationState !== "verified");
  renderResultEvidence(view.search_run);
  renderResultDrilldown(view);
  renderTerminationSummary(view);
  renderOpeningHandSummary(view.route.opening_hand);
  renderPeakBoardSummary(view.route.peak_board);
  const preferenceRows = Array.isArray(view.score.preference)
    ? view.score.preference.map((component) => ({
      title: `${UI_TEXT.preference} ${component.rule_id || UI_TEXT.rule}`,
      detail: `${component.match_status || UI_TEXT.unknown} / ${component.applied_value ?? 0}`,
    }))
    : [];
  const actionRows = view.route.actions.length
    ? view.route.actions.map((action) => ({
      title: action.decision_kind || action.action_id || UI_TEXT.routeAction,
      detail: action.state_hash_after
        ? `${UI_TEXT.committedRouteEvent} / 状態IDは内部詳細`
        : UI_TEXT.committedRouteEvent,
    }))
    : [{
      title: view.search_run.termination_reason || UI_TEXT.terminalResult,
      detail: view.search_run.best_observed
        ? UI_TEXT.bestObservedNotCertified
        : UI_TEXT.frontierCertified,
    }];
  const candidateRows = Array.isArray(view.search_run.candidate_evidence?.candidates)
    ? view.search_run.candidate_evidence.candidates.slice(0, 8).map((candidate) => ({
      title: `${UI_TEXT.candidate} ${candidate.action_id || "action"}`,
      detail: `${candidate.status || UI_TEXT.unknown} / depth ${candidate.depth ?? "-"}`,
    }))
    : [];
  const rows = [...preferenceRows, ...actionRows, ...candidateRows];
  renderResultRows(rows);
  elements.resultNoteTitle.textContent = UI_TEXT.committedArtifactResult;
  elements.resultNoteDetail.textContent = `${view.artifacts.route.schema_version} / ${view.artifact_set_id}`;
}

function renderResultError(message) {
  clearReplayVerificationTimer();
  currentReplayJobId = null;
  currentResultView = null;
  elements.resultEyebrow.textContent = UI_TEXT.resultUnavailable;
  elements.resultRouteId.textContent = UI_TEXT.notLoaded;
  elements.resultSuccess.textContent = UI_TEXT.blocked;
  elements.resultPeak.textContent = "-";
  elements.resultTerminal.textContent = "-";
  elements.resultActions.textContent = "-";
  setResultVerificationState(UI_TEXT.unavailable, false);
  renderResultEvidence(null);
  renderTerminationSummary(null);
  renderOpeningHandSummary(null);
  renderPeakBoardSummary(null);
  elements.resultDrilldown.hidden = true;
  renderResultTable([], []);
  renderResultRows([{ title: UI_TEXT.artifactVerificationFailed, detail: message }]);
  elements.resultNoteTitle.textContent = UI_TEXT.failClosedResult;
  elements.resultNoteDetail.textContent = UI_TEXT.rendererDidNotSubstitute;
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
    renderResultError(response.diagnostics[0]?.message || UI_TEXT.committedArtifactsUnavailable);
  }
  elements.resultDialog.showModal();
  replaceHash(`view=result&deck=${encodeURIComponent(selectedDeck.id)}`);
}

async function pollReplayVerification() {
  if (!currentReplayJobId) return;
  const response = await window.routeLabBridge.invoke("job.status", { job_id: currentReplayJobId });
  if (!response.ok) {
    setResultVerificationState(UI_TEXT.statusUnavailable, Boolean(currentJobId));
    showToast(response.diagnostics[0]?.message || UI_TEXT.replayStatusFailed);
    return;
  }
  const state = response.result.job.state;
  if (state === "succeeded") {
    setResultVerificationState("verified", false);
    elements.resultEyebrow.textContent = UI_TEXT.realJobReplayVerified;
    showToast(UI_TEXT.replaySucceeded);
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
      setResultVerificationState(UI_TEXT.statusUnavailable, Boolean(currentJobId));
      showToast(UI_TEXT.replayPollingFailed);
    });
  }, 750);
}

async function enqueueReplayVerification() {
  if (!desktopBridgeAvailable() || !currentJobId) {
    setResultVerificationState(UI_TEXT.previewOnly, false);
    showToast(UI_TEXT.replayRequiresCommittedJob);
    return;
  }
  clearReplayVerificationTimer();
  setResultVerificationState(UI_TEXT.queueing, false);
  const response = await window.routeLabBridge.invoke("job.enqueue_replay_verification", {
    search_job_id: currentJobId,
    idempotency_key: `replay-verification-${currentJobId}`,
    priority: 5,
  });
  if (!response.ok) {
    setResultVerificationState(UI_TEXT.unavailable, true);
    showToast(response.diagnostics[0]?.message || UI_TEXT.replayEnqueueFailed);
    return;
  }
  currentReplayJobId = response.result.job.job_id;
  setResultVerificationState(response.result.source?.verification_state || response.result.job.state || "queued", false);
  showToast(UI_TEXT.replayQueued);
  await pollReplayVerification();
}

function openCard(card) {
  document.querySelector("#card-code").textContent = `${UI_TEXT.codePrefix} ${card.code}`;
  document.querySelector("#card-title").textContent = card.name;
  const metadata = document.querySelector("#card-metadata");
  metadata.replaceChildren();
  for (const [label, value] of [[UI_TEXT.typeLabel, card.type], [UI_TEXT.attributeLabel, card.attribute], [UI_TEXT.atkDefLabel, card.stats], [UI_TEXT.localeLabel, UI_TEXT.localeValue]]) {
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
  profilePageState.deckId = selectedDeck?.id || "";
  renderProfileDeckOptions();
  const view = params.get("view");
  showWorkspaceView(["runs", "profiles", "settings"].includes(view) ? view : "decks", false);
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
  const profilesActive = view === "profiles";
  const settingsActive = view === "settings";
  const decksActive = !analyticsActive && !profilesActive && !settingsActive;
  elements.catalogPane.hidden = !decksActive;
  elements.detailPane.hidden = !decksActive;
  elements.analyticsPane.hidden = !analyticsActive;
  elements.profilesPane.hidden = !profilesActive;
  elements.settingsPane.hidden = !settingsActive;
  elements.workspace.classList.toggle("analytics-active", analyticsActive || settingsActive);
  setRailCurrent(settingsActive ? "settings" : profilesActive ? "profiles" : analyticsActive ? "runs" : "decks");
  if (analyticsActive && analyticsController.metrics().query_count === 0) {
    analyticsController.refresh();
  }
  if (profilesActive) {
    refreshDeckProfiles().catch(() => showToast(UI_TEXT.profileCatalogUnavailable));
  }
  if (settingsActive) {
    refreshSettings().catch(() => showToast(UI_TEXT.settingsLoadFailed));
  }
  if (updateHash) {
    const deckHash = `deck=${encodeURIComponent(selectedDeck?.id || "")}`;
    replaceHash(analyticsActive ? "view=runs" : settingsActive ? "view=settings" : profilesActive ? `view=profiles&${deckHash}` : deckHash);
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
    if (view === "profiles") {
      showWorkspaceView("profiles");
      return;
    }
    if (view === "settings") {
      showWorkspaceView("settings");
      return;
    }
    if (view === "decks") {
      showWorkspaceView("decks");
      activateTab("overview");
      document.querySelector("#workspace").focus({ preventScroll: true });
      return;
    }
    showToast(UI_TEXT.settingsBridgeIssue);
  });
});

document.querySelector("#open-search").addEventListener("click", openSearch);
elements.deckSettings.addEventListener("click", openDeckSettings);
elements.deckSettingsForm.addEventListener("submit", (event) => {
  saveDeckSettings(event).catch(() => {
    setDeckSettingsStatus("error", UI_TEXT.deckInputRejected, UI_TEXT.deckSettingsFailed);
  });
});
elements.settingsForm.addEventListener("submit", (event) => {
  saveDesktopSettings(event).catch(() => {
    elements.settingsStatus.textContent = UI_TEXT.settingsSaveFailed;
  });
});
elements.settingsReset.addEventListener("click", () => {
  resetDesktopSettings(false).catch(() => {
    elements.settingsStatus.textContent = UI_TEXT.settingsSaveFailed;
  });
});
elements.settingsSafeReset.addEventListener("click", () => {
  resetDesktopSettings(true).catch(() => {
    elements.settingsStatus.textContent = UI_TEXT.settingsSaveFailed;
  });
});
document.querySelector("#close-deck-settings").addEventListener("click", () => elements.deckSettingsDialog.close());
document.querySelector("#cancel-deck-settings").addEventListener("click", () => elements.deckSettingsDialog.close());
document.querySelector("#close-search").addEventListener("click", closeSearch);
document.querySelector("#cancel-search").addEventListener("click", closeSearch);
document.querySelector("#run-preflight").addEventListener("click", () => {
  runPreflight().catch(() => {
    invalidatePreflight();
    showToast(UI_TEXT.scenarioPreflightFailed);
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
      elements.jobTitle.textContent = UI_TEXT.searchFailed;
      elements.jobLog.textContent = UI_TEXT.desktopSearchDispatchFailed;
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
elements.editProfiles.addEventListener("click", openProfilePageForSelectedDeck);
elements.profileNew.addEventListener("click", () => {
  profilePageState.selectedDeckProfileId = "";
  profilePageState.rules = [];
  renderDeckProfileList();
  resetProfileEditor();
  elements.deckProfileName.focus();
});
elements.profileDeckSelect.addEventListener("change", () => {
  profilePageState.deckId = elements.profileDeckSelect.value;
  profilePageState.selectedDeckProfileId = "";
  refreshDeckProfiles().catch(() => showToast(UI_TEXT.profileCatalogUnavailable));
});
elements.profileIncludeArchived.addEventListener("change", () => {
  refreshDeckProfiles().catch(() => showToast(UI_TEXT.profileCatalogUnavailable));
});
elements.deckProfileAddRule.addEventListener("click", addProfileRule);
elements.deckProfileForm.addEventListener("submit", (event) => {
  saveDeckProfile(event).catch(() => {
    elements.deckProfileEditStatus.textContent = UI_TEXT.profileSaveFailed;
  });
});
elements.deckProfileArchive.addEventListener("click", () => {
  archiveDeckProfile().catch(() => {
    elements.deckProfileEditStatus.textContent = UI_TEXT.profileArchiveFailed;
  });
});

elements.cancelJob.addEventListener("click", () => {
  cancelJob().catch(() => showToast(UI_TEXT.cancellationFailed));
});
elements.viewResult.addEventListener("click", () => {
  openResult().catch(() => {
    renderResultError(UI_TEXT.committedArtifactsUnavailable);
    elements.resultDialog.showModal();
  });
});
elements.verifyResult.addEventListener("click", () => {
  enqueueReplayVerification().catch(() => {
    setResultVerificationState(UI_TEXT.unavailable, Boolean(currentJobId));
    showToast(UI_TEXT.replayEnqueueFailed);
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
  cancelJob().catch(() => showToast(UI_TEXT.cancellationFailed));
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
    setInlineDeckStatus("error", UI_TEXT.deckRegistrationFailed, UI_TEXT.inlineDeckRequiresBridge);
  });
});

document.querySelector("#import-deck").addEventListener("click", () => {
  importDesktopYdk().catch(() => showToast(UI_TEXT.ydkImportFailed));
});
document.querySelector("#new-inline").addEventListener("click", () => openInlineDeckDialog());

document.documentElement.dataset.workflowVersion = WORKFLOW_VERSION;
updateOpeningHandFields();
initializeFromHash();
window.addEventListener("routelabbridgeready", () => {
  refreshDesktopCatalog().catch(() => showToast(UI_TEXT.desktopCatalogFailed));
  refreshPreferenceProfiles().catch(() => showToast(UI_TEXT.terminalProfileCatalogFailed));
  if (!elements.analyticsPane.hidden) analyticsController.refresh();
});
refreshPreferenceProfiles().catch(() => showToast(UI_TEXT.terminalProfileCatalogFailed));
refreshDesktopCatalog().catch(() => showToast(UI_TEXT.desktopCatalogFailed));
