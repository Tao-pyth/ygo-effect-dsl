# Package 0.5.0 Versioned Export Parity

Status: Implemented local contract

Last updated: 2026-07-16

## Scope

`analytics-export-contract-v1`は、immutable analytics snapshotまたは検証済み`analytics-comparison-response-v1`から、JSON、CSV、Parquetの再現可能な成果物を生成する。CLI、desktop bridge、desktop UIは独自にserializeせず、同じ`AnalyticsExportService`を使用する。実storageの10万run／100万row校正は[#167](https://github.com/Tao-pyth/ygo-effect-dsl/issues/167)の別gateであり、この契約の完了からproduction性能を主張しない。

## Authority and schemas

| Concern | Authority |
|---|---|
| filter、sort、selected fields、value state | `AnalyticsQueryService.select_for_export()` |
| query source | content-addressed `analytics-snapshot-v1` |
| comparison source | `analytics-comparison-response-v1` |
| canonical semantic dataset | `analytics-export-data-v1` |
| serialization and checksum | `AnalyticsExportService` |
| background lifecycle | `job-spec-v2` export job and `job-catalog-v2` |
| renderer | command input and status presentation only |

公開schemaは`analytics-export-request-v1`、`analytics-export-data-v1`、`analytics-export-manifest-v1`、`analytics-export-result-v1`、`analytics-export-worker-v1`である。machine-readable契約は`src/ygo_effect_dsl/resources/analytics-export-contract-v1.json`とする。各schema versionはpackage versionから独立し、未知versionをfail-closeする。

## Source binding

Query exportはcursorを受け付けず、開始時のcurrent snapshot IDへ一度だけ束縛する。filter、sort、field projection、missing／unknown／redacted／not-applicable／quarantined stateは通常queryと同じ実装を通る。snapshot消失、cursor混入、scan上限、row上限は空結果へ変換しない。

Comparison exportは既存responseを再計算せず、そのrequest IDとreport IDを内容から再検証して保存する。desktop rendererはcomparison responseを直接注入できず、設定済みPython comparison handlerへrequestを渡してresponseを生成する。CLIはローカルの検証済みresponseファイルを入力とする。

## Formats and parity

- JSONはcanonical semantic datasetをsort-key、compact UTF-8で保存する。
- CSVはquery row IDと各fieldのstate/valueを分離し、valueをcanonical JSON cellとして保存する。先頭が`= + - @ tab CR`のcellはapostrophe escapeする。
- ParquetはCSVと同じflat semantic columnsをstring columnとして保存し、data schemaとsource kindをschema metadataへ付ける。optional analytics dependencyがなければ明示的に失敗する。
- 三形式は`exportsemantic_` digestが一致し、decoderで同じcanonical datasetへ戻らなければならない。
- CLI、service、desktop bridge workerは同じ形式についてdata bytesとmanifest bytesが完全一致しなければならない。

## Manifest and provenance

Manifestはformat、row count、data filename／bytes／SHA-256、semantic digest、bound request、request ID、snapshot ID、source IDs、comparison report ID、query fingerprint、package／Python／pyarrow versionを持つ。`analyticsexport_` IDはmanifest identityから導出する。既存同一ID directoryは両checksumが一致する場合だけidempotent成功とし、競合内容を上書きしない。

## Background execution

Desktop APIの`analytics.export.enqueue`はrenderer pathを受け取らず、format、source kind、typed source、priority、idempotency keyだけを受け取る。requestをcontent-addressed fileへ保存してexport jobを作り、専用workerだけが`kind=export`をclaimする。Search workerも`kind=search`だけをclaimし、異種jobをquarantineしない。

Workerはcancel signalをquery走査中とserialize前に検査し、transient I/O、disk full、lease expiry、worker crashをversion付きretry policyで扱う。dataとmanifestはattempt stagingへwrite／fsync／checksum検証後にatomic publishし、同じSQLite transactionでjob successとartifact referenceを確定する。UIは既存`job.status`と`job.cancel`を利用する。

## Limits and security

既定上限はscan 100,000 rows、output 100,000 rows、data 512 MiBである。#167の実測では100,000行のJSON/CSV/Parquet buildが約28.7から30.6秒、peak RSSが最大約2.48GBであり、未検証の1,000,000行exportを許可しない。direct writerとbackground workerはいずれもstagingを含む空きdiskを事前検査する。出力先はcallerまたはservice所有rootで解決し、export ID directoryと固定filenameだけを使用する。rendererからpath、URI、filename、Python objectを受け取らない。

## Verification

`docs/storage/evidence/analytics_export.json`は同じsnapshot/queryについて三形式のsemantic digest一致、service／CLI subprocess／desktop bridge workerのbyte一致、formula-leading cell非露出、renderer非serializeを記録する。sample dataと各manifestは`docs/storage/evidence/analytics_export_v1/`に保存する。取消、再試行、job種別分離、byte上限、content-addressed snapshot、CLI/API parityは自動testで固定する。
