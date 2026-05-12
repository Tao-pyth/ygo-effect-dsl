# Spec Status Matrix

このページは、現時点で **実装・運用済みの仕様** と、**ロードマップ上で検討中の仕様** を整理した一覧です。  
基準日は **2026-05-12**。

## 1) 現在のプロジェクトが満たしている仕様（v0.0系）

| 区分 | 仕様項目 | 現状 |
|---|---|---|
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
| ルール辞書 | `negate` のスターター action rule | 対応済み |
| 品質保証 | representative-card データセット + golden 比較テスト | 対応済み |
| 位置づけ | v0.0 は「完全なゲーム意味論」より「変換の安定性・診断」を優先 | 現行方針 |

---

## 2) ロードマップ上で検討されている仕様

### v0.1 (Planned)
- 型の厳格化
- カード例（fixtures/examples）の拡充
- `validate` の強化

### v0.2+ (Planned)
- チェーン / スタックの段階導入
- 探索エンジン（状態ハッシュ、枝刈り）

### README上の中期計画（v0.1開始時の方向性）
- 最小の状態モデル（`Deck`, `Hand`, `Field`, `GY`, `Banished`, `Extra`, `Flags`）
- 狭い action 語彙（`draw`, `add_to_hand`, `send_to_gy`, `destroy`, `special_summon`, `banish`, `negate`）

---

## 3) 仕様境界（現時点で対象外 / 非目標）

- 相手レスポンスを含む完全な対戦ルール再現
- 確率モデル / 最適化
- ETL領域（API取得・画像取得・SQLite正規化）
- フル chain/stack シミュレーション
- 完全な相手インタラクションモデル

---

## 4) 補足

- 正式な仕様本文は `docs/spec/v0.0/*` が正本。
- 本ページは、Spec本文・Changelog・Roadmap・README の差分を実務向けに再整理したサマリ。
