# Project Charter

Version: 0.2

Status: Authoritative Baseline

## 1. Project Purpose

このプロジェクトは、遊戯王 OCG の展開探索、コンボ解析、妨害耐性解析、リカバリ解析、デッキ評価を自動化するための「ゲームエンジン + AI 探索」基盤を構築する。

本プロジェクトはデュエルクライアントの開発を目的としない。目的は、人間が手作業で検証している展開ルート、選択分岐、妨害後の復帰可能性、盤面評価を、再現可能な探索問題として扱えるようにすることである。

## 2. Design Philosophy

本プロジェクトは DDD を主軸にしない。中心にあるのは、ドメインモデルの表現ではなく、外部ルールエンジンを真実源としたゲーム状態の遷移、探索、評価、実験である。

優先順位は次の通りとする。

1. ルールの正当性
2. Replay による再現性
3. Action 単位の探索可能性
4. Peak Board による成果評価
5. 実験、統計、比較の拡張性
6. 実装の単純さ

設計上の判断は「思想 → 仕様 → 設計 → 実装」の順序で行う。実装都合で思想を曲げない。破壊的変更が必要な場合でも、この Charter の方針を優先する。

## 3. Responsibility Boundary

責務は明確に分離する。

- Python: 探索、評価、統計、ログ、実験制御を担当する。
- ocgcore: ルール、合法手判定、状態遷移、Lua 実行を担当する。
- EDOPro Lua: カード効果とカードデータの真実源として利用する。

Python は遊戯王のルールを再実装しない。Python が保持してよいのは、探索や評価に必要な抽象化、Action、Replay、統計、実験結果である。

## 4. System Overview

```text
Python
  ├─ Search Engine
  ├─ Replay
  ├─ Evaluation
  ├─ Experiment
  ├─ Statistics
  ├─ Logging
  └─ Bridge
       │
       ▼
    ocgcore
       │
       ▼
EDOPro Lua + Card Data
```

Bridge は Python と ocgcore の境界であり、最重要コンポーネントの一つである。ocgcore の Message を Python 側の Action に変換し、Python の Action を ocgcore へ入力できる形に変換する。

## 5. Core Requirements

- 既存の EDOPro Lua とカードデータを利用する。
- 全カードルール対応を長期目標とする。
- Python にゲームルールを持たせない。
- Replay による再現を初期実装の基準にする。
- Action を探索の最小単位にする。
- Peak Board を正式な探索結果として扱う。
- END_TURN を探索対象の Action として扱う。
- State Evaluation と Action Evaluation を分離する。
- 妨害はユーザー指定位置に注入する。
- すべての結果を再現可能にする。

## 6. Documentation Architecture

文書は実装より上位の判断基準である。最終的な文書構成は次を目標にする。

```text
docs/
  00_project_charter.md
  architecture.md
  roadmap.md
  glossary.md
  adr/
    ADR-000.md
    ADR-001.md
  search/
    overview.md
    action.md
    beam_search.md
    mcts.md
    pruning.md
    replay.md
  evaluation/
    state.md
    action.md
    peak_board.md
    scoring.md
  bridge/
    ocgcore.md
    messages.md
    api.md
    replay.md
  experiment/
    interruption.md
    recovery.md
    statistics.md
    reports.md
  data/
    card_pool.md
    replay_format.md
```

文書の階層は次の通りとする。

```text
Project Charter
  ▼
Architecture
  ▼
Specifications
  ▼
ADR
  ▼
Implementation
```

Charter は思想、Architecture は責務、Specifications は詳細仕様、ADR は設計判断、Implementation は実装を扱う。

## 7. Source Architecture

ソースコードは責務単位で分離する。最終的な構成は次を目標にする。

```text
src/
  engine/
    bridge/
    replay/
    search/
    evaluation/
    logging/
    statistics/
    experiment/
    util/
```

現在の `src/ygo_effect_dsl/` には legacy DSL CORE が残っている。これは engine 層の前段ではなく、互換維持のための一時残置であり、廃止対象とする。新規実装は engine/bridge、engine/replay、今後追加する engine/search へ集約する。

## 8. Search Engine

Search Engine はプロジェクトの中心である。探索は Action を単位として進み、Replay と Evaluation を利用して分岐を比較する。

想定構成は次の通り。

```text
search/
  action.py
  node.py
  tree.py
  search_engine.py
  random_search.py
  beam.py
  mcts.py
  pruning.py
  priority_queue.py
```

責務の流れは次の通り。

```text
Search Engine
  ▼
Node 生成
  ▼
Action 取得
  ▼
Replay
  ▼
Evaluation
  ▼
Pruning
```

探索アルゴリズムは段階的に導入する。初期段階では Random Search と統計収集を優先し、評価関数を先に複雑化しない。

## 9. Action

Action は探索の最小単位である。ocgcore の Message をそのまま探索単位にせず、Bridge で Python 側の Action に変換する。

代表的な Action は次の通り。

- NormalSummon
- SpecialSummon
- ActivateEffect
- SelectCard
- SelectOption
- EndTurn

END_TURN は探索終了の単なる制御命令ではなく、「ここで止める」という意思決定を表す Action として扱う。

## 10. Replay

Replay は独立モジュールとする。Replay は探索結果の説明、再実行、比較、妨害注入、統計化の基盤である。

想定構成は次の通り。

```text
replay/
  history.py
  serializer.py
  replayer.py
  seed.py
  snapshot.py
```

Replay が保持する情報は次の通り。

- Seed
- Deck
- Action 履歴
- 選択履歴
- バージョン情報
- 評価結果
- 実験条件

初期実装では Replay による再現を基準にする。将来的に Snapshot と clone_duel を導入し、探索効率を改善する。

## 11. Bridge

Bridge は ocgcore と Python の境界を担当する。

想定構成は次の通り。

```text
bridge/
  bridge.py
  message_decoder.py
  message_encoder.py
  action_factory.py
  core_loader.py
```

Bridge の変換方向は次の二つである。

```text
ocgcore
  ▼
Message
  ▼
Action
  ▼
Python
```

```text
Python
  ▼
Action
  ▼
ocgcore
```

Bridge はルールを判断しない。Bridge は Message と Action の変換責務に限定する。

## 12. Evaluation

Evaluation は AI 探索の品質を決める中核である。ただし State Evaluation と Action Evaluation は別物として扱う。

想定構成は次の通り。

```text
evaluation/
  state.py
  action.py
  peak.py
  resource.py
  score.py
```

State Evaluation は盤面やリソースの価値を評価する。Action Evaluation は特定の行動選択の期待値や安定性を評価する。

State Evaluation の例:

- 妨害数
- 手札
- 墓地
- リソース
- 継続力
- 制圧力

Action Evaluation の例:

- 成功率
- 平均 Peak Score
- 将来期待値
- 訪問回数

## 13. Peak Board

探索結果は Terminal Board ではなく Peak Board を正式結果とする。Peak Board とは、探索途中で到達した最も評価値の高い停止可能盤面である。

Terminal Board は比較、分析、失敗理由の確認に利用するが、主成果としては扱わない。

この方針を採用する理由は、展開を続けることで盤面が弱くなるケースが存在するためである。探索は「最後まで動いた結果」ではなく、「どこで止めるべきか」を含めて最適化する。

## 14. Interruption And Recovery

妨害解析は、相手 AI の完全実装を初期目標にしない。ユーザーが「この効果に灰流うららを打つ」「この特殊召喚に妨害を入れる」といった注入位置を指定し、その後の Replay からリカバリ探索を行う。

目的は最適妨害の発見ではなく、指定妨害に対する耐性、復帰可能性、代替ルートを解析することである。

## 15. Experiment

Experiment は研究用途の責務として独立させる。

想定構成は次の通り。

```text
experiment/
  interruption.py
  recovery.py
  comparison.py
  benchmark.py
  statistics.py
```

Experiment は探索アルゴリズム、評価関数、デッキ、妨害条件、カードプールを比較できるようにする。

## 16. Logging And Statistics

ログは Replay 可能であることを基準に保存する。人間向けの表示ログと機械処理向けの構造化ログを混同しない。

Logging の想定構成は次の通り。

```text
logging/
  logger.py
  route_logger.py
  state_logger.py
  action_logger.py
  experiment_logger.py
```

Statistics の想定構成は次の通り。

```text
statistics/
  deck.py
  action.py
  state.py
  route.py
  heatmap.py
```

保存形式は段階的に拡張する。

- CSV
- SQLite
- DuckDB
- Parquet

## 17. Data

Data は将来的に大きくなるため、実装コードとは分離する。

```text
data/
  replay/
  statistics/
  cache/
  reports/
  exports/
```

生成物、キャッシュ、実験結果、外部出力は混在させない。

## 18. Architecture Decision Records

重要な設計判断は ADR として残す。ADR は「何を採用したか」だけでなく、「なぜ採用したか」「何を採用しなかったか」を記録する。

初期 ADR は次を予定する。

- ADR-0000: Project Charter の採用
- ADR-0001: Replay を基準実装にする
- ADR-0002: Python はルールを持たない
- ADR-0003: DSL CORE を探索エンジンから除外し廃止対象にする
- ADR-0004: Peak Board を正式結果にする
- ADR-0005: END_TURN を Action として扱う
- ADR-0006: State Evaluation と Action Evaluation を分離する

ADR は Codex、Claude、ChatGPT、人間のいずれが読んでも、設計判断の理由を追跡できる状態にする。

## 19. Migration Policy

後方互換性は必須要件ではない。次の観点で破壊的変更を許容する。

- Charter との整合性
- ocgcore 統合の単純性
- Replay 可能性
- 探索エンジンの拡張性
- 評価と統計の分離
- 長期保守性

ただし、破壊的変更を行う場合は、変更理由を Architecture または ADR に記録する。

## 20. Roadmap

開発は次の順序で進める。

1. Project Charter の確定
2. Documentation Architecture の整備
3. Bridge の最小実装
4. Replay の最小実装
5. Action モデルの確定
6. Peak Board 評価の導入
7. Random Search の実装
8. State Evaluation の導入
9. 統計収集の導入
10. Beam Search の導入
11. 妨害注入と Recovery 探索
12. MCTS の検証
13. 全カード対応に向けた検証基盤の拡張

## 21. Development Rules

- Charter を最上位文書とする。
- 仕様変更は Charter、Architecture、ADR のいずれかを先に更新する。
- 実装より仕様を優先する。
- Python にルールを実装しない。
- DSL CORE を実行系、合法手判定、Action 生成の真実源として使わない。
- Replay できない探索結果を正式結果として扱わない。
- Action、Replay、Evaluation、Bridge の責務を混ぜない。
- 生成 AI と人間が同じ設計文書を参照できる状態を維持する。

## 22. Long Term Goal

長期目標は、遊戯王 OCG の展開探索エンジンを完成させ、展開探索、妨害耐性、リカバリ、デッキ評価を再現可能に自動化することである。

ルールの唯一の真実源は ocgcore と EDOPro Lua とし、Python は探索と評価のための制御層に徹する。
