# Release Stage Index: 0.3.0 to 1.0.0

Status: Package 0.5.0 released; 0.5.1 active; 0.6.0 and 0.7.0 planned

Last updated: 2026-07-16

## Purpose

本書はpackage `0.3.0`から`1.0.0`までのstage、依存関係、責任境界、親Issueを一つの索引にする。現行packageは`0.5.0`である。`0.4.0`は実装stageとして完了し、独立tagを作らず累積`0.5.0`へ収録した。次のactive package milestoneは`0.5.1`、後続のplanned milestoneは`0.6.0`と`0.7.0`である。

## Stage dependency

```text
0.3.0 real-core and EDOPro Lua qualified baseline
  -> 0.4.0 search breadth and private-view safety
      -> 0.5.0 corpus analytics and UI
          -> 0.5.1 verification efficiency and compatible maintenance
              -> 0.6.0 deterministic parallel search and measured latency reduction
                  -> 0.7.0 evidence-driven research dashboard and preference-aware results
                      -> 1.0.0 stable distribution and operations
```

| Stage | Parent | 入力 | 主成果 | 次stageへ渡す不変条件 |
|---|---|---|---|---|
| `0.3.0` | [#131](https://github.com/Tao-pyth/ygo-effect-dsl/issues/131) | 現行Random Search、real-core frontier、asset lock | clean bootstrap、3 deck qualification、10万node evidence | core由来合法性、fresh Replay、exact identity、fail-close |
| `0.4.0` | [#132](https://github.com/Tao-pyth/ygo-effect-dsl/issues/132) | `0.3.0`の実core基準線 | Beam/MCTS、PlayerView、複数妨害、複数turn | strategy決定性、hidden情報非漏洩、Route lineage |
| `0.5.0` | [#133](https://github.com/Tao-pyth/ygo-effect-dsl/issues/133) | `0.4.0`のversion付きevidence | corpus/job/query/comparison/UI | provenance、idempotency、CLI/API/UI semantic一致 |
| `0.5.1` | [#236](https://github.com/Tao-pyth/ygo-effect-dsl/issues/236) | release済み`0.5.0`検証profile | test分類、fixture統合、quiet evidence | semantic coverage維持、wall time・出力byte測定削減 |
| `0.6.0` | [#258](https://github.com/Tao-pyth/ygo-effect-dsl/issues/258) | serial SearchExecutor、独立parallel contract、`0.5.1`検証profile | node-level process pool、strategy並列化、desktop、100k speedup evidence | fresh Replay、semantic commit、pool determinism、bounded resource |
| `0.7.0` | [#276](https://github.com/Tao-pyth/ygo-effect-dsl/issues/276) | `0.6.0` bounded Search、desktop artifact publication、analytics | real result、terminal preference、Route randomness、Replay verification、Top-K/coverage | artifact truth、immutable evaluation、reliability provenance、best-observed honesty |
| `1.0.0` | [#134](https://github.com/Tao-pyth/ygo-effect-dsl/issues/134) | qualification済みruntimeとanalytics | stable compatibility、license、release、ops | support期間内の互換性と監査可能な配布 |

## Version allocation rules

1. package versionは利用者に提供する全体releaseを表す。
2. schema/contract versionは保存形式、API、semanticの互換境界を表す。
3. package milestone開始時にschema番号を予約しない。
4. optional field追加でもcanonical hashや意味が変わる場合は、対象contractのversion更新を検討する。
5. strategy、evaluator、cache policyは独立versionを持ち、package versionだけで再現性を表現しない。
6. old Experiment/Route/Replayを黙って再解釈せず、read、replay、migration、rejectのいずれかを明示する。

## Cross-stage mandatory gates

- Pythonはルールを所有しない。
- runtime resolverはnetwork accessやinstallを行わない。
- asset/core mismatchは実行前に停止する。
- node/replay/depth budgetではworker retry、pool size、完了順でsemantic結果を変えない。wall-clock deadlineはtiming-censoredとして分離する。
- private情報を保存・表示・exportするsurfaceはPlayerView policyに従う。
- third-party assetは審査なしに配布物へ含めない。
- evidenceにはpackage、schema、lock、deck、seed、budget、hardware/workload manifestを必要範囲で保存する。
- real job resultはcommit済みartifactへ結び、synthetic、unverified、censored、unknownを成功・verified・optimalへ読み替えない。
- terminal preference、gameplay randomness、ranking、coverageは独立version identityを持ち、legacy artifactの欠落を既定値で再解釈しない。

## Detailed specifications

- [0.3.0 scope](v0.3.0/00_scope.md)
- [0.3.0 real-core integration](v0.3.0/10_real_core_integration.md)
- [0.3.0 work breakdown](v0.3.0/20_work_breakdown.md)
- [0.3.0 acceptance](v0.3.0/30_acceptance.md)
- [0.4.0 scope](v0.4.0/00_scope.md)
- [0.4.0 contracts](v0.4.0/10_search_and_player_view_contracts.md)
- [0.4.0 work breakdown and acceptance](v0.4.0/20_work_breakdown_and_acceptance.md)
- [0.5.0 scope](v0.5.0/00_scope.md)
- [0.5.0 analytics contracts](v0.5.0/10_analytics_contracts.md)
- [0.5.0 desktop UI requirements](v0.5.0/15_desktop_ui_requirements.md)
- [0.5.0 work breakdown and acceptance](v0.5.0/20_work_breakdown_and_acceptance.md)
- [0.5.1 verification efficiency scope](v0.5.1/00_scope.md)
- [0.6.0 deterministic parallel search scope](v0.6.0/00_scope.md)
- [0.6.0 parallel execution contracts](v0.6.0/10_parallel_execution_contracts.md)
- [0.6.0 work breakdown and acceptance](v0.6.0/20_work_breakdown_and_acceptance.md)
- [0.7.0 evidence-driven research dashboard scope](v0.7.0/00_scope.md)
- [0.7.0 evaluation, randomness, and result contracts](v0.7.0/10_evaluation_randomness_and_result_contracts.md)
- [0.7.0 research dashboard workflow](v0.7.0/15_research_dashboard_workflow.md)
- [0.7.0 work breakdown and acceptance](v0.7.0/20_work_breakdown_and_acceptance.md)
- [1.0.0 scope](v1.0.0/00_scope.md)
- [1.0.0 production contracts](v1.0.0/10_production_distribution_contracts.md)
- [1.0.0 work breakdown and acceptance](v1.0.0/20_work_breakdown_and_acceptance.md)
- [Validation register](00_validation_register.md)
