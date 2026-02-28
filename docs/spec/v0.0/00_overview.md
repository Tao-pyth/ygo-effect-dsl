# ygoEffectDSL Spec v0.0 (Draft) — Overview

> **Status**: Draft (experimental)  
> **Last updated**: 2026-02-28

## 目的（Goal）
- 遊戯王カードの効果テキストを、機械処理可能な DSL（構造化データ）へ変換する。
- その DSL を用いて、状態遷移（State Transition）として効果適用を記述・探索可能にする。

## 非目的（Non-goals）
- 対戦相手の介入（レスポンス/妨害）を含む完全なルール再現（※将来検討）
- 確率モデル/最適化（※将来検討）
- ETL（API取得・画像取得・SQLite正規化）

## 対象範囲（Scope）
- 入力：ETLが生成した `cards.jsonl`（英語/日本語テキストを含む）
- 出力：効果DSL（YAML/JSON）
- 探索：自ターン展開（相手レスポンス無し）を前提にした状態遷移

## 用語（Glossary）
- **State**: 盤面スナップショット（手札/場/墓地/除外/デッキ など）
- **Effect**: カード効果（テキスト上の1効果単位）
- **Transition**: 効果適用による State → State の変換
- **Trigger / Condition / Cost / Action / Restriction**: DSLの主要構成要素

## 参照
- docs/spec/v0.0/10_grammar.md（構文）
- docs/spec/v0.0/20_semantics.md（意味論・評価順序）
- docs/spec/v0.0/30_examples.md（例）
