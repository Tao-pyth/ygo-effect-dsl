# Package 0.5.0 Analytics Contracts

Storage authority and schema-evolution boundaries are fixed by
[`ADR 0015`](../../adr/0015_v05_aggregation_catalog_boundary.md). SQLite owns
single-host operational state, Parquet owns rebuildable corpus metrics, and UI
caches are disposable projections rather than evidence.

Status: Implemented and released in package 0.5.0

Last updated: 2026-07-14

## Storage boundary

[#157](https://github.com/Tao-pyth/ygo-effect-dsl/issues/157)はSQLite、DuckDB等のcatalog候補とParquetの責任分担を、実workloadで決定する。選定前に特定DBを公開contractにしない。

論理層は次の3層を分離する。

| Layer | Mutability | Responsibility |
|---|---|---|
| raw evidence | immutable | SearchRun/Route/Replay/Event/Decisionの原本とchecksum |
| catalog/aggregate | rebuildable | identity索引、job、dedup、partition、derived metrics |
| presentation cache | disposable | API/UIの短期cache、view materialization |

raw evidenceをschema migrationでin-place再解釈しない。migrationはnew snapshotを作り、old/new semantic digestを比較する。

## Corpus manifest

The implemented baseline is `corpus-manifest-v1`, validated by
`corpus-manifest-validation-v1` and indexed in `corpus-catalog-v1`.
`corpus_item_id` identifies exact content plus its provenance identity, while
`corpussemantic_` identifies the reaggregation unit independently of source
path, ingest time, and byte serialization. Exact duplicates are idempotent;
semantic duplicates retain every raw item and record the first matching item.

Only `complete` items can enter aggregation. `incomplete`, `corrupt`, and
`quarantined` items remain inspectable but ineligible. Invalid schema, missing
provenance, ID mismatch, and embedded third-party assets are stored in an
idempotent quarantine ledger with machine-readable diagnostics. Manifests store
asset lock, database hash, and source commit references only; they never embed
third-party CDB, Lua, image, or card-text assets.

各corpus itemは最低限次を持つ。

- corpus/item ID、content SHA-256、ingest timestamp、source URIまたはlocal provenance
- package/contract/schema version
- experiment/scenario/deck/opening hand/search/evaluator identity
- core/asset lock、Route/Replay/State identity
- complete/PlayerView information modeとredaction policy
- complete/incomplete/corrupt/quarantined状態
- source/derived artifactのparent lineage

exact duplicateはcontent identityでidempotentに扱う。semantic duplicateの判定は分析用labelに留め、raw itemを削除しない。

## Job state machine

The implemented baseline is `job-state-machine-v1`, persisted in a dedicated
`job-catalog-v2` SQLite catalog. The public states are `queued`, `running`,
`cancelling`, `cancelled`, `succeeded`, `failed`, `retrying`, and
`quarantined`. Every transition stores the attempt, actor, UTC timestamp, and
reason. Invalid transitions fail closed.

| From | Allowed targets |
|---|---|
| queued | running, cancelling, failed, quarantined |
| running | cancelling, succeeded, failed, retrying, quarantined |
| cancelling | cancelled, failed, quarantined |
| failed | retrying, quarantined |
| retrying | running, cancelling, failed, quarantined |
| cancelled, succeeded, quarantined | none |

`job-spec-v2` provides common idempotency, input digest, priority, maximum
attempt, dependency, job deadline, and `job-retry-policy-v1` fields. It
validates exact payloads for search, replay, import, aggregate, and export jobs.
A dependency must already exist and must reach `succeeded` before its child can
be claimed. Selection is deterministic by priority, creation time, and job ID.
Search budgets and semantic stop conditions remain inside the referenced
Experiment; the generic job deadline only bounds execution time.

Running work is owned by an attempt-scoped lease token. Heartbeats extend the
lease, stale tokens cannot mutate a newer attempt, and expired jobs return to
`retrying` until `max_attempts` is exhausted. Expired cancelling jobs become
`cancelled`. `succeeded` and its non-empty artifact set are committed in one
SQLite transaction; constraint failure leaves the job running and publishes no
artifact.

`job-checkpoint-v1` binds canonical payload, input digest, attempt, sequence,
recovery position, completed units, optional total units, and optional semantic
result digest. Recovery position is an idempotency key: equal content is
accepted, conflicting content fails closed. Progress cannot decrease, a known
total cannot change, payload size is limited to 1 MiB, and resume requires the
immutable JobSpec input digest. This preserves unknown totals rather than
inventing a percentage.

Workers poll `job-control-v1` for cooperative cancel, lease expiry, attempt hard
timeout, and job deadline. `JobRecoverySupervisor` invokes the process owner's
terminate/kill callback before releasing a timed-out lease. Failed termination
leaves the attempt running. Retry eligibility and exponential backoff come only
from the versioned policy; exhausted or non-retryable attempts fail closed.

Filesystem publication follows ADR 0015: write and fsync an attempt staging
file, verify its SHA-256, atomically rename it, then commit success and artifact
references in SQLite. `JobArtifactPublisher.reconcile()` verifies every
committed reference, preserves active attempts, and removes unreferenced files
from inactive attempts. Missing or hash-mismatched committed artifacts are
corruption. Fault vectors cover checkpoint commit boundaries, partial writes,
disk full, aggregate multi-artifact rename, catalog commit, hard timeout, and
process-termination failure.

`job-status-v1` is read from one SQLite snapshot and exposed by the API and
`job-inspect --catalog CATALOG JOB_ID`. It includes attempt, cancel/retry reason,
recovery position, latest checkpoint, transitions, and artifacts. Catalog v1
requires explicit migration and is never modified in place by a v2 reader.

## Query API

`analytics-query-contract-v1`は同期query APIの公開境界である。request、response、errorはそれぞれ`analytics-query-request-v1`、`analytics-query-response-v1`、`analytics-query-error-v1`でversion管理し、配布物の`analytics-query-contract-v1.json`をmachine-readable contractとする。

- filter fieldはrun、deck、card、strategy、interruption、success、score、time、version、statusを必須集合とし、route、experiment、evaluator、target board、action count、resource consumption、state hashも選択できる。filterはfieldごとの型付きoperatorだけを受理し、文字列式や任意SQLは受理しない。
- cardとinterruptionは複数値を保持し、contains、contains-any、contains-allで検査する。score、time、数値metricはinclusive rangeを持つ。
- valueはvalue、empty、missing、unknown、redacted、not-applicable、quarantinedを明示し、`null`へ統合しない。通常filterはobserved valueだけに適用し、状態自体は`state_is`でfilterする。
- sortは許可fieldを最大4個まで指定し、同値時は常に`row_id`昇順で順序を固定する。selected fieldsはrow identityを削らず、payloadのvaluesだけを縮小する。
- cursorはchecksum、request fingerprint、snapshot ID、last row ID、sort valuesを含むopaque tokenである。fields、filter、sort、limitまたはsnapshotを変更した再利用はfail-closeする。同一cursorの再利用は同じsnapshotが保持される間idempotentである。
- snapshotはcontent-addressedかつimmutableとする。concurrent ingestは新snapshotをcurrentにするだけで、既存cursorのresponse seriesは旧snapshotを読み続ける。旧snapshotを破棄した場合は`snapshot_unavailable`を返し、暗黙に新snapshotへ移動しない。
- 同期実装が検査可能なsnapshot row数には明示上限を設ける。上限超過は`sync_scan_limit_exceeded`と`async_job_required=true`を返し、既存`export` jobへquery snapshot IDを渡す。同期APIでunbounded scan/exportを開始しない。
- `AggregationRecord`のschemaは変更せず、`analytics_row_from_aggregation()`でquery rowへ変換する。元recordに存在しないdeck/card/strategy/interruption/statusは呼び出し側がprovenanceから明示し、省略時はmissingとする。

## Comparison semantics

`analytics-comparison-contract-v1`はquery snapshotから作るbaseline/interrupted/recovery比較の共通payloadである。UI、CLI、exportは独自に差分を再計算せず、`build_analytics_comparison_report()`のversion付きresponseを利用する。

- 対応キーはdeck、scenario、opening hand、trial、interruptionと`strategy-interruption-lineage-v1`のvalidated lineage IDから作る。source lineageのdivergence ID、lineage ID、recovery action count、各arm semantic IDを再計算して照合し、任意のrun IDだけでpairを推測しない。
- pairはbaseline、interrupted、recoveryを別armとして保持する。arm欠落は`incomplete`とmissing valueを返し、0差や失敗へ変換しない。重複armとsnapshot混在はconfiguration errorとしてfail-closeする。
- absolute deltaは`after - before`、relative deltaは`(after - before) / abs(before)`とする。beforeが0の場合のrelative deltaは`not_applicable`であり、0ではない。missing、unknown、redacted、quarantined等はquery value stateを維持する。
- evaluator ID/version/config、search strategy ID/version/config、observation schema、search schemaが完全一致する場合だけ既定で比較する。差がある場合は両context IDを指定した`validated_semantic_equivalence` evidenceが必要で、なければ`incomparable`としてdeltaを出さない。
- planned budgetのunitと上限が一致し、budget evidenceが記録されていることをpair deltaの条件とする。consumed/plannedとpartial状態はarmごとに保存する。early stop、timeout、pruned、partial budget、failed、quarantined completionはcensoredとして表示し、集約deltaとconfidence sampleから除外する。
- statistical pruning policyはpairとreportのbias metadataへ必ず残す。partial budget pair数、censored pair数、context不一致、missing pair数をsample情報として分離する。
- confidenceはpaired meanのnormal approximation v1をprovisional methodとしてversion、confidence level、assumption、sample countと共に返す。2 pair未満は`unavailable_insufficient_sample`とし、値を生成しない。将来別methodを追加しても既存methodを暗黙変更しない。
- machine-readable正本は配布resourceの`analytics-comparison-contract-v1.json`とする。既存`interruption-comparison-v1`は単一Route pairの詳細比較として維持し、corpus統計契約へ置き換えない。

## Parquet and snapshots

`parquet-lifecycle-contract-v1`をcompaction、migration、backfill、rollbackの公開境界とし、machine-readable正本を配布resourceの`parquet-lifecycle-contract-v1.json`とする。既存の1 run単位writerは変更せず、lifecycle層が同一partitionのsmall fileをimmutable snapshotへまとめる。

- partitionはevaluator version、Experiment ID、run dateを維持する。sortはrun ID、Route ID、target board、aggregation record ID、compressionはzstd level 3、row groupは16,384行とする。20,000 unique行の固定計測では選択構成が911,526 bytes、snappyが1,832,077 bytes、4,096-row groupのzstdが934,282 bytesだった。
- target file sizeは16 MiB、保守的なplanning値は256 bytes/rowとする。production規模校正では既存partition、zstd level 3、16,384 row group、sort policyを維持した。policy上の行数ceilingは131,072だが、size見積りを先に適用するため既定の実効上限は65,536行/fileである。実file splitはsize、row-group、partition境界をすべて守る。
- manifestはfile checksum、schema、row count、bytes、column min/max、partition、source snapshot/file set、created-by job、disk preflight、write amplificationを保持する。manifest、file、pointerの不一致はfail-closeする。
- compactionとmigrationは新snapshot directoryへ全fileとmanifestを書き、再読込とsemantic parityを確認した後、`current-snapshot.json`だけをatomic replaceする。readerはpointerを1回読み、旧snapshotまたは新snapshotの一方だけを読む。stagingと非active snapshotをrecursive scanしない。
- active snapshot後にingestされた新run fileは、そのsnapshotを途中変更せず次回compactionで取り込む。既存record IDのmetric変更を通常ingestで追加せず、明示migrationを要求する。
- semantic parityはrecord set、state hash、score、success、Action count、partitionを照合する。nullable derived metricのbackfillは許可するが、core metric変更は拒否する。未知のaggregation schemaはcodecを推測せず拒否する。
- rollbackは保持済みsnapshotを検証してpointerを再切替する。旧snapshotの削除は自動化せず、明示maintenanceとretention判断へ分離する。

## UI contract

first screenはmarketing pageやrun overviewではなくdeck catalogとする。主要viewは次のとおり。

- deck catalog、deck detail、card list、card detail/effect text
- deck statistics、過去run、strategy/interruption comparison
- search launch form、scenario preflight、job progress/result
- job queue/progress/failure
- corpus/run/strategy/interruption comparison
- score/resource/success distribution
- Route、Event、Decision、lineage drill-down
- filter、column、density、shareable state、export

primary flowは`deck catalog -> deck detail/statistics -> search form -> preflight -> job -> result`とする。run observation tableは`analytics-query-contract-v1`によるserver-side sort/filter、500行cursor pagination、viewport row virtualizationを実装済みである。stable row dimensions、keyboard navigation、focus、screen-reader count/name、loading/empty/errorを`desktop-virtual-table-v1`へ固定する。partial/redacted/quarantined/staleはquery value stateをそのまま表示し、PlayerView policyをUI payload、tooltip、downloadにも適用する。実storageは10万run、100万Event/Decision row、10万aggregation rowで校正済みである。browser rendererの10万行fixtureはpersistent storageの代替ではなく、両証跡を[production scale calibration](23_production_scale_calibration.md)で明示的に分離する。

## Card presentation contract

card detailはcode、name、type、attribute/race、level/rank/link、ATK/DEF、setcode等のmetadataとeffect textを表示する。`card-presentation-v1`と`LocalizedCardPresentationProvider`は、ocgcore callback用`SQLiteCardDataProvider`から分離したread-only interfaceとして実装済みである。詳細は[card presentation contract](16_card_presentation_contract.md)に固定する。

- verified local CDB等をread-only sourceにする。
- locale、source lock、CDB commit/hash、field completenessをpayloadへ含める。
- missing/unknown/redacted/stale/version mismatchを空文字と区別する。
- effect textは表示・検索補助だけに使用し、Search/Replay/Evaluationへ入力しない。
- legacy card-text artifact pipelineへ依存しない。
- card text/CDB/imageをrepository、wheel、desktop executableへ無審査同梱しない。
- imageは別のoptional contractとし、text-onlyでも全操作を完了できるようにする。

詳細と未確定事項は[#183](https://github.com/Tao-pyth/ygo-effect-dsl/issues/183)で管理する。

## Windows desktop boundary

UIはWindows desktop applicationとして提供する。shell、Python process、local API/IPC、installer、update方式は[#181](https://github.com/Tao-pyth/ygo-effect-dsl/issues/181)のADR前に固定しない。

- desktop shellはsearch worker/native coreを直接所有せず、Python service境界を明示する。
- app終了、worker crash、upgrade、rollback時のprocess ownershipを定義する。
- file picker/YDK import、single instance、deep link、local path権限を検証する。
- localhostを使う場合はbind範囲、authentication、CSP、port collisionを扱う。
- third-party card assetsをinstallerへ含めず、owned local asset resolverを利用する。

## Export contract

`analytics-export-contract-v1`を実装し、JSON/CSV/Parquet exportはquery snapshot、filter、sort、redaction、comparison semanticsをAPIと共有する。schema、manifest、checksum、source/software provenanceを付け、同一形式のCLI/service/desktop worker bytesと三形式のsemantic digestを一致させる。large exportは専用background jobとしてcancel/retry/atomic publishする。CSV formula injection、renderer path input、row/byte/disk上限をfail-closeする。詳細と証跡は[versioned export parity](22_versioned_export_parity.md)に固定する。scale校正で100,000行三形式のsemantic parityを再確認した一方、最大peak RSSが約2.48 GBだったため、scan/output hard capは100,000行とし、未測定の100万行exportを拒否する。

## Production scale calibration

`analytics-scale-calibration-v1`は、raw JSONL、SQLite catalog、Parquet lifecycle、persistent query、application query、desktop bridge、三形式exportを同じscale manifestで測る。固定evidenceは10万run、100万Event/Decision row、10万aggregation rowを満たし、crash、migration、rollback、concurrent ingest/query、concurrent compaction/read、cancelを含む。

- persistent warm filter/sortはp50 33.19 ms、p95 35.80 ms、p99 36.64 msだった。
- application queryはp50 9.18 s、desktop bridge queryはp50 9.36 sであり、同期scan 10,000行の既定を維持する。
- JSON/CSV/Parquet 100,000行exportは約28.7から30.6秒、最大peak RSS約2.48 GBだった。
- Parquet compactionは100 fileを2 fileへ減らし、write amplificationは0.9296だった。
- machine-readable summary、sample、再現手順、非保証範囲は[production scale calibration](23_production_scale_calibration.md)を正本とする。
