# ygo-effect-dsl

`ygo-effect-dsl` は、遊戯王OCGの展開ルートを探索し、妨害前後の到達盤面、リカバリ、デッキ性能を再現可能に比較するための基盤です。

本プロジェクトのDSLは **Route Information DSL（Route DSL）** です。Route DSLはカード効果を記述する言語ではなく、ocgcore / EDOPro Luaが実行したルートのAction履歴、途中盤面、Peak Board、評価、妨害分岐を保存・交換するデータ契約です。

## 名称と責務

repository/distribution名 `ygo-effect-dsl`、Python import `ygo_effect_dsl`、CLI `ygo-effect-dsl` は互換性のため維持します。製品の説明は **Reproducible Yu-Gi-Oh! route search and Route Information DSL** です。名称判断とrename再検討条件は [ADR-0008](docs/adr/0008_project_name_and_boundary.md) に固定しています。

無修飾のDSLはRoute DSLを指します。旧 `dsl` packageと `ingest / transform / validate / analyze` は **legacy card-text artifact pipeline** であり、Search engineやRoute DSLの入力にはしません。

## 原則

- EDOPro Luaをカード効果の真実源とする。
- ocgcoreを合法手判定、チェーン処理、状態遷移の真実源とする。
- PythonはBridge、Replay、探索、評価、実験、統計を担当する。
- カードごとの効果定義をPython DSLへ書き直さない。
- Replayできないルートを正式な探索結果として扱わない。
- 成功条件と盤面スコアを分離する。
- 探索終了盤面だけでなく、途中の最良停止可能盤面をPeak Boardとして保存する。

```text
EDOPro Lua + card data
  -> ocgcore
  -> Bridge / DecisionRequest
  -> Action / Replay
  -> Search / Evaluation
  -> Route DSL
  -> compare / aggregate / report / re-evaluate
```

## Route DSL

Route DSLは次の情報を一つのルート成果物として保持します。

- 実験条件、デッキ、初手、seed、使用アセットのversion
- DecisionRequestに対して選択したAction列
- Replay stepに対応する途中盤面と評価内訳
- 停止可能な最良盤面であるPeak Board
- 実際に探索を終了したTerminal Board
- 成功条件の判定結果
- 指定妨害と、その位置から分岐したリカバリルート
- 親ルート、分岐stepなどのlineage

Route DSLはカード効果、対象処理、コスト、合法性を解釈しません。再実行時は内包するReplayをocgcoreへ適用し、記録済みの `request_signature` と実際のDecisionRequestが一致することを検証します。

最小形は [examples/route_dsl/minimal_route.yaml](examples/route_dsl/minimal_route.yaml)、正式な責務は [Route DSL Overview](docs/route_dsl/00_overview.md)、fieldと不変条件は [Route DSL Schema 0.1](docs/route_dsl/10_schema.md) を参照してください。

## 現在地

実装済み:

- pin済みocgcore / EDOPro Lua assetのbootstrap、検証、隔離worker実行
- API v11 MessageからDecisionRequestとActionへの変換、安定ID、protocol失敗の検出
- 完全Replay trace、fresh worker再生、canonical State ID、Peak / Terminal Board評価
- Experiment validation / run / inspect / replay / reportとRoute DSL 0.1の保存・検証
- 探索の終了、枝刈りguardrail、prefix cache、並列schedulerの独立contract
- 実core workerのpool 1/2/4/8 stress、single-flight、crash/timeout/callback retry検証
- ocgcore v11 native snapshot/cloneのsource auditと不採用guard（fresh Replayへ固定）
- prefix cacheの4,096-entry/16 MiB校正、index write amplification、pool memory metadata
- Route正規化、分岐説明、妨害target identity、親子Route比較
- State差分から再計算できるversion付き資源消費vector/scalarとRoute自動ランキング
- optional PyArrowによるversion付きParquet集計、partition、catalog公開、schema evolution guard
- `core-interruption-candidate-policy-v1`による、core提示candidateだけを使う実core妨害選択
- 対象なし手札`14558127`、コストあり手札`27204311`、field複数対象`10045474`のmatrix fixtureと、2妨害を順次追加する段階Route
- `sampled_private_state`の決定論的な初手samplingと、妨害samplingから独立したReplay/State identity
- `FailureRecord`によるpath停止、worker交換/retry、experiment中止の区別

未実装またはproduction検証前:

- Random Search / Beam Search / MCTSをfrontierへ接続する一般探索executor
- 任意カード・任意デッキを対象にしたscenario生成とasset網羅性
- 検証済みmatrix/sequence fixture外の汎用妨害scenario生成とproduction探索
- 発動無効、効果無効、タイミングを逃す処理の一般化
- `ParallelTaskResult v2`契約
- 複数デッキ・10万node級のproduction worker/cache予算校正
- 大規模デッキ統計、比較レポートUI

`examples/route_dsl/minimal_route.yaml` は契約確認用です。実core prototypeはpin済みocgcore上でmatrix、段階妨害、初手samplingを検証しますが、その成功を任意カード、発動無効・効果無効・タイミング処理、production規模へ一般化しません。real-core PlayerView Replayは未対応であり、生成要求をfail-closeします。未検証事項はGitHub Issueで追跡します。

## セットアップ

```bash
pip install -e .
# Parquet analyticsも使う場合
pip install -e ".[analytics]"
```

## 実行可能プロトタイプ

固定初手・先攻1ターン・妨害なしの最小フローを、決定論的なscripted coreで実行できます。これは実ocgcoreやEDOPro Luaを実行するものではなく、Bridge差し替え前にDecisionRequest、Action、Replay、評価、Route DSLの接続を検証するための仮設実装です。

```bash
python -m ygo_effect_dsl prototype-run examples/prototype/fixed_hand_normal_summon.yaml --out data/prototype/route.yaml
python -m ygo_effect_dsl prototype-verify examples/prototype/fixed_hand_normal_summon.yaml data/prototype/route.yaml
python -m ygo_effect_dsl prototype-real-run --out data/prototype/real-core-route.yaml
python -m ygo_effect_dsl prototype-real-verify data/prototype/real-core-route.yaml
python -m ygo_effect_dsl prototype-real-stress --out docs/search/evidence/real_core_parallel_stress.json
python -m ygo_effect_dsl.spikes.direct_random_trace_evidence --out docs/ocgcore/evidence/direct_random_trace.json
python -m ygo_effect_dsl.spikes.action_aggregation_edge_evidence --out docs/ocgcore/evidence/action_aggregation_edges.json
python -m ygo_effect_dsl.spikes.resource_consumption_evidence --out docs/evaluation/evidence/resource_consumption.json
python -m ygo_effect_dsl experiment-run examples/experiments/real_core_effect_veiler_interrupted.yaml --out data/prototype/interrupted.route.yaml
python -m ygo_effect_dsl experiment-replay examples/experiments/real_core_effect_veiler_interrupted.yaml data/prototype/interrupted.route.yaml
```

`prototype-verify`は別プロセスで同じシナリオを再実行し、DecisionRequest署名、Action ID、state hash、評価、Route IDを含むRoute DSL全体の一致を検査します。仮設契約の要検証事項はGitHub Issueで管理します。

Route DSLサンプルを検証します。

```bash
python -m ygo_effect_dsl validate-route examples/route_dsl/minimal_route.yaml
```

期待する出力:

```text
validate-route: ok route_id=route_example_normal_summon
```

テストを実行します。

```bash
python -m pytest
```

## 文書

- [Project Charter](docs/00_project_charter.md)
- [Architecture](docs/10_architecture.md)
- [Roadmap](docs/20_roadmap.md)
- [Glossary](docs/30_glossary.md)
- [Route DSL Overview](docs/route_dsl/00_overview.md)
- [Route DSL Schema 0.1](docs/route_dsl/10_schema.md)
- [ADR-0004: Route Information DSL](docs/adr/0004_route_information_dsl.md)
- [ADR-0008: Project name and boundary](docs/adr/0008_project_name_and_boundary.md)
- [Bridge DecisionRequest](docs/spec/v0.3a/10_bridge_decision_request.md)
- [Action](docs/spec/v0.3a/20_action.md)
- [Replay Determinism](docs/spec/v0.3a/30_replay_determinism.md)
- [Peak Board](docs/spec/v0.3a/50_peak_board.md)
- [Evaluation and Experiment](docs/spec/v0.3a/60_evaluation_experiment.md)

文書の優先順位は `Project Charter -> Architecture -> Specifications -> ADR -> Implementation` です。

## 旧カードテキスト変換

v0.0で実装した `ingest / transform / validate / analyze` は、カード効果テキストを構造化する過去の研究機能です。現在は **legacy card-text artifact pipeline** と呼び、移行期間の互換確認用にのみ残しています。

この出力はRoute DSLではなく、探索用Action、合法手、状態遷移、補助的なルール推論の入力にも使用しません。旧機能を保守する場合の仕様は `docs/spec/v0.0/` に歴史資料として残しています。

## 対象範囲

目標:

- 固定初手・ランダム初手からの展開探索
- 任意停止を含むPeak Boardの抽出
- ルート保存、再生、比較、再評価
- 指定妨害の注入とリカバリ探索
- 初動率、事故率、成功率、妨害耐性の集計
- 同一条件によるデッキ構築比較

初期段階の対象外:

- Pythonによる遊戯王ルール再実装
- カードごとの効果DSL作成
- 完全な対戦AI
- 相手の最適妨害タイミングの自動探索
- 勝率予測
- 人間向けデュエル画面

## License

TBD
