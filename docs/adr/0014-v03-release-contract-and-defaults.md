# ADR 0014: Release package 0.3.0 without changing serialized contracts

Status: accepted for v0.3

Date: 2026-07-15

## Context

実ocgcore、EDOPro Lua、任意deck入力、Random Search、worker failure、10万logical node、480 fresh Replayのqualificationをpackage releaseへ反映する必要がある。一方、package versionとserialized contract versionは別責務であり、未完了の統計校正をrelease都合で完了扱いしてはならない。

## Decision

package/CLIを`0.3.0`とする。これは実core qualification済みのWindows x64向けsource milestoneであり、一般公開distributionやproduction supportの承認ではない。Experiment、Scenario、Decision、Action、Replay、Route DSL、SearchRunの保存形とsemanticは変更しないため、contract versionは据え置く。

| Boundary | v0.3 decision |
|---|---|
| Experiment | `0.4`を書き出し、`0.3b`を実行可能、`0.3a`を明示的migration入力として読み取る |
| Route DSL | `0.1`と`route-normalization-v2`を維持する |
| Decision / Action / Replay | `0.3a`、`ygo-replay-manifest-v1`、`fresh-replay-verification-v1`を維持する |
| Search | `search-executor-v4`、`search-run-result-v4`、`random-search-strategy-v1`を維持する。Beam/MCTSは明示的未実装error |
| Budget | `max_nodes`または`max_seconds`をExperimentで必須とし、暗黙のproject defaultを追加しない。`max_depth`と`max_replays`も指定時は強制する |
| Worker | `real-core-worker-policy-v1`のdefault pool 4、max pool 8、`real-core-memory-preflight-v1`の1.5 GiB上限を採用する |
| Resolver | `resolver-index-policy-v1`の`checked_process_local`を採用し、persistent index/native state reuseを行わない |
| Pruning | `pruning-guardrail-policy-v2`はversion付き研究契約として保持するが、executorのproduction defaultへ接続しない |
| Resource metric | `resource_consumption_v1`は再計算可能なprovisional指標として保持し、best Route順序や一般deck品質の根拠に使わない |

#110がmulti-deck sibling traceでfalse-prune率と検出力を校正するまで統計的枝刈りは既定無効とする。#108がblind domain-review rankingを完了するまで`resource_consumption_v1`のweight品質を主張しない。後続で枝刈りを採用する場合は新しいpolicy decisionを、weightを変更する場合は新しいevaluator versionを作り、既存reportの再現性を維持する。

今回のreleaseはnon-breakingでありartifact migrationは不要である。`0.3a/0.3b`互換を廃止する場合は、最短でも一つのminor releaseでdeprecationを通知し、package `1.0.0`より前に黙って再解釈しない。

wheel、sdist、Windows executableはqualificationのためbuildするが、third-party core/assetsを含めない。project licenseが`NOASSERTION`のため、distribution policyは一般公開releaseを引き続きfail-closeする。`v0.3.0` tagはreview済みsource identityであり、配布承認ではない。

## Evidence

- `docs/adr/evidence/0105_general_search_100k.json`: 3 profile x 100,000 logical node、pool非依存semantic
- `docs/adr/evidence/0128_real_core_replay_pool.json`: 480 fresh Replay、default 4/max 8、1.5 GiB memory preflight
- `docs/adr/evidence/0212_resolver_index_policy.json`: persistent/resident候補の測定済み不採用
- `docs/ocgcore/evidence/real_deck_qualification.json`: 3 real deckの反復Search/Replay
- `docs/ocgcore/evidence/lua_load_qualification.json`: official CardScripts 12,702件のnative load
- `docs/ocgcore/evidence/self_hosted_smoke_workflow.json`: workflow run 29380688844の実core smoke
- #108: evaluator weightの未完了human calibration
- #110: pruningの未完了multi-deck statistical calibration

## Consequences

利用者は既存Experiment/Routeをmigrationなしで再生でき、実測済みworker上限を利用できる。探索品質を過大表示しない代わりに、枝刈りによる高速化とresource metricによる一般品質rankingは後続校正まで利用範囲が限定される。
