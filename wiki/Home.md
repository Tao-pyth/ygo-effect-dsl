# ygo-effect-dsl Wiki

このWikiは、`ygo-effect-dsl` を初めて読む人や、仕様の全体像を短時間でつかみたい人のための日本語ガイドです。

正確な仕様の一次情報はリポジトリ内の `docs/spec/` です。Wikiは、その仕様を読みやすく案内するチュートリアル、用語集、運用メモとして扱います。

## このプロジェクトの目的

`ygo-effect-dsl` は、遊戯王カードの効果テキストを機械処理しやすいDSLへ変換し、変換結果を検証・分析するための研究用COREです。

現在の主な目標は v0.0 の安定化です。完全なゲームエンジンを作る前に、まず変換結果の構造を安定させ、どこまで意味を抽出できているかを測れる状態にします。

## まず読むページ

- [[Getting-Started]]: サンプルデータを使って `ingest -> transform -> validate -> analyze` を動かす手順
- [[Concepts]]: DSL、Effect、Action、Target、State Transition などの基本概念
- [[Spec-Index]]: `docs/spec/` の読み方と、各仕様ファイルの役割
- [[Examples-Gallery]]: DSL YAML の最小例と、よくある効果の表現例
- [[FAQ]]: v0.0、検証結果、ETLとの関係などのよくある質問
- [[Roadmap]]: v0.0 から v0.1 以降に向けた進め方

## 5分で見る開発ループ

```bash
pip install -e .
python -m ygo_effect_dsl ingest --dataset examples/sample_dataset
python -m ygo_effect_dsl transform --dataset examples/sample_dataset --out data/dsl_out
python -m ygo_effect_dsl validate data/dsl_out/yaml
python -m ygo_effect_dsl analyze data/dsl_out/yaml --out data/reports
```

主な出力は次の通りです。

- DSL YAML: `data/dsl_out/yaml/*.yaml`
- transform レポート: `data/dsl_out/reports/`
- analyze レポート: `data/reports/analysis_report.json`

## v0.0で大事にしていること

v0.0 は研究用の変換ベースラインです。意味解釈の完全性よりも、安定した構造と診断可能性を優先します。

- `card`、`effects[]`、`actions[]`、`targets[]` の形を安定させる
- 未解決の意味を無理に消さず、warning として可視化する
- golden test と analyze metrics で変換品質を追跡する
- v0.1 の最小 state/action semantics に進むための足場を作る

## 公式仕様へのリンク

- [Spec Overview](../docs/spec/v0.0/00_overview.md)
- [Grammar](../docs/spec/v0.0/10_grammar.md)
- [Semantics](../docs/spec/v0.0/20_semantics.md)
- [Examples](../docs/spec/v0.0/30_examples.md)
- [Validation](../docs/spec/v0.0/40_validation.md)
- [Changelog](../docs/spec/v0.0/50_changelog.md)
- [Input Contract](../docs/contract/input_contract.md)
