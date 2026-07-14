# ygo-effect-dsl

`ygo-effect-dsl` は、遊戯王OCGの展開ルートを探索し、妨害前後の到達盤面、リカバリ、デッキ性能を再現可能に比較するための基盤です。

本プロジェクトのDSLは **Route Information DSL（Route DSL）** です。Route DSLはカード効果を記述する言語ではなく、ocgcore / EDOPro Luaが実行したルートのAction履歴、途中盤面、Peak Board、評価、妨害分岐を保存・交換するデータ契約です。

## 名称と責務

repository/distribution名 `ygo-effect-dsl`、Python import `ygo_effect_dsl`、CLI `ygo-effect-dsl` は互換性のため維持します。製品の説明は **Reproducible Yu-Gi-Oh! route search and Route Information DSL** です。名称判断とrename再検討条件は [ADR-0008](docs/adr/0008_project_name_and_boundary.md) に固定しています。

無修飾のDSLはRoute DSLを指します。旧 `dsl` packageと `ingest / transform / validate / analyze` は **legacy card-text artifact pipeline** であり、Search engineやRoute DSLの入力にはしません。

## Versionと互換性

現在のpackage/CLI releaseは **`0.2.0`**、Git tagは **`v0.2.0`** です。これはPythonエンジニア向けGeneral Search MVPのsource milestoneであり、production対応や第三者assetの再配布を保証する一般公開distributionではありません。

package versionと機能契約のschema versionは独立して管理します。package versionは配布物全体の変更をSemVerで表し、schema versionは保存データまたはAPIの互換境界を表します。したがって、Experiment `0.4`をpackage `0.4.0`へ揃える運用は行いません。

| 機能領域 | 現行version | 互換性と用途 |
|---|---|---|
| Package / CLI | `0.2.0` | General Search MVP candidate全体のrelease version |
| Project identity | `project-identity-v1` | repository、import、CLI、製品説明の安定名 |
| Experiment | `0.4` | 現行scenario/search入力。`0.3b`は実行互換、`0.3a`は読み取り・migration入力 |
| Scenario / preflight | `scenario-v1` / `scenario-manifest-v1` / `scenario-preflight-v1` | YDK/inline、初手、asset/card/script事前検査 |
| Decision / Action / Replay | `0.3a` | request、選択、再生の基礎契約。`ygo-replay-manifest-v1` / `fresh-replay-verification-v1` |
| Route DSL | `0.1` | 最良Routeの交換形式。正規化出力は`route-normalization-v2` |
| Information boundary | `information-policy-v1` / `information-audit-v1` | 探索・評価が参照できる情報とaccess証跡 |
| State identity | `ygo-state-id-v1` / `ygo-rule-state-v1` / `ygo-visibility-state-v1` | exact dedup、ルール状態、可視性状態 |
| Evaluation | `evaluation-result-v1` / `score-breakdown-v1` / `route-resource-consumption-v1` | 成功、盤面score、資源消費 |
| Search executor | `search-executor-v3` / `search-frontier-v2` / `search-run-result-v3` / `random-search-strategy-v1` | state completenessとExperiment digestを明示する決定論的Random Search。Beam/MCTSは未実装 |
| Search support | `search-termination-v1` / `prefix-cache-policy-v1` / `parallel-search-result-v2` / `pruning-guardrail-policy-v2` | 予算、cache、並列結果、枝刈りguardrail |
| Real-core frontier | `real-core-frontier-v2` / `real-core-worker-failure-v1` | fresh worker Replay、state completeness、failure envelope |
| Specified interruption | `core-interruption-candidate-policy-v1` / `interruption-support-taxonomy-v1` | core提示candidateだけを使う妨害分岐と対応分類 |
| Storage / aggregation | `raw-event-log-v1` / `run-catalog-v2` / `aggregation-v1` | JSONL、run catalog、optional Parquet集計 |
| Benchmark / policy | `general-search-benchmark-v1` / `cache-worker-policy-v2` / `memory-preflight-v2` | 10万logical node校正とmemory gate |
| ocgcore / assets | API `11.0`, `ocgcore-v11.0-win-x64-msvc-v1`, `ocgcore-assets-202504-v1` | commitとhashをlockし、runtime network accessと再配布を禁止 |

package versionの正本は `ygo_effect_dsl.version.__version__` です。`python -m ygo_effect_dsl --version`で現在値を確認できます。機能契約の正本は各moduleの`*_SCHEMA_VERSION`とvalidatorであり、この表はrelease時の互換性索引です。

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

## 現在地: General Search MVP

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

今回のGeneral Search MVPで追加した範囲:

- 現在checkoutを親/子Pythonプロセスから一貫してimportする開発環境
- Experiment `0.4`の任意YDK/inlineデッキ入力、内容hash、fixed/random/conditional初手
- DB行、Lua script、asset lock、重複枚数、deck構造をfail-closeで検査するscenario preflight
- 実ocgcore frontierへ接続する決定論的Random Search executorと`experiment-search`
- ユーザー指定カードについて、coreが提示する全発動機会をPASS/発動へ分岐する妨害scenario
- 短展開、長展開、墓地・除外またはchain多発fixtureによる10万logical node evidence

production前または後続Issue:

- Beam Search / MCTS本体。MVPではstrategy interfaceと明示的な未実装エラーだけを提供する
- PlayerView Replay（#125）。real-coreでは引き続きfail-closeする
- 大規模デッキ統計と比較UI（#126）
- #110の統計的枝刈り校正と#108の評価weight校正
- pool別の実core Replay throughput/RSS校正（#128）。現行10万node evidenceはlogical workloadの校正である
- production運用、互換性、一般公開配布（#127）
- #91のライセンス・第三者成果物審査。完了までは第三者assetを同梱・公開配布しない

今後のpackage releaseは機能契約の成熟度を基準に進めます。`0.3.0`では`#123/#105/#128/#110/#108`を中心に実core校正と探索品質を固め、`0.4.0`ではPlayerView Replay、Beam/MCTS、複数妨害・複数turnへ拡張します。`0.5.0`では大規模統計と比較UIを接続し、`1.0.0`は`#91/#127`のライセンス、互換性、配布、運用gateを満たした場合だけ候補にします。既存schemaの意味や保存形式を変更する場合はpackage番号に追従させず、その機能契約自体を別versionへ上げます。

実装は `#119 → #124 → #121 → #120 → #122/#123 → #105` の依存順で行った。MVPで実動する探索strategyはRandom Searchだけであり、10万node evidenceは手動またはself-hosted workflow、CIは縮小smoke corpusを使用する。

`examples/route_dsl/minimal_route.yaml` は契約確認用です。General Search MVPは任意YDK/inlineを事前検査し、pin済みocgcoreが提示するcandidateだけでRandom Searchを行います。ただし、任意のカード効果・発動無効・効果無効・タイミング処理をPython側で推測せず、未検証taxonomyはfail-closeします。real-core PlayerView Replayとproduction規模の実worker校正は未対応であり、GitHub Issueで追跡します。

## セットアップ

```bash
pip install -e .
python -c "import ygo_effect_dsl; print(ygo_effect_dsl.__file__)"
python -m ygo_effect_dsl --version
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
python -m ygo_effect_dsl experiment-search examples/experiments/general_search_inline.yaml --out data/prototype/general-search.route.yaml --search-report data/prototype/general-search.report.json
python -m ygo_effect_dsl experiment-replay examples/experiments/general_search_inline.yaml data/prototype/general-search.route.yaml --verification-report data/prototype/general-search.replay-verification.json
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
- [Release Stage Specifications: 0.3.0 to 1.0.0](docs/spec/00_release_stage_index.md)
- [Release Validation Register](docs/spec/00_validation_register.md)
- [Changelog](CHANGELOG.md)
- [Versioning and Release Policy](docs/release/00_versioning.md)
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
