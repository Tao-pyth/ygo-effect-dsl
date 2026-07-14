# ygoEffectDSL Spec v0.0 - Overview

> **Status**: Historical baseline / legacy card-text artifact / removal target
> **Last updated**: 2026-07-13

## 目的

v0.0 は、遊戯王カードの効果テキストを機械処理可能な DSL へ変換し、変換結果を検証・分析できるようにする過去の研究用ベースラインである。

現在のProject Charterでは、v0.0出力は `legacy card-text artifact` であり、現在のRoute DSLではない。v0.0のAction / Target / Cost / Restriction / Diagnosticsは既存互換の観測対象であり、Bridge、Replay、Search、Evaluation、Route DSLの入力根拠にしない。本folder内の「DSL」は歴史的なv0.0名称としてのみ読む。

## 非目的

- Python による遊戯王ルール再実装
- ocgcore の代替ルールエンジン
- 実 duel の状態遷移実行
- チェーン、優先権、相手レスポンスを含む完全な対戦シミュレーション
- 確率モデル、最適化、探索アルゴリズム
- ETL 領域の API 取得、画像取得、SQLite 正規化

## 対象範囲

- 入力: ETL が生成した `manifest.json` と `cards.jsonl`
- 出力: legacy card-text YAML / JSON
- 検証: DSL shape、diagnostics、互換 fallback、未解決 target / action の可視化
- 分析: action coverage、target resolution、unmatched fragments、validation counts

## Charter との関係

`docs/00_project_charter.md` が最上位方針である。v0.0は過去のcard-text conversionであり、Python-only game engineではない。

状態や action の意味は、現在の探索エンジン設計には接続しない。実行系入力と実ルールの真実源は ocgcore / EDOPro Lua である。

## 用語

- **v0.0 historical DSL**: 当時カード効果テキストを構造化していた変換結果。現在のRoute DSLとは別形式。
- **Effect**: カードテキスト中の効果単位。
- **Action**: 効果が行う処理候補。v0.0 では `actions[]` が canonical。
- **Target**: action / cost / condition が参照する対象候補。
- **Diagnostics**: 未解決、曖昧、互換 fallback などの観測点。
- **State candidate**: 過去の v0.1 検討で使われた候補情報。現在の探索エンジン入力ではない。

## 参照

- [Grammar](10_grammar.md)
- [Semantics](20_semantics.md)
- [Examples](30_examples.md)
- [Validation](40_validation.md)
- [Representative Benchmark Policy](60_representative_benchmark.md)
