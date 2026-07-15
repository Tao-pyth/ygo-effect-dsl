# Release Validation Register

Status: Active verification log

Last updated: 2026-07-15

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
| `VAL-007` | clean core bootstrap | `ocgcore-clean-bootstrap-qualification-v1`で空root、同一root再実行、build/runtime partial復旧、独立root、download partial復旧の5 buildを検証。全回source/toolchain/API/size一致、manifest verify成功 | `VERIFIED_LOCAL` | [#136](https://github.com/Tao-pyth/ygo-effect-dsl/issues/136) |
| `VAL-008` | 任意deck一般性 | `deckqual_21dcdadd...`で外部short/long/grave-banishの3 deckを各2反復。YDK/inline、random/fixed/conditional hand、distinct deck hash、preflight、Random Search、fresh Replay、success/legal stop、長展開24 Action、墓地遷移を確認 | `VERIFIED_LOCAL` | [#139](https://github.com/Tao-pyth/ygo-effect-dsl/issues/139) |
| `VAL-009` | Lua load境界 | `ocgcore-lua-load-qualification-v1`でofficial 12,702件を7 fresh workerから全件native load。helper 26件の順序、cold/warm/fresh resolver同値性、negative probe、unsafe library無効を確認。BabelCDB欠落120件は通常preflightでfail-close | `VERIFIED_LOCAL` | [#140](https://github.com/Tao-pyth/ygo-effect-dsl/issues/140) |
| `VAL-010` | Message/Decision一般性 | 固定API 11.0全message registry、unknown ID fail-close、重複candidate拒否、Route decode/encode往復を実装。固定5 Routeと外部short/long/grave-banish 3 Routeの計106 caseで未知shapeなし、required 7 category complete | `VERIFIED_LOCAL` | [#141](https://github.com/Tao-pyth/ygo-effect-dsl/issues/141) |
| `VAL-011` | 妨害timing policy | `interruption-support-taxonomy-v1`でstandardだけをfixed-fixture scopeとして許可。damage step、simultaneous trigger、mandatory trigger、SEGOCは優先順位と昇格条件を固定し、未検証時はfail-close | `VERIFIED_LOCAL` | [#123](https://github.com/Tao-pyth/ygo-effect-dsl/issues/123), [#207](https://github.com/Tao-pyth/ygo-effect-dsl/issues/207)-[#210](https://github.com/Tao-pyth/ygo-effect-dsl/issues/210) |
| `VAL-012` | 10万node・実worker性能 | 外部qualification 3 Routeで10万logical nodeを再校正。480 fresh Replayを完走し、resolver reuse候補はmutation/isolation境界を保つ優位未証明として測定済み棄却 | `VERIFIED_LOCAL` | [#105](https://github.com/Tao-pyth/ygo-effect-dsl/issues/105), [#128](https://github.com/Tao-pyth/ygo-effect-dsl/issues/128), [#212](https://github.com/Tao-pyth/ygo-effect-dsl/issues/212) |
| `VAL-013` | worker障害 | version付きfrontier attempt/quarantine、retry exhaustion、structured Search failure、Route先行/report commit markerを実装。実core stress `realcorestress_a6868c...`でcrash/timeout/callback例外、pool 1/2/4、完了順独立、fresh replacement、全process終了を確認 | `VERIFIED_LOCAL` | [#142](https://github.com/Tao-pyth/ygo-effect-dsl/issues/142) |
| `VAL-014` | supported platform | `ocgcore-platform-contract-v1`でWindows x64、Python 3.10+、VS 2022 MSVCをsupportedとし、他OS/architectureをnative load前にfail-close | `VERIFIED_LOCAL` | [#135](https://github.com/Tao-pyth/ygo-effect-dsl/issues/135) |
| `VAL-015` | Beam/MCTS | interface接続点のみ。ordering、statistics、決定性、実装は未完了 | `OPEN` | [#145](https://github.com/Tao-pyth/ygo-effect-dsl/issues/145)-[#149](https://github.com/Tao-pyth/ygo-effect-dsl/issues/149) |
| `VAL-016` | PlayerView | `player-view-replay-v1`を実core fresh Replayから生成し、viewer 0/1のallowlist投影、private lineage分離、`information-access-audit-v2` canary検査、CLI atomic publishを確認 | `VERIFIED_LOCAL` | [#125](https://github.com/Tao-pyth/ygo-effect-dsl/issues/125), [#150](https://github.com/Tao-pyth/ygo-effect-dsl/issues/150), [#151](https://github.com/Tao-pyth/ygo-effect-dsl/issues/151) |
| `VAL-017` | analytics storage/UI | storage ADR、job recovery、query/comparison API、100万row UI校正は未完了 | `OPEN` | [#133](https://github.com/Tao-pyth/ygo-effect-dsl/issues/133) |
| `VAL-018` | license/asset distribution | root project licenseとBabelCDB等の再配布可否が未確定 | `BLOCKED` | [#91](https://github.com/Tao-pyth/ygo-effect-dsl/issues/91), [#169](https://github.com/Tao-pyth/ygo-effect-dsl/issues/169) |
| `VAL-019` | production operations | compatibility、upgrade/rollback、observability、incident、soakを未検証 | `OPEN` | [#127](https://github.com/Tao-pyth/ygo-effect-dsl/issues/127), [#134](https://github.com/Tao-pyth/ygo-effect-dsl/issues/134) |
| `VAL-020` | GitHub Actions runtime | checkout v7、setup-python v6、upload-artifact v7へ更新しNode 24対応。ephemeral runner v2.335.1のworkflow run 29380688844で実core smokeを完走 | `VERIFIED_REAL_CORE` | [#138](https://github.com/Tao-pyth/ygo-effect-dsl/issues/138), [#173](https://github.com/Tao-pyth/ygo-effect-dsl/issues/173) |
| `VAL-021` | Windows desktop architecture | Windows desktop要件は確定したが、shell、Python service/IPC、installer/update境界は未選定 | `OPEN` | [#181](https://github.com/Tao-pyth/ygo-effect-dsl/issues/181) |
| `VAL-022` | card detail/effect text | 現行real-core providerは`datas`表だけを読み、表示用`texts` provider、locale、license/fallback契約は未実装 | `OPEN` | [#183](https://github.com/Tao-pyth/ygo-effect-dsl/issues/183), [#91](https://github.com/Tao-pyth/ygo-effect-dsl/issues/91) |
| `VAL-023` | real-core State dedup | `SearchFrontier v2`でstate completenessを明示し、`query_api_projection`による枝削除を禁止。synthetic exact/projection回帰と実core frontier宣言を検証 | `VERIFIED_LOCAL` | [#192](https://github.com/Tao-pyth/ygo-effect-dsl/issues/192) |
| `VAL-024` | fresh Replay success artifact | SearchRunと共通のExperiment digest、Route/State/manifest/scenario/runtime/Lua identityを結ぶ`fresh-replay-verification-v1`を一意tempからatomic保存。general-search実core CLIとWindows並行writerで確認 | `VERIFIED_LOCAL` | [#193](https://github.com/Tao-pyth/ygo-effect-dsl/issues/193) |
| `VAL-025` | 外部3 deck qualification harness | `real-deck-qualification-index-v2`、全profileのsuccess/legal stop、外部path制約、2回反復、profile witness、distinct deck hash、custom fixture/妨害拒否、atomic sanitized indexを確認。実行済みindexは`docs/ocgcore/evidence/real_deck_qualification.json` | `VERIFIED_LOCAL` | [#194](https://github.com/Tao-pyth/ygo-effect-dsl/issues/194) / [#203](https://github.com/Tao-pyth/ygo-effect-dsl/issues/203) |
| `VAL-026` | operator walkthrough | editable install/import、doctor/bootstrap/verify、inline/YDK preflight、Search artifact commit、fresh Replay、owned cache復旧、diagnostic routingを現CLIへ同期。既存cacheで10-node inline Search/Replayを手順どおり実行 | `VERIFIED_LOCAL` | [#143](https://github.com/Tao-pyth/ygo-effect-dsl/issues/143) |

## Verification commands used

```powershell
python -m ygo_effect_dsl ocgcore-doctor
python -m ygo_effect_dsl ocgcore-verify
python -m ygo_effect_dsl ocgcore-assets-verify
python -m ygo_effect_dsl ocgcore-clean-bootstrap-qualify --work-root <external> --out docs/ocgcore/evidence/clean_bootstrap_qualification.json
python -m ygo_effect_dsl ocgcore-lua-qualify --out docs/ocgcore/evidence/lua_load_qualification.json
python -m ygo_effect_dsl experiment-search examples/experiments/general_search_inline.yaml --out <temp>/best.route.yaml --search-report <temp>/report.json
python -m ygo_effect_dsl experiment-replay examples/experiments/general_search_inline.yaml <temp>/best.route.yaml
python -m ygo_effect_dsl real-deck-qualify --experiment short=<external>/short.yaml --experiment long=<external>/long.yaml --experiment grave_banish=<external>/grave-banish.yaml --artifact-root <external>/raw --index-out <sanitized-index>.json
python -m ygo_effect_dsl ocgcore-decision-corpus --route <external>/short.route.yaml --route <external>/long.route.yaml --route <external>/grave-banish.route.yaml --out <sanitized-decision-corpus>.json
python -m ygo_effect_dsl prototype-real-stress --out <external>/worker-failure-acceptance.json --pool-sizes 1,2,4 --tasks 4
```

`VAL-006`のlocal smoke結果は`nodes=10`、`replays=10`、`worker_invocations=10`、`worker_retries=0`、terminationは`max_nodes`だった。これは接続確認であり、成功predicate達成率やproduction性能の証拠には使用しない。

`VAL-013`のlocal stressは`semantic_report_id=realcorestress_a6868c199d651249f3cf4ff0d79978b61f3c8bebca0f233666698965d722a4cf`、`task_count=4`で、`all_failure_categories_observed`、`callback_native_path_observed`、`completion_order_independent`、`pool_independent_route_replay_ids`、`pool_independent_semantic_result`、`process_cleanup_observed`、`recovered_once`、`replacement_process_isolated`、`retry_exhaustion_failed`、`retry_seed_and_slot_stable`がすべてtrueだった。これはworker障害acceptanceのlocal evidenceであり、10万node性能校正`VAL-012`の代替ではない。

`VAL-010`のlocal evidenceは`corpus_id=decisioncorpus_b134c9a8d6855ab39b11f36f7c3d00135a8c47a52ed125b865b69cdeb39e7fe4`、固定5 Routeと外部qualification 3 Routeの計8 Route、106 decision caseで、required 7 categoryがcompleteである。全caseでsource frame decodeとresponse encodeを再計算した。固定lockと代表corpusのMessage/Decision一般性を示すが、未実行カードや#123の未検証timing categoryを保証しない。

`VAL-012`のlocal evidenceは`benchmark_id=realreplaybench_0e34c19adba235cd1a1824aa7715b17a22a9692733edb61396a333e7398f2c42`である。外部qualification済みshort 8 Action、long 24 Action、grave/banish 11 Actionを各pool/persistence modeで16回、計480回fresh Replayし、全Route ID/terminal Stateとpool/mode不変性が一致した。mainとactive process treeの合計peakはpool 1/2/4/8/16で約209/356/633/1,164/2,216 MiBで、pool 16は旧logical上限を超え、long/graveではpool 8よりthroughputが低下した。このhostの`real-core-worker-policy-v1`はdefault 4、max 8、`real-core-memory-preflight-v1`は1.5 GiBとする。これは32 GiB Windows hostのlocal校正であり、他hostの性能保証ではない。

`VAL-009`のlocal evidenceは`qualification_id=luaqualification_2d42852ce777de439c149bffc28e347210cebeef31db0b1cce7b219a28acc17a`、official 12,702 script、7 fresh worker、native failure 0、helper 26件、最大worker peak RSS 84,602,880 bytesである。BabelCDB coverageは12,582件で、DB行のない120件はscript-only load確認に限定し、通常deckの利用可能cardとは扱わない。persistent resolver indexは性能不足による未実装ではなく、live path identity検査を維持するため明示的に不採用とした。

`VAL-007`のlocal evidenceは`qualification_id=corebootstrap_12a20bd0e3606d14d3fc597eb6a60aeca2e9ec1478430de73427a4d3298531d1`である。MSVC `14.44.35207`による5 buildは34.376〜45.601秒、binary size 1,306,624 bytes、session内SHA-256 `03e360cf694f5ac6ba686de1d3bec7ccde3f3233d01bfe3265884a18ce1b9028`で一致した。これは一つのWindows host上の単一session evidenceである。事前診断runでは同一入力から別hashも観測したため、cross-session/cross-host bit reproducibilityを一般化せず[#171](https://github.com/Tao-pyth/ygo-effect-dsl/issues/171)のrelease gateとして維持する。clean bootstrap完了は、固定source/toolchain/APIと各build固有hashをmanifestで検証でき、再実行・中断復旧できることを意味する。

`VAL-026`のlocal walkthrough runは10 node/10 Replay、Route `route_1413fc434d81c8259cc2e512e0e2b869289fa802e09306c163027385a8b01246`、terminal State `state_5619746ab2aca3662c747ca7fddb9e269261ae3c58b2bc59f9bee5070f89764a`でfresh Replay一致を確認した。success predicateはfalseであり、接続・artifact整合のsmokeをdeck品質証跡へ拡大解釈しない。

## Update rule

各`OPEN/BLOCKED`項目は、Issueに再現手順、raw evidence、環境manifest、結論を保存した後にのみstatusを変更する。asset lockやdefault policyを先に変更して不確定事項を解消済み扱いにしてはならない。
