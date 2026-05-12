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

### Empty block ratio policy

`quality.empty_block_ratio` is the ratio of effects where each structural block
remained empty after transform. For object-shaped blocks, empty means `{}`. For
`actions`, empty means an empty or missing `actions[]` list. The metric is about
converter coverage, not card legality or gameplay power.

v0.0 treats this metric as advisory. It should make parser gaps visible during
review, but it should not fail CI by itself. The transform still contains known
fallbacks, the representative dataset is small, and some blocks are optional in
real card text. Making CI fail on the first threshold would encourage noisy
patches that hide `{}` without adding reliable semantics. CI should continue to
gate schema validity, validation errors, golden regressions, and smoke checks;
empty block ratio should guide the next dictionary or parser issue until the
dataset and semantics are stable enough for v0.1-era gates.

Use these provisional thresholds as investigation triggers:

- `trigger >= 0.50`: investigate whether timing phrases such as "when", "if",
  "during", and phase/turn markers are being missed. Some continuous effects
  may have no trigger, so inspect examples before changing rules.
- `restriction >= 0.80`: investigate, but expect this block to be naturally
  high. Many effects have no "once per turn", activation limit, or material
  restriction. Repeated phrases such as "you can only use this effect..." should
  still become parser work.
- `condition >= 0.50`: investigate missed "if you control", "while", "except",
  location, face-up, and state requirements. A high value often means the
  converter is placing requirement text into action fragments or dropping it.
- `cost >= 0.50`: investigate missed "discard", "send", "tribute", "banish",
  "pay", and detach clauses that appear before the main action. Empty cost is
  legitimate for many effects, so confirm the sample has cost language.
- `action >= 0.50`: investigate legacy single-action fallback coverage. Because
  `actions[]` is canonical, this field mainly shows whether compatibility
  output is still useful or drifting.
- `actions >= 0.50`: investigate first. A high value means the canonical action
  list is often empty, so v0.1 state/action semantics would not have enough
  structured operations to consume.

For new Japanese programmers, use this investigation flow when a ratio is above
the threshold:

1. Open `analysis_report.json` and identify the highest block ratio.
2. Pick three to five affected cards or effects from the transformed YAML.
3. Read the original Japanese and English effect text beside the emitted block.
4. Decide whether the text truly has no such block, or whether the parser missed
   a phrase.
5. If the phrase is action-like, compare it with `stats.unmatched_fragments_top`
   and existing action dictionary rules.
6. If the phrase names a target, compare `targets[]`, action `target_id`, and
   `stats.targets_count.resolution_rate`.
7. Add or adjust the smallest dictionary, extractor, or transform rule that
   captures the repeated phrase.
8. Re-run `transform`, `validate`, and `analyze`; confirm the ratio moves down
   without increasing validation errors or unmatched fragments.

The v0.0 stabilization meaning is simple: ratios should become explainable.
They do not all need to be low, but a high value should have a known reason,
examples, and a follow-up issue. The v0.1 connection is also direct: early
state/query behavior should only be built on blocks that are common enough,
resolved enough, and validation-clean enough for analyze to show repeatable
structure.

This dashboard is necessary for v0.0 stabilization because v0.0 is about making
conversion quality visible and repeatable. It also connects directly to v0.1:
the minimal state/action semantics should only depend on action types, targets,
and selectors that analyze already shows as common, resolved, and validation
clean.
