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

## Analyze Metrics

`analyze` is intended to be the main v0.0 development feedback loop. It reports:

- action type coverage
- target declaration and target reference resolution rate
- top unmatched fragments
- empty block ratios
- validation severity counts
- validation code counts

These metrics make dictionary and transform changes visible before any state engine work begins.

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
