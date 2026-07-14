# Evaluation And Experiment Specification

Status: Frozen pre-search contract (ADR-0007)

Last updated: 2026-07-13

## Responsibility

Evaluation は State と Action path の価値を測る。
Experiment は探索条件、評価器、成功条件、予算、再現性 metadata を束ねる。
Evaluation は状態遷移を実装しない。
成功条件とスコアは分離する。
Route DSLはExperiment識別子、評価器version、success、evaluation vector、total scoreを保存し、同じReplayを別条件で再評価できるようにする。

## Evaluation Vector

評価器は scalar score だけでなく evaluation vector を返す。
既定の vector field は次である。

- `interruptions`: 妨害数。
- `resource_balance`: 手札、場、墓地、除外、extra deck を含むリソース評価。
- `follow_up`: 次ターン以降の継続力。
- `protection`: 盤面耐性。
- `damage_pressure`: 打点または lethal pressure。
- `consistency_cost`: その盤面へ到達するための消費。
- `risk`: timeout、unsupported message、非公開情報 sampling 依存などのリスク。

評価器は vector field の schema version を持つ。
vector schema が変わる場合、過去 cache は無効化する。

## Temporary Values

評価成分は `persistent` または `temporary` に分類する。`persistent` は評価境界でcore Stateから残存確認できた値であり、expirationを持たない。`temporary` は `ConstraintExpiration` による期限と、評価境界での次の証拠状態を必須とする。

- `observed_active`: 評価境界でも有効とcore Stateから確認できたため、durable valueへ含める。
- `observed_expired`: 評価境界より前に失効したと確認できたため、durable valueから除外する。
- `unverified`: 評価境界での有効性を確認できないため、保守的にdurable valueから除外する。

一時値の有効性をPython側のカードルール推測だけで `observed_active` にしてはならない。Issue #94では、現行API v11 queryで取得できる攻撃力とstatus bitについて、固定したreset sourceと境界前後のquery transitionを組み合わせて検証した。任意のeffect/resetは公開APIから列挙できないため、同じ証跡がない値は引き続き`unverified`とする。詳細は`docs/ocgcore/10_temporary_modifiers.md`を参照する。

評価器は `temporary-effect-evaluation-v1` レポートを出力する。レポートは評価境界、成分ごとの分類・期限・証拠、metricごとのraw/durable/除外値、除外理由、未検証成分、過大評価を防止したmetricを保存する。レポート全体は成分から再計算でき、Route DSL validatorは改変されたdurable valueや説明を拒否する。

## Score

総合スコアは evaluation vector から evaluator が deterministic に計算する。
score formula は evaluator id と version に紐づける。
Experiment は evaluator id、version、config hash を保存する。

scoreは `score-breakdown-v1` としてtotalと同時に保存する。各termは `metric`, `raw_value`, `resolved_value`, `weight`, `contribution`, `resolution` を持ち、`total_score` は全contributionの合計でなければならない。breakdownにはschema version、欠損metric一覧、内容hashを含める。Route DSLのcheckpointは `evaluation-result-v1` 内にbreakdownを保存し、vector、total、evaluator id/version/config hashを同じ記録へ束ねる。

欠損値は暗黙に0へ変換しない。Evaluator configは次のいずれかを明示する。

- `error`: 欠損を評価失敗として扱う。既定値。
- `zero`: `raw_value: null`, `resolved_value: 0`, `resolution: zero` として保存する。
- `configured_default`: metric別の設定値で補完し、`resolution: configured_default` として保存する。default未設定なら評価失敗とする。

vectorはbreakdownの全 `resolved_value` と一致しなければならない。重みのないvector metricや、vectorにない隠れた加点を許可しない。これによりtotalだけを見た場合でも、どの観測値・補完値・重みが寄与したかを再構築できる。

2つのcheckpointを比較する場合は `score-comparison-v1` を生成し、metricごとにbefore/afterのresolved value、weight、contribution、contribution deltaを保存する。Peak Boardのdurability reportはこの比較を含み、処理前後でtotalが同じ場合も内訳の相殺を確認できる。

妨害数の定義は evaluator が所有する。
例として、無効、除去、召喚阻害、墓地阻害、サーチ阻害をどう数えるかは evaluator version に固定する。
Python core は妨害数を汎用ルールとして推測しない。

## Success Predicate

success predicate は run の成功判定であり、score とは別である。
高 score でも success が false になる場合がある。
低 score でも指定 predicate を満たせば success は true になり得る。

例:

- `board_has_2_interruptions`
- `can_end_on_named_card`
- `survives_single_handtrap`
- `reaches_opponent_turn_start_with_negate`

success predicate は id、version、config hash を持つ。

## Evaluator Plugin

評価器は plugin として扱う。
plugin は次のinterfaceを提供する。

```python
class Evaluator:
    evaluator_id: str
    version: str

    def evaluate(
        self,
        state: EvaluationInput,
        context: EvaluationContext,
    ) -> EvaluationOutput:
        ...
```

`EvaluationInput` は `state_hash`, `board_summary`, `turn`, `phase`, `information_mode` を持つ。Evaluatorは状態遷移を行わず、この入力を読み取り専用データとして評価する。`EvaluationContext` は `experiment_id`, `evaluate_at`, `evaluator_config` を持つ。

`EvaluationOutput` は次を持つ。

- `vector`
- `total_score`
- `explanations`

`explanations` は report 用であり、score 計算の source of truth ではない。
success predicateはEvaluator APIの返却値に含めず、scoreと独立して判定する。

`EvaluatorRegistry` は `(evaluator_id, version)` を一意キーとして登録・解決する。同じキーの重複登録と、未登録versionの暗黙fallbackは禁止する。RegistryはExperimentの `evaluator.id`, `evaluator.version`, `evaluator.config` からEvaluatorを選び、`evaluation-result-v1` を返す。結果にはvectorとtotal scoreに加え、evaluator id/version/config hashを保存する。

目的別Evaluatorの追加手順は次のとおりである。

1. `Evaluator` Protocolを実装し、不変な `evaluator_id` と `version` を定義する。
2. application起動時に対象Registryへ明示登録する。
3. Experiment YAMLで同じid/versionと設定値を指定し、contract testで入力・vector・total scoreを固定する。

Evaluatorのversionを変更せずに計算意味を変えてはならない。設定だけが変わる場合もconfig hashが変わるため、評価cacheと探索結果を区別できる。

## Experiment Schema

Experiment YAML の最小形は次である。

```yaml
experiment:
  schema_version: "0.3a"
  experiment_id: first_turn_control_random_v1
  objective: first_turn_control
  deck:
    id: control_deck_v1
    source: ydk
  player:
    starting_player: 0
    perspective: 0
  turn_limit: 2
  information_mode: complete_information
  evaluate_at: legal_stop
  success_predicate:
    id: board_has_2_interruptions
    version: "1"
    config: {}
  evaluator:
    id: control_board
    version: "1"
    config: {}
  search:
    strategy: random
    budget:
      max_nodes: 1000
      max_seconds: 60
    parameters: {}
  interruption:
    mode: none
    definitions: []
  replay:
    strict_versions: true
```

V0.3a では `search.strategy` を記録するが、探索戦略の詳細実装は V0.3b 以降に送る。
Experiment単体は `validate-experiment` CLIで検証する。実行環境のcore/assets/seedはExperimentへ重複保存せず、Replay manifestで固定する。

## Cache Invalidation

評価 cache key は次を含める。

- state hash
- evaluator id
- evaluator version
- evaluator config hash
- success predicate id
- success predicate version
- information mode
- evaluate_at
- asset config hash
- experiment schema version

これらのいずれかが変わる場合、cache は互換なしとして扱う。

## Action Statistics

Experiment は Action 価値の統計項目を記録できる。

- visit count
- success count
- best score
- average score
- score variance
- first success depth
- failure categories
- replay links

これらは探索の観測結果であり、Replay の正当性条件ではない。

## Acceptance Criteria

- success predicate と score evaluator が別概念として定義されている。
- evaluation vector と total score の関係が定義されている。
- score breakdownにschema version、重み、欠損解決、寄与値が保存される。
- checkpoint比較でmetricごとの寄与差分を出力できる。
- evaluator plugin が id、version、config hash を持つ。
- Evaluator Registryがid/versionの完全一致で登録・選択する。
- evaluator または predicate の変更で cache が無効化される。
- Experiment YAML の最小形が提示されている。
- 期限切れまたは未検証の一時値をdurable valueへ含めない。
- 一時値の除外量と理由を説明レポートへ保存する。

## Future Contract Tests

- `test_experiment_schema_validation`
- `test_evaluator_cache_key_changes_with_evaluator_version`
- `test_success_predicate_is_independent_from_total_score`
- `test_experiment_records_information_mode`
- `test_experiment_records_evaluate_at`
