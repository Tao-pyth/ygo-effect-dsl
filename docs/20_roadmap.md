# Roadmap

Status: General Search MVP candidate

Last updated: 2026-07-14

## 1. Completed Foundations

- Project Charterと責務境界
- Pythonがカードルールを所有しないADR
- DecisionRequest、Action、Replay v0.3aの最小契約
- request signatureとaction IDの決定性
- STOP_LINEとEND_TURNの分離仕様
- Peak Board、Evaluation、Experimentの仕様
- 旧カードテキスト変換を本流から除外する判断
- Route DSL 0.1の責務、最小schema、validator、fixture

## 2. Completed Runtime Baseline

Route DSL Baselineと固定fixture中心の実core validation sliceは完了している。これらはGeneral Search MVPの入力・出力契約として維持する。

- pin済みocgcore / EDOPro Lua assetのbootstrap、検証、隔離worker
- API v11 Message、DecisionRequest、Action、完全Replay trace
- fresh worker Replay、canonical State ID、Peak / Terminal Board評価
- Experiment run / inspect / replay / reportとRoute DSL 0.1
- STOP_LINEとEND_TURN、探索予算、prefix cache、並列schedulerの独立contract
- 固定matrix/sequence fixtureによる妨害、lineage、失敗分類
- 初手sampling、資源消費評価、Route比較、optional Parquet集計

この到達点は任意カード、任意デッキ、一般探索、production規模を保証しない。

## 3. Current Phase: General Search MVP Candidate

対象利用者は、ローカルasset cacheを準備できるPythonエンジニアである。目標は、任意YDK/inlineデッキを事前検査し、実ocgcore上で決定論的Random Searchと指定妨害探索を実行し、再生可能な最良Route DSLをCLI/APIから出力できる状態である。

依存順は次のとおりとし、scenario入力契約を一般探索executorより先に固定した。

1. `[完了] #119` 開発環境: editable install、pytest、CLI subprocess、real-core workerのimport元を現在checkoutへ統一した。
2. `[完了] #124` 文書: 実装済み、MVP対象、production前を本ロードマップ基準へ同期した。
3. `[完了] #121` scenario: Experiment `0.4`、任意YDK/inline、fixed/random/conditional初手、manifest、preflightを追加した。
4. `[完了] #120` search: real-core frontier、Random Search、予算、決定論的tie-break、`experiment-search`を追加した。
5. `[完了] #122` interruption: 指定カードの全発動機会とsupport taxonomyをcore candidateだけから生成した。未検証categoryのfixture拡張は`#123`で継続する。
6. `[完了] #105 logical calibration` hardening: 3 fixture、10万logical node、pool 1/2/4/8/16の性能・メモリ・再現性evidenceを固定した。pool別の実core Replay throughput/RSSは`#128`で継続する。

## 4. MVP Contracts

### Scenario and preflight

- Experiment `0.4`を追加し、`0.3a/0.3b`の読み取り・Replay互換を維持する。
- `deck.source`は`fixed`、`inline`、`ydk`とし、YDK内容SHA-256をmanifestへ保存する。
- preflightはDB行、Lua script、asset lock、重複枚数、構造上のdeck制約を検査する。
- 欠落、不一致、conditional hand不成立をstructured diagnosticとして保存し、実行前にfail-closeする。

### Search executor

- MVPで実動させるstrategyは`RandomSearchStrategyV1`だけとする。
- RNGはseedとsemantic node IDから導出し、pool size、完了順、retryへ依存させない。
- STOP_LINEを合法候補として扱い、END_TURNと区別する。
- `max_nodes`、`max_seconds`、`max_depth`、`max_replays`を強制する。
- best Route順序はsuccess、peak score、terminal score、Action数、Route IDで固定する。
- prefix cacheは検証済みReplay hintだけに使い、native stateを再利用しない。枝削除はexact State identityだけに限定する。
- Beam Search / MCTSは同じinterfaceへ接続可能にするが、MVPでは指定時に未実装エラーを返す。

### Specified interruption

- ユーザー指定カードについて、coreが提示した全発動機会をPASS/発動へ分岐する。
- activation、cost、target、optionはDecisionRequest制約から生成し、Pythonで効果、合法性、タイミングを推測しない。
- targetless、cost、single/multi-target、hand/field sourceを機械可読taxonomyとして保存する。
- 未知candidate形状、候補消失、曖昧な対応はconfiguration failureまたはpath failureにする。
- damage step、mandatory trigger、SEGOC等の未検証categoryは成功扱いにしない。

### Production-scale evidence

- 短展開、長展開、墓地・除外またはchain多発の3 fixtureをpin済みassetから固定する。
- 各fixtureで同一の10万logical node workloadをpool 1/2/4/8/16で実行する。
- throughput、worker/main RSS、prefix/cache、fresh Replay、artifact量、write amplification、crash recoveryをJSON/Parquetへ保存する。
- semantic結果とbest Routeがpool sizeに依存しないことを必須とする。
- 10万node計測は手動またはself-hosted workflowで行い、通常CIは縮小smoke corpusを使う。
- 現行evidenceはlogical workload校正であり、pool別の実core Replay throughput/RSSをproduction性能の根拠にはしない。実worker校正は`#128`で行う。

## 5. MVP Completion Gate

- clean checkout、editable install、親/子Pythonプロセスのimport元一致
- YDK/inline正規化、deck hash、asset欠落、未知card/script、conditional hand失敗の検査
- 同一seed/budgetでSearchRunとbest Routeが再現し、pool sizeでsemantic結果が変化しない
- STOP_LINE、END_TURN、全budget、frontier exhausted、worker crash/timeout/retryの検査
- 指定妨害の全発動機会、cost/target、候補消失、unsupported taxonomyの検査
- Route ID、Replay、Experiment `0.3a/0.3b`の回帰
- wheel/sdist、Windows executable、clean venv CLI smoke。第三者assetは同梱しない
- 全テスト、GitHub Actions、10万node evidence、commit、push、PR、merge、`main`同期

## 6. Production Before and Later Work

- Beam Search / MCTS本体
- PlayerView Replay（#125）
- 大規模デッキ統計と比較UI（#126）
- 複数妨害、妨害位置の自動探索、後攻盤面突破、複数ターン探索
- #110の枝刈り統計校正。完了までは統計的枝刈りをproduction既定にしない
- #108の評価weight校正
- snapshot / clone最適化、distributed workers、長期運用監視、互換性保証
- pool別の実core Replay throughput/RSS校正（#128）
- production運用、互換性、配布品質（#127）
- #91のライセンス・第三者成果物審査を含む一般公開配布

## 7. Explicit Non-Goals for MVP

- Python製カード効果エンジン
- カードごとのRoute DSL手書き
- 全ルート完全列挙
- 完全な相手AI
- 勝率予測
- オンライン対戦クライアント
- 一般公開配布

## 8. Legacy Removal

`ingest / transform / validate / analyze` とカードテキスト辞書は、Route DSL runtimeが依存していないことをテストで固定した後に削除する。旧出力をRoute DSLへ変換するmigrationは作らない。両者は意味的に別形式である。
