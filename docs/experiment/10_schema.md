# Experiment Schema

Status: V0.4 current contract; V0.3b executable compatibility contract; V0.3a readable legacy contract

Last updated: 2026-07-14

## Purpose

Experimentは実行条件をコードから分離し、Route間の比較単位を固定する。配布JSON Schemaは `src/ygo_effect_dsl/resources/experiment.schema.json`、実行時validatorは `ygo_effect_dsl.experiment.validate_experiment` をsource of truthとして同じ必須項目を検査する。

## Required Fields

- `schema_version`: currentは `0.4`。`0.3b` は既存runnerの実行互換、`0.3a` はmigration入力として保持する。
- `experiment_id`, `objective`: 実験識別子と目的
- `deck`: deck idと `fixed` / `inline` / `ydk` のsource
- `player`: starting playerと評価perspective
- `turn_limit`: 1以上の最大turn
- `information_mode`, `information_policy`, `evaluate_at`: 情報境界、アクセス方針、評価時点
- `success_predicate`, `evaluator`: id、version、configを持つplugin参照
- `search`: strategy、budget、任意parameters
- `interruption`: `none` / `scripted` / `sampled` / `specified` とdefinition一覧
- `replay`: strict version検証方針
- `scenario`: `0.4`で必須となる`scenario-v1`のopening handと実行前検査条件

探索budgetは `max_nodes` または `max_seconds` の少なくとも一方を持ち、値は0より大きくする。`interruption.mode: none` の場合、definitionsは空でなければならない。

`information_policy` は `information-policy-v1` のschema、canonical `policy_id`、`deck_order`、`opening_hand`、`sampling_reference` を持つ。`viewer` は重複保存せず、`information_mode: player_view` の場合に `player.perspective` から導出する。policy IDはinformation modeと導出viewerも含めて計算するため、perspectiveだけを書き換えた文書は拒否する。

`interruption.mode: sampled` は `interruption-sampling-v1` のsampler IDと非負seedを必須とする。選択結果はReplay manifestへ保存し、fresh replayで同じdefinitionを再選択する。`none` / `scripted` にsampling設定を混在させない。

## Migration

`0.3a` の `information_mode` だけからdeck orderやopening handを推測しない。移行時は全policy次元を明示する。

```powershell
python -m ygo_effect_dsl experiment-migrate legacy.yaml --deck-order known --opening-hand fixed --out current.yaml
```

sampled private stateまたは `probability_distribution` を選ぶ場合は、sampler ID/version/seed等をJSON objectで `--sampling-reference-json` に渡す。current execution commandはlegacy `0.3a` を拒否し、`0.3b`または`0.4`への明示migrationを要求する。現行CLIの`experiment-migrate`は、情報境界を明示した`0.3b`文書を生成する。

## Validation

```powershell
python -m ygo_effect_dsl validate-experiment examples/experiments/real_core_effect_veiler.yaml
```

失敗時は `$.deck: required_field: is required` のようにYAML path、安定したerror code、説明を出力する。Route DSL内の `experiment` も同じvalidatorを通すため、単体Experimentと実行結果で契約が分岐しない。

## CLI Workflow

```powershell
python -m ygo_effect_dsl experiment-run examples/experiments/real_core_effect_veiler.yaml --out data/route.yaml
python -m ygo_effect_dsl experiment-inspect examples/experiments/real_core_effect_veiler.yaml data/route.yaml
python -m ygo_effect_dsl experiment-replay examples/experiments/real_core_effect_veiler.yaml data/route.yaml
python -m ygo_effect_dsl experiment-search examples/experiments/general_search_inline.yaml --out data/best.route.yaml --search-report data/search-report.json
```

`run` は検証済みExperimentをworkerへ渡してRoute DSLを生成する。`inspect` はcoreを再実行せず、Experiment一致とRoute整合性を検証してscore概要を表示する。`replay` はfresh workerで同じExperimentを再実行し、request列とRoute全体の一致を検証する。

設定の優先順位は「明示CLI引数 > Experimentファイル」である。CLI引数が省略された項目はファイル値を保持し、コード側defaultで上書きしない。現行CLIはbudget、Evaluator id/version、interruption modeを上書きできる。解決後ExperimentはRouteへ保存されるため、実行時の最終値を追跡できる。

V0.3bの `real_core_prototype` runnerは固定Effect Veilerシナリオとの実行互換を維持する。V0.4は`fixed` / `inline` / `ydk` deckとfixed/random/conditional opening handを`scenario-v1`で表し、`experiment-search`実行前にDB行、Lua script、asset lock、重複枚数、deck構造をfail-closeで検査する。`specified`妨害はPythonで効果やタイミングを推測せず、coreが提示したcandidateだけから応答を生成する。

## Runtime Boundary

Experimentはcore binary、カードDB、script commit、seedの実値を所有しない。これら実行環境の固定値はReplay manifestへ保存する。Experimentは利用するdeck、player、評価器、妨害、探索予算を指定し、Replayは実行時に解決した環境とAction列を証明する。

`0.3b/0.4` RouteはExperiment、Replay root、Replay manifest、information auditに同じ `policy_id` を保存する。Route validatorは一致とaudit IDを検証し、方針の異なるReplayやauditの混入を拒否する。
