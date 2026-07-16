# Roadmap

Status: Package `0.5.0` Windows desktop analytics source milestone released / `0.5.1` active / `0.6.0` parallel-search planned / `0.7.0` research-dashboard planned

Last updated: 2026-07-16

## 1. Version model

package/CLIの現行releaseは`0.5.0`、対応tagは`v0.5.0`である。`0.4.0`はSearch/PlayerView実装stageとして完了したが独立tagを作らず、累積`0.5.0`へ収録した。`0.5.1`はactive maintenance、`0.6.0`はplanned parallel-search release、`0.7.0`はplanned evidence-driven research-dashboard release、`1.0.0`はplanned stable production milestoneである。package versionは配布物全体のSemVer、schema/contract versionは保存形式とAPIの互換境界として独立管理する。

| 領域 | 現行version | 現在の位置付け |
|---|---|---|
| Package / CLI | `0.5.0` | 実core探索、PlayerView、Windows desktop、corpus analyticsのsource milestone |
| Project identity | `project-identity-v1` | repository、Python import、CLI、製品説明の安定名 |
| Experiment | `0.4` | 現行scenario/search入力。`0.3b`は実行互換、`0.3a`は読み取り・migration入力 |
| Scenario | `scenario-v1` / `scenario-manifest-v1` / `scenario-preflight-v1` | fixed/inline/YDK、初手、asset/card/script事前検査 |
| Decision / Action / Replay | `0.3a` / `ygo-replay-manifest-v1` / `fresh-replay-verification-v1` | core request、選択、fresh Replayと成功証跡の基礎契約 |
| Route DSL | `0.1` / `route-normalization-v2` | 探索Routeの交換・再生形式 |
| Information boundary | `information-policy-v1` / `information-audit-v1` | 探索・評価の参照可能情報とaccess証跡 |
| State identity | `ygo-state-id-v1` / `ygo-rule-state-v1` / `ygo-visibility-state-v1` | exact dedup、ルール状態、可視性状態 |
| Evaluation | `evaluation-result-v1` / `score-breakdown-v1` / `route-resource-consumption-v1` | 成功、盤面score、資源消費。位置別terminal preferenceは`0.7.0`でcontract決定後にversion付与 |
| Search | `search-executor-v5` / `search-frontier-v2` / `search-run-result-v5` / `search-strategy-evidence-v1` / `search-run-report-v1` / `search-run-failure-v2` / `search-artifact-commit-v1` / `random-search-strategy-v1` / `beam-search-strategy-v1` / `mcts-strategy-v1` | state completeness、structured failure、atomic commit付きRandom、層単位Beam、直列semantic update MCTSが実動。node-level poolは`0.6.0`計画 |
| Real core | `real-core-frontier-v2` / `real-core-worker-failure-v1` / `real-core-frontier-worker-attempt-v1` / `real-core-frontier-worker-failure-v1` | ocgcore API 11.0のfresh worker Replay、state completeness、retry/quarantine evidence |
| Core bootstrap qualification | `ocgcore-clean-bootstrap-qualification-v1` | 空root・再実行・build/download中断復旧の5 build local evidence。再現buildは#171 |
| Real-deck qualification | `real-deck-qualification-index-v2` | 全profileでsuccess/legal stopを要求する外部short/long/grave-banish deckの反復証跡とsanitized index |
| Lua load qualification | `ocgcore-lua-load-qualification-v1` | official 12,702 scriptのresolver/native load証跡。CDB欠落120件はfail-close |
| Specified interruption | `core-interruption-candidate-policy-v1` / `interruption-support-taxonomy-v1` | core提示candidateだけを使う妨害分岐 |
| Storage / aggregation | `raw-event-log-v1` / `run-catalog-v2` / `aggregation-v1` | JSONL、run catalog、optional Parquet集計 |
| Runtime lock | `ocgcore-v11.0-win-x64-msvc-v1` | commit/tree/API/build入力を固定 |
| Asset lock | `ocgcore-assets-202504-v1` | CardScripts/BabelCDBのcommit/tree/file hashを固定 |
| Benchmark policy | `general-search-benchmark-v1` / `real-core-benchmark-base-routes-v2` / `cache-worker-policy-v2` / `memory-preflight-v2` | 外部qualification 3 Routeの10万logical node校正 |
| Real Replay policy | `real-core-replay-benchmark-v1` / `real-core-worker-policy-v1` / `real-core-memory-preflight-v1` | pool 1/2/4/8/16の480 fresh Replay、既定4・最大8・1.5 GiB preflight |
| Resolver index policy | `resolver-index-policy-v1` | asset mutation検査を維持し、cross-process/resident reuseをv0.3では棄却 |
| Real-core platform | `ocgcore-platform-contract-v1` / `ocgcore-doctor-v2` | Windows x64、Python 3.10+、VS 2022 MSVCのみsupported |
| Research dashboard | package `0.7.0` planned、contract version未予約 | real result、terminal preference、Route randomness、fresh Replay、Top-K/coverageを統合 |

versionの詳細正本は[release stage index](spec/00_release_stage_index.md)、未確定事項は[validation register](spec/00_validation_register.md)とする。

## 2. Implemented baseline

`0.5.0`には`0.3.0`のreal-core qualificationを維持した上で次が存在する。

- project-owned ocgcore/CardScripts/BabelCDB bootstrap、hash検証、runtime network禁止
- official CardScripts 12,702件のfresh-worker native load、helper順序、resolver cache同値性のlocal qualification
- ocgcore API 11.0のlifecycle、callback、Message decode、Action response、State query
- Experiment `0.4`のinline/YDK、fixed/random/conditional hand、manifest、preflight
- `RealCoreFrontierAdapter`、決定論的Random Search、budget、STOP_LINE、best Route tie-break
- 指定妨害候補とsupport taxonomyの基礎契約
- Route DSL出力とfresh Replay、JSONL/catalog/optional Parquet evidence
- Random/Beam/MCTS、PlayerView、複数妨害、後攻、複数turn、duel-end frontier
- corpus provenance、job recovery、query/comparison、Parquet lifecycle、versioned export
- deck-first Windows desktop、card presentation、real-core search worker、virtualized table
- 10万run、100万Event/Decision row、10万aggregation rowのscale evidence

2026-07-14に既存lock済みassetで10 nodeの`experiment-search`とbest Routeの`experiment-replay`を実行し、実ocgcore/EDOPro Luaのend-to-end動作を確認した。同日に空root、再実行、build/runtime partial、独立root、download partialの5 build clean-bootstrap qualificationも完了した。さらに外部short/long/grave-banishの3 deckをYDK/inlineとrandom/fixed/conditional handで各2反復し、sanitized evidence `deckqual_21dcdadd...`を取得した。2026-07-15には固定5 Routeと外部3 Routeの106 Decisionをround-tripし、外部corpusで未知shapeがないことも確認した。同じ外部3 Routeをbase v2へ固定して10万logical nodeを再校正し、pool 1/2/4/8/16、persistence disabled/index-onlyの計480 fresh Replayも完走した。任意deckの代表corpusと実worker local performance gateは通過したが、未実行カード、競技デッキ全般、他host性能を保証しない。single-sessionのDLL hash一致をcross-host再現buildへ一般化せず、#171を維持する。

## 3. Release stages

実装stageの依存順は`0.3.0 → 0.4.0 → 0.5.0 → 0.5.1 → 0.6.0 → 0.7.0 → 1.0.0`とする。`0.4.0`は独立package tagを作らず`0.5.0`へ累積収録した。後続stageは前段のrelease gateを弱めてはならない。

| Package目標 | 主目的 | 親Issue | 詳細spec | 完了判定の要点 |
|---|---|---|---|---|
| `0.3.0` | 実ocgcore/EDOPro Lua統合と任意deck・性能のqualification | [#131](https://github.com/Tao-pyth/ygo-effect-dsl/issues/131) | [v0.3.0](spec/v0.3.0/00_scope.md) | clean bootstrap、3 real deck、fail-close、実worker 10万node、決定性 |
| `0.4.0` | Beam/MCTS、PlayerView、複数妨害、後攻・複数turn | [#132](https://github.com/Tao-pyth/ygo-effect-dsl/issues/132) | [v0.4.0](spec/v0.4.0/00_scope.md) | strategy適合、private情報非漏洩、lineage相互検証 |
| `0.5.0` | deck-first Windows desktop UI、大規模corpus、比較API、統計、長時間job | [#133](https://github.com/Tao-pyth/ygo-effect-dsl/issues/133) | [v0.5.0](spec/v0.5.0/00_scope.md) | deckから探索実行、card detail、job復旧、10万run/100万row、CLI/API/UI一致 |
| `0.5.1` | 検証profile再編、test時間・CI負荷・agent出力削減 | [#236](https://github.com/Tao-pyth/ygo-effect-dsl/issues/236) | [v0.5.1](spec/v0.5.1/00_scope.md) | release検証範囲を維持し、同一host wall timeと成功時log量を測定削減 |
| `0.6.0` | 決定論的node-level並列探索と実測探索時間短縮 | [#258](https://github.com/Tao-pyth/ygo-effect-dsl/issues/258) | [v0.6.0](spec/v0.6.0/00_scope.md) | pool 1互換、pool 1/2/4 semantic一致、3 fixture中2件以上25%短縮、bounded resource |
| `0.7.0` | 実成果物、位置別評価、Route randomness、Replayを統合する研究dashboard | [#276](https://github.com/Tao-pyth/ygo-effect-dsl/issues/276) | [v0.7.0](spec/v0.7.0/00_scope.md) | synthetic隔離、immutable profile、randomness provenance、fresh Replay、best-observed/coverage |
| `1.0.0` | stable compatibility、license、配布、security、運用 | [#134](https://github.com/Tao-pyth/ygo-effect-dsl/issues/134) | [v1.0.0](spec/v1.0.0/00_scope.md) | 法務承認、再現build、upgrade/rollback、soak、release provenance |

`0.5.0`の実装項目、local scale gate、package version、source tagは2026-07-16に完了した。10万run、100万Event/Decision row、10万aggregation rowのevidenceに基づき、export hard capは100,000行へ校正した。一般配布・production保証は`1.0.0`の#91/#134まで行わない。

## 4. Package 0.5.0 completion record

`0.5.0`は#132/#133の実装stageを累積し、Random/Beam/MCTS、PlayerView、指定妨害、複数turn、corpus/job/query/comparison、Parquet lifecycle、Windows desktop、export、scale evidenceを同一source milestoneへ固定した。release完了時点では未検証timing category #207-#210、node-level pool/cache #231、localized presentation #247を成功扱いせず`1.0.0`へ移動した。その後2026-07-16の計画変更で#231だけを`0.6.0`へ再割当し、license/distribution/production項目は`1.0.0`に維持した。CHANGELOG、package metadata、README、roadmap、governance、tagを`0.5.0`へ同期し、third-party assetsを成果物へ含めない。

## 5. Package 0.6.0 planned path

`0.6.0`は独立parallel contractを実SearchExecutorへ接続し、速度改善をsemantic不変性と同時に検証する。親Issueは[#258](https://github.com/Tao-pyth/ygo-effect-dsl/issues/258)で、GitHub上でも次の17件をsub-issueとして管理する。

1. [#259](https://github.com/Tao-pyth/ygo-effect-dsl/issues/259)、[#260](https://github.com/Tao-pyth/ygo-effect-dsl/issues/260)、[#266](https://github.com/Tao-pyth/ygo-effect-dsl/issues/266)、[#269](https://github.com/Tao-pyth/ygo-effect-dsl/issues/269)でcontract、serial bottleneck、budget/deadline、memory policyを先に固定する。
2. [#261](https://github.com/Tao-pyth/ygo-effect-dsl/issues/261)、[#262](https://github.com/Tao-pyth/ygo-effect-dsl/issues/262)、[#231](https://github.com/Tao-pyth/ygo-effect-dsl/issues/231)でtask-oriented frontier、入力policy、bounded coordinatorを接続する。
3. [#267](https://github.com/Tao-pyth/ygo-effect-dsl/issues/267)、[#270](https://github.com/Tao-pyth/ygo-effect-dsl/issues/270)でfailure/cancel/retryとtelemetryを共通化する。
4. [#263](https://github.com/Tao-pyth/ygo-effect-dsl/issues/263)、[#264](https://github.com/Tao-pyth/ygo-effect-dsl/issues/264)、[#265](https://github.com/Tao-pyth/ygo-effect-dsl/issues/265)、[#268](https://github.com/Tao-pyth/ygo-effect-dsl/issues/268)でRandom、Beam、MCTS、verified prefix cacheを個別接続する。
5. [#272](https://github.com/Tao-pyth/ygo-effect-dsl/issues/272)、[#271](https://github.com/Tao-pyth/ygo-effect-dsl/issues/271)でconcurrency matrixとWindows desktop操作を検証する。
6. [#273](https://github.com/Tao-pyth/ygo-effect-dsl/issues/273)で3 fixture × pool 1/2/4/8の100,000 logical-node evidenceを作り、[#274](https://github.com/Tao-pyth/ygo-effect-dsl/issues/274)でsource release gateを閉じる。

performance gateは、同一host・同一node/replay budgetのwarm runでpool 4がpool 1より3 fixture中2件以上25%短く、全fixtureで10%超の悪化がなく、semantic digest、best Route、lineageが一致することである。wall-clock deadlineはpool依存の`timing_censored`結果として分離する。未達ならparallel modeを既定にせず、探索時間短縮済みreleaseとして完了扱いにしない。

## 6. Package 0.7.0 planned path

`0.7.0`は`0.5.0`のWindows desktopと`0.6.0`のbounded parallel Searchを、結果の真正性と利用者定義評価を備えた研究workbenchへ接続する。親Issueは[#276](https://github.com/Tao-pyth/ygo-effect-dsl/issues/276)で、30件をGitHub sub-issueとして管理する。

1. [#277](https://github.com/Tao-pyth/ygo-effect-dsl/issues/277)-[#282](https://github.com/Tao-pyth/ygo-effect-dsl/issues/282)でterminal projection、immutable profile、Route gameplay randomness、ranking、result/verification、coverage/checkpoint契約を固定する。
2. [#283](https://github.com/Tao-pyth/ygo-effect-dsl/issues/283)-[#288](https://github.com/Tao-pyth/ygo-effect-dsl/issues/288)でprofile catalog/evaluator/APIとauthoritative randomness/rankingを実装する。
3. [#289](https://github.com/Tao-pyth/ygo-effect-dsl/issues/289)-[#293](https://github.com/Tao-pyth/ygo-effect-dsl/issues/293)でverified artifact service、独立fresh Replay、Top-K/candidate evidence、frontier exhaustion、logical resumeを実装する。
4. [#294](https://github.com/Tao-pyth/ygo-effect-dsl/issues/294)-[#302](https://github.com/Tao-pyth/ygo-effect-dsl/issues/302)でreal result、Action/board/score、profile/scenario input、job monitor、Replay、Top-K、conditioned analyticsをdesktopへ接続する。
5. [#303](https://github.com/Tao-pyth/ygo-effect-dsl/issues/303)でNeuron公式accessを調査し、非公式scrapingを行わず採否を決める。
6. [#304](https://github.com/Tao-pyth/ygo-effect-dsl/issues/304)-[#306](https://github.com/Tao-pyth/ygo-effect-dsl/issues/306)でcompatibility、real-core workflow、desktop quality、source release gateを完了する。

UIの直近presetは先攻初期盤面構築とし、後攻盤面と複数turnリレーを追加しない。profileはcard code、controller、location、position、count、signed integer weightを保持し、Routeはgameplay randomnessをopening-hand/Search/worker randomnessから分離する。結果はcoverage証明がない限り`best observed`であり、node上限なしmodeは提供しない。代表カードによるvariant代替とcost-card modeは採用せず、ユーザー負担と具体scenario検証件数の均衡は独立modeではなく継続的な設計制約として扱う。詳細は[ADR-0017](adr/0017_v07_research_dashboard_evaluation_and_reliability.md)、[ADR-0018](adr/0018_reject_representative_and_cost_card_modes.md)、[evaluation/randomness/result contracts](spec/v0.7.0/10_evaluation_randomness_and_result_contracts.md)、[research dashboard workflow](spec/v0.7.0/15_research_dashboard_workflow.md)を正本とする。

## 7. Package 0.3.0 completion record

`0.3.0`は次のcritical pathを完了し、ADR 0014でcontract/defaultを確定した。

1. [#135](https://github.com/Tao-pyth/ygo-effect-dsl/issues/135)でsupported platform/toolchainを確定する。
2. [#136](https://github.com/Tao-pyth/ygo-effect-dsl/issues/136)で空cacheからocgcoreを取得・build・verifyし、5 build local qualificationを完了した。
3. [#137](https://github.com/Tao-pyth/ygo-effect-dsl/issues/137)でBabelCDBのtag/固定commit差異を解決し、asset clean bootstrapを証明する。
4. [#140](https://github.com/Tao-pyth/ygo-effect-dsl/issues/140)と[#141](https://github.com/Tao-pyth/ygo-effect-dsl/issues/141)でLua/Message/Decision境界をfail-close検証し、official Lua全件loadと外部3 deckを含む106 Decision caseを完了した。
5. [#139](https://github.com/Tao-pyth/ygo-effect-dsl/issues/139)で短展開・長展開・墓地/除外の3 deckをpreflightからReplayまで通し、`deckqual_21dcdadd...`として完了した。
6. [#142](https://github.com/Tao-pyth/ygo-effect-dsl/issues/142)、[#105](https://github.com/Tao-pyth/ygo-effect-dsl/issues/105)、[#128](https://github.com/Tao-pyth/ygo-effect-dsl/issues/128)でworker障害と10万node実測を完了する。
7. [#138](https://github.com/Tao-pyth/ygo-effect-dsl/issues/138)と[#143](https://github.com/Tao-pyth/ygo-effect-dsl/issues/143)でself-hosted smokeと利用手順を固定する。
8. [#144](https://github.com/Tao-pyth/ygo-effect-dsl/issues/144)と[ADR 0014](adr/0014-v03-release-contract-and-defaults.md)でcontract versionとdefault policyを決める。

asset lock、第三者asset、default performance policyは、対応する検証Issueとreviewを経ずに変更しない。upstream version変更時だけ再実行する[#117](https://github.com/Tao-pyth/ygo-effect-dsl/issues/117)は関連監査であり、通常の`0.3.0`完了条件には含めない。

## 8. Release rules

- 新しいstrategyは専用contract versionを追加する。既存schemaの必須fieldや意味を変える場合だけschemaをversion upする。
- Pythonはカード効果、合法性、timing、chain処理を推測しない。真実源は固定したocgcore/EDOPro Luaとする。
- unknown Message、candidate、Lua、asset不一致、Replay divergenceはfail-closeする。
- native duel handle/Lua stateをcacheやprocess間で共有しない。cache hitでもfresh Replayする。
- node/replay/depth budgetのsemantic結果はpool size、worker完了順、retryに依存させない。wall-clock deadlineはtiming-censoredとして別扱いにする。
- parallel既定値は同一hostのserial比較、semantic一致、memory preflightを満たしたversion付きevidenceなしに変更しない。
- real job resultはcommit済みartifactだけを使用し、synthetic preview、未検証Replay、coverage未証明をreal/verified/optimalと表示しない。
- terminal preference、randomness、rankingはversion付きidentityを保存し、legacy Route/SearchRunを黙って再解釈しない。
- gameplay randomnessはcore由来evidenceだけで判定し、Search RNG、worker順序、effect text推測を混入しない。
- third-party core/assetsをwheel、sdist、executable、CI artifactへ同梱しない。
- `#91`完了前に一般公開distributionを行わない。
- 各releaseは全test、必要なmanual/self-hosted evidence、commit、push、PR、CI、merge、`main`同期、tag/changelog整合を完了してから宣言する。

## 9. Explicit non-goals

- Python製カード効果エンジン
- 一般deckの最適性証明または完全な相手AI
- 勝率予測
- オンライン対戦クライアント
- third-party assetの無審査配布
- 実測根拠のないnative snapshot/cloneまたはdistributed worker導入
