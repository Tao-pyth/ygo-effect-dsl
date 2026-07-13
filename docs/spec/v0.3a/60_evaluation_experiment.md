# Evaluation And Experiment Specification

Status: V0.3a specification baseline

Last updated: 2026-07-13

## Responsibility

Evaluation は State と Action path の価値を測る。
Experiment は探索条件、評価器、成功条件、予算、再現性 metadata を束ねる。
Evaluation は状態遷移を実装しない。
成功条件とスコアは分離する。

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

## Score

総合スコアは evaluation vector から evaluator が deterministic に計算する。
score formula は evaluator id と version に紐づける。
Experiment は evaluator id、version、config hash を保存する。

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
plugin は次の interface を提供する。

```python
class Evaluator:
    evaluator_id: str
    version: str

    def evaluate(self, state: State, context: "EvaluationContext") -> "EvaluationResult":
        ...
```

`EvaluationResult` は次を持つ。

- `vector`
- `total_score`
- `success`
- `explanations`
- `cache_key`

`explanations` は report 用であり、score 計算の source of truth ではない。

## Experiment Schema

Experiment YAML の最小形は次である。

```yaml
experiment:
  schema_version: "0.3a"
  experiment_id: first_turn_control_random_v1
  objective: first_turn_control
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
  replay:
    strict_versions: true
  assets:
    rule_config: master_rule_5
```

V0.3a では `search.strategy` を記録するが、探索戦略の詳細実装は V0.3b 以降に送る。

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
- evaluator plugin が id、version、config hash を持つ。
- evaluator または predicate の変更で cache が無効化される。
- Experiment YAML の最小形が提示されている。

## Future Contract Tests

- `test_experiment_schema_validation`
- `test_evaluator_cache_key_changes_with_evaluator_version`
- `test_success_predicate_is_independent_from_total_score`
- `test_experiment_records_information_mode`
- `test_experiment_records_evaluate_at`
