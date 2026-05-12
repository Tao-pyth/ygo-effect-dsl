# ygoEffectDSL Spec v0.0 (Draft) — Examples

この文書は **最小例 → 複雑例** の順に、DSLの具体例を掲載します。

## Example 1: Skeleton（空に近い例）
```yaml
dsl_version: "0.0"
card:
  cid: 123456
  name:
    en: "Example Card"
    ja: ""
effects:
  - id: "123456_001"
    order: 1
    trigger: {}
    restriction: {}
    condition: {}
    cost: {}
    action: {}
meta: {}
```

## Example 2: Trigger + Action（簡単な例）
（ここに具体例を追記）

## Example 3: Cost + Target（将来例）
（ここに具体例を追記）

## Example 4: Analyze Report Development Dashboard

`python -m ygo_effect_dsl analyze data/dsl_out/yaml --out data/reports`
creates `analysis_report.json`. For v0.0, read this file as the daily
development dashboard for dictionary and transform work. The report is not a
score for card strength or game correctness; it tells you where the converter
is still losing structure.

Minimal shape:

```json
{
  "stats": {
    "action_type_coverage": {
      "add_to_hand": 12,
      "special_summon": 8
    },
    "targets_count": {
      "references": 20,
      "resolved_references": 18,
      "resolution_rate": 0.9
    },
    "unmatched_fragments_top": [
      {
        "fragment": "then, you can draw 1 card",
        "count": 4
      }
    ]
  },
  "quality": {
    "empty_block_ratio": {
      "trigger": 0.42,
      "restriction": 0.81,
      "condition": 0.55,
      "cost": 0.67,
      "action": 0.12,
      "actions": 0.08
    }
  },
  "validation": {
    "severity_counts": {
      "error": 0,
      "warning": 7,
      "info": 0
    },
    "code_counts": {
      "warning:unresolved_target": 3,
      "warning:unknown_action": 4
    }
  }
}
```

Field guide:

- `stats.action_type_coverage` shows the emitted action vocabulary. If an
  expected action type is missing or rare, add or tune action dictionary rules
  before adding state-engine behavior for it.
- `stats.targets_count.resolution_rate` is the target reference resolution rate.
  It is computed from `references` and `resolved_references`. Low values mean
  actions are pointing at `target_id` values that are not present in the same
  effect's `targets[]`, so target extraction or transform wiring should be
  fixed next.
- `stats.unmatched_fragments_top` lists repeated action-candidate fragments
  whose `matched_rule_ids` were empty. Start dictionary work here because one
  high-count fragment can improve many cards.
- `quality.empty_block_ratio` shows how often `trigger`, `restriction`,
  `condition`, `cost`, `action`, or `actions` stayed empty. A high ratio marks
  the next block parser or transform rule family to improve.
- `validation.severity_counts` and `validation.code_counts` summarize validate
  diagnostics. First keep `error` at `0`, then use warning codes such as
  `warning:unknown_action`, `warning:unresolved_target`,
  `warning:missing_selector`, and `warning:legacy_action_fallback` as the
  transform TODO list.

For a new Japanese programmer, the recommended reading order is:

1. Check `validation.severity_counts.error`. If it is not `0`, fix DSL shape
   before optimizing coverage.
2. Check `validation.code_counts`. Repeated codes tell you the contract that is
   currently failing most often.
3. Check `stats.unmatched_fragments_top`. Add dictionary rules for the highest
   repeated fragments.
4. Check `stats.targets_count.resolution_rate`. If it drops, inspect target
   declarations and action `target_id` values together.
5. Check `quality.empty_block_ratio`. Pick the noisiest block and improve that
   transform family.
6. Re-run `transform`, `validate`, and `analyze`; the same fields should move in
   the expected direction.

This dashboard is necessary for v0.0 stabilization because v0.0 is about making
conversion quality visible and repeatable. It also connects directly to v0.1:
the minimal state/action semantics should only depend on action types, targets,
and selectors that analyze already shows as common, resolved, and validation
clean.
