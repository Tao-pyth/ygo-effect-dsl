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
| `VAL-005` | BabelCDB lock | tag `20250419`は`4c8e9ca...`を指すがlockは同日後刻の`f89c9a...`を固定。空cacheから固定commitを直接fetchし、tree/file hashまで検証済み。ref不在contract testも追加 | `VERIFIED_LOCAL` | [#137](https://github.com/Tao-pyth/ygo-effect-dsl/issues/137) |
| `VAL-006` | 実core/Lua end-to-end | inline fixtureで10 node/10 fresh ReplayのRandom Search、Route出力、best Route Replay、final state hash確認に成功 | `VERIFIED_LOCAL` | [#138](https://github.com/Tao-pyth/ygo-effect-dsl/issues/138) |
| `VAL-007` | clean core bootstrap | 空rootからcommit/tree/API 11.0を検証。3 buildは同一DLL hash、初回1 buildだけ別hashのためbit reproducibility調査を継続 | `OPEN` | [#136](https://github.com/Tao-pyth/ygo-effect-dsl/issues/136) |
| `VAL-008` | 任意deck一般性 | 単一inline smokeは成功。短/長/墓地・除外またはchain多発の3 deck qualificationは未実施 | `OPEN` | [#139](https://github.com/Tao-pyth/ygo-effect-dsl/issues/139) |
| `VAL-009` | Lua load境界 | `ocgcore-lua-load-qualification-v1`でofficial 12,702件を7 fresh workerから全件native load。helper 26件の順序、cold/warm/fresh resolver同値性、negative probe、unsafe library無効を確認。BabelCDB欠落120件は通常preflightでfail-close | `VERIFIED_LOCAL` | [#140](https://github.com/Tao-pyth/ygo-effect-dsl/issues/140) |
| `VAL-010` | Message/Decision一般性 | 固定API 11.0全message registry、unknown ID fail-close、重複candidate拒否、Route decode/encode往復の`ocgcore-decision-shape-corpus-v1`を実装。固定matrixでtargetless/cost/single/multi-target/option/hand/fieldを確認したが、外部3 deck corpusは未取得 | `OPEN` | [#141](https://github.com/Tao-pyth/ygo-effect-dsl/issues/141) |
| `VAL-011` | 妨害timing | targetless/cost/target等の基礎taxonomyはある。damage step、mandatory trigger、SEGOC等は未完了 | `OPEN` | [#123](https://github.com/Tao-pyth/ygo-effect-dsl/issues/123) |
| `VAL-012` | 10万node実worker性能 | logical workload evidenceはあるが、pool 1/2/4/8/16の実Replay throughput/RSSは未測定 | `OPEN` | [#105](https://github.com/Tao-pyth/ygo-effect-dsl/issues/105), [#128](https://github.com/Tao-pyth/ygo-effect-dsl/issues/128) |
| `VAL-013` | worker障害 | version付きfrontier attempt/quarantine、retry exhaustion、structured Search failure、Route先行/report commit markerを実装。実core stress `realcorestress_a6868c...`でcrash/timeout/callback例外、pool 1/2/4、完了順独立、fresh replacement、全process終了を確認 | `VERIFIED_LOCAL` | [#142](https://github.com/Tao-pyth/ygo-effect-dsl/issues/142) |
| `VAL-014` | supported platform | lockはWindows x64/MSVC。Linux/macOSと複数Python versionのsupport宣言は未確定 | `OPEN` | [#135](https://github.com/Tao-pyth/ygo-effect-dsl/issues/135) |
| `VAL-015` | Beam/MCTS | interface接続点のみ。ordering、statistics、決定性、実装は未完了 | `OPEN` | [#145](https://github.com/Tao-pyth/ygo-effect-dsl/issues/145)-[#149](https://github.com/Tao-pyth/ygo-effect-dsl/issues/149) |
| `VAL-016` | PlayerView | private-view real Replay、redaction、leak auditは未実装 | `OPEN` | [#125](https://github.com/Tao-pyth/ygo-effect-dsl/issues/125), [#150](https://github.com/Tao-pyth/ygo-effect-dsl/issues/150), [#151](https://github.com/Tao-pyth/ygo-effect-dsl/issues/151) |
| `VAL-017` | analytics storage/UI | storage ADR、job recovery、query/comparison API、100万row UI校正は未完了 | `OPEN` | [#133](https://github.com/Tao-pyth/ygo-effect-dsl/issues/133) |
| `VAL-018` | license/asset distribution | root project licenseとBabelCDB等の再配布可否が未確定 | `BLOCKED` | [#91](https://github.com/Tao-pyth/ygo-effect-dsl/issues/91), [#169](https://github.com/Tao-pyth/ygo-effect-dsl/issues/169) |
| `VAL-019` | production operations | compatibility、upgrade/rollback、observability、incident、soakを未検証 | `OPEN` | [#127](https://github.com/Tao-pyth/ygo-effect-dsl/issues/127), [#134](https://github.com/Tao-pyth/ygo-effect-dsl/issues/134) |
| `VAL-020` | GitHub Actions runtime | current workflowのaction pin/runtime deprecationをrelease前に再監査する必要がある | `OPEN` | [#138](https://github.com/Tao-pyth/ygo-effect-dsl/issues/138), [#173](https://github.com/Tao-pyth/ygo-effect-dsl/issues/173) |
| `VAL-021` | Windows desktop architecture | Windows desktop要件は確定したが、shell、Python service/IPC、installer/update境界は未選定 | `OPEN` | [#181](https://github.com/Tao-pyth/ygo-effect-dsl/issues/181) |
| `VAL-022` | card detail/effect text | 現行real-core providerは`datas`表だけを読み、表示用`texts` provider、locale、license/fallback契約は未実装 | `OPEN` | [#183](https://github.com/Tao-pyth/ygo-effect-dsl/issues/183), [#91](https://github.com/Tao-pyth/ygo-effect-dsl/issues/91) |
| `VAL-023` | real-core State dedup | `SearchFrontier v2`でstate completenessを明示し、`query_api_projection`による枝削除を禁止。synthetic exact/projection回帰と実core frontier宣言を検証 | `VERIFIED_LOCAL` | [#192](https://github.com/Tao-pyth/ygo-effect-dsl/issues/192) |
| `VAL-024` | fresh Replay success artifact | SearchRunと共通のExperiment digest、Route/State/manifest/scenario/runtime/Lua identityを結ぶ`fresh-replay-verification-v1`を一意tempからatomic保存。general-search実core CLIとWindows並行writerで確認 | `VERIFIED_LOCAL` | [#193](https://github.com/Tao-pyth/ygo-effect-dsl/issues/193) |
| `VAL-025` | 外部3 deck qualification harness | `real-deck-qualification-index-v1`、外部path制約、2回反復、profile witness、distinct deck hash、custom fixture/妨害拒否、atomic sanitized indexをasset不要testで確認。実3 deck証跡は未取得 | `VERIFIED_LOCAL` | [#194](https://github.com/Tao-pyth/ygo-effect-dsl/issues/194) |
| `VAL-026` | operator walkthrough | editable install/import、doctor/bootstrap/verify、inline/YDK preflight、Search artifact commit、fresh Replay、owned cache復旧、diagnostic routingを現CLIへ同期。既存cacheで10-node inline Search/Replayを手順どおり実行 | `VERIFIED_LOCAL` | [#143](https://github.com/Tao-pyth/ygo-effect-dsl/issues/143) |

## Verification commands used

```powershell
python -m ygo_effect_dsl ocgcore-doctor
python -m ygo_effect_dsl ocgcore-verify
python -m ygo_effect_dsl ocgcore-assets-verify
python -m ygo_effect_dsl ocgcore-lua-qualify --out docs/ocgcore/evidence/lua_load_qualification.json
python -m ygo_effect_dsl experiment-search examples/experiments/general_search_inline.yaml --out <temp>/best.route.yaml --search-report <temp>/report.json
python -m ygo_effect_dsl experiment-replay examples/experiments/general_search_inline.yaml <temp>/best.route.yaml
python -m ygo_effect_dsl real-deck-qualify --experiment short=<external>/short.yaml --experiment long=<external>/long.yaml --experiment grave_banish=<external>/grave-banish.yaml --artifact-root <external>/raw --index-out <sanitized-index>.json
python -m ygo_effect_dsl ocgcore-decision-corpus --route <external>/short.route.yaml --route <external>/long.route.yaml --route <external>/grave-banish.route.yaml --out <sanitized-decision-corpus>.json
python -m ygo_effect_dsl prototype-real-stress --out <external>/worker-failure-acceptance.json --pool-sizes 1,2,4 --tasks 4
```

`VAL-006`のlocal smoke結果は`nodes=10`、`replays=10`、`worker_invocations=10`、`worker_retries=0`、terminationは`max_nodes`だった。これは接続確認であり、成功predicate達成率やproduction性能の証拠には使用しない。

`VAL-013`のlocal stressは`semantic_report_id=realcorestress_a6868c199d651249f3cf4ff0d79978b61f3c8bebca0f233666698965d722a4cf`、`task_count=4`で、`all_failure_categories_observed`、`callback_native_path_observed`、`completion_order_independent`、`pool_independent_route_replay_ids`、`pool_independent_semantic_result`、`process_cleanup_observed`、`recovered_once`、`replacement_process_isolated`、`retry_exhaustion_failed`、`retry_seed_and_slot_stable`がすべてtrueだった。これはworker障害acceptanceのlocal evidenceであり、10万node性能校正`VAL-012`の代替ではない。

`VAL-010`のlocal fixture evidenceは`corpus_id=decisioncorpus_4320f03495f29e9eb79c7489321ddd5c4529c1a812b2ae425f10de010fea9103`、5 Route、63 decision caseで、required 7 categoryがcompleteである。これは固定fixtureのcodec/taxonomy coverageであり、外部3 deck一般性の証明ではない。

`VAL-009`のlocal evidenceは`qualification_id=luaqualification_2d42852ce777de439c149bffc28e347210cebeef31db0b1cce7b219a28acc17a`、official 12,702 script、7 fresh worker、native failure 0、helper 26件、最大worker peak RSS 84,602,880 bytesである。BabelCDB coverageは12,582件で、DB行のない120件はscript-only load確認に限定し、通常deckの利用可能cardとは扱わない。persistent resolver indexは性能不足による未実装ではなく、live path identity検査を維持するため明示的に不採用とした。

`VAL-026`のlocal walkthrough runは10 node/10 Replay、Route `route_1413fc434d81c8259cc2e512e0e2b869289fa802e09306c163027385a8b01246`、terminal State `state_5619746ab2aca3662c747ca7fddb9e269261ae3c58b2bc59f9bee5070f89764a`でfresh Replay一致を確認した。success predicateはfalseであり、接続・artifact整合のsmokeをdeck品質証跡へ拡大解釈しない。

## Update rule

各`OPEN/BLOCKED`項目は、Issueに再現手順、raw evidence、環境manifest、結論を保存した後にのみstatusを変更する。asset lockやdefault policyを先に変更して不確定事項を解消済み扱いにしてはならない。
