# Real ocgcore operator walkthrough

Status: Package 0.3.0 qualification workflow

Last updated: 2026-07-14

## Scope

この手順は、Windows x64上のPythonエンジニアが、現在checkoutをeditable installし、固定したocgcore/CardScripts/BabelCDBを検証して、Experiment `0.4`のinlineまたはYDK deckをpreflightし、Random Searchの最良Routeをfresh workerでReplayするまでを対象とする。third-party assetはrepository、wheel、exeへ同梱しない。Beam Search、MCTS、PlayerView Replay、production SLA、任意カード完全対応は対象外である。

コマンドはrepository rootのPowerShellで実行する。`$ExternalRoot`を全コマンドで統一し、別lockや別cacheを混在させない。

```powershell
$Repo = (Get-Location).Path
$ExternalRoot = Join-Path $env:LOCALAPPDATA 'ygo-effect-dsl\external'
$RunRoot = Join-Path $env:TEMP 'ygo-effect-dsl-real-core-smoke'
New-Item -ItemType Directory -Force -Path $RunRoot | Out-Null
```

## 1. Current checkout

Python 3.10以上、Git、Visual Studio 2022 C++ Build Toolsを用意する。editable install後、親processとworkerが別installではなく現在checkoutの`src`をimportすることをassertする。

```powershell
python -m pip install -e .
python -c "from pathlib import Path; import ygo_effect_dsl; expected=(Path.cwd()/'src'/'ygo_effect_dsl').resolve(); actual=Path(ygo_effect_dsl.__file__).resolve().parent; assert actual == expected, (actual, expected); print(f'checkout-import: ok path={actual}')"
python -m ygo_effect_dsl --version
```

期待する先頭は`checkout-import: ok`と`ygo-effect-dsl 0.2.0`である。package versionはこの手順の更新後に上がり得るため、固定値より`src/ygo_effect_dsl/version.py`との一致を優先する。

## 2. Doctor and bootstrap

`ocgcore-doctor-v2`はinstallを行わず、`ocgcore-platform-contract-v1`のOS/architecture/Python、Git、MSVC、Premake cache、`Y:` drive、対象pathをJSONで報告する。Windows x64、Python 3.10+以外はstable diagnosticでfail-closeする。`ok`がfalseならbootstrapへ進まない。

```powershell
python -m ygo_effect_dsl ocgcore-doctor --external-root $ExternalRoot
```

clean rootでは次の順にcoreとassetを取得する。networkを許可するコマンドは2つのbootstrapだけである。

```powershell
python -m ygo_effect_dsl ocgcore-bootstrap --external-root $ExternalRoot
python -m ygo_effect_dsl ocgcore-verify --external-root $ExternalRoot
python -m ygo_effect_dsl ocgcore-assets-bootstrap --external-root $ExternalRoot
python -m ygo_effect_dsl ocgcore-assets-verify --external-root $ExternalRoot
```

成功時のprefixは次である。SHA-256とabsolute binary pathはhostごとに表示されるため、文書の固定文字列として比較しない。

```text
ocgcore-bootstrap: ok lock_id=ocgcore-v11.0-win-x64-msvc-v1 api=11.0 ...
ocgcore-verify: ok lock_id=ocgcore-v11.0-win-x64-msvc-v1 mode=runtime
ocgcore-assets-bootstrap: ok asset_lock_id=ocgcore-assets-202504-v1 repositories=2
ocgcore-assets-verify: ok asset_lock_id=ocgcore-assets-202504-v1 repositories=2
```

既にcacheがあるhostでは、最初に2つのverifyを実行する。両方成功するならbootstrapの再実行は不要である。networkを禁止してbootstrapのidempotenceだけを確認する場合は`--offline`を付ける。cache不足時のoffline failureを別refや最新tagへのfallbackで回避してはならない。

## 3. Pinned Lua smoke

全12,702件のLua qualificationはpin変更時またはmanual release gateで実行する。通常のoperator smokeでは2件だけをfresh workerへ通し、partial evidenceであることを明示する。

```powershell
$LuaSmoke = Join-Path $RunRoot 'lua-smoke.json'
python -m ygo_effect_dsl ocgcore-lua-qualify --external-root $ExternalRoot --smoke-limit 2 --out $LuaSmoke
```

期待するprefixは`ocgcore-lua-qualify: smoke_only`である。`smoke_only`を全corpus qualificationとして扱わない。full gateでは`--smoke-limit`を外し、`qualified`、`scripts=12702/12702`、native failure 0を確認する。現行asset lockにはCardScriptsに存在してBabelCDBにDB行がない120 scriptがあり、通常deck preflightはそれらを利用可能と推測せず拒否する。

## 4. Inline environment smoke

まず既知のinline Experimentを作業directoryへ複製する。元fixtureを直接編集せず、生成Route/Search report/Replay reportもrepository外または`data/`の作業領域へ置く。

```powershell
$Experiment = Join-Path $RunRoot 'experiment.yaml'
$BestRoute = Join-Path $RunRoot 'best.route.yaml'
$SearchReport = Join-Path $RunRoot 'search-report.json'
$ReplayReport = Join-Path $RunRoot 'replay-verification.json'
Copy-Item -LiteralPath (Join-Path $Repo 'examples\experiments\general_search_inline.yaml') -Destination $Experiment
python -m ygo_effect_dsl validate-experiment $Experiment
python -m ygo_effect_dsl experiment-search $Experiment --external-root $ExternalRoot --out $BestRoute --search-report $SearchReport
python -m ygo_effect_dsl experiment-inspect $Experiment $BestRoute
python -m ygo_effect_dsl experiment-replay $Experiment $BestRoute --external-root $ExternalRoot --verification-report $ReplayReport
```

成功時は順に次のprefixを出す。

```text
validate-experiment: ok experiment_id=general_search_inline_smoke
experiment-search: ok experiment_id=general_search_inline_smoke ...
experiment-inspect: ok experiment_id=general_search_inline_smoke ...
experiment-replay: ok ... experiment_id=general_search_inline_smoke ...
```

`validate-experiment`はschemaとcross-field contractだけを検査する。DB行、Lua script、asset lock、deck構造、固定初手を含むscenario preflightは`experiment-search`がworker起動前に実行する。preflight failure時はRouteを成功artifactとしてpublishせず、`$SearchReport`へ`status: configuration_failure`、`scenario-preflight-v1`、安定diagnostic codeを保存する。

Search成功後は`$SearchReport`の`artifact_commit.status`が`committed`で、`route_id`とRoute file SHA-256が一致することを確認する。`fresh-replay-verification-v1` Replay reportはfresh workerのRoute全文一致後だけ作成され、`verification_scope: general_search`を持つ。

この10-node smokeはbudget内の接続と再現性を確認するため、`experiment-inspect`が`success=false`でもSearch/Replay自体は正常になり得る。success predicate達成率やdeck品質の証跡には使用しない。必要ならExperimentのbudgetを明示的に増やすが、smoke結果と別runとして保存する。

## 5. User YDK

YDKはUTF-8で、`#main`、`#extra`、`!side`の3 sectionをすべて持つ。empty extra/sideでもmarkerは省略しない。

```text
#created by operator
#main
<main deck card code, one per line>
#extra
<extra deck card code, one per line>
!side
<side deck card code, one per line>
```

`$Experiment`の`deck`を次へ置き換える。relative pathはExperiment fileのdirectoryを基準に解決される。`scenario.opening_hand.cards`はYDK main deck内に実在する5枚へ変更する。固定初手を使う限り`information_policy.opening_hand: fixed`は維持する。

```yaml
deck:
  id: operator_ydk
  source: ydk
  path: deck.ydk
scenario:
  schema_version: scenario-v1
  opening_hand:
    mode: fixed
    cards: [<code1>, <code2>, <code3>, <code4>, <code5>]
```

別deckの成果物を上書きしないよう`experiment_id`、`deck.id`、output名も変更し、4章と同じvalidate/search/inspect/replayを実行する。YDK raw bytesのSHA-256、正規化したmain/extra/sideのdeck SHA-256、実際のopening hand、asset lock identityはscenario manifestへ保存される。効果、合法性、timingをcard codeやテキストからPythonで補完しない。

## 6. Cache inspection and recovery

verify失敗時はcache root全体を削除しない。まずlock directoryとmanifestをread-onlyで確認する。

```powershell
$LockRoot = Join-Path $ExternalRoot 'ocgcore-v11.0-win-x64-msvc-v1'
Get-ChildItem -LiteralPath $LockRoot -Force
Get-Content -LiteralPath (Join-Path $LockRoot 'install-manifest.json') -ErrorAction SilentlyContinue
Get-Content -LiteralPath (Join-Path $LockRoot 'asset-manifest.json') -ErrorAction SilentlyContinue
git -C (Join-Path $LockRoot 'source') status --short
git -C (Join-Path $LockRoot 'assets\CardScripts') status --short
git -C (Join-Path $LockRoot 'assets\BabelCDB') status --short
```

bootstrapは自身が所有する`.source.partial`、`.build.partial`、`.runtime.partial`、asset partialを次回実行時に検査または片付ける。中断後は同じ`--external-root`でbootstrapを再実行する。source/assetsのcommit、tree、origin、dirty stateがlockと異なる場合は既存directoryを勝手に置換せず停止する。その場合は旧rootを証跡として保持し、空の別rootを指定してclean bootstrapを行う。

```powershell
$RecoveryRoot = Join-Path $env:TEMP 'ygo-effect-dsl-recovery-external'
python -m ygo_effect_dsl ocgcore-doctor --external-root $RecoveryRoot
python -m ygo_effect_dsl ocgcore-bootstrap --external-root $RecoveryRoot
python -m ygo_effect_dsl ocgcore-assets-bootstrap --external-root $RecoveryRoot
python -m ygo_effect_dsl ocgcore-verify --external-root $RecoveryRoot
python -m ygo_effect_dsl ocgcore-assets-verify --external-root $RecoveryRoot
```

異常cacheを手作業で修正してverifyを通す、別commitへcheckoutする、manifestのhashを書き換える、DLLやLuaを別installからcopyする操作は禁止する。これらは再現性を失わせる。

## 7. Diagnostic routing

| Symptom or code | Boundary | Next check |
|---|---|---|
| doctor `ok: false` | host/toolchain | OS/architecture、Git、MSVC、`Y:`使用、path permission |
| install/asset manifest missing | bootstrap commit | 同じrootで対応bootstrapを再実行 |
| commit/tree/hash/API mismatch | pinned dependency | manifestとGit statusを保全し、別empty rootで再取得 |
| `ydk_*` | YDK parser | UTF-8、3 marker、正整数card code、Experiment基準path |
| `invalid_main_deck_size` / `duplicate_card_limit_exceeded` | structural preflight | main 40..60、extra/side各15以下、全section合計同code 3枚以下 |
| `missing_card_database_row` | BabelCDB | 現lockでは未対応card。推測recordで継続しない |
| `missing_card_script` | CardScripts | official profileにscriptがない。legacy/rush等へ暗黙fallbackしない |
| `worker_timeout` / `worker_crash` | isolated native worker | Search reportのattempt/quarantineを確認し、同一semantic inputのfresh retryだけを許可 |
| Replay divergence | Route/core/asset identity | Route、Experiment、lock、request/state hashを照合し、成功扱いしない |

## 8. External three-deck release gate

これは日常のoperator smokeではなく、package 0.3.0 release用gateである。`short`、`long`、`grave_banish`のExperiment/YDKとraw artifact rootはrepository外に置き、3 deckを別入力として用意してから実行する。

```powershell
python -m ygo_effect_dsl real-deck-qualify --experiment short=D:\qualification\short.yaml --experiment long=D:\qualification\long.yaml --experiment grave_banish=D:\qualification\grave-banish.yaml --artifact-root D:\qualification\raw --index-out D:\qualification\real-deck-index.json --external-root $ExternalRoot
```

各profileはSearchとfresh Replayを2回ずつ実行し、SearchRun ID、best Route ID、terminal State、profile witnessが反復一致した場合だけsanitized indexをatomic保存する。2026-07-14の実行済みindexは`docs/ocgcore/evidence/real_deck_qualification.json`で、qualification IDは`deckqual_21dcdaddae643c08f562fd216dc2b0cc1f379b513d7c404727b5c1c6836d1599`である。inputs/raw artifactsは再配布せず、lock更新時は外部corpusから再実行する。

## Completion check

operator smoke完了は、core/assets verify、inline preflight、Search report commit、best Route、fresh Replay reportが同じlock/Experiment identityで揃った状態を指す。外部YDKを含む3 deck qualificationは別途完了済みである。10万node実worker性能とproduction配布は専用Issueの証跡が必要で、このwalkthrough成功や3 deck indexだけでは完了しない。
