# ygoEffectDSL Spec v0.0 (Draft) - Changelog

> Policy: every spec, CLI, transform, validation, analysis, or fixture change should be recorded here while v0.0 remains experimental.

## Unreleased

- docs: align v0.0 semantics, wiki pages, and ADRs with the Project Charter;
  replace the old State -> State execution framing with conversion semantics
  and engine-boundary candidates, add ADR-0001/0002, and rename the transform
  rule engine to `PatternRuleEngine` to avoid implying Python owns game rules.
- docs: expand the authoritative Project Charter with the full responsibility
  map for documentation, source layout, search, replay, bridge, evaluation,
  experiment, logging, statistics, data, ADRs, roadmap, and long-term goals.
- docs: establish V0.1 as the Project Charter and architecture baseline for
  future game engine + AI search work, update README, add Architecture,
  Roadmap, Glossary, and ADR-0000, and clarify that current DSL conversion
  remains the measurable input layer rather than the final product.
- ci: add representative golden preview workflow that can regenerate
  `tests/golden/representative_cards/expected.json` in GitHub Actions and
  publish the result as a review artifact without committing it.
- ci: add Windows PyInstaller workflow that runs pytest before building and
  uploading `ygo-effect-dsl-win64`.
- feat: add `ygo-effect-dsl` console script and bundled-resource dictionary
  default for frozen executable runs.
- fix: escape unmatched fragment CLI output so `analyze` works on Windows
  consoles with non-UTF-8 default encodings.
- fix: keep semicolon cost fragments out of `actions[]` so cost/action
  separation does not inflate representative action coverage, and bind
  normalized params per parsed fragment so representative 9010 emits
  `discard` in `cost` and only `draw n=2` in `actions[]`.
- docs: add version/tag/release policy for SemVer, v0 line operation,
  tag-triggered distribution, artifact naming, changelog expectations, and
  future app/schema/ruleset version separation.
- docs: add an anonymous validation Issue template and local log format for
  reporting YAML validation summaries without publishing protected source data.
- docs: add Issue #27 pending local commits checklist for publishing
  `main...origin/main [ahead N]`, waiting for explicit push/PR approval, and
  requiring green GitHub Actions before continuing the Issue #13 first batch.
- ci: add GitHub Actions pytest workflow for pull requests and pushes, covering
  representative golden/analyze regression checks without updating golden
  fixtures.
- docs: document local verification prerequisites and stop condition for
  representative-card golden/analyze workflow before Issue #13 first-batch
  fixture edits.
- docs: add Issue #13 first-batch source review note for slots 9001, 9004,
  and 9013 without changing representative dataset or golden fixtures.
- docs: add Issue #13 migration checklist, first-batch slot priorities, and
  golden/analyze review items for real-card representative benchmark updates.
- examples: add 10 fictional synthetic test cards for GitHub-distributable
  pipeline verification without copying official card records.
- test: cover the synthetic example dataset through ingest, transform, and
  validate.
- docs: add v0.1 overview, minimal state/action semantics, and first 10 one-step application candidates.
- docs: document representative benchmark slot coverage, real-card replacement priorities, and golden update workflow.
- test: strengthen representative-card golden comparison with full DSL payload snapshots and diagnostics.
- docs: define provisional `quality.empty_block_ratio` thresholds and advisory investigation policy for v0.0 stabilization.
- test: add analyze dashboard golden fixture and smoke checks for report fields.
- feat: print analyze dashboard summaries in CLI output for action coverage, target resolution, unmatched fragments, and validation code counts.
- docs: add hourly brainstorm workflow and report template for tracking research CORE hypotheses and issue triage decisions.
- docs: add analyze report dashboard reading guide with field names for action coverage, target resolution, unmatched fragments, empty blocks, and validation counts.
- docs: synchronize grammar with current transform output: `card.info` removed, `card.props` added, `actions[]` is canonical, `action` is legacy fallback, and `targets[]` is part of the effect shape.
- feat: add validation severity levels (`error`, `warning`, `info`) and surface warnings for `unknown_action`, `unresolved_target`, `missing_selector`, and `legacy_action_fallback`.
- docs: detail validation severity/code contracts, validate CLI output, and v0.1 connection in `40_validation.md`.
- feat: expand analyze report with action type coverage, target reference resolution rate, unmatched fragment ranking, and validation severity/code counts.
- feat: add starter `negate` action rule and candidate extraction coverage.
- test: add representative-card benchmark dataset and golden-output comparison with explicit `YGO_UPDATE_GOLDEN=1` update flow.
- feat: manifest.json + cards.jsonl minimum dataset flow (`ingest -> transform -> validate -> analyze`) with CLI, sample dataset, and smoke tests.
- docs: README documentation/changelog policy.
- Initial draft created on 2026-02-28.
