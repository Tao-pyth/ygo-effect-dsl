# General Search Benchmark

Status: MVP logical-node calibration

`general_search_benchmark`は、short、long、grave/banish or chainの3 profileについて、fresh real-coreで生成したbase Route IDと文書digestをpinし、そのdigestから同一logical node workloadを生成する。pool `1/2/4/8/16`の完了順を変えてもsemantic digestとbest Route順位が一致することを検査し、cache、artifact、RSS、crash recovery、memory preflightをversion付きJSONへ保存する。

```powershell
python -m ygo_effect_dsl.spikes.general_search_benchmark `
  --nodes 100000 `
  --pool-sizes 1,2,4,8,16 `
  --probe-real-worker `
  --base-evidence docs/adr/evidence/0105_real_core_base_routes.json `
  --out docs/adr/evidence/0105_general_search_100k.json `
  --parquet-out docs/adr/evidence/0105_general_search_100k.parquet
```

base Route evidenceは`--base-evidence-out`と3個の`--base-route PROFILE=PATH`で再生成できる。通常CIは専用テストの縮小corpusを使い、10万nodeは手動またはself-hosted runnerで実行する。これはexecutor、prefix cache、artifact writeのlogical校正であり、ocgcore workerを150万回起動するthroughput測定ではない。`--probe-real-worker`はactive root-frontier workerを1回起動してpeak RSSを測るが、pool別real Replay throughputは別途production検証が必要である。pyarrowがない環境ではJSONをauthoritative evidenceとし、Parquet未生成を正常状態として記録する。

統計的枝刈りは`#110`、評価weightは`#108`の校正完了までproduction既定にしない。
