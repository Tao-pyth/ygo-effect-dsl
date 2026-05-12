# ygo-effect-dsl

Research CORE for turning Yu-Gi-Oh! card effect text into a structured DSL, then validating and analyzing the conversion quality.

The current goal is v0.0 stabilization: make transform output measurable and trustworthy before building a full state engine.

## 5-Minute Loop

Install locally:

```bash
pip install -e .
```

Run the sample dataset through the core pipeline:

```bash
python -m ygo_effect_dsl ingest --dataset examples/sample_dataset
python -m ygo_effect_dsl transform --dataset examples/sample_dataset --out data/dsl_out
python -m ygo_effect_dsl validate data/dsl_out/yaml
python -m ygo_effect_dsl analyze data/dsl_out/yaml --out data/reports
```

Key outputs:

- DSL YAML: `data/dsl_out/yaml/*.yaml`
- Transform reports: `data/dsl_out/reports/`
- Analyze report: `data/reports/analysis_report.json`

## What v0.0 Means

v0.0 is a research conversion baseline. It prioritizes stable structure and diagnostics over complete game semantics.

Current DSL focus:

- `card` identity, text, and compact `props`
- `effects[]`
- canonical `actions[]`
- compatibility `action` fallback
- `targets[]`
- validation diagnostics
- analyze metrics for conversion quality

`card.info` is not exported in the DSL. Raw ETL info blobs may be normalized into compact `card.props`.

## Development Loop

Run tests:

```bash
python -m pytest
```

Representative-card golden tests compare transform output for `tests/datasets/representative_cards`.

Update golden files only when the DSL change is intentional:

```bash
$env:YGO_UPDATE_GOLDEN="1"
python -m pytest tests/test_representative_golden.py
Remove-Item Env:\YGO_UPDATE_GOLDEN
```

Then review `tests/golden/representative_cards/` before committing.

## Representative Benchmark Policy

`tests/datasets/representative_cards/cards.jsonl` is the small benchmark used to
keep v0.0 transform behavior measurable while the parser is still changing. It
currently has 20 synthetic slots. Treat each row as a semantic slot first and as
a card name second: a replacement is useful only when it keeps the same action,
target, cost, or restriction pressure visible in the golden snapshot.

Current slot coverage:

| CID | Slot | Action coverage | Target coverage | Cost coverage | Restriction coverage |
| --- | --- | --- | --- | --- | --- |
| 9001 | simple draw | `draw` | none | none | none |
| 9002 | summon-triggered search | `add_to_hand` from Deck to hand | none | none | Normal Summon trigger, no restriction |
| 9003 | simple destroy | `destroy` | inline description, no declared target | none | none |
| 9004 | simple send | `send_to_gy` | inline monster description | none | none |
| 9005 | self summon | `special_summon` self | none | none | none |
| 9006 | summon from Deck | `special_summon` from Deck | inline LIGHT Spellcaster Tuner description | none | none |
| 9007 | banish from GY | `banish` | inline GY description | none | none |
| 9008 | targeted return to Extra Deck | `return_to_extra` | `targets[]` monster you control | none | target clause only |
| 9009 | targeted destroy | `destroy` | `targets[]` card your opponent controls | none | target clause only |
| 9010 | discard cost into draw | `draw`, plus current extra `discard` action trace | none | `discard` 1 card | none |
| 9011 | once-per-turn classifier | `draw` | none | none | OPT text is detected as a restriction candidate; emitted global restriction is still empty |
| 9012 | generic monster search | `add_to_hand` from Deck to hand | inline monster description | none | none |
| 9013 | summon from GY | `special_summon` from GY | inline monster description | none | none |
| 9014 | summon from hand | `special_summon` from hand | inline monster description | none | none |
| 9015 | discard action | `discard` | inline monster description | none | none |
| 9016 | targeted shuffle to Deck | `return_to_deck` shuffle mode | `targets[]` card in either GY | none | target clause only |
| 9017 | negate | `negate` effect | implicit "that effect" | none | none |
| 9018 | targeted banish | `banish` | `targets[]` monster in your GY | none | target clause only |
| 9019 | multi-action sequence | `draw`, `send_to_gy` | inline monster description | none | none |
| 9020 | unmatched fragment sentinel | no action yet | hand phrase remains unmatched | none | none |

Replacement priorities from synthetic to real cards:

1. Replace slots whose real card text is short, famous, and mechanically narrow:
   draw, generic search, Monster Reborn-style GY summon, destroy Spell/Trap, and
   Foolish Burial-style send to GY. These should preserve action coverage while
   making the fixture recognizable.
2. Replace target-heavy slots after checking that the real text keeps the same
   `targets[]` shape. Target wording has more parser surface area than simple
   actions, so preserve one slot each for controlled monster, opponent card,
   either GY, and your GY.
3. Replace cost and restriction slots only when the golden diff is intentionally
   reviewed. These slots expose current rough edges: semicolon costs can also
   appear in `actions[]`, and OPT text is counted as a restriction candidate but
   does not yet populate `meta.restrictions.global`.
4. Keep one unmatched or partially unmatched real card slot for v0.0. It is a
   canary for dictionary gaps and helps `analyze` keep surfacing work that should
   not be hidden by only testing already-supported text.

Obvious real-card candidates to verify against local source data before editing
the dataset:

- 9001 simple draw: `Pot of Greed`.
- 9012 generic monster search: `Reinforcement of the Army`.
- 9013 summon from GY: `Monster Reborn`.
- 9004 simple send: `Foolish Burial`.
- 9003 simple destroy: `Mystical Space Typhoon` or another short destroy card,
  depending on whether the slot should stay "card on the field" or narrow to
  Spell/Trap.
- 9017 negate: a short "negate that effect" hand-trap or response card, after
  confirming the surrounding trigger/cost text does not change the slot's role.

When replacing a row, keep `tests/golden/representative_cards/expected.json` as a
full snapshot and update it only as a deliberate second step:

1. Change one or a small batch of rows in `tests/datasets/representative_cards/cards.jsonl`.
2. Run `python -m pytest tests/test_representative_golden.py` once to see the
   failing diff.
3. Confirm the diff preserves or intentionally improves the slot's action,
   target, cost, restriction, diagnostics, and `meta.action_candidate_trace`.
4. Regenerate with `YGO_UPDATE_GOLDEN=1` only after that review.
5. Re-run the representative golden test and the analyze checks, then inspect
   `tests/golden/representative_cards/expected.json` before committing.

This benchmark is the bridge between v0.0 stabilization and v0.1 semantics.
v0.0 needs stable, reviewable outputs for `actions[]`, `targets[]`, costs,
restrictions, diagnostics, and analyze metrics. v0.1 should only build minimal
state/action behavior on card patterns whose transform output has survived this
representative golden loop.

## Hourly Brainstorm Workflow

Hourly brainstorms are tracked as a primary research output, not as setup for later work. Use them to record hypotheses that move `ygo-effect-dsl` toward a research CORE, including why an issue was or was not created.

See [Hourly Brainstorm Workflow](docs/hourly_brainstorm.md) for the operating viewpoints and the report template used by Automation final reports.

## Analyze Metrics

`analyze` is intended to be the main v0.0 development feedback loop. It reports:

- `stats.action_type_coverage`: which action `type` values the transform currently emits
- `stats.targets_count.resolution_rate`: how many action `target_id` references resolve to declared `targets[]`
- `stats.unmatched_fragments_top`: frequent action-candidate text fragments that no dictionary rule matched
- `quality.empty_block_ratio`: which effect blocks still fall back to `{}` or empty `actions[]`
- `validation.severity_counts` and `validation.code_counts`: validation TODOs grouped by seriousness and code

Read the report as a dashboard: unmatched fragments point to dictionary gaps, target resolution points to target extraction/transform gaps, empty block ratios point to missing block parsers, and validation counts show which DSL contracts are still noisy. These metrics make dictionary and transform changes visible before any state engine work begins. See [Examples](docs/spec/v0.0/30_examples.md#example-4-analyze-report-development-dashboard) for the field-level reading guide.

For v0.0, `quality.empty_block_ratio` is an advisory signal, not a CI failure gate. The provisional investigation threshold is `0.50` for semantic blocks (`trigger`, `condition`, `cost`, `action`, `actions`) and `0.80` for `restriction`, because many cards legitimately have no restriction text yet the parser still needs visibility into repeated omissions. See [Empty block ratio policy](docs/spec/v0.0/30_examples.md#empty-block-ratio-policy) for the block-by-block interpretation and investigation flow.

The `analyze` CLI also prints the most important dashboard summaries directly, including action type coverage, target resolution rate, unmatched fragment counts, and validation code counts. This keeps the next dictionary/transform target visible without opening the JSON report first.

## Validation Diagnostics

`validate` separates diagnostics into three severities:

- `error`: DSL shape is invalid. Fix this before later pipeline steps depend on the output.
- `warning`: DSL shape is valid, but some meaning is unresolved or compatibility-only.
- `info`: analysis note that does not block processing.

For Japanese contributors: first check that `errors=0`, then use warning codes such as `unknown_action`, `unresolved_target`, `missing_selector`, and `legacy_action_fallback` as the TODO list for improving transform rules. The detailed contract is in [Validation](docs/spec/v0.0/40_validation.md).

## Specs

Spec is the source of truth:

- [Grammar](docs/spec/v0.0/10_grammar.md)
- [Semantics](docs/spec/v0.0/20_semantics.md)
- [Validation](docs/spec/v0.0/40_validation.md)
- [Changelog](docs/spec/v0.0/50_changelog.md)

Documentation and behavior changes should update the changelog in the same change.

## Roadmap

Milestone A: v0.0 spec sync
Milestone B: representative-card benchmark
Milestone C: golden test + diagnostics
Milestone D: analyze coverage dashboard
Milestone E: v0.1 minimal state/action semantics

v0.1 should start with a small read/query state model (`Deck`, `Hand`, `Field`, `GY`, `Banished`, `Extra`, `Flags`) and a narrow action vocabulary (`draw`, `add_to_hand`, `send_to_gy`, `destroy`, `special_summon`, `banish`, `negate`).

## Scope

Included:

- ingest/transform/validate/analyze pipeline
- DSL generation and contract validation
- representative benchmark and golden regression tests
- research experiments around formalization
- foundations for state-transition modeling

Excluded for now:

- API fetching
- image downloading
- direct SQLite dependency on ETL internals
- full chain/stack simulation
- full opponent interaction modeling

## Input Contract

CORE expects ETL export artifacts:

- `manifest.json`
- `cards.jsonl`

These are produced by `ygo-effect-dsl-etl`. CORE does not read the ETL SQLite database directly.

## License

TBD
