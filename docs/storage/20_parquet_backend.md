# Parquet Aggregation Backend

Status: Implemented optional analytics backend

Last updated: 2026-07-13

## Boundary

Parquetは多数runのRoute metricを走査する派生集計であり、Replay、raw core frame、Action、Route DSLのsource of truthではない。個別runの監査はJSONLとRouteを使い、Parquet行からReplayを復元しない。

backendは`pyarrow==25.0.0`を直接使うoptional dependencyである。

```bash
pip install -e ".[analytics]"
```

PyArrowを選ぶ理由は、Arrow schema metadata、nullable列、Parquet型、partition pathをDataFrame層なしで直接固定できるためである。Windows CPython 3.13 wheelの実測は27,861,162 bytes、Polars 1.42.1とruntime wheelの合計は53,553,054 bytesだった。PyArrow installed packageは85,439,441 bytes、別processでの`import pyarrow, pyarrow.parquet`は5回すべて成功し、中央値は254.326 msだった。時間は環境依存の観測値であり、性能保証には使わない。

## Schema v1

`aggregation-v1`の1行は次を持つ。

- identity: aggregation record ID、run ID、Route ID、Experiment ID
- evaluator: evaluator ID、version、config hash
- target: `peak_board`または`terminal_board`、State hash
- values: success、score、atomic Action count
- optional metric: `resource_consumption` (`float64 nullable`)
- partition columns: evaluator version、Experiment ID、run date

record IDはrun、Route、target、evaluator identityから生成し、nullable metric追加では変えない。batch IDは行の全内容を含むため、metric値が変われば別fileになる。

Parquet schema metadataへ`ygo.schema_version=aggregation-v1`と`ygo.partition_layout=evaluator_version/experiment_id/run_date`を保存する。必須列欠損、未知列、型不一致、metadata不一致はfail-closeする。

## Partition Layout

1 fileは1 runかつ1 partitionに限定する。Hive形式のpathは次である。

```text
evaluator_version=<version>/experiment_id=<id>/run_date=YYYY-MM-DD/part-<batch-id>.parquet
```

partition値はpercent encodeし、slashやWindows予約文字をdirectory境界として解釈しない。readerは行内partition列とpathを照合する。同一record IDが複数fileに存在するdatasetは拒否する。

## Publication Boundary

`publish_aggregation_partition`は次の順序を固定する。

1. JSONLのrecord hash、run ID、連続sequenceを検証する。
2. 各Routeに`route_completed` eventがあることを検証する。
3. SQLite catalogのrunが`complete`でExperiment IDが一致することを検証する。
4. 同一partitionへ一時Parquetを書き、schemaと全行を再読込する。
5. fileをatomic replaceで公開する。
6. SQLite transactionでbatch ID、path、row count、SHA-256を登録する。

filesystemとSQLiteを単一transactionにはできない。手順6が失敗した場合、catalogから参照されない完成fileが残るが、不完全fileへの参照は作られない。同一batchの再実行はfile内容とcatalog recordが一致すれば冪等に成功し、不一致なら拒否する。orphan fileの削除はcatalog照合後に行う保守処理であり、このwriterが推測削除しない。

## Schema Evolution

同じ`aggregation-v1`内で後方互換とするのは、schemaで宣言済みのnullable metric列が旧fileに存在しない場合だけである。readerはその列を`null`で補う。metricの型変更、必須化、意味変更、partition変更は新しいaggregation schema versionを作り、旧artifactを別pathへ保持したまま書き直す。

Run catalogはParquet参照追加により`run-catalog-v2`となる。v1 databaseをin-placeで暗黙更新せず、schema不一致として明示migrationを要求する。

## Evidence

固定evidenceは`docs/storage/evidence/parquet_backend.json`、evidence IDは`parquetevidence_d715ef89e639f4f4159c85d5695a2e2b7b273caa63740a2349335d64a8d0b69c`である。代表実Routeのwrite/read、catalog公開、nullable列追加、型変更拒否、Windows wheel/起動probeを含む。

機能部分はtestごとにfresh temporary directoryへ再生成する。配布probeを再取得する場合は、PyArrow wheelとPolars wheel一式を明示して次を実行する。

```powershell
python -m ygo_effect_dsl.spikes.parquet_backend_evidence --out docs/storage/evidence/parquet_backend.json --pyarrow-wheel <pyarrow-wheel> --polars-wheel <polars-wheel> --polars-wheel <polars-runtime-wheel>
```

参照: [PyArrow package](https://pypi.org/project/pyarrow/)、[Arrow Parquet API](https://arrow.apache.org/docs/python/parquet.html)、[Arrow Dataset writer](https://arrow.apache.org/docs/python/generated/pyarrow.dataset.write_dataset.html)、[Polars package](https://pypi.org/project/polars/)。
