# Package 0.6.0 Work Breakdown and Acceptance

Status: Issue-backed plan

Last updated: 2026-07-16

Parent: [#258](https://github.com/Tao-pyth/ygo-effect-dsl/issues/258)

## Work items

| Order | Issue | Deliverable | Acceptance evidence |
|---|---|---|---|
| 1 | [#259](https://github.com/Tao-pyth/ygo-effect-dsl/issues/259) | deterministic parallel execution contract | pool/completion/retry golden vectors、migration/reject rules |
| 2 | [#260](https://github.com/Tao-pyth/ygo-effect-dsl/issues/260) | pool 1 bottleneck baseline | cold/warm 3 fixture × 3 strategy timing/RSS profile |
| 3 | [#266](https://github.com/Tao-pyth/ygo-effect-dsl/issues/266) | semantic budget/deadline separation | fake-clock boundary、timing-censored report |
| 4 | [#269](https://github.com/Tao-pyth/ygo-effect-dsl/issues/269) | memory and adaptive pool policy | pool 1/2/4/8/16 RSS、reject/fallback evidence |
| 5 | [#261](https://github.com/Tao-pyth/ygo-effect-dsl/issues/261) | cancellable task-oriented frontier | submit/result/cancel/drain、Windows cleanup |
| 6 | [#262](https://github.com/Tao-pyth/ygo-effect-dsl/issues/262) | Experiment/CLI/API pool policy | round-trip、canonical hash、old input compatibility |
| 7 | [#231](https://github.com/Tao-pyth/ygo-effect-dsl/issues/231) | SearchExecutor pool coordinator | bounded queue、semantic commit、pool 1/2/4 equality |
| 8 | [#267](https://github.com/Tao-pyth/ygo-effect-dsl/issues/267) | crash/timeout/retry/cancel hardening | fault injection、no double update、no orphan process |
| 9 | [#270](https://github.com/Tao-pyth/ygo-effect-dsl/issues/270) | parallel report/export telemetry | JSON/SQLite/Parquet parity、canonical digest |
| 10 | [#263](https://github.com/Tao-pyth/ygo-effect-dsl/issues/263) | Random dispatch window | depth-first commit、pool determinism、waste metric |
| 11 | [#264](https://github.com/Tao-pyth/ygo-effect-dsl/issues/264) | Beam layer parallelism | stable layer barrier、width/tie/partial-layer vectors |
| 12 | [#265](https://github.com/Tao-pyth/ygo-effect-dsl/issues/265) | deterministic batched MCTS | ordinal batch、single backprop、statistics equality |
| 13 | [#268](https://github.com/Tao-pyth/ygo-effect-dsl/issues/268) | verified prefix cache integration | cache on/off equality、corruption/eviction evidence |
| 14 | [#272](https://github.com/Tao-pyth/ygo-effect-dsl/issues/272) | concurrency conformance suite | strategy × pool × ordering × failure matrix |
| 15 | [#271](https://github.com/Tao-pyth/ygo-effect-dsl/issues/271) | Windows desktop parallel controls | real-core pool 1/4、cancel/recovery、responsive/a11y evidence |
| 16 | [#273](https://github.com/Tao-pyth/ygo-effect-dsl/issues/273) | 100k-node release qualification | speedup、RSS、semantic equality、self-hosted artifact |
| 17 | [#274](https://github.com/Tao-pyth/ygo-effect-dsl/issues/274) | documentation and source release | package audit、CI、tag/changelog/milestone parity |

## Dependency order

```text
#259 contract + #260 baseline
  -> #266 budget/deadline + #269 memory policy
      -> #261 frontier task API + #262 configuration
          -> #231 coordinator + #267 failure handling + #270 telemetry
              -> #263 Random / #264 Beam / #265 MCTS / #268 cache
                  -> #272 conformance + #271 desktop
                      -> #273 100k qualification
                          -> #274 release gate
```

strategy work may proceed in parallel only after shared task/commit/budget contracts are reviewed. #273 may not substitute synthetic throughput for real-core evidence.

## Gate A: semantic correctness

- pool 1 matches the package `0.5.0` serial golden behavior.
- node/replay/depth budget runs produce the same semantic digest、best Route、lineage for pool 1/2/4.
- completion order、worker slot、retry、cache mode do not alter strategy semantic updates.
- STOP_LINE、END_TURN、terminal、exact dedup、frontier exhausted ordering remains compatible.
- deadline-censored results are not compared as complete deterministic runs.

## Gate B: isolation and failure

- native duel/Lua/mutable state is never shared across tasks or processes.
- crash、timeout、retry exhaustion、malformed/duplicate/late result、cancel are fail-close.
- retry updates strategy statistics at most once.
- worker process tree、handle、temporary file is cleaned after success、failure、cancel.
- Route/SearchRun/report publication remains atomic and restart-safe.

## Gate C: product contract

- Experiment、CLI、Python API、desktop use one validated effective policy.
- old Experiment inputs retain serial-compatible behavior.
- reports distinguish logical progress from in-flight/speculative physical work.
- PlayerView/redaction applies to worker failures、telemetry、exports.
- desktop shows preflight rejection、fallback、timing censor、cancel/recovery without UI blocking.

## Gate D: measured speedup

- same host、lock、seed、node/replay budget、warm condition、5+ repeats per cell。
- pool 4 median wall time is at least 25% lower than pool 1 for at least two of three representative fixtures.
- no representative fixture regresses by more than 10%.
- throughput gain is not achieved through fewer committed nodes、different Route result、or omitted failures.
- full evidence records hardware、commit、workload、RSS、I/O、waste、cache、artifact volume.

## Release rejection conditions

- speedup threshold is not met or only synthetic adapters show improvement.
- semantic results differ across pool sizes for node/replay budget runs.
- unbounded speculative work、queue、RSS、process、handle、or artifact growth remains.
- deadline run is presented as pool-independent deterministic evidence.
- worker crash、cache corruption、or retry exhaustion is converted to success.
- parallel mode silently changes old Experiment behavior.
- third-party core/assets are bundled or general distribution is implied before `1.0.0` gates.
