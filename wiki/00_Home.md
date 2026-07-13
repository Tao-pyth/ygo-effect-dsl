# ygo-effect-dsl Wiki

このWikiは、`ygo-effect-dsl` を初めて読む人や、仕様の全体像を短時間でつかみたい人のための日本語ガイドです。

最上位方針はリポジトリ内の `docs/00_project_charter.md` です。正確な仕様の一次情報は `docs/` です。Wikiは、その方針と仕様を読みやすく案内するチュートリアル、用語集、運用メモとして扱います。

## このプロジェクトの目的

`ygo-effect-dsl` は、遊戯王 OCG の展開探索、妨害耐性解析、リカバリ解析、デッキ評価を再現可能にするためのゲーム木探索エンジン基盤です。

現在の基準は Project Charter と ADR-0003 です。v0.0 の変換基盤は legacy / deprecated / removal target であり、V0.2 では ocgcore / EDOPro Lua 由来の Bridge / Replay の最小実装へ進みます。Python でのルール再実装は目標にしません。

## まず読むページ

- [[Getting-Started]]: サンプルデータを使って `ingest -> transform -> validate -> analyze` を動かす手順
- [[Concepts]]: DSL、Effect、Action、Target、State Candidate などの基本概念
- [[Spec-Index]]: `docs/spec/` の読み方と、各仕様ファイルの役割
- [[Examples-Gallery]]: DSL YAML の最小例と、よくある効果の表現例
- [[FAQ]]: v0.0、検証結果、ETLとの関係などのよくある質問
- [[Roadmap]]: V0.1 baseline から V0.2 以降に向けた進め方

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

## 現在大事にしていること

v0.0 は過去の研究用変換ベースラインです。現在は探索エンジンの入力基盤ではなく、互換維持のため一時残置される廃止対象です。

- `card`、`effects[]`、`actions[]`、`targets[]` の形を安定させる
- 未解決の意味を無理に消さず、warning として可視化する
- golden test と analyze metrics で変換品質を追跡する
- Python に遊戯王ルールを持たせず、ocgcore / EDOPro Lua を将来の真実源にする
- Replay 可能性と Bridge 境界は ocgcore / EDOPro Lua 由来の入力で設計する

## 公式仕様へのリンク

- [Project Charter](../docs/00_project_charter.md)
- [Spec Overview](../docs/spec/v0.0/00_overview.md)
- [Grammar](../docs/spec/v0.0/10_grammar.md)
- [Semantics](../docs/spec/v0.0/20_semantics.md)
- [Examples](../docs/spec/v0.0/30_examples.md)
- [Validation](../docs/spec/v0.0/40_validation.md)
- [Changelog](../docs/spec/v0.0/50_changelog.md)
- [Input Contract](../docs/contract/00_input_contract.md)
