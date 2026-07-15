# Package 0.5.0 Work Breakdown and Acceptance

Status: Issue-backed plan

Last updated: 2026-07-16

## Work items

| Order | Issue | Deliverable | Acceptance evidence |
|---|---|---|---|
| 1 | [#157](https://github.com/Tao-pyth/ygo-effect-dsl/issues/157) | aggregation catalog/storage ADR | workload、failure、migration比較 |
| 2 | [#158](https://github.com/Tao-pyth/ygo-effect-dsl/issues/158) | corpus manifest/provenance/dedup | idempotent ingest、quarantine vectors |
| 3 | [#159](https://github.com/Tao-pyth/ygo-effect-dsl/issues/159) | background job state machine | transition table、lease/orphan tests |
| 4 | [#160](https://github.com/Tao-pyth/ygo-effect-dsl/issues/160) | cancel/retry/checkpoint recovery | fault injection、duplicate/loss audit |
| 5 | [#161](https://github.com/Tao-pyth/ygo-effect-dsl/issues/161) | paginated/filter query API | machine-readable schema、snapshot cursor tests |
| 6 | [#162](https://github.com/Tao-pyth/ygo-effect-dsl/issues/162) | Route comparison/uncertainty | missing/partial/version mismatch vectors |
| 7 | [#163](https://github.com/Tao-pyth/ygo-effect-dsl/issues/163) | Parquet partition/compaction/migration | atomic snapshot、semantic parity、write amplification |
| 8 | [#126](https://github.com/Tao-pyth/ygo-effect-dsl/issues/126), [#164](https://github.com/Tao-pyth/ygo-effect-dsl/issues/164) | analytics UI and Route drill-down | screen/state contract、PlayerView compliance |
| 9 | [#181](https://github.com/Tao-pyth/ygo-effect-dsl/issues/181) | Windows desktop shell/Python service ADR | startup/RSS/package/security/rollback比較 |
| 10 | [#182](https://github.com/Tao-pyth/ygo-effect-dsl/issues/182) | deck catalog to search-launch workflow | packaged static import/preflight/form/job/result prototype、Edge DOM/screenshot evidence |
| 11 | [#183](https://github.com/Tao-pyth/ygo-effect-dsl/issues/183) / [#247](https://github.com/Tao-pyth/ygo-effect-dsl/issues/247) | card detail/effect-text presentation | local provider、locale、license、dependency boundary、localized source/label drift qualification |
| 12 | [#184](https://github.com/Tao-pyth/ygo-effect-dsl/issues/184) | research dashboard visual/interaction system | versioned tokens/states、1440×900/960×700 prototype、keyboard/CSP baseline |
| 13 | [#244](https://github.com/Tao-pyth/ygo-effect-dsl/issues/244) | pywebview shell/versioned bridge | single invoke allowlist、native YDK、job/query/card adapter、WebView2 live smoke |
| 14 | [#245](https://github.com/Tao-pyth/ygo-effect-dsl/issues/245) | desktop lifecycle/a11y/recovery | process-tree cleanup、crash recovery、screen reader、packaged smoke |
| 15 | [#165](https://github.com/Tao-pyth/ygo-effect-dsl/issues/165) | virtualized accessible tables | Playwright、a11y、10万row responsiveness |
| 16 | [#166](https://github.com/Tao-pyth/ygo-effect-dsl/issues/166) | versioned export parity | CLI/API/UI byte/semantic comparison |
| 17 | [#167](https://github.com/Tao-pyth/ygo-effect-dsl/issues/167) | 10万run/100万row calibration | p50/p95/p99、RSS、disk、UI evidence |

## Implementation status

Items 1 through 14 are implemented and backed by versioned local evidence. Item 14 is specified by [desktop lifecycle contract](19_desktop_lifecycle_recovery.md) and `desktoplifecycleevidence_e294d061...`; it includes real ocgcore desktop execution, process-tree cleanup, retry/checkpoint recovery, and the structural accessibility/security baseline. Items 15 through 17 remain the active v0.5 completion path. Signing/update and distribution approval remain separate #134/#91 release gates and are not implied by completion of this table.

## Gate A: data integrity

- corpus itemからsource SearchRun/Route/Replay/core/asset/deck identityへ追跡できる。
- same item再取込がidempotentである。
- corrupt/incomplete/unknown schemaをaggregateへ混入させない。
- raw evidenceをin-place変更しない。
- migration/compaction前後でrow count、checksum set、semantic aggregateを照合する。
- crash時にreaderがpartial snapshotを見ない。

## Gate B: job reliability

- 全state transitionをmachine-readable tableとtestで固定する。
- worker/process crash、lease expiry、cancel、retry exhaustion、disk fullを注入する。
- committed jobの重複・消失・orphan artifactがない。
- checkpoint resumeとfresh rerunのsemantic結果が一致する。
- progressはmonotonicで、unknown totalを偽のpercentageにしない。

## Gate C: API and comparison

- stable cursor paginationをconcurrent ingest中に検証する。
- filter/sort/limitにpreflight上限を適用する。
- unknown/missing/redacted/not-applicable/quarantinedを区別する。
- baseline/interrupted/recoveryのpairとlineageを検証する。
- version/budget違いで比較不能な組合せをrejectする。
- CLI/API/UIが同じquery/comparison payloadから同じ結果を示す。

## Gate D: UI and export

- first screenをdeck catalogとし、deck選択からsearch form/preflight/job/resultへ進める。
- deck統計からfailureの最初のdivergenceまで辿れる。
- card detail/effect textをlocal verified sourceから表示し、Search/Replayへ入力しない。
- Windows desktop shellとPython/search workerのprocess境界をADRどおり実装する。
- loading/empty/error/partial/redacted/cancelled/quarantined/stale状態を実装する。
- tableは10万row相当でserver-side queryとvirtualizationを使う。
- 主要desktop解像度と最小windowでtext、toolbar、table、dialogが重ならない。
- keyboard/a11y testとPlayerView leak auditを通す。
- JSON/CSV/Parquet exportにschema/checksum/provenanceを付ける。

## Gate E: scale evidence

10万run以上、100万Event/Decision row以上で次を測る。

- ingest/aggregate/compaction/migration/export throughput
- query/comparison p50/p95/p99 latency
- worker/main/API/UI RSSとdisk/file count
- write amplification、cold/warm cache差
- concurrent ingest/query/job cancellation
- UI input-to-result latency、long task、layout stability

hardware/software/workload manifestを付け、測定値からdefault limit、partition、file size、query timeoutを決める。CIは縮小smokeとし、大規模evidenceはmanual/self-hostedで保持する。

## Release rejection conditions

- source不明またはprivate情報を含むartifactを黙って集計する。
- comparison不能を0または同等と表示する。
- job successとartifact commitが分離し、duplicate/lossが起きる。
- UIだけ別計算を行いCLI/APIと結果がずれる。
- storage/frameworkをbenchmark/ADRなしでstable contractにする。
