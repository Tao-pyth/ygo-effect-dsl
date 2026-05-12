# ygoEffectDSL Spec v0.0 (Draft) - Changelog

> Policy: every spec, CLI, transform, validation, analysis, or fixture change should be recorded here while v0.0 remains experimental.

## Unreleased

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
