# Package 0.5.0 Work Breakdown and Acceptance

Status: Issue-backed plan

Last updated: 2026-07-14

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
| 9 | [#165](https://github.com/Tao-pyth/ygo-effect-dsl/issues/165) | virtualized accessible tables | Playwright、a11y、10万row responsiveness |
| 10 | [#166](https://github.com/Tao-pyth/ygo-effect-dsl/issues/166) | versioned export parity | CLI/API/UI byte/semantic comparison |
| 11 | [#167](https://github.com/Tao-pyth/ygo-effect-dsl/issues/167) | 10万run/100万row calibration | p50/p95/p99、RSS、disk、UI evidence |

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

- corpus/run overviewからfailureの最初のdivergenceまで辿れる。
- loading/empty/error/partial/redacted/cancelled状態を実装する。
- tableは10万row相当でserver-side queryとvirtualizationを使う。
- desktop/mobileでtext、toolbar、table、dialogが重ならない。
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
