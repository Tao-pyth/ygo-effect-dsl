# Package 0.6.0 Parallel Execution Contracts

Status: Planned contract; issues [#259](https://github.com/Tao-pyth/ygo-effect-dsl/issues/259), [#266](https://github.com/Tao-pyth/ygo-effect-dsl/issues/266), [#270](https://github.com/Tao-pyth/ygo-effect-dsl/issues/270)

Last updated: 2026-07-16

## 1. Execution model

parallel runtimeは`logical task`と`physical attempt`を区別する。logical taskはstrategy ordinal、semantic node ID、Action ID、Experiment digestから一意に決まり、worker slot、process ID、completion timestampをidentityへ含めない。physical attemptは同じlogical taskの初回実行またはretryであり、attemptごとにworker/process/failure evidenceを持つ。

coordinatorはtaskをbounded queueへdispatchし、完了結果を受信順ではなくstrategy別semantic commit orderへ並べる。logical taskは高々一度だけcommitできる。duplicate、late、unknown task resultは成功扱いせずstructured failureまたは明示discard evidenceにする。

## 2. Fresh Replay boundary

- 各taskはroot ExperimentとAction prefixからocgcoreへfresh Replayする。
- native duel handle、Lua VM、mutable query stateをprocess間で共有しない。
- prefix cacheはcontent-addressed verified hintであり、native snapshotではない。
- cache hit、retry、worker replacementでもReplay request/response signatureを再検証する。
- Pythonは合法性、カード効果、timing、chainを補完しない。

## 3. Strategy commit order

### Random Search

depth-first semantic orderを正本とし、dispatch window内の独立Replayだけを先行実行できる。RNGはseedとsemantic node IDから導出し、worker ID、pool size、completion orderを入力にしない。budget後に完了したtaskはstrategy stateへcommitせず、wasted physical workとして記録する。

### Beam Search

同一frontier layerの候補を並列実行し、layer ordinal、parent rank、Action ID順に全結果をcommitしてからwidth/tie ruleを適用する。部分layerを完全layerとしてpruneしてはならない。

### MCTS

simulation ordinal単位のdeterministic batchを使う。batch内は共通selection snapshotからdispatchし、ordinal順に一度だけbackpropagateする。virtual lossは採用せず、failed/retried simulationでvisit/valueを二重更新しない。

## 4. Budget and deadline

`max_nodes`、`max_replays`、`max_depth`はsemantic budgetであり、logical commit orderに従って消費する。physical attempt、retry、speculative/wasted Replayは別resource counterへ保存する。`max_seconds`はoperational deadlineであり、host loadやpool sizeの影響を受けるため、終了結果を`timing_censored`とする。

同じnode/replay/depth budgetのpool 1/2/4はsemantic digest、best Route、lineageが一致しなければならない。deadline runは再生可能prefixとcensor reasonを保存するが、pool determinismの完全一致証拠へ使用しない。

## 5. Pool and failure policy

- pool、queue、in-flight、dispatch windowには有限上限を持たせる。
- user指定poolがmemory preflightに違反する場合はsilent clampせず、rejectまたは明示serial fallbackにする。
- crash、timeout、broken pipe、malformed resultは既存`FailureRecord` taxonomyへ写像する。
- retryは同じlogical taskへ帰属し、attempt historyを削除しない。
- experiment abort時は未完了taskをbest-effort cancelし、成功aggregateを発行しない。
- process tree、handle、temporary artifactをSearchRun終了時に回収する。

## 6. Configuration contract

Experiment/API/CLI/desktopは同じversion付きpolicyを使用し、少なくともexecution mode、requested/effective pool、max in-flight、dispatch window、cache mode、memory limit、fallback behaviorを表す。旧Experimentでpolicyが省略された場合はserial-compatible defaultを使う。automatic pool selectionはpolicy versionとhardware/preflight evidenceをSearch reportへ保存する。

## 7. Required telemetry

Search reportは次をlogical/physicalに分けて記録する。

- requested/effective pool、queue depth、in-flight peak、worker utilization。
- logical、committed、physical、retried、speculative、wasted Replay count。
- queue wait、worker startup、core、decode、evaluation、cache、artifact write time。
- main/worker/process-tree RSS、I/O bytes、cache hit/eviction/lock wait。
- deadline censor、cancel、failure、fallback、worker replacement reason。

canonical semantic digestはtimestamp、PID、worker slot、completion orderのような非semantic fieldを含めない。

## 8. Release claim

parallel optionが動くことだけでは`0.6.0`完了にならない。[#273](https://github.com/Tao-pyth/ygo-effect-dsl/issues/273)の同一host benchmarkで、pool 4がpool 1に対して3 fixture中2件以上25%短縮し、全fixtureで10%超の悪化がなく、node/replay budgetのsemantic結果が一致した場合に限り、探索時間短縮をrelease claimにできる。
