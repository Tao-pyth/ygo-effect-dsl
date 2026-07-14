# Documentation Policy

## Purpose

文書はRoute DSL、ocgcore境界、Replay、探索、評価、実験の契約を実装と同期させる。現在の無修飾の「DSL」はRoute DSLを意味する。旧カードテキスト変換を扱う場合は、必ず `legacy card-text artifact` または「旧カードテキスト変換物」と明記する。

## Authority

判断の優先順位は次の通りとする。

```text
Project Charter
  -> Architecture
  -> Specifications
  -> ADR
  -> Implementation
```

READMEとWikiは入口であり、上位文書と矛盾してはならない。

## Formal Documentation

`docs/` はプロジェクトの動作と設計を制約する正式領域である。

- `00_project_charter.md`: 目的、原則、責務、機能範囲
- `10_architecture.md`: コンポーネント境界と依存方向
- `20_roadmap.md`: 実装順序と完了条件
- `30_glossary.md`: 現行用語
- `route_dsl/`: Route DSLの現行契約
- `spec/v0.3a/`: Bridge、Action、Replay、State、Peak Board、Evaluation契約
- `adr/`: 重要な設計判断
- `spec/v0.0`, `spec/v0.1`: 旧カードテキスト変換の歴史資料

## Supporting Documentation

`wiki/` は日本語オンボーディング、例、FAQなどの補助領域である。正式なfieldや不変条件をWikiだけで定義しない。

## Change Rules

- Route DSL shapeを変更する場合はschema version、migration要否、fixture、validator testを同時に更新する。
- DecisionRequest、Action、Replay fieldを変更する場合はRoute DSLへの影響を確認する。
- Evaluation fieldを変更する場合はevaluator versionと再評価互換性を確認する。
- 旧カードテキスト変換を変更する場合は現行Route DSL変更と混同せず、歴史仕様側へ記録する。
- 実装済みと計画中を明示し、mock fixtureを実デュエル出力と表現しない。

## Naming

Markdownは原則として各folder内で `00_`, `10_`, `20_` の順序prefixを使う。ADRは4桁連番を維持する。データ契約やPython moduleは各tool / languageの命名規則を優先する。

## Practical Test

文書が「ツールは何を保証するか」に答えるなら `docs/` に置く。「なぜこの設計か」「どう学ぶか」に答えるなら `wiki/` に置く。
