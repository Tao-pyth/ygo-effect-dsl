# Roadmap

Status: V0.1 baseline

## 1. V0.0 まで

V0.0 は DSL 変換基盤の安定化を目的とした段階である。

- ETL export artifact の ingest
- DSL YAML への transform
- validate による contract check
- analyze による変換品質の可視化
- representative benchmark と golden regression

この段階では、完全なゲーム状態遷移を実装しない。目的は、将来の engine が利用できる Action と Target を観測可能にすることである。

## 2. V0.1

V0.1 は設計基盤を確立する段階である。

必須項目:

- Project Charter の採用
- README の更新
- Architecture 文書の追加
- V0.1 minimal semantics の再定義
- ADR による設計判断の記録

V0.1 では、既存コードを「DSL Conversion CORE」として維持し、将来の Engine Boundary を文書化する。

## 3. V0.2

V0.2 では、Bridge と Replay の最小実装を目指す。

候補:

- Action model の明確化
- Replay history / serializer の最小実装
- ocgcore 連携調査
- Message decoder / encoder の設計
- synthetic fixture による replay smoke test

## 4. V0.3

V0.3 では、Search と Evaluation の最小垂直スライスを目指す。

候補:

- Random Search
- END_TURN action
- Peak Board tracking
- State Evaluation prototype
- route logging

## 5. V0.4 以降

V0.4 以降は探索品質と実験基盤を拡張する。

候補:

- Beam Search
- MCTS
- interruption injection
- recovery search
- statistics export
- DuckDB / Parquet support

## 6. 長期目標

長期目標は、遊戯王 OCG の展開探索、妨害耐性、リカバリ、デッキ評価を再現可能に自動化することである。ルールの真実源は ocgcore / EDOPro Lua とし、Python は探索と評価の制御層に徹する。
