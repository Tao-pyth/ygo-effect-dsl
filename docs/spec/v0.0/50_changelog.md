# ygoEffectDSL Spec v0.0 (Draft) - Changelog

> Policy: every spec, CLI, transform, validation, analysis, or fixture change should be recorded here while v0.0 remains experimental.

## Unreleased

- docs: synchronize grammar with current transform output: `card.info` removed, `card.props` added, `actions[]` is canonical, `action` is legacy fallback, and `targets[]` is part of the effect shape.
- feat: add validation severity levels (`error`, `warning`, `info`) and surface warnings for `unknown_action`, `unresolved_target`, `missing_selector`, and `legacy_action_fallback`.
- feat: expand analyze report with action type coverage, target reference resolution rate, unmatched fragment ranking, and validation severity/code counts.
- feat: add starter `negate` action rule and candidate extraction coverage.
- test: add representative-card benchmark dataset and golden-output comparison with explicit `YGO_UPDATE_GOLDEN=1` update flow.
- feat: manifest.json + cards.jsonl minimum dataset flow (`ingest -> transform -> validate -> analyze`) with CLI, sample dataset, and smoke tests.
- docs: README documentation/changelog policy.
- Initial draft created on 2026-02-28.
