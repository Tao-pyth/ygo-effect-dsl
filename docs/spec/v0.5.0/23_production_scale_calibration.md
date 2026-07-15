# Package 0.5.0 Production Scale Calibration

Status: Implemented local evidence

Last updated: 2026-07-16

## Scope

`analytics-scale-calibration-v1`は、10万run、100万Event/Decision row、10万aggregation rowの同一workloadをproduction schemaと公開application serviceへ通し、Package 0.5.0のscale gateを校正する。測定対象はraw JSONL、SQLite run catalog、Parquet lifecycle、query/comparison、desktop bridge、JSON/CSV/Parquet export、cancel、concurrent ingest/query、crash recoveryである。

このevidenceは単一の32 GiB Windows hostにおけるlocal qualificationであり、production SLA、他host性能、100万aggregation rowまたは100万行exportを保証しない。rendererの10万行測定は別のdeterministic browser fixtureであり、persistent storage workloadと同一であるとは扱わない。

## Contract and workload

machine-readable契約は`analytics-scale-calibration-v1.json`、固定summaryは`docs/storage/evidence/analytics_scale_calibration.json`、operation sampleは`docs/storage/evidence/analytics_scale_samples.parquet`である。evidence IDは`analyticsscaleevidence_2227888e4cb3b0d779fd5b6220833ddd1214b03252aee583efa425ab7e78e3a4`とする。

| Dimension | Value |
|---|---:|
| run catalog rows / raw files | 100,000 |
| Event/Decision rows | 1,000,000 |
| aggregation/query rows | 100,000 |
| legacy Parquet files | 100 |
| query samples | 9 |
| platform | Windows 11 x64、12 logical CPU、32 GiB RAM |
| runtime | Python 3.13.7、SQLite 3.50.4、PyArrow 25.0.0 |

測定時のpackage metadataはrelease前checkoutの`0.3.0`を記録している。結果の同一性はpackage文字列ではなく、commit上のcontract resource、evidence ID、sample checksumで検証する。0.5.0 release artifactの性能保証へ読み替えない。

## Results

代表値は次のとおり。全sample、p50/p95/p99、RSS、throughputはParquet evidenceを正本とする。

| Operation | Result |
|---|---|
| raw ingest | 100万row / 100,000 file、131.2 s、約7,623 row/s |
| catalog create / finish | 100,000 runを316 ms / 473 ms |
| legacy Parquet publish / read | 100,000 rowを2.68 s / 5.19 s |
| compaction | 100 fileから2 file、50.9 s、write amplification 0.9296 |
| migration recovery | 100,000 row、52.0 s、write amplification 1.0006 |
| persistent warm filter/sort | p50 33.19 ms、p95 35.80 ms、p99 36.64 ms |
| persistent run drill-down | p50 1.65 ms、p95 2.00 ms、p99 2.03 ms |
| persistent comparison | p50 1.23 ms、p95 1.53 ms、p99 1.56 ms |
| application query | p50 9.18 s、p95 10.34 s、p99 10.59 s |
| desktop bridge query | p50 9.36 s、p95 10.22 s、p99 10.36 s |
| 100,000-row export | JSON 30.0 s / 68.8 MB、CSV 30.6 s / 21.2 MB、Parquet 28.7 s / 13.3 MB |
| export peak RSS | 最大約2.48 GB |
| cancel acknowledgement | 36.9 ms |
| final work root | 約407 MB、100,122 files |

全形式のexport semantic digestは一致した。pointer更新前crashでは旧snapshotを維持し、migration recoveryとrollback、concurrent compaction readerの旧または新の完全snapshot、concurrent ingest中のquery snapshot固定を確認した。

## Policy decisions

- synchronous query scanは10,000行を維持する。それを超える走査はasync exportまたは明示service policyを要求する。
- export scan/output hard capは1,000,000行から実測済みの100,000行へ縮小する。data capは512 MiBを維持する。
- Parquetはzstd level 3、16,384 row group、16 MiB target、既存partition/sort keyを維持する。scale測定でsemantic parity、recovery、file reductionを再確認した。
- 100,000 raw fileは監査境界を満たすが、file count costが大きい。raw evidence retention/packingを変更する場合はimmutabilityとrun provenanceを保つ別contractが必要である。
- application snapshotは100,000行で大きなmaterialization costを持つ。UIが全行をPython object化せず、既存500行cursorとvirtualizationを使う方針を維持する。

## Reproduction

CIは小規模smokeをtest suiteで実行し、full workloadはmanual/self-hosted workflowに分離する。

```powershell
python -m ygo_effect_dsl.spikes.analytics_scale_calibration `
  --runs 100000 `
  --event-rows 1000000 `
  --analytical-rows 100000 `
  --out docs/storage/evidence/analytics_scale_calibration.json `
  --samples-out docs/storage/evidence/analytics_scale_samples.parquet
```

`.github/workflows/analytics-scale-calibration.yml`は同じ既定workloadをWindows self-hosted runnerで実行する。通常CIで10万fileを毎回生成しない。
