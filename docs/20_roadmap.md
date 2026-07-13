# Roadmap

Status: V0.3a planning baseline

Last updated: 2026-07-13

## 1. V0.0 まで

V0.0 は legacy DSL 変換基盤の安定化を目的とした段階である。

- ETL export artifact の ingest
- DSL YAML への transform
- validate による contract check
- analyze による変換品質の可視化
- representative benchmark と golden regression

この段階では、完全なゲーム状態遷移を実装しない。
現在の方針では、この DSL CORE は探索エンジンの入力基盤ではなく、legacy / deprecated / removal target として扱う。

## 2. V0.1

V0.1 は設計基盤を確立する段階である。

- Project Charter の採用
- README の更新
- Architecture 文書の追加
- V0.1 minimal semantics の再定義
- ADR による設計判断の記録

V0.1 では、既存 DSL CORE を legacy / deprecated / removal target として明記し、実行系を ocgcore / EDOPro Lua -> Bridge へ移す方針を文書化する。

## 3. V0.2

V0.2 では、Bridge と Replay の最小実装を目的とする。

- Action-like dict と正式 Action model の境界整理
- Replay history / serializer の最小実装
- ocgcore 連携調査
- Message decoder / encoder の設計
- synthetic fixture による replay smoke test

V0.2 の Bridge / Replay は mock / interface baseline であり、DecisionRequest、Action ID、Replay 決定性保証は V0.3a で上位契約として仕様化する。

## 4. V0.3a

V0.3a では探索アルゴリズム実装に入る前に、境界、再現性、状態表現を仕様として固定する。
V0.2 の mock Bridge / Replay baseline は維持し、後続実装が従う上位契約を定義する。

成果物:

- Bridge / DecisionRequest specification
- Action specification
- Replay determinism specification
- State identity specification
- Peak Board / legal stop specification
- Evaluation / Experiment specification

V0.3a では Python dataclass、serializer、CLI、探索実装、契約テスト実装は変更しない。
完了条件は、後続実装者が追加判断なしで型、保存形式、署名、停止条件、評価設定を実装できる状態になっていることである。

## 5. V0.3b

V0.3b では V0.3a の境界仕様に従い、Search と Evaluation の最小垂直スライスを実装する。

- Random Search
- END_TURN action
- Peak Board tracking
- State Evaluation prototype
- route logging
- V0.3a contract tests

探索戦略の詳細最適化は、Bridge、Action、Replay、State の契約テストが安定してから扱う。

## 6. V0.4 以降

V0.4 以降は探索品質と実験基盤を拡張する。

- Beam Search
- MCTS
- interruption injection
- recovery search
- statistics export
- DuckDB / Parquet support
- transposition table
- prefix Replay cache
- deterministic aggregation

妨害注入、リカバリ、非公開情報 sampling、並列化は、Replay 決定性と State identity の仕様に依存するため、V0.3a/V0.3b の完了後に実装する。

## 7. 長期目標

長期目標は、遊戯王 OCG の展開探索、妨害耐性、リカバリ、デッキ評価を再現可能に自動化することである。
ルールの真実源は ocgcore / EDOPro Lua とし、Python は探索、Replay、評価、統計、実験制御を担当する。
