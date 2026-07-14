# Roadmap

Status: Route DSL transition

Last updated: 2026-07-13

## 1. Completed Foundations

- Project Charterと責務境界
- Pythonがカードルールを所有しないADR
- DecisionRequest、Action、Replay v0.3aの最小契約
- request signatureとaction IDの決定性
- STOP_LINEとEND_TURNの分離仕様
- Peak Board、Evaluation、Experimentの仕様
- 旧カードテキスト変換を本流から除外する判断
- Route DSL 0.1の責務、最小schema、validator、fixture

## 2. Current Phase: Route DSL Baseline

現在の目的は、Route DSLを単なる文書名ではなく、後続実装が出力できる安定した成果物契約にすることである。

- Replay eventとRoute checkpointの参照規則を固定する
- Peak Board / Terminal Boardの保存形を固定する
- interruption / recovery lineageをfixtureで具体化する
- Route IDのcanonical生成規則を定義する
- YAML / JSON serializerとround-trip testを追加する
- legacy card-text codeを `legacy/` へ隔離する移行計画を確定する

## 3. Milestone A: Fixed-Hand Runtime Slice

固定デッキ、固定初手、先攻1ターン、妨害なしに限定し、実ocgcoreから一つのRoute DSLを生成する。

1. ocgcore buildとEDOPro assetsのversion固定
2. デュエル初期化
3. core Message decoder
4. DecisionRequest生成
5. Action encoder
6. Replay executor
7. legal stop判定
8. checkpoint / state hash生成
9. 単純評価器とPeak Board追跡
10. Route DSL出力と再実行検証

完了条件は、生成したRoute DSLのReplayを新規プロセスで再実行し、全DecisionRequest署名と最終state hashが一致することである。

## 4. Milestone B: Search

- exhaustive search for small fixtures
- Random Search
- search budget (`max_nodes`, `max_seconds`, `max_depth`)
- STOP_LINE候補
- deterministic tie-break
- prefix Replay cache
- route deduplication by state identity

完了条件は、同じseedと予算で同じ最良Route DSLを得られることである。

## 5. Milestone C: Interruption and Recovery

- Action / effect / chain位置による妨害指定
- 妨害使用可否のocgcore検証
- base routeのprefix Replay
- 妨害後のSearch再開
- child Route DSLとlineage
- 妨害前後の評価差、成功条件差、資源差の比較
- 追加カードの2×2実core counterfactual、provenance、最小必要集合

## 6. Milestone D: Deck Experiments

- ランダム初手、固定初手、条件付き初手
- 重複カードを考慮した初手組合せ
- 初動、事故、条件付き初動の分類
- 初動率、成功率、平均Peak score、盤面分布
- 妨害耐性、リカバリ成功率
- デッキ構築差分比較
- Markdown / CSV / JSON / HTML出力

## 7. Later Work

- Beam Search / MCTS
- 複数妨害
- 妨害位置の自動探索
- 後攻盤面突破
- 複数ターン探索
- DuckDB / Parquet
- snapshot / clone_duel最適化
- distributed workers
- 可視化UI

## 8. Explicit Non-Goals for Initial Delivery

- Python製カード効果エンジン
- カードごとのRoute DSL手書き
- 全ルート完全列挙
- 完全な相手AI
- 勝率予測
- オンライン対戦クライアント

## 9. Legacy Removal

`ingest / transform / validate / analyze` とカードテキスト辞書は、Route DSL runtimeが依存していないことをテストで固定した後に削除する。旧出力をRoute DSLへ変換するmigrationは作らない。両者は意味的に別形式である。
