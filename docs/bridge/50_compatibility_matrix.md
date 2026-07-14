# Bridge and replay compatibility matrix

Status: ocgcore API 11.0 prototype coverage

Last updated: 2026-07-15

## Status meanings

- `real_core`: a pinned DLL/assets scenario records and verifies the request and response in a fresh worker process.
- `codec_only`: deterministic binary decode/encode fixtures exist, but no representative real-card route proves the continuation.
- `state_observed`: the resulting zone/count can be queried, but the operation that changes it is not covered.
- `unsupported`: no compatible end-to-end or codec contract exists. Selection messages in this state raise `UnsupportedBridgeMessageError`.

Bridge全体のmachine-readable sourceは`ocgcore.compatibility.compatibility_report()`、Action aggregation lifecycleは`action_aggregation_compatibility_report()`である。`ocgcore-v11-compatibility-v2`は固定API 11.0のdecision、non-decision、明示unsupported message集合と`unknown_message_policy: fail_close`を公開する。Tests require every known API 11.0 selection message and every operation category from issue #54 to have exactly one status.

## Current result

| Category | Status | Scope |
| --- | --- | --- |
| Normal summon | real_core | idle command, place, optional chain pass, legal stop, fresh replay |
| Chain | real_core | optional pass、effect activation setup、`MSG_CHAINED`、resolution、固定fixtureでの発動無効・効果無効・タイミングを逃した通知 |
| Special summon | codec_only | idle candidate only; continuation not covered |
| Target/card selection and cost shape | real_core | target hint、selected-card `REASON_COST` move、optionを固定fixtureで検証 |
| Draw, banished | state_observed | query coverage only |
| Graveyard | real_core | selected hand costの移動とqueryを検証 |
| Search, non-targeting effect | unsupported | no representative route |
| Simultaneous trigger ordering | unsupported | `interruption-support-taxonomy-v1`でfail-close。実core fixtureは[#208](https://github.com/Tao-pyth/ygo-effect-dsl/issues/208) |
| Continuous/replacement effects | unsupported | no behavior fixture |
| Fusion/Synchro/Xyz/Link and other summon methods | unsupported | no request-sequence fixture |
| Direct `Duel.GetRandomNumber` trace | real_core | pinned real card/database runtime records draw order/range/result through core `logHandler`; transport equivalence is verified by #107; #111 proves script log and random frame can share one native process call, while public API exposes no cross-channel shared sequence |
| Persistent card instance trace | real_core | v1 authority is frozen by #112; opt-in v2 performs nonce-checked scan before every card-bearing Request, enriches Action/snapshot/Route/attribution, and verifies draw/search/salvage, hand/deck/set shuffle, grave/banished movement, control change, hidden projection, and fresh-process identity in #116 |

Message types 11、12、14、15、16、18はreal-core evidenceを持つ。その他の既知API 11.0 response要求message type（10〜26のselection/sort、132、140〜143）はdeterministic codec evidenceを持つ。既知decision messageに`unsupported`は残らないが、代表的continuationがないoperation rowは引き続きunsupportedである。

## Decision shape corpus

`ocgcore-api-11.0-message-registry-v1`は固定upstream `common.h`のmessage IDをdecision、non-decision、明示unsupported `MSG_RELOAD_FIELD=162`へ分離する。registry外IDをnon-decisionと推測して無視せず、`UnsupportedBridgeMessageError`として停止する。診断はmessage ID、payload length/SHA-256、protocol/registry version、可視盤面とchain本文を除いたdecision contextを保存し、raw payload本文は保存しない。DecisionRequest candidate IDの重複はresponse lookup前に拒否する。

`ocgcore-decision-shape-corpus`は一つ以上の実core Routeを入力し、各Replay eventについて直前のcore outputをbinary decodeし、記録Actionをresponse encodeして、request signature、frame hash、response hashを相互検証する。出力`ocgcore-decision-shape-corpus-v1`はcandidate field shape、cost/target/option role、targetless/single/multi-target、hand/field source、negative case registryだけを保持し、`payload_hex`と`response_hex`を除外する。

```powershell
python -m ygo_effect_dsl ocgcore-decision-corpus --route <route-a.yaml> --route <route-b.yaml> --out <decision-corpus.json>
```

固定action-aggregation Route、妨害matrix、外部short/long/grave-banish qualification Routeを合わせ、targetless、cost、single/multi-target、option、hand/field sourceをlocal確認済みである。`docs/ocgcore/evidence/decision_shape_corpus.json`は8 Route・106 decision caseを持ち、corpus IDは`decisioncorpus_b134c9a8d6855ab39b11f36f7c3d00135a8c47a52ed125b865b69cdeb39e7fe4`である。全caseでsource frame再decodeとAction response再encodeがround-tripし、外部3 deckで未知shapeは観測されなかった。これは固定lockと代表corpusの証拠であり、未実行カードやdamage step、simultaneous trigger、mandatory trigger、SEGOC等の裁定へ一般化しない。

Action role分類はAPI v11 raw frame layoutへ固定する。正常activation setup、target-loss fizzle、`MSG_CHAIN_NEGATED`、`MSG_CHAIN_DISABLED`、multi-chain、multi-selection、resolution-selectionは`real_core`である。同一source・cost・request・actionの固定fixtureでは、発動無効がtype 75、効果無効がtype 76として区別される。任意の`EVENT_TO_GRAVE` triggerがchain解決中に候補化されない固定fixtureではtype 120 (`MSG_MISSED_EFFECT`) とpass-onlyの次要求を検証する。ただし、これらは任意カードの裁定一般を保証しない。cancelのraw Replay contractは維持するが、API 11.0ではnative cancel応答`ffffffff`後も`MSG_CHAINED`が発生するため`raw_replay_contract_core_unreachable`とする。Issue #115の2026-07-14監査では、最新release `v11.0`と未release `master` API 11.0の該当source contractにrollback分岐がないことを確認した。`master` binaryは実行未検証であり、source audit以上のclaimは行わない。新tag/APIまたは該当制御フロー変更をIssue #117の再監査triggerとする。`MSG_MOVE.reason`、`MSG_HINT`、chain lifecycle payloadの形式が変わるcore/API版では互換性を引き継がずfail-closeする。hint欠落、未知reason、選択cardとの不一致は`selection`へfallbackし、表示上の誤集約を避ける。

This matrix measures Bridge/Replay compatibility, not card-rule correctness. A state-observed or codec-only row must not be presented as end-to-end support.
