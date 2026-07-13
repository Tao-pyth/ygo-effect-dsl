# ygoEffectDSL Spec v0.0 - Overview

> **Status**: Historical baseline / maintained under Project Charter
> **Last updated**: 2026-07-13

## 目的

v0.0 は、遊戯王カードの効果テキストを機械処理可能な DSL へ変換し、変換結果を検証・分析できるようにする研究用ベースラインである。

v0.0 の中心は、完全なゲーム実行ではなく、後続の Bridge、Replay、Search、Evaluation が読める Action / Target / Cost / Restriction / Diagnostics を安定して出力することである。

## 非目的

- Python による遊戯王ルール再実装
- ocgcore の代替ルールエンジン
- 実 duel の状態遷移実行
- チェーン、優先権、相手レスポンスを含む完全な対戦シミュレーション
- 確率モデル、最適化、探索アルゴリズム
- ETL 領域の API 取得、画像取得、SQLite 正規化

## 対象範囲

- 入力: ETL が生成した `manifest.json` と `cards.jsonl`
- 出力: DSL YAML / JSON
- 検証: DSL shape、diagnostics、互換 fallback、未解決 target / action の可視化
- 分析: action coverage、target resolution、unmatched fragments、validation counts

## Charter との関係

`docs/00_project_charter.md` が最上位方針である。v0.0 は Charter の長期目標に向けた DSL Conversion CORE であり、Python-only game engine ではない。

状態や action の意味は、将来の Bridge / Replay / Search / Evaluation に渡す候補情報として扱う。実ルールの真実源は ocgcore / EDOPro Lua である。

## 用語

- **DSL**: カード効果テキストを構造化した変換結果。
- **Effect**: カードテキスト中の効果単位。
- **Action**: 効果が行う処理候補。v0.0 では `actions[]` が canonical。
- **Target**: action / cost / condition が参照する対象候補。
- **Diagnostics**: 未解決、曖昧、互換 fallback などの観測点。
- **State candidate**: 将来の state/action semantics が読む候補情報。v0.0 では実行しない。

## 参照

- [Grammar](10_grammar.md)
- [Semantics](20_semantics.md)
- [Examples](30_examples.md)
- [Validation](40_validation.md)
- [Representative Benchmark Policy](60_representative_benchmark.md)
