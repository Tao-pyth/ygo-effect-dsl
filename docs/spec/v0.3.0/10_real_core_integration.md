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

## Qualification boundary

local smoke成功だけではqualificationにならない。空cache、3種類のdeck、Lua/error corpus、worker fault injection、pool別10万nodeを同じlockとversionで通し、raw evidenceを保存した時点で`0.3.0`のreal-core gateを満たす。
