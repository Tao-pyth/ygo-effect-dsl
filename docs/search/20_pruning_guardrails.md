# Search Pruning Guardrails

Status: V0.2 correlation-guarded implementation contract

Last updated: 2026-07-13

## Safety boundary

枝刈りは探索結果を高速化する一方、誤判定すると強い低確率Routeを回復不能な形で失う。`SearchPruningGuardrails` は次の条件をすべて満たす場合だけ枝を削除する。

1. candidateとincumbentが同じexact `parent_state_id` の兄弟Actionである。
2. evaluator、evaluator version/config、information mode、評価時点、score schema、State ID schema、実験環境が現在のdata identityと一致する。
3. score sampleごとに独立sampling unit IDと独立性の根拠が記録される。同一unit内のsampleは平均へ集約し、独立標本数を水増ししない。
4. 両Actionが最低独立sampling unit数を満たす。
5. candidateのoptimistic upper boundへmarginを加えても、incumbentのpessimistic lower boundを下回る。

近似State keyは入力にせず、異なる親State間の統計比較を拒否する。data identityが変わった場合は`invalidate`を返し、旧sampleを破棄して再探索する。評価関数IDが同じでもversionまたはconfig hashが変われば再利用しない。

## Config

Experiment `0.3a` のschemaを変更せず、既存の自由形式領域を使う。

```yaml
search:
  parameters:
    pruning:
      minimum_action_visits: 20
      unexplored_action_probability: 0.15
      confidence_delta: 0.01
      score_lower_bound: -100
      score_upper_bound: 1000
      prune_margin: 10
      bound_method: independent_cluster_hoeffding_v1
```

`minimum_action_visits`は互換性のため名称を維持するが、既定方式ではraw score数ではなく独立sampling unit数を表す。独立unitは、互いに独立にseedされたroot trialなど、独立性の根拠を説明できる単位でなければならない。同じroot trialからtranspositionや探索policyによって複数scoreが得られた場合は同じunit IDを付ける。IDまたは根拠がない場合は区間を計算せず`independence_unverified`でkeepする。

unexplored Actionを選ぶ確率は`0 < p <= 1`とし、callerがReplay可能な乱数drawを渡す。guardrail内部で乱数を生成しないため、選択結果とdrawをReplayへ保存できる。

## Evidence and audit

各`ActionEvidence`はexact親State ID、Action ID、pruning dataset ID、全score sample、各sampleのsampling unit ID、独立性の根拠を持つ。各判定は`keep`、`prune`、`invalidate`のいずれかと理由、raw観測数、独立unit数、平均、confidence interval、optimistic/pessimistic bound、canonical decision IDを返す。unexplored選択判定も同じaudit logへ記録する。

主な理由は次の通り。

- `mandatory_minimum_visits`: 最低観測数まで削除禁止。
- `incumbent_under_sampled`: 比較基準側のsample不足。
- `independence_unverified`: 独立sampling unitまたは根拠がなく、確率的枝刈りを禁止。
- `confidence_overlap`: 区間が分離せず削除禁止。
- `optimistic_bound_dominated`: 安全margin込みでも上限が劣るため削除。
- `data_identity_mismatch`: 評価または環境変更により旧データを無効化。

## Statistical model decision

`independent_cluster_hoeffding_v1`を既定方式とする。同一unit内scoreの平均を1標本とし、独立unit間だけにHoeffding boundを適用する。`confidence_delta`はcandidateとincumbentを合わせたfamily-wise error budgetであり、各Actionへ半分ずつ配分する。scoreが設定範囲外なら設定不整合として停止する。time/node budgetとは独立であり、探索予算が尽きたことだけを枝刈り理由にしてはならない。

`bounded_hoeffding_v0`はraw scoreをIID標本として数えるため非推奨とし、明示指定された互換モードでのみ残す。bootstrapとempirical Bernsteinもraw sampleへ適用すれば相関問題を解決しない。独立性を確立できない任意依存sampleに対しては、設定score全域を区間とする以外に分布非依存の収縮根拠がないため、枝刈りしない。

## Benchmark result

再現コマンドは次の通り。

```powershell
$env:PYTHONPATH='src'
python -m ygo_effect_dsl.spikes.pruning_bound_benchmark --out docs/search/evidence/pruning_bound_benchmark.json
```

benchmarkは真の平均20の低頻度candidateと平均15のincumbentを比較し、同じscoreを相関block内で反復する。10独立unitを各100回複製した5000 trialでは、旧Hoeffdingのfalse-prune率は10.36%、raw percentile bootstrapは37.58%で、指定delta 5%を超えた。完全相関では双方78.14%だった。新方式とscore全域方式は全ケース0件である。証跡IDは`prunebench_28623f04ba08d8b18966a6ef51407cc314bcbe5efeecaf6bac27d3e2efffaeee`で、[benchmark JSON](evidence/pruning_bound_benchmark.json)へ保存する。checked証跡は1デッキ・1シナリオで兄弟Action反復を持たないため、実データ相関とproduction parameterは校正不能である。

暫定値は`confidence_delta=0.01`、`minimum_action_visits=20`独立unit、`prune_margin=0`、evaluatorの正確なscore上下限とする。ただし本番既定値ではない。multi-deck実探索traceによる校正はIssue #110で追跡する。
