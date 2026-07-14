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
