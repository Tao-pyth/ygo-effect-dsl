# General Search Benchmark

Status: MVP logical-node calibration

`general_search_benchmark`は、外部qualification済みshort、long、grave/banishの成功Route 3本を`real-core-benchmark-base-routes-v2`へpinし、その文書digestから同一logical node workloadを生成する。pool `1/2/4/8/16`の完了順を変えてもsemantic digestとbest Route順位が一致することを検査し、cache、artifact、RSS、crash recovery、memory preflightをversion付きJSONへ保存する。base evidenceはExperiment文書digest、Route ID/digest、terminal Stateだけを持ち、raw path、deck、opening hand、card codeを保存しない。

```powershell
python -m ygo_effect_dsl.spikes.general_search_benchmark `
  --nodes 100000 `
  --pool-sizes 1,2,4,8,16 `
  --probe-real-worker `
  --base-evidence docs/adr/evidence/0105_real_core_base_routes.json `
  --out docs/adr/evidence/0105_general_search_100k.json `
  --parquet-out docs/adr/evidence/0105_general_search_100k.parquet
```

base Route evidenceは`--base-evidence-out`と3個の`--base-route PROFILE=PATH`で再生成できる。通常CIは専用テストの縮小corpusを使い、10万nodeは手動またはself-hosted runnerで実行する。これはexecutor、prefix cache、artifact writeのlogical校正であり、ocgcore workerを150万回起動するthroughput測定ではない。`--probe-real-worker`はactive root-frontier workerを1回起動してpeak RSSを測る。pool別実測の正本は[Real-core Replay pool calibration](40_real_core_replay_benchmark.md)である。pyarrowがない環境ではJSONをauthoritative evidenceとし、Parquet未生成を正常状態として記録する。

統計的枝刈りは`#110`、評価weightは`#108`の校正完了までproduction既定にしない。
