# Release Validation Register

Status: Active verification log

Last updated: 2026-07-14

## Status definitions

- `VERIFIED_LOCAL`: 現在のcheckoutとこのhostで実行確認済み。clean hostや他platformへ一般化しない。
- `VERIFIED_UPSTREAM`: upstream repository/tag/commitを一次情報で確認済み。
- `OPEN`: 結論に必要な証跡が不足している。リンク先Issueで検証する。
- `BLOCKED`: 外部判断または前提Issueが完了するまで進めない。

## Register

| ID | 論点 | 2026-07-14の確認結果 | Status | Owner |
|---|---|---|---|---|
| `VAL-001` | package/tag基準 | sourceは`0.2.0`、tag `v0.2.0`はcommit `22ffce0`を指す | `VERIFIED_LOCAL` | release process |
| `VAL-002` | ocgcore lock | upstream latest release tagは`v11.0`、固定commit `158aebe...`、tree `23915a...`、API `11.0` | `VERIFIED_UPSTREAM` | [#136](https://github.com/Tao-pyth/ygo-effect-dsl/issues/136) |
| `VAL-003` | 現在hostのcore runtime | `ocgcore-doctor`、`ocgcore-verify`成功。Windows x64、VS 2022/MSVC、owned cacheを使用 | `VERIFIED_LOCAL` | [#135](https://github.com/Tao-pyth/ygo-effect-dsl/issues/135) |
| `VAL-004` | CardScripts lock | tag `20250420`のpeeled commitが固定commit `c8e9c0...`と一致 | `VERIFIED_UPSTREAM` | [#140](https://github.com/Tao-pyth/ygo-effect-dsl/issues/140) |
| `VAL-005` | BabelCDB lock | tag `20250419`は`4c8e9ca...`を指すがlockは同日後刻の`f89c9a...`を固定。既存cache verifyは成功、clean取得は未証明 | `OPEN` | [#137](https://github.com/Tao-pyth/ygo-effect-dsl/issues/137) |
| `VAL-006` | 実core/Lua end-to-end | inline fixtureで10 node/10 fresh ReplayのRandom Search、Route出力、best Route Replay、final state hash確認に成功 | `VERIFIED_LOCAL` | [#138](https://github.com/Tao-pyth/ygo-effect-dsl/issues/138) |
| `VAL-007` | clean core bootstrap | core未取得hostからsource/build/hash/APIを再現する証跡が未作成 | `OPEN` | [#136](https://github.com/Tao-pyth/ygo-effect-dsl/issues/136) |
| `VAL-008` | 任意deck一般性 | 単一inline smokeは成功。短/長/墓地・除外またはchain多発の3 deck qualificationは未実施 | `OPEN` | [#139](https://github.com/Tao-pyth/ygo-effect-dsl/issues/139) |
| `VAL-009` | Lua load境界 |固定helper/card scriptは動作。path traversal、case、欠落、syntax error、未知helperのsystematic corpusは未完了 | `OPEN` | [#140](https://github.com/Tao-pyth/ygo-effect-dsl/issues/140) |
| `VAL-010` | Message/Decision一般性 | API 11.0 registryと既存fixtureはあるが、任意deckで未知形状が出ない保証はない | `OPEN` | [#141](https://github.com/Tao-pyth/ygo-effect-dsl/issues/141) |
| `VAL-011` | 妨害timing | targetless/cost/target等の基礎taxonomyはある。damage step、mandatory trigger、SEGOC等は未完了 | `OPEN` | [#123](https://github.com/Tao-pyth/ygo-effect-dsl/issues/123) |
| `VAL-012` | 10万node実worker性能 | logical workload evidenceはあるが、pool 1/2/4/8/16の実Replay throughput/RSSは未測定 | `OPEN` | [#105](https://github.com/Tao-pyth/ygo-effect-dsl/issues/105), [#128](https://github.com/Tao-pyth/ygo-effect-dsl/issues/128) |
| `VAL-013` | worker障害 | failure envelopeはあるが、crash/timeout/retry/quarantineのrelease acceptanceを未固定 | `OPEN` | [#142](https://github.com/Tao-pyth/ygo-effect-dsl/issues/142) |
| `VAL-014` | supported platform | lockはWindows x64/MSVC。Linux/macOSと複数Python versionのsupport宣言は未確定 | `OPEN` | [#135](https://github.com/Tao-pyth/ygo-effect-dsl/issues/135) |
| `VAL-015` | Beam/MCTS | interface接続点のみ。ordering、statistics、決定性、実装は未完了 | `OPEN` | [#145](https://github.com/Tao-pyth/ygo-effect-dsl/issues/145)-[#149](https://github.com/Tao-pyth/ygo-effect-dsl/issues/149) |
| `VAL-016` | PlayerView | private-view real Replay、redaction、leak auditは未実装 | `OPEN` | [#125](https://github.com/Tao-pyth/ygo-effect-dsl/issues/125), [#150](https://github.com/Tao-pyth/ygo-effect-dsl/issues/150), [#151](https://github.com/Tao-pyth/ygo-effect-dsl/issues/151) |
| `VAL-017` | analytics storage/UI | storage ADR、job recovery、query/comparison API、100万row UI校正は未完了 | `OPEN` | [#133](https://github.com/Tao-pyth/ygo-effect-dsl/issues/133) |
| `VAL-018` | license/asset distribution | root project licenseとBabelCDB等の再配布可否が未確定 | `BLOCKED` | [#91](https://github.com/Tao-pyth/ygo-effect-dsl/issues/91), [#169](https://github.com/Tao-pyth/ygo-effect-dsl/issues/169) |
| `VAL-019` | production operations | compatibility、upgrade/rollback、observability、incident、soakを未検証 | `OPEN` | [#127](https://github.com/Tao-pyth/ygo-effect-dsl/issues/127), [#134](https://github.com/Tao-pyth/ygo-effect-dsl/issues/134) |
| `VAL-020` | GitHub Actions runtime | current workflowのaction pin/runtime deprecationをrelease前に再監査する必要がある | `OPEN` | [#138](https://github.com/Tao-pyth/ygo-effect-dsl/issues/138), [#173](https://github.com/Tao-pyth/ygo-effect-dsl/issues/173) |
| `VAL-021` | Windows desktop architecture | Windows desktop要件は確定したが、shell、Python service/IPC、installer/update境界は未選定 | `OPEN` | [#181](https://github.com/Tao-pyth/ygo-effect-dsl/issues/181) |
| `VAL-022` | card detail/effect text | 現行real-core providerは`datas`表だけを読み、表示用`texts` provider、locale、license/fallback契約は未実装 | `OPEN` | [#183](https://github.com/Tao-pyth/ygo-effect-dsl/issues/183), [#91](https://github.com/Tao-pyth/ygo-effect-dsl/issues/91) |

## Verification commands used

```powershell
python -m ygo_effect_dsl ocgcore-doctor
python -m ygo_effect_dsl ocgcore-verify
python -m ygo_effect_dsl ocgcore-assets-verify
python -m ygo_effect_dsl experiment-search examples/experiments/general_search_inline.yaml --out <temp>/best.route.yaml --search-report <temp>/report.json
python -m ygo_effect_dsl experiment-replay examples/experiments/general_search_inline.yaml <temp>/best.route.yaml
```

`VAL-006`のlocal smoke結果は`nodes=10`、`replays=10`、`worker_invocations=10`、`worker_retries=0`、terminationは`max_nodes`だった。これは接続確認であり、成功predicate達成率やproduction性能の証拠には使用しない。

## Update rule

各`OPEN/BLOCKED`項目は、Issueに再現手順、raw evidence、環境manifest、結論を保存した後にのみstatusを変更する。asset lockやdefault policyを先に変更して不確定事項を解消済み扱いにしてはならない。
