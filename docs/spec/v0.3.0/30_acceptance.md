# Package 0.3.0 Acceptance and Release Gate

Status: Mandatory gate

Last updated: 2026-07-14

## Gate A: environment and clean acquisition

- supported matrix上のclean Windows x64 hostでeditable installとCLI subprocessのimport元がcheckoutに一致する。
- `ocgcore-doctor`がtoolchain、path、permission、build driveを判定する。
- 空owned cacheからcore source、Premake、CardScripts、BabelCDBを固定identityで取得できる。
- 二回目bootstrapがidempotentであり、中断から復旧できる。
- source/toolchain/APIと各buildのDLL hashをmanifestで検証する。cross-session/cross-host bit一致は`1.0.0`の#171で扱い、`0.3.0`のclean acquisitionと混同しない。
- runtime/asset resolverがnetwork接続やfallback取得を行わない。
- BabelCDB ref/commit差異について、再現可能取得またはreview済みlock移行ADRがある。

## Gate B: real-core and Lua boundary

- DLL hash/export/API `11.0`を検証する。
- DataReader/Done、ScriptReader、LogHandlerのlifecycleとexception containmentを通す。
- root helper/card scriptのload順、hash、allowlisted pathを確認する。
- unsafe Lua libraryは無効である。
- missing DB row/script、syntax/load error、path traversal、unknown message/candidateをfail-closeする。

## Gate C: arbitrary deck workflow

- short combo、long combo、grave/banishまたはchain-heavyの3 deckを用いる。
- YDK 3 sectionとinline main/extra/sideを正規化し、source/deck SHA-256を保存する。
- fixed/random/conditional opening handを検証する。
- preflight、Random Search、best Route DSL、fresh Replayを同一manifestで追跡する。
- 同一seed/budget/lockでSearchRun、best Route、final state hashが再現する。
- 異なるseedで探索順が変わることを確認しつつ、各run内のReplay整合を保つ。
- raw Experiment/YDK/Routeはrepository外に保持し、`real-deck-qualification-index-v1`だけを公開可能なsanitized evidenceとする。

## Gate D: search and failure semantics

- STOP_LINEとEND_TURNを別Actionとして扱う。
- max_nodes/max_replays/max_depth/max_seconds、frontier exhaustedを一意のtermination reasonで報告する。
- pool size、worker完了順、retryでsemantic resultとbest Routeを変えない。
- prefix cache on/offでsemantic結果が一致する。
- exact State identity以外で枝を削除しない。
- crash、timeout、IPC切断、不正response、retry exhaustionをbudget terminationと区別する。
- partial artifactを成功runとしてpublishしない。

## Gate E: interruption and evaluation

- targetless、cost、single/multi-target、hand/field sourceのsupported taxonomyをReplayする。
- candidate消失、曖昧response、unsupported timingをfailureとして保存する。
- #123のcategoryごとにsupported/unsupportedと根拠を明示する。
- #110完了前にstatistical pruningをproduction defaultへしない。
- #108完了前にevaluator weightを一般deck品質の根拠としない。

## Gate F: performance evidence

3 deckの同一logical workloadをpool 1/2/4/8/16で各10万node実行し、次をJSON/Parquetへ保存する。

- logical/physical node、fresh Replay、worker invocation/retry
- throughput、elapsed、prefix length、entry bytes、hit/eviction
- worker peak RSS、main RSS、process/handle数
- artifact bytes/count、write amplification、checkpoint/recovery
- semantic digest、best Route ID、termination reason
- host CPU/RAM/OS/Python/compiler/core/asset/package/schema/workload identity

CIは縮小smokeを使い、10万nodeはmanualまたはself-hosted workflowとする。logical scheduler benchmarkだけで実core throughput/RSS gateを通してはならない。

## Gate G: compatibility and release

- Experiment `0.3a/0.3b/0.4`の既存fixtureを定義済みcompatibility modeで扱う。
- Route ID、Replay、normalization、catalogの全回帰を通す。
- wheel/sdist/Windows executable/clean venv smokeを通す。
- third-party core/assetsをartifactへ同梱しない。
- operator walkthroughとknown limitationsを現行CLIに同期する。
- #144でpackage/schema/policy/evaluator version変更を決定し、changelogへ反映する。
- test、GitHub Actions、required self-hosted evidence、review、commit、push、PR、merge、`main`同期、tagを完了する。

## Minimum operator sequence

実行順、期待出力、YDK差し替え、owned cache復旧、diagnostic routingの正本は[Real ocgcore operator walkthrough](../../ocgcore/50_operator_walkthrough.md)とする。

```powershell
python -m ygo_effect_dsl ocgcore-doctor
python -m ygo_effect_dsl ocgcore-bootstrap
python -m ygo_effect_dsl ocgcore-verify
python -m ygo_effect_dsl ocgcore-assets-bootstrap
python -m ygo_effect_dsl ocgcore-assets-verify
python -m ygo_effect_dsl ocgcore-clean-bootstrap-qualify --work-root <external> --out <clean-bootstrap-evidence.json>
python -m ygo_effect_dsl experiment-search <experiment.yaml> --out <best.route.yaml> --search-report <report.json>
python -m ygo_effect_dsl experiment-replay <experiment.yaml> <best.route.yaml>
python -m ygo_effect_dsl real-deck-qualify --experiment short=<external>/short.yaml --experiment long=<external>/long.yaml --experiment grave_banish=<external>/grave-banish.yaml --artifact-root <external>/raw --index-out <sanitized-index>.json
```

`experiment-search`は実worker起動前にscenario preflightを実行し、結果をSearchRun reportへ保存する。独立したpreflight CLIは現行`0.2.0`に存在しない。

`real-deck-qualify`は3 profileを各2回実行し、SearchRun ID、best Route ID、terminal State hash、profile witnessの一致後だけindexをatomic保存する。`short`はlegal stop/success、`long`はAction数とturn/phase列、`grave_banish`はgraveyard/banished count遷移をcore観測から証跡化する。harness testだけではGate Cを通過せず、外部3 deckの実行済みindexが必要である。

実際のCLI名・引数が変わる場合はoperator guide、CLI help、subprocess testを同じPRで更新する。

## Release rejection conditions

一つでも次に該当する場合は`0.3.0`をreleaseしない。

- clean bootstrapが固定source/toolchain/APIを取得できない、または各buildのDLL hashをmanifest検証できない。
- unknown/ambiguous shapeを推測処理して成功扱いにする。
- pool/retry/cacheでbest Routeまたはsemantic digestが変わる。
- worker leak、unbounded RSS、破損artifact、Replay divergenceが残る。
- third-party assetが配布物へ混入する。
- evidenceなしにsupported platform、任意deck、production性能を主張する。
