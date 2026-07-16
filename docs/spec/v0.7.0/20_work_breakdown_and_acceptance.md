# Package 0.7.0 Work Breakdown and Acceptance

Status: Issue-backed plan

Last updated: 2026-07-16

Parent: [#276](https://github.com/Tao-pyth/ygo-effect-dsl/issues/276)

## Work items

| Order | Issue | Deliverable | Acceptance evidence |
|---|---|---|---|
| 1 | [#277](https://github.com/Tao-pyth/ygo-effect-dsl/issues/277) | terminal-board projection/card predicate contract | location/position/count/redaction vectors |
| 2 | [#278](https://github.com/Tao-pyth/ygo-effect-dsl/issues/278) | immutable terminal preference profile | digest、clone-on-edit、compatibility matrix |
| 3 | [#279](https://github.com/Tao-pyth/ygo-effect-dsl/issues/279) | Route gameplay-randomness taxonomy | domain separation、direct evidence、unknown policy |
| 4 | [#280](https://github.com/Tao-pyth/ygo-effect-dsl/issues/280) | preference/reliability ranking policy | stable order、penalty、strict deterministic vectors |
| 5 | [#281](https://github.com/Tao-pyth/ygo-effect-dsl/issues/281) | truthful result/verification/optimality states | synthetic isolation、best-observed、mismatch rules |
| 6 | [#282](https://github.com/Tao-pyth/ygo-effect-dsl/issues/282) | bounded coverage/checkpoint/adaptive budget contract | censor、resume identity、hard limits |
| 7 | [#283](https://github.com/Tao-pyth/ygo-effect-dsl/issues/283) | evaluation-profile catalog | atomic CRUD、dedup、migration |
| 8 | [#284](https://github.com/Tao-pyth/ygo-effect-dsl/issues/284) | location-aware terminal evaluator | matched-instance score breakdown |
| 9 | [#285](https://github.com/Tao-pyth/ygo-effect-dsl/issues/285) | Experiment/CLI/API profile binding | digest round-trip、preflight、legacy input |
| 10 | [#286](https://github.com/Tao-pyth/ygo-effect-dsl/issues/286) | authoritative gameplay-randomness capture | real-core event/Action/seed evidence |
| 11 | [#287](https://github.com/Tao-pyth/ygo-effect-dsl/issues/287) | Route/SearchRun randomness persistence | summary recomputation、Replay identity、redaction |
| 12 | [#288](https://github.com/Tao-pyth/ygo-effect-dsl/issues/288) | reliability-aware ranking implementation | pool/order/retry equality、legacy policy regression |
| 13 | [#289](https://github.com/Tao-pyth/ygo-effect-dsl/issues/289) | verified job-artifact result service | ownership/path/hash/schema failure vectors |
| 14 | [#290](https://github.com/Tao-pyth/ygo-effect-dsl/issues/290) | independent fresh-Replay jobs | verified/mismatch/failure atomic artifacts |
| 15 | [#291](https://github.com/Tao-pyth/ygo-effect-dsl/issues/291) | Top-K/candidate/path evidence | count reconciliation、bounded pagination |
| 16 | [#292](https://github.com/Tao-pyth/ygo-effect-dsl/issues/292) | bounded frontier exhaustion | small exhaustive corpus、coverage certificate |
| 17 | [#293](https://github.com/Tao-pyth/ygo-effect-dsl/issues/293) | logical checkpoint/resume/adaptive budget | split-vs-whole semantic equality、drift rejection |
| 18 | [#294](https://github.com/Tao-pyth/ygo-effect-dsl/issues/294) | real result dialog | two-job artifact hydration、no fixture fallback |
| 19 | [#295](https://github.com/Tao-pyth/ygo-effect-dsl/issues/295) | Action/board/score/termination renderer | card-level Route inspection、best-observed label |
| 20 | [#296](https://github.com/Tao-pyth/ygo-effect-dsl/issues/296) | terminal preference profile editor | hand/field/set/grave rules、clone-on-edit |
| 21 | [#297](https://github.com/Tao-pyth/ygo-effect-dsl/issues/297) | conditional hand/evaluator/success UI | impossible condition、qualified preset、cohort provenance |
| 22 | [#298](https://github.com/Tao-pyth/ygo-effect-dsl/issues/298) | inline deck/interruption UI | typed bridge、deck diagnostics、taxonomy rejection |
| 23 | [#299](https://github.com/Tao-pyth/ygo-effect-dsl/issues/299) | real job/coverage/reliability monitor | logical/physical metrics、censor and cancel states |
| 24 | [#300](https://github.com/Tao-pyth/ygo-effect-dsl/issues/300) | Replay verification UI | independent lifecycle、difference drill-down |
| 25 | [#301](https://github.com/Tao-pyth/ygo-effect-dsl/issues/301) | Top-K/candidate/path drill-down | report parity、virtualization、navigation |
| 26 | [#302](https://github.com/Tao-pyth/ygo-effect-dsl/issues/302) | conditioned deck/run analytics | cohort separation、lineage comparison、export parity |
| 27 | [#303](https://github.com/Tao-pyth/ygo-effect-dsl/issues/303) | Neuron official-access decision | dated sources、terms/auth/privacy、YDK fallback |
| 28 | [#304](https://github.com/Tao-pyth/ygo-effect-dsl/issues/304) | contract/migration conformance suite | matrix、property/golden/fault vectors、legacy regression |
| 29 | [#305](https://github.com/Tao-pyth/ygo-effect-dsl/issues/305) | real-core dashboard qualification | end-to-end artifacts、screenshots、a11y/security/resource |
| 30 | [#306](https://github.com/Tao-pyth/ygo-effect-dsl/issues/306) | documentation/source release | CI、package audit、tag/changelog/milestone parity |

## Dependency order

```text
#277 terminal projection -> #278 profile -> #283 catalog -> #284 evaluator -> #285 API
#279 randomness -> #286 capture -> #287 persistence -> #280/#288 ranking
#281 result truth -> #289 artifact service -> #294/#295 real result
#290 Replay service -> #300 verification UI
#291 search evidence -> #301 drill-down -> #302 analytics
#282 coverage/resume -> #292 exhaustion + #293 checkpoint/adaptive -> #299 monitor
#296/#297/#298 scenario/profile UI after shared backend contracts
all paths -> #304 conformance + #305 real-core qualification -> #306 release
```

[#289](https://github.com/Tao-pyth/ygo-effect-dsl/issues/289)と[#294](https://github.com/Tao-pyth/ygo-effect-dsl/issues/294)は、実job結果を固定synthetic表示から切り離すtrust gateとして他のdesktop拡張より先に完了する。profile UIはprofile catalog/evaluator、randomness表示はRoute event persistence、Top-K UIはbounded reportを先行条件とする。

## Gate A: artifact truth and Replay

- real jobのresult viewはcommit済みRoute/reportだけを使用する。
- path、hash、schema、Experiment、Route、SearchRun、profile、ranking、randomness identityを検証する。
- synthetic previewはreal job namespace、export、verificationへ入らない。
- fresh Replayは別worker/jobで実行し、一致時だけverifiedになる。
- mismatch、replay failure、artifact corruption、quarantineを成功扱いにしない。

## Gate B: terminal preference

- hand、face-up monster、set spell/trap、graveyardの位置別ruleを同じcard codeへ設定できる。
- once、per-copy、threshold、positive/negative integer weightを再計算できる。
- profileはimmutable digestを持ち、run後の編集で過去scoreが変わらない。
- base、preference、random penalty、compositeを分離表示する。
- profileが異なるrunをanalyticsでsilent mergeしない。

## Gate C: randomness and ranking

- opening-hand sampling、Search RNG、worker orderをgameplay randomnessへ含めない。
- core由来eventとRoute stepを照合し、unknown probabilityを推測しない。
- replay determinismとgameplay stochasticityを分離する。
- default policyはsuccess/scoreを保った上で非random Routeを優先し、strict modeを別指定する。
- pool、completion order、retry、cacheでrank、Top-K、best Routeを変えない。

## Gate D: explainability and long search

- ResultはAction、terminal board、score、termination、Top-K、candidate/path evidenceを表示する。
- 未探索、pruned、failed、censored、不合法を区別する。
- frontier exhaustedにはcomplete candidate/frontier accountingとcoverage certificateを要求する。
- checkpoint/resumeはpending frontierとstrategy stateを保存し、job progress metadataで代用しない。
- node無制限を提供せず、time/RSS/disk/Replay/frontier hard limitを維持する。

## Gate E: desktop and analytics

- conditional hand、qualified evaluator/success、inline deck、specified interruptionをtyped serviceへ接続する。
- starting-player toggleとmulti-turn inputは追加せず、先攻初期盤面presetを維持する。
- job monitorはattempt数をReplay数として表示せず、実logical/physical metricを使用する。
- conditional/fixed/random、partial/failed/censored、profile versionをcohortで分離する。
- 1440×900、960×700、760×900、keyboard、high contrast、reduced motion、CSP/path/redactionを検証する。

## Release rejection conditions

- real jobに固定Route、score、Action、verified labelを表示する。
- legacy Routeのrandomness欠落をdeterministicと解釈する。
- card effect textからlocation、legality、random probabilityをPythonが推測する。
- profile編集が既存Experiment/SearchRunのscoreを変更する。
- scoreに関係なく全stochastic Routeをdefaultで無条件に下位へ落とす。
- resource-censored runをfrontier exhaustedまたはoptimalと表示する。
- Neuron非公式scraping、third-party asset同梱、一般distributionをrelease条件にする。
