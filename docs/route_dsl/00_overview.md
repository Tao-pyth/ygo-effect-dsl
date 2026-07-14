# Route Information DSL Overview

Status: Authoritative baseline

Last updated: 2026-07-13

## Purpose

本プロジェクトで無修飾の「DSL」は Route Information DSL（以下 Route DSL）を指す。Route DSL は、ocgcore / EDOPro Lua が実行した、またはその実行結果から探索した展開ルートを、保存、再生、比較、再評価、集計するための構造化データ契約である。

Route DSL はカード効果を記述する言語ではない。カード効果、合法手、チェーン処理、状態遷移は EDOPro Lua と ocgcore が所有する。Python はそれらの結果として得られた DecisionRequest、Action、状態識別子、評価、妨害分岐を Route DSL に記録する。

## Data Flow

```text
EDOPro Lua + card data
  -> ocgcore
  -> Bridge / DecisionRequest
  -> Action / Replay
  -> Search / Evaluation
  -> Route DSL
  -> compare / aggregate / report / re-evaluate
```

Route DSL を ocgcore へ直接入力してカード効果を実行してはならない。再実行時は、Route DSL 内の Replay と同じ初期条件・Action 履歴を ocgcore に適用し、各 DecisionRequest の署名一致を検証する。

## Responsibilities

Route DSL が保持する情報:

- 実験条件と識別子
- 初期状態、バージョン、seedを含むReplay
- DecisionRequestに対して選択したAction列
- 主要な途中盤面のチェックポイント
- Peak Boardと探索終了盤面
- 成功条件と評価内訳
- 妨害位置、妨害結果、リカバリ分岐
- 親ルート、分岐位置などのlineage

Route DSL が保持しない責務:

- カード効果本文の意味定義
- Lua効果の代替実装
- 合法手判定
- チェーン、コスト、対象、状態遷移の実行
- Search戦略そのもの
- 評価関数の実装コード

## Replayとの関係

Replayは「同じ環境・初期条件・Action履歴から同じDecisionRequestへ戻る」ための実行履歴である。Route DSLはReplayを内包し、評価済みチェックポイント、Peak Board、妨害、比較用metadataを加えた探索成果物である。

Replayが再現性を証明し、Route DSLがそのルートの意味と分析結果を伝える。Route DSLの評価値が変わってもReplayのAction履歴は変わらないため、同じルートを別の評価器で再評価できる。

## Historical Card-Text Artifact

v0.0で作成していたカード効果テキスト由来のYAMLは、現在のDSLではない。文書とコードでは `legacy card-text artifact` または「旧カードテキスト変換物」と呼ぶ。互換確認用の `ingest / transform / validate / analyze` は一時的に残るが、Route DSL、Bridge、Replay、Search、Evaluationの入力にしてはならない。
