# ygo-effect-dsl Wiki

このWikiは、`ygo-effect-dsl` の現行方針を日本語で案内する補助資料です。最上位方針は [Project Charter](../docs/00_project_charter.md)、Route DSLの正式仕様は [Route DSL Overview](../docs/route_dsl/00_overview.md) と [Schema 0.1](../docs/route_dsl/10_schema.md) です。

## このプロジェクトのDSL

本プロジェクトのDSLはRoute Information DSLです。ocgcore / EDOPro Luaが実行した展開ルートを、Replay、途中盤面、Peak Board、評価、妨害分岐とともに保存・比較するための形式です。

カード効果をDSLへ書き直すプロジェクトではありません。カード効果はEDOPro Lua、合法手と状態遷移はocgcoreが担当します。

## まず読むページ

- [[Getting-Started]]: Route DSLサンプルを検証する
- [[Concepts]]: Route DSL、Replay、Action、Peak Boardの関係
- [[Spec-Index]]: 正式仕様への案内
- [[Examples-Gallery]]: Route DSL 0.1の例
- [[FAQ]]: Lua、旧変換、Replayに関する質問
- [[Roadmap]]: 実ocgcore接続から探索・妨害解析までの順序

## 最小確認

```bash
pip install -e .
python -m ygo_effect_dsl validate-route examples/route_dsl/minimal_route.yaml
python -m pytest
```

`ingest / transform / validate / analyze` はv0.0の旧カードテキスト変換コマンドです。Route DSLの生成パイプラインではありません。
