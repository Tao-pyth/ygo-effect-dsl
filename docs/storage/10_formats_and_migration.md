# Storage Formats And Migration

Status: V0.3a prototype contract

Last updated: 2026-07-13

## Format Ownership

| Artifact | Format | Schema | Audience | Purpose |
| --- | --- | --- | --- | --- |
| raw event log | JSON Lines | `raw-event-log-v1` | machine | 順序付きruntime観測の追記・stream処理 |
| run/route catalog | SQLite | `run-catalog-v2` | machine | transaction付きrun lifecycle、Route検索、集計artifact参照 |
| aggregation | Parquet | `aggregation-v1` | analytics | 多数runの列指向metric集計 |
| Experiment | YAML | `0.3a` | human/machine | review可能な実行設定 |
| Route DSL | YAML | `0.1` | human/machine | review可能な再現経路 |
| report | Markdown | `report-v1` | human | 説明・比較・リンク表示 |

形式選定のsource of truthは `ygo_effect_dsl.storage.storage_policy_document()` である。Parquetのschema、partition、公開境界は[Parquet Aggregation Backend](20_parquet_backend.md)で固定する。

## Raw Event Log

JSONL 1行は `run_id`, `sequence`, `event_type`, `payload`, `schema_version`, `record_id` を持つ。1ファイルには1つのrunだけを保存し、sequenceは0から連続させる。record idは行内容のcanonical hashであり、改変・欠落・順序変更をreaderで拒否する。writerは一時ファイルを完成させてから置換し、途中行を完成artifactとして公開しない。

## Run Catalog

SQLiteはrun id、Experiment id、status、開始/終了時刻、失敗概要、Route参照、公開済みParquet batch参照を保存する。`schema_meta` のversionが実装と一致しないDBは開かず、明示migrationを要求する。外部キーを有効にし、存在しないrunへRouteを登録しない。Parquet参照は完了runだけへ追加できる。

SQLiteはReplay本文やraw frameのsource of truthではない。大きなartifactはファイルとして保存し、catalogは識別子と参照だけをtransaction管理する。

## Human Reports And Aggregation

Markdown/HTML reportは人間向けの派生物であり、Replayやscore計算のsource of truthにしない。reportの表・説明はversion付きRoute/Evaluationから再生成する。

Parquet aggregationは多数runの比較・統計用派生物であり、個別Actionの監査にはJSONL/Routeを使う。raw log、catalog、aggregation、reportを同じファイルへ混在させない。backendはoptional dependencyの`pyarrow==25.0.0`を直接使用し、通常のRoute実行へanalytics依存を強制しない。

## Migration Policy

自動in-place migrationは禁止する。schema更新時は次の順序を守る。

1. 旧artifactを旧schemaで読んで検証する。
2. 新versionを別artifactへ書き出す。
3. record数、hash、run/route参照を検証する。
4. catalog参照をtransactionで新artifactへ切り替える。
5. 旧artifactを保持するか、明示的にarchiveする。

readerは既定でschema version完全一致だけを受理する。同一versionで宣言済みのnullable metric列が旧fileにない場合だけ`null`で補完する。未知列、必須列欠損、型変更は拒否し、新schemaへの明示migrationを要求する。
