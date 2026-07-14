# Changelog

All notable package changes are documented here. Package versions follow Semantic Versioning and remain independent from Experiment, Route DSL, Replay, Search, and other functional contract versions.

## 0.2.0 - 2026-07-14

Status: General Search MVP candidate for Python engineers using a local asset cache. This source milestone does not authorize redistribution of third-party assets or claim production support.

### Added

- Experiment `0.4` with fixed, inline, and YDK decks; fixed, seeded random, and conditional opening hands; scenario manifest; and fail-closed preflight diagnostics.
- Deterministic `RandomSearchStrategyV1`, real-core frontier Replay, enforced search budgets, stable best-Route ordering, and the `experiment-search` CLI.
- Specified-interruption generation from core-provided activation, cost, target, and option candidates with a machine-readable support taxonomy.
- Three-profile 100,000 logical-node benchmark evidence, cache/worker policy v2, and memory preflight v2.
- Package `--version` output and a single package-version source used by setuptools.

### Compatibility

- Route DSL remains `0.1`; DecisionRequest, Action, and Replay remain `0.3a`.
- Experiment `0.3b` remains executable and `0.3a` remains readable as explicit migration input.
- Beam Search, MCTS, real-core PlayerView Replay, large-scale statistics UI, and production distribution remain outside this release.
- ocgcore and third-party assets are not bundled.
