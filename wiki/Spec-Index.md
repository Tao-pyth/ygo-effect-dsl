# Spec Index

このページは、`docs/spec/` にある仕様文書への案内です。Wikiは読み物、`docs/spec/` は一次情報として扱います。

## v0.0 Spec

| File | 内容 | まず読むべき人 |
| --- | --- | --- |
| [00 Overview](../docs/spec/v0.0/00_overview.md) | v0.0の目的、スコープ、用語 | 全体像を知りたい人 |
| [10 Grammar](../docs/spec/v0.0/10_grammar.md) | DSL YAMLの構造、必須キー、action/target形式 | transformerやvalidatorを触る人 |
| [20 Semantics](../docs/spec/v0.0/20_semantics.md) | legacy DSL変換結果の読み方、Action/Target候補、diagnostics | 過去仕様を確認する人 |
| [30 Examples](../docs/spec/v0.0/30_examples.md) | DSLの具体例 | 出力例から理解したい人 |
| [40 Validation](../docs/spec/v0.0/40_validation.md) | severity、diagnostic code、validate CLIの読み方 | 変換品質を改善する人 |
| [50 Changelog](../docs/spec/v0.0/50_changelog.md) | 仕様・CLI・変換・検証・fixture変更の記録 | 変更履歴を追う人 |

## v0.1 Spec

| File | 内容 | まず読むべき人 |
| --- | --- | --- |
| [V0.1 Overview](../docs/spec/v0.1/00_overview.md) | 過去のDSL接続案、非目標、現在の廃止方針 | V0.1の履歴を確認する人 |
| [Minimal Semantics](../docs/spec/v0.1/10_minimal_semantics.md) | read-only state/action candidate の過去案 | legacy DSLの履歴を確認する人 |
| [First 10 One-Step Applications](../docs/spec/v0.1/20_first_10_applications.md) | 代表カードから読み取った one-step candidate の過去記録 | 過去検討の根拠を確認する人 |

## Project Decisions

- [Project Charter](../docs/00_project_charter.md)
- [ADR-0000: Project Charter](../docs/adr/0000_project_charter.md)
- [ADR-0001: Replay Baseline](../docs/adr/0001_replay_baseline.md)
- [ADR-0002: Python Does Not Own Rules](../docs/adr/0002_python_does_not_own_rules.md)
- [ADR-0003: Deprecate DSL CORE](../docs/adr/0003_deprecate_dsl_core.md)

## Input Contract

COREが読む入力は、ETLが出力する成果物です。

- [Input Contract](../docs/contract/input_contract.md)
- `manifest.json`
- `cards.jsonl`

COREはETL内部のSQLiteには直接依存しません。境界は export artifact です。

## 仕様を変更する時の基本ルール

仕様、CLI、transform、validation、analysis、fixtureを変える場合は、同じ変更で changelog も更新します。

代表カードのDSL出力が変わる場合は、golden testの差分も確認します。意図した変更であれば `YGO_UPDATE_GOLDEN=1` を使って更新します。

## v0.0 Grammarの要点

v0.0では、未解決の意味があっても構造キーを省略しません。

- 空文字は `""`
- 空リストは `[]`
- 空オブジェクトは `{}`

`actions[]` が正規のaction表現です。単数の `action` は互換用fallbackとして扱います。

## Validationの要点

`validate` は、完全なゲームルールとして正しいかではなく、legacy v0.0 DSLとして読める形かを確認します。

- `error`: shape invalid。まず直す
- `warning`: shape valid。変換品質改善のTODOとして読む
- `info`: 補助情報

代表的な warning は `unknown_action`、`unresolved_target`、`missing_selector`、`legacy_action_fallback` です。
