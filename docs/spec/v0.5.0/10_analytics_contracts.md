# Package 0.5.0 Analytics Contracts

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

最低状態は`queued`、`running`、`cancelling`、`cancelled`、`succeeded`、`failed`、`retrying`、`quarantined`とする。不正遷移を拒否し、state changeはattempt、actor、timestamp、reasonを持つ。

- lease/heartbeatでorphan workerを検出する。
- idempotency keyで同一jobの二重commitを防ぐ。
- search budgetとjob deadlineを別fieldにする。
- checkpointはschema/version/input hashに一致する場合だけresumeする。
- success stateとartifact manifest commitをatomicに対応付ける。
- cancellation後のpartial artifactはquarantineまたは明示的partial状態にする。

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

first screenはmarketing pageではなくcorpus/run overviewとする。主要viewは次のとおり。

- job queue/progress/failure
- corpus/run/deck/strategy/interruption comparison
- score/resource/success distribution
- Route、Event、Decision、lineage drill-down
- filter、column、density、shareable state、export

large tableはserver-side sort/filterとvirtualizationを使う。stable row dimensions、keyboard navigation、focus、screen-reader label、loading/empty/error/partial/redacted stateを実装する。PlayerView policyをUI payload、tooltip、downloadにも適用する。

## Export contract

JSON/CSV/Parquet exportはquery snapshot、filter、sort、redaction、comparison semanticsをAPIと共有し、schema、manifest、checksum、provenanceを付ける。large exportはbackground jobとし、cancel/retry可能にする。CSV formula injection、path traversal、memory/disk limitを防御する。
