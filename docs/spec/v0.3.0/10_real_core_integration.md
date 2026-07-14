# Package 0.3.0 Real ocgcore / EDOPro Lua Integration Contract

Status: Qualification contract

Last updated: 2026-07-14

## Authority boundary

合法手、カード効果、cost、target、chain、timing、状態遷移の真実源はocgcoreとEDOPro Luaである。Pythonはbinary/message境界の検証、CDB/Lua供給、候補の構造化、探索順、Replay、評価、診断を担当する。card codeやscript名から効果・合法性・timingを推測して不足を補わない。

## Locked inputs

| Component | Locked identity | Policy |
|---|---|---|
| ocgcore | tag `v11.0`, commit `158aebe758be3c46249c75d602e3f16d63d2ef31`, tree `23915a17e8e0d6b0b64ffc868bf0067a55e00aa0`, API `11.0` | Windows x64, VS 2022, Release, `/Brepro`, runtime network禁止 |
| Lua submodule | commit `1ab3208a1fceb12fca8f24ba57d6e13c5bff15e3` | core source lockに含める |
| CardScripts | ref `20250420`, commit `c8e9c0bcd026a5ccc303bbc73881b8f86f818657`, tree `8796d294eaea50ca58ccd8560bb0511923dcc364` | AGPL、local取得、非同梱 |
| BabelCDB | ref `20250419`, commit `f89c9a4be9a5f193e29b788e3cf880563f4f79b4`, tree `2468d312ab6e7bdbc403f3764ee24f9062f61335` | license `NOASSERTION`、local取得、非同梱、[#137](https://github.com/Tao-pyth/ygo-effect-dsl/issues/137)でref差異を検証 |

lockはcommit/treeだけでなくrequired fileのsize/SHA-256を検証する。runtime resolverはdownload、checkout、build、installを行わない。

## Bootstrap sequence

1. `ocgcore-doctor`がOS、architecture、Python、Git、MSVC、Premake cache、build drive、path/permissionを事前検査する。
2. `ocgcore-bootstrap`だけがcore source/toolを取得し、pristine sourceとdisposable build treeを分離する。
3. buildは既存`Y:`を上書きせず、所有する一時mappingだけを解放する。
4. `ocgcore-verify`がsource commit/tree/submodule、DLL hash、export、API versionを照合する。
5. `ocgcore-assets-bootstrap`だけがCardScripts/BabelCDBを取得する。
6. `ocgcore-assets-verify`がcommit/treeとrequired file hashを照合する。
7. manifest commitが完了するまでruntime resolverから新assetを見せない。

bootstrap以外のCLI、worker、Replay、Searchはnetworkへ接続しない。`--offline`はcache不足時に即時失敗し、別refへfallbackしない。

### Clean-bootstrap qualification

`ocgcore-clean-bootstrap-qualification-v1`はrepository外の一意sessionで空root、同一root再実行、build/runtime partial復旧、独立空root、download partial復旧の5 buildを行う。各buildはfreshに`ocgcore-verify`を通し、絶対pathを除いたsource/tree/submodule、API、compiler、Premake、DLL size/SHA-256、所要時間をcanonical evidenceへ保存する。lock不一致は`lock_mismatch`、破損DLLは`runtime_integrity_mismatch`、API不一致は`api_mismatch`として停止する。

2026-07-14のlocal qualification `corebootstrap_12a20bd0e3606d14d3fc597eb6a60aeca2e9ec1478430de73427a4d3298531d1`はMSVC `14.44.35207`で全5 buildに成功した。session内DLLは1,306,624 bytes、SHA-256 `03e360cf694f5ac6ba686de1d3bec7ccde3f3233d01bfe3265884a18ce1b9028`で一致したが、事前診断runでは別hashも観測した。したがって`0.3.0`では固定入力、per-build integrity、再実行、中断復旧をqualifiedとし、cross-session/cross-host bit reproducibilityは[#171](https://github.com/Tao-pyth/ygo-effect-dsl/issues/171)まで一般化しない。

## Runtime architecture

```text
Experiment 0.4
  -> Scenario normalization and preflight
      -> asset/core resolver (read-only verification)
          -> fresh worker process
              -> OCG_CreateDuel callbacks
                  -> SQLite DataReader / DataReaderDone
                  -> CardScripts ScriptReader / OCG_LoadScript
                  -> LogHandler
              -> OCG_DuelProcess message frames
                  -> DecisionRequest and candidates
                      -> SearchStrategy selects Action or STOP_LINE
                          -> response bytes
                              -> State query / evaluation / evidence
  -> best Route DSL
      -> fresh worker Replay
          -> state/request/route identity verification
```

workerごとにnative duel、callback、SQLite connection、Lua lifecycleを所有する。native pointer、duel handle、Lua state、message bufferをprocess間またはprefix cacheへ保存しない。

## CDB contract

- SQLiteはread-onlyで開き、`datas`行をcard codeで取得する。
- DB row欠落、schema欠落、type/range不正、callback中例外をnative ABI外へ送出しない。
- callback引数pointerはcallback中だけ借用し、保存しない。
- DataReaderDoneを含むlifecycleを一度だけ完了する。
- deck preflightは実worker起動前に全card codeのDB rowを確認する。

## EDOPro Lua contract

- root helperとcard scriptはallowlisted asset root配下だけから解決する。
- coreが要求した相対script名、解決先、content hash、load結果をaudit可能にする。
- path traversal、root外symlink、曖昧なcase、duplicate resolutionを拒否する。
- missing、read error、encoding/syntax/load errorをstructured diagnosticへ変換する。
- `enableUnsafeLibraries=0`を既定かつrelease testで固定する。
- Pythonがmissing scriptの効果をstub実装して探索を継続してはならない。

### Resolver and audit contract

`ResolvedScript` schema version 1は、coreの要求名、allowlisted rootからの相対解決path、source kind、byte size、SHA-256、実際に渡すbytesを一体で扱う。absolute pathはReplay向け監査情報へ含めない。filesystem resolverは各path segmentをcase-sensitiveに照合し、casefold衝突、case不一致、`..`、drive path、symlink、Windows reparse point/junctionを拒否する。file handleはno-followで開き、上限+1 byteまでのbounded readとopen前後のidentity検査を行う。directory indexはmtime/identity変更時に再構築する。

Experiment `0.3a/0.3b`のReplay互換profileは従来どおりroot、`official`、`pre-release`、`pre-errata`、`goat`、`skill`、`rush`、`unofficial`の優先順で最初の一致を使う。Experiment `0.4`は`card-scripts-official-v1`を固定し、bare card scriptを`official`だけから解決する一方、helperは全allowlisted directoryを検索する。複数helper解決とprofile外の明示card pathは曖昧またはprofile逸脱として停止する。goat、rush、skill等の新規`0.4`実行profileはscenario契約へ追加するまでfail-closeする。

`c0.lua`だけはocgcoreが存在しないcard code 0に要求する既知sentinelとして、`source_kind=virtual`、`resolved_path=builtin/c0.lua`、空bytesを明示記録する。任意のmissing card scriptをこのsentinelで代替してはならない。

duel sessionはscript要求開始順のsequenceを発行し、`loaded`、`missing`、`rejected`、`asset_error`、`invalid_encoding`、`provider_error`を区別する。audit manifestは`profile_id`を持ち、各entryは解決済みの場合にrelative path、size、SHA-256を持つ。`experiment_manifest.lua_script_resolution`から取得でき、Experiment `0.4`の完了Routeは同じ内容を`result.lua_script_resolution`へ保存してRoute IDとfresh Replayのdocument一致検証対象にする。`0.3a/0.3b` Routeは読み取り・Replay identityを変更しない。`enableUnsafeLibraries`は常に0である。

### Official Lua load qualification

`ocgcore-lua-load-qualification-v1`は、Experiment `0.4`が使用するofficial profileの全card scriptを対象とする。親processはpin済みcore/assetsを先に検証し、各scriptをcold、同一providerのwarm、fresh providerで解決してrelative path、size、SHA-256の列が完全一致することを必須にする。directory indexはprocess-localのfile identity cacheだけを使用し、stale indexによるpath検査回避を避けるため永続indexは採用しない。

native検査は最大2,048 scriptごとのfresh worker/duelで行い、`constant.lua`、`utility.lua`とそのhelper closureを先にロードする。その後、direct `OCG_LoadScript`ではなく`OCG_DuelNewCard`を使い、core自身の`load_card_script`による`self_code`、`self_table`設定と`initial_effect`実行まで通す。各batchのhelper load digestは一致必須であり、card scriptから追加要求されたofficial card依存も別digestへ保存する。syntax error、invalid callback name encoding、unsafe library、path traversal、case mismatch、missing、duplicate fixtureをnegative probeとして保持する。

2026-07-14のlocal evidenceではofficial 12,702件を7 fresh workerで全件ロードし、helper closure 26件、native failure 0、worker内load合計22.178秒、最大worker peak RSS 84,602,880 bytesを観測した。BabelCDBで裏付けられるscriptは12,582件で、120件はDB行がなく、15件はaliasを持つ。全scriptの構文/load corpusを強制するためqualification workerだけはaliasを0にし、DB欠落時は最小normal-card recordを使う。この操作はカード効果や合法性の補完ではなくscript loader検査専用であり、通常scenarioではDB欠落120件をpreflightで拒否する。したがってLua load境界はlocal qualifiedだが、任意card/deck一般性`VAL-008`の完了証跡ではない。

```powershell
python -m ygo_effect_dsl ocgcore-lua-qualify --out docs/ocgcore/evidence/lua_load_qualification.json
```

## Scenario-to-Replay identity

一つのqualified runは最低限次を結合する。

- package/Experiment/Scenario/Search/Route/Replay contract version
- core lock ID、API、source commit/tree、DLL hash
- asset lock ID、CardScripts/BabelCDB commit/tree、required file hash
- normalized deck sections、source hash、deck hash、opening hand mode/seed/result
- search strategy version、seed、budget、semantic node ID
- Action/request signature、Route ID、state hash、evaluation version
- worker attempt、retry、timeout/crash classification

このidentityの不一致はwarningで継続せず、strict Replayでは停止する。

## Fresh Replay verification artifact

`experiment-replay --verification-report FILE`はfresh workerのRoute全文一致後にだけ`fresh-replay-verification-v1`を保存する。reportはrun ID、SearchRunと共通のExperiment digest、Route ID/document digest、event count、terminal State hash、Replay manifest hash、core/asset lock、scenario manifest digest、deck/source hash、Lua resolution audit digestをcontent-addressed `verification_id`へ結合する。`verification_scope: general_search`はExperiment `0.4`、scenario manifest、公式Lua auditを必須とし、`scripted_real_core`のlegacy Replayと区別する。YDKだけがsource SHA-256を持ち、scenario/runtimeのasset lock不一致は拒否する。deck section、opening hand、絶対path、card database、Lua本文はreportへ複製しない。

書き込みは同一directoryの一意なtemporary fileをflush/fsyncしてから`os.replace`し、Windowsの一時的なreplace競合だけをbounded retryする。検証またはreplace失敗時は成功reportを書かず、既存destinationを保持してtemporary fileを削除する。`verification_id`は偶発的な破損とjoin不一致を検出するcontent IDであり、攻撃者による再計算を防ぐ電子署名ではない。署名・trusted catalog anchoringはproduction provenanceの別契約とする。

## Worker attempt and artifact commit

General Searchのfresh workerごとに`real-core-frontier-worker-attempt-v1`を生成する。attemptはsemanticなinput digest、local attempt index、process ID、return code、stdout/stderr digest、終了確認、failure category、retryable、quarantinedを持つ。Search reportは全成功attemptを列挙せずinvocation countとして集計し、failure/retryが発生したReplayのattempt lineageだけを保持するため、通常runのledger memoryはO(failure count)である。raw stdout/stderrはSearch reportへ複製しない。crash、timeout、IPC失敗は失敗attemptをquarantineしてfresh processだけでretryし、不正JSON、failure envelope不正、frontier schema不正は`worker_protocol`としてretryしない。全retry消費時は`real-core-frontier-worker-failure-v1`がattempt ID列と`retry_exhausted`を保持する。

worker processはocgcore DLLを同一process内へloadするleaf processであり、子process生成をworker contractで許可しない。timeout時はworkerをkillして`communicate`で回収し、attemptの`terminated`を確認する。将来workerから別processを起動する構成へ変える場合は、process group/job objectによるtree cleanupを先にversion付きcontractへ追加する。

`experiment-search`はRouteとSearch reportをそれぞれ一意temporary fileからatomic replaceする。成功時はRouteを先にpublishし、そのSHA-256とRoute IDを`search-artifact-commit-v1`へ記録したSearch reportを最後にcommit markerとしてpublishする。readerはreportのhashとRouteを照合し、report欠落、`not_published`、hash不一致を成功runとして扱わない。preflight、worker、artifact失敗は`search-run-failure-v2`でbudget terminationと区別し、既存Routeを削除または上書き途中にしない。

## Fail-close classes

| Class | Examples | Required result |
|---|---|---|
| environment | unsupported OS/API/compiler、path/permission | worker開始前にconfiguration failure |
| asset | commit/tree/hash不一致、DB/Lua欠落 | preflight failure |
| protocol | unknown message ID、truncated frame、不正candidate | pathまたはconfiguration failure。推測decode禁止 |
| response | stale signature、候補消失、constraint違反 | path failureとlineage保存 |
| worker | crash、hang、IPC切断、native callback error | attempt failure、policy内retry、最終分類 |
| replay | request/state/route divergence | replay failure。best Route成功扱い禁止 |
| budget | max node/replay/depth/seconds | 正常termination reason。worker failureと混同しない |

### API 11.0 message registry and Decision shape corpus

`ocgcore-api-11.0-message-registry-v1`は固定core sourceの全message IDを列挙する。decoderを持つdecision、意味をPythonで解釈せずtraceとして保持する既知non-decision、card-instance authorityを壊すため拒否する`MSG_RELOAD_FIELD`を明示的に分離する。registry外IDは将来のdecisionである可能性を排除できないため、暗黙に無視せずpath failureとする。診断にはraw payload本文ではなくSHA-256と長さ、sanitized decision contextを残す。

`ocgcore-decision-shape-corpus-v1`はRoute validator通過後、各eventのsource frameを再decodeし、記録Actionを再encodeする。request signature、payload hash、response hashのいずれかが一致しないRouteはcorpusへ入れない。candidate payloadは値ではなくfield集合とresponse codecだけを保存する。negative registryはunknown message、unknown candidate shape、candidate disappearance、ambiguous candidate/response、unverified interruption categoryのclassificationを固定する。

```powershell
python -m ygo_effect_dsl ocgcore-decision-corpus --route <real-core-route.yaml> --out <decision-corpus.json>
```

2026-07-15に固定5 Routeへ`#139/#194`の外部short/long/grave-banish 3 Routeを追加し、計8 Route・106 Decision caseを同じCLIで再検証した。corpus IDは`decisioncorpus_b134c9a8d6855ab39b11f36f7c3d00135a8c47a52ed125b865b69cdeb39e7fe4`で、未知shapeはなくrequired 7 categoryがcompleteであるため`VAL-010`をlocal verifiedとする。これは固定lockと代表corpusの結果であり、#123でfail-closeしたdamage step、simultaneous trigger、mandatory trigger、SEGOCを暗黙にsupportしない。

## Qualification boundary

local smoke成功だけではqualificationにならない。空cache、3種類のdeck、Lua/error corpus、worker fault injection、pool別10万nodeを同じlockとversionで通し、raw evidenceを保存した時点で`0.3.0`のreal-core gateを満たす。

実coreの`SearchFrontier v2`は`state_completeness`を必須とする。現行ocgcore query APIから構築する`state_id`は`query_api_projection`であり、観測、semantic node ID、集計には利用できるがexact dedup authorityではない。使用済み効果や完全な履歴を含むexact identityを取得できるまで、同じprojectionだけを根拠にbranchを削除しない。

### External three-deck qualification harness

`real-deck-qualify`はrepository外のExperiment `0.4`を`short`、`long`、`grave_banish`の順で正確に3件受け取る。deck sourceは`inline`または`ydk`だけを許可し、YDK自体もrepository外を必須とする。3件のnormalized deck SHA-256は相互に異ならなければならない。`runner.fixture_script_id`、Random Search以外、`interruption-support-taxonomy-v1`で未検証の指定妨害・chain-heavy categoryはconfiguration failureとする。

各profileはpreflight後に既存`experiment-search`と`experiment-replay --verification-report`を2回ずつ別processで実行する。SearchRun ID、best Route ID、terminal State hash、core観測witnessが反復間で一致しない場合、qualification indexをpublishしない。全profileでcore由来の`success=true`とlegal stop `core_end_turn_available`を必須とする。そのうえで`long` witnessは12 Action以上とcheckpointのturn/phase列、`grave_banish` witnessはinitial snapshotとcheckpoint間のgraveyard/banished count変化を追加条件とする。カード名・効果・合法性をPythonで推測しない。

raw SearchRun、Route、Replay report、Experiment、YDKはexternal evidence storageへ残す。repositoryへ保存可能な`real-deck-qualification-index-v2`はExperiment/deck/lock identity、各artifact SHA-256、反復不変条件、sanitized witnessだけを含み、card code列、deck section、opening hand、Route本文、絶対pathを含めない。v2では全profileのsuccess/legal stopをwitnessへ明示する。indexは全profile成功後だけatomic replaceで保存する。

2026-07-14に外部short/long/grave-banish corpusを各2反復し、`deckqual_21dcdaddae643c08f562fd216dc2b0cc1f379b513d7c404727b5c1c6836d1599`を取得した。shortはYDK/random hand/8 Action、longはinline/fixed hand/24 Action、grave-banishはYDK/conditional hand/11 Actionである。3 deck hash、SearchRun ID、best Route ID、terminal State hash、witnessが反復一致し、全profileがsuccess/legal stop、grave-banishがgraveyard 0→1遷移を満たした。sanitized indexは`docs/ocgcore/evidence/real_deck_qualification.json`へ保存し、raw inputs/artifactsはrepository外に維持する。
