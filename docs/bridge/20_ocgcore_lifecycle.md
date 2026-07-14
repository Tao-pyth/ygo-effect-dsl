# ocgcore C API Lifecycle Contract

Status: Implemented and locally qualified for issues #88 and #140

Last updated: 2026-07-14

## 目的

この文書は、Windows x64 worker内でocgcore API 11.0を呼ぶ際のライフサイクル、callback、メモリ所有権を固定する。Bridgeはnative境界の検証、データ供給、buffer copy、診断化のみを担当し、カードの合法性、チェーン解決、勝敗などのルール判断は行わない。

## 固定C ABI

calling conventionはWindows x64の既定C ABIであり、関数は`ctypes.CDLL`、callbackは`ctypes.CFUNCTYPE`で宣言する。duel生成前にOS、CPU、export、API version、struct layoutを検査し、1項目でも不一致なら`version_mismatch`として停止する。

| 項目 | 固定値 |
| --- | --- |
| OS / architecture | Windows x64、pointer 8 bytes |
| ocgcore API | 11.0 |
| `OCG_Player` | 12 bytes |
| `OCG_CardData` | 64 bytes |
| `OCG_DuelOptions` | 136 bytes |
| `OCG_NewCardInfo` | 24 bytes |
| `OCG_QueryInfo` | 20 bytes |
| native message / query上限 | 1 MiB |
| response / Lua上限 | 1 MiB |
| unsafe Lua libraries | 常に無効 |

`OCG_DuelOptions`のpayload pointerはすべてnullとし、main processのobjectやaddressをnativeへ渡さない。`enableUnsafeLibraries`は設定値にかかわらず有効化できず、manifestには`false`を記録する。

## 状態遷移

libraryは`discovered -> version_checked -> closed`の順に進む。active duelが1件でもある間は`close()`を拒否する。duelの正常系は次のとおりで、`cards_loaded`はカードを追加した場合だけ通る。

```text
version_checked -> duel_created -> cards_loaded? -> started -> processing
                                                         |        |
                                                         |        +-> ended
                                                         +-> awaiting_response
                                                               |
                                                               +-> processing
```

nativeまたはcallbackの失敗とbudget超過は`failed`へ遷移する。生成済みの全状態から`destroyed`へ遷移でき、`destroy()`は複数回呼んでも`OCG_DestroyDuel`を1回だけ実行する。

| 操作 | 許可状態 |
| --- | --- |
| `add_card()`, `load_script()`, `start()` | `duel_created`, `cards_loaded` |
| `process()` | `started`, `processing` |
| `respond()` | `awaiting_response` |
| query群 | `failed`, `destroyed`以外 |
| `destroy()` | `destroyed`以外。`destroyed`ではno-op |

1 duelは生成したthreadだけが操作する。callback中の公開API再入と別threadからの操作は`invalid_state`として拒否する。ただし`ScriptReader`が同じcallback内で`OCG_LoadScript`を呼ぶことはC API契約上の必須動作であり、内部呼び出しとして許可する。

## Callback契約

| Callback | 入力元 | Bridgeの処理 | 失敗category |
| --- | --- | --- | --- |
| `DataReader` | card code | read-only `cards.cdb` providerから`OCG_CardData`へコピー | 欠落・DB異常は`asset_error` |
| `DataReaderDone` | `OCG_CardData*` | 対応するsetcode配列のPython所有を解除 | その他は`core_error` |
| `ScriptReader` | Lua file name | CardScripts providerからbytesを取得し`OCG_LoadScript`へ渡す | 欠落・load拒否は`asset_error` |
| `LogHandler` | message, log type | UTF-8を置換ありでdecodeし`Diagnostic`へコピー | handler異常は`core_error` |

全callbackは`BaseException`を捕捉する。Python例外をC ABIの外へ送出せず、callback終了後の最初の安全な公開API境界で`OcgcoreCallbackError`として送出する。ocgcoreはduel生成中に一時カード用の`c0.lua`を要求するため、CardScripts資産にはこれを含める。欠落時は生成されたnative duelを直ちに破棄してからエラーを返す。

## メモリ所有権

| 対象 | 所有者 | 有効期間 | 解放・copy規則 |
| --- | --- | --- | --- |
| DLL handle | `OcgcoreLibrary` | library open中 | active duelが0のときだけ`FreeLibrary` |
| `OCG_Duel` handle | `OcgcoreDuel` | create成功からdestroyまで | `OCG_DestroyDuel`を厳密に1回 |
| optionsとcallback function | `OcgcoreDuel` | native duelの全期間 | destroy後にPython参照を解除 |
| callback payload | 未使用 | なし | 常にnull |
| callback引数pointer | ocgcoreから一時借用 | callback中のみ | 保存せず、必要情報だけcopy |
| `OCG_CardData`本体 | ocgcore | `DataReader`呼び出し側が管理 | Bridgeはfieldを書き込むだけ |
| null終端setcode配列 | `OcgcoreDuel` | `DataReader`から対応する`DataReaderDone`まで | addressごとに保持しDoneで解除 |
| CDB record | provider | Python method呼び出し中 | scalarとtupleへ変換して返す |
| Lua bytes | provider / `OcgcoreDuel` | `OCG_LoadScript`呼び出し完了まで | 1 MiB以下を同期呼び出しで渡す |
| message / query buffer | ocgcore | 次のnative API呼び出しまで | 長さ検証後ただちに`bytes`へcopy |
| response buffer | `OcgcoreDuel` | `OCG_DuelSetResponse`呼び出し中 | 呼び出し完了までPython参照を保持 |
| log string | ocgcore | `LogHandler`中のみ | Python `str`へcopyしpointerは破棄 |

`cards.cdb`はSQLite URIの`mode=ro`で開き、標準`datas` tableの値だけを構造変換する。カード効果や合法性を補完しない。CardScriptsのfilesystem providerはroot外参照を拒否する。

## Process budgetと診断

`OCG_DuelProcess`の結果は`END=0`、`AWAITING=1`、`CONTINUE=2`として検証する。`CONTINUE`は指定step数またはwall-clock deadlineまでworker内で進める。未知status、1 MiB超のbuffer、null pointerと非0 lengthの組み合わせはエラーとする。

このwall-clock検査はnative callから制御が戻った場合だけ実行できる。native内部のhang、abort、access violationはADR-0005に従いmain process側のdeadlineでworkerをkillして隔離する。worker protocolへ返す情報はcategory、message、callback名、log type、最後の安全なoperationなどのcopy済み値に限定し、native pointer、callback payload、生のC構造体を含めない。

| 事象 | category | retry方針 |
| --- | --- | --- |
| OS / architecture / API / layout不一致 | `version_mismatch` | retryしない |
| create status異常 | `core_error` | native duelがあれば破棄後に失敗 |
| CDB / Lua欠落、Lua load拒否 | `asset_error` | 資産を修正するまでretryしない |
| callback内の任意例外 | `core_error` | duel破棄、worker再利用可否は上位で判断 |
| status / buffer / pointer異常 | `invalid_message`または`core_error` | duel破棄 |
| step / wall-clock / worker deadline超過 | `timeout` | workerを破棄して置換 |
| APIの無効な呼び順 | `invalid_state` | 呼び出し側の不具合として扱う |

## 検証

`tests/test_ocgcore_lifecycle.py`はfake nativeによる全状態、無効遷移、buffer copy、二重destroy、thread affinity、create失敗、step budget、LogHandlerを検証する。検証済み実coreが利用可能な環境では、setcode解放、欠落CDB、欠落Lua、callback任意例外、生成中callback失敗後の再生成も実行する。

`ocgcore-lua-qualify`はofficial CardScripts全件をfresh workerへ分割し、strict resolverのcold/warm/fresh同値性、helper load順、`OCG_DuelNewCard`経由のcard scriptと`initial_effect`、unsafe library無効、negative probeを検査する。証跡は絶対pathやLua本文を含めず、relative path/hash/count/digestだけをatomic保存する。現行pinでは12,702 scriptのnative loadが成功し、BabelCDBにない120 scriptは通常scenarioでfail-closeする。

```powershell
$env:PYTHONPATH='src'
python -m pytest tests\test_ocgcore_lifecycle.py -q
python -m ygo_effect_dsl ocgcore-lua-qualify --out docs\ocgcore\evidence\lua_load_qualification.json
```
