# Package 0.5.0 Analytics Contracts

Storage authority and schema-evolution boundaries are fixed by
[`ADR 0015`](../../adr/0015_v05_aggregation_catalog_boundary.md). SQLite owns
single-host operational state, Parquet owns rebuildable corpus metrics, and UI
caches are disposable projections rather than evidence.

Status: Contract design backlog

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

query APIはstable cursor ordering、limit、filter、selected fieldsを持つ。最低filterはrun/deck/card/strategy/interruption/success/score/time/version/statusである。

- cursorはquery/filter/sort/snapshot identityへbindする。
- concurrent ingest中も一つのresponse seriesは同じsnapshotを読む。
- unbounded scan/exportを同期APIで実行しない。
- unknown、missing、redacted、not-applicable、quarantinedを別値として表す。
- request/response/errorにversion付きmachine-readable schemaを持つ。

## Comparison semantics

baseline/interrupted/recoveryの比較はvalidated lineage keyに基づく。絶対差、相対差、pair completeness、budget completeness、sample size、confidence情報を別fieldにする。

- pair欠落を0差にしない。
- evaluator/search/schema versionが異なる場合、比較可能条件を満たさなければrejectする。
- early stop、timeout、pruning、partial budgetをuncertainty metadataへ残す。
- confidence intervalを表示する場合はmethod/version/assumption/sample countを保存する。
- statistical pruningやweight由来のbiasを隠さない。

## Parquet and snapshots

partition key、sort、row group、compression、target file sizeはbenchmarkから決める。small-file compactionとmigrationはatomic publishを使い、readerは旧snapshotまたは新snapshotのどちらかだけを見る。

manifestはfile checksum、schema、row count、min/max、partition、source set、created-by jobを持つ。compaction前後とmigration前後でsemantic aggregateを照合する。

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

primary flowは`deck catalog -> deck detail/statistics -> search form -> preflight -> job -> result`とする。large tableはserver-side sort/filterとvirtualizationを使う。stable row dimensions、keyboard navigation、focus、screen-reader label、loading/empty/error/partial/redacted/quarantined/stale stateを実装する。PlayerView policyをUI payload、tooltip、downloadにも適用する。

## Card presentation contract

card detailはcode、name、type、attribute/race、level/rank/link、ATK/DEF、setcode等のmetadataとeffect textを表示する。ただし現行`SQLiteCardDataProvider`はocgcore callback用に`datas`表だけを読むため、presentation用metadata/text providerを別interfaceとして追加する。

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

JSON/CSV/Parquet exportはquery snapshot、filter、sort、redaction、comparison semanticsをAPIと共有し、schema、manifest、checksum、provenanceを付ける。large exportはbackground jobとし、cancel/retry可能にする。CSV formula injection、path traversal、memory/disk limitを防御する。
