# Spec Status Matrix

このページは、現時点で実装・運用済みの仕様と、ロードマップ上で検討中の仕様を整理した補助資料です。

基準日は **2026-07-13**。最上位方針は [Project Charter](../docs/00_project_charter.md) です。

## 1. 現在のプロジェクトが満たしている仕様

| 区分 | 仕様項目 | 現状 |
| --- | --- | --- |
| 方針 | Project Charter を最上位文書として採用 | 対応済み |
| 方針 | プロジェクト方向を「ゲームエンジン + AI 探索」として定義 | 対応済み |
| 方針 | Python は遊戯王ルールを持たない | 対応済み |
| データフロー | `manifest.json` + `cards.jsonl` を受け取り、`ingest -> transform -> validate -> analyze` を実行 | 対応済み |
| DSL形状 | `card.info` を廃止し `card.props` を採用 | 反映済み |
| DSL形状 | `effects[]` 配下で `actions[]` を正規形として採用 | 反映済み |
| DSL互換 | 旧 `action` フィールドをレガシーフォールバックとして許容 | 対応済み |
| DSL形状 | `targets[]` を effect shape に含める | 反映済み |
| 検証 | severity (`error` / `warning` / `info`) を持つ診断 | 対応済み |
| 検証 | `unknown_action`, `unresolved_target`, `missing_selector`, `legacy_action_fallback` 警告の可視化 | 対応済み |
| 分析 | action type coverage の集計 | 対応済み |
| 分析 | target reference resolution rate の集計 | 対応済み |
| 分析 | unmatched fragment のランキング | 対応済み |
| 分析 | validation severity/code 別集計 | 対応済み |
| 品質保証 | representative-card データセット + golden 比較テスト | 対応済み |

## 2. V0.1 baseline

V0.1 は完成したゲームエンジンではなく、設計基盤の確立です。

- Project Charter を最上位方針として採用
- README / Architecture / Roadmap / Glossary を V0.1 baseline として整備
- v0.1 minimal state/action semantics を engine boundary contract として定義
- Python は遊戯王ルールを持たず、ocgcore / EDOPro Lua を将来の真実源とする方針を明文化

## 3. V0.2 planned

V0.2 は Bridge / Replay baseline です。GitHub milestone と issue で管理しています。

- Replay baseline ADR
- Python does not own rules ADR
- Bridge / Replay specifications
- Minimal Replay model
- Bridge interface boundary
- Replay smoke test

## 4. V0.3+ planned

- Random Search
- END_TURN action
- Peak Board tracking
- State Evaluation prototype
- route logging

Beam Search、MCTS、妨害注入、Recovery 探索はさらに後の段階で扱います。

## 5. 仕様境界

現時点で対象外または非目標のもの:

- 相手レスポンスを含む完全な対戦ルール再現
- Python による遊戯王ルール再実装
- ocgcore の代替実装
- ETL 領域の API 取得、画像取得、SQLite 正規化
- フル chain / stack simulation
- 完全な相手インタラクションモデル

## 6. 補足

- 最上位方針は `docs/00_project_charter.md`。
- 正式な仕様本文は `docs/spec/*`。
- Wiki は、Spec 本文、Changelog、Roadmap、README の差分を実務向けに再整理したサマリ。
