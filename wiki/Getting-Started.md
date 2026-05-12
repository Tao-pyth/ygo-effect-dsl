# Getting Started

このページでは、サンプルデータを使って `ygo-effect-dsl` の基本パイプラインを動かします。目的は、カードデータを取り込み、DSLへ変換し、検証し、変換品質を分析する流れを一度通すことです。

## 前提

Python環境でリポジトリをチェックアウトしていることを前提にします。

```bash
pip install -e .
```

テストも動かせる状態にしておくと、仕様変更や辞書追加の影響を確認しやすくなります。

```bash
python -m pytest
```

## 最小パイプライン

サンプルデータセットを使う場合は、次の順に実行します。

```bash
python -m ygo_effect_dsl ingest --dataset examples/sample_dataset
python -m ygo_effect_dsl transform --dataset examples/sample_dataset --out data/dsl_out
python -m ygo_effect_dsl validate data/dsl_out/yaml
python -m ygo_effect_dsl analyze data/dsl_out/yaml --out data/reports
```

各コマンドの役割は次の通りです。

| Step | コマンド | 役割 |
| --- | --- | --- |
| 1 | `ingest` | ETLが出力した `manifest.json` と `cards.jsonl` を確認し、COREが読める入力として扱う |
| 2 | `transform` | カード効果テキストを v0.0 DSL YAML へ変換する |
| 3 | `validate` | DSLの構造と診断コードを確認する |
| 4 | `analyze` | action coverage、target解決率、warning件数などを集計する |

## 出力を見る

変換後は主に次の場所を確認します。

- `data/dsl_out/yaml/*.yaml`: カードごとのDSL出力
- `data/dsl_out/reports/`: transform時の補助レポート
- `data/reports/analysis_report.json`: analyzeの集計結果

まず見るべきなのは `validate` の集計です。

```text
validate: scanned=20
validate: errors=0 warnings=2 info=0
```

`errors=0` であれば、v0.0 DSLとして後続処理が読める形です。`warning` は失敗ではなく、変換品質を改善するためのTODOとして読みます。

## warningの読み方

代表的な warning code は次の通りです。

| Code | 意味 | 次に見る場所 |
| --- | --- | --- |
| `unknown_action` | action語彙にまだ落とし込めていない | transformer / dictionary の action 抽出 |
| `unresolved_target` | targetの種類が `unknown` のまま | selector 抽出、対象パターン |
| `missing_selector` | actionに対象情報が不足している | `targets[]` または inline selector |
| `legacy_action_fallback` | `actions[]` ではなく古い `action` に依存している | canonical `actions[]` への移行 |

詳しくは [[Spec-Index]] から Validation 仕様を参照してください。

## golden testを更新する時

代表カードの期待出力を意図的に変える場合だけ、goldenを更新します。

```powershell
$env:YGO_UPDATE_GOLDEN="1"
python -m pytest tests/test_representative_golden.py
Remove-Item Env:\YGO_UPDATE_GOLDEN
```

更新後は `tests/golden/representative_cards/` の差分を確認し、DSL変更が意図通りかを見ます。

## 次に読むページ

- DSLの各フィールドの意味を知りたい場合: [[Concepts]]
- 仕様ファイルの場所を確認したい場合: [[Spec-Index]]
- YAML例から理解したい場合: [[Examples-Gallery]]
