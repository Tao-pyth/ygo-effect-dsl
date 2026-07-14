# ocgcore Binary Message and Response Contract

Status: Implemented prototype baseline for issues #67 and #89

Last updated: 2026-07-13

## 目的と責務

この契約は、ocgcore API 11.0のowned `bytes`を`DecisionRequest`へdecodeし、選択済み`Action`を`OCG_DuelSetResponse`用のowned `bytes`へencodeする境界を定める。Bridgeはbinary layoutと選択制約を検証するが、候補の合法性を作らず、表示label、探索node ID、native pointerをresponse生成根拠にしない。

依存方向は次で固定する。

```text
ocgcore bytes -> OcgcoreMessageDecoder -> DecisionRequest -> Search / Replay
ocgcore bytes <- ActionResponseEncoder <- Action          <- Search / Replay
```

SearchとReplayは`protocol.py`、`ctypes`、message IDへ依存しない。ocgcore固有情報はCandidateのowned primitive payloadとDecisionContextへ閉じ込める。

## Versionとframing

実装versionは`ocgcore-api-11.0`、response codecは`ocgcore-api-11.0-response-v1`である。別API versionを指定したdecoder / encoderは処理前に`version_mismatch`で停止する。

`OCG_DuelGetMessage`が返すstreamは次のlittle-endian frameの連結として読む。frame lengthはmessage type 1 byteを含む。

```text
u32 frame_length
u8  message_type
u8[frame_length - 1] payload
```

streamと各frameは1 MiB以下、frame lengthは1以上、宣言lengthと実buffer長は完全一致が必要である。切断、余剰byte、複数selection requestを含む1 batchは`invalid_message`とする。非selection messageは後続のstate decoder用にframeとして保持するが、DecisionRequestへ混入させない。selection messageでregistry未登録のものは`unsupported_message`とし、候補なしへ変換しない。

## API 11.0 decision registry

| Message | ID | Request type | Payload | Response |
| --- | ---: | --- | --- | --- |
| `MSG_SELECT_BATTLECMD` | 10 | `select_battle_command` | effects、attackers、phase controls | packed command `i32` |
| `MSG_SELECT_IDLECMD` | 11 | `select_idle_command` | summons、sets、effects、phase controls | packed command `i32` |
| `MSG_SELECT_EFFECTYN` | 12 | `select_effect_yes_no` | player、card location、effect description | yes/no `i32` |
| `MSG_SELECT_YESNO` | 13 | `select_yes_no` | `u8 player, u64 description` | selected candidateの`i32 value` |
| `MSG_SELECT_OPTION` | 14 | `select_option` | `u8 player, u8 count, u64[count] options` | option index `i32` |
| `MSG_SELECT_CARD` | 15 | `select_card` | player、cancel、min/max/count、card location列 | compact card index列 |
| `MSG_SELECT_CHAIN` | 16 | `select_chain` | effect chains、forced、timing | effect index / pass `i32` |
| `MSG_SELECT_PLACE` | 18 | `select_place` | count、unavailable zone mask | controller/location/sequence列 |
| `MSG_SELECT_POSITION` | 19 | `select_position` | `u8 player, u32 code, u8 mask` | position bit `i32` |
| `MSG_SELECT_TRIBUTE` | 20 | `select_tribute` | weighted cards、cancel、min/max | compact card index列 |
| `MSG_SORT_CHAIN` | 21 | `sort_chain` | card列 | original indexごとのorder `u8`列 |
| `MSG_SELECT_COUNTER` | 22 | `select_counter` | counter type、required count、card別上限 | card別allocation `i16`列 |
| `MSG_SELECT_SUM` | 23 | `select_sum` | target、must/select cards、sum parameters | compact card index列 |
| `MSG_SELECT_DISFIELD` | 24 | `select_disabled_field` | count、unavailable zone mask | controller/location/sequence列 |
| `MSG_SORT_CARD` | 25 | `sort_card` | card列 | original indexごとのorder `u8`列 |
| `MSG_SELECT_UNSELECT_CARD` | 26 | `select_unselect_card` | selected/unselected cards、finish/cancel | one index or `i32(-1)` |
| `MSG_ROCK_PAPER_SCISSORS` | 132 | `rock_paper_scissors` | player | hand sign `i32` |
| `MSG_ANNOUNCE_RACE` | 140 | `announce_race` | count、available `u64` mask | selected `u64` mask |
| `MSG_ANNOUNCE_ATTRIB` | 141 | `announce_attribute` | count、available `u32` mask | selected `u32` mask |
| `MSG_ANNOUNCE_CARD` | 142 | `announce_card` | declarability opcode列 | selected card code `i32` |
| `MSG_ANNOUNCE_NUMBER` | 143 | `announce_number` | number options | option index `i32` |

これは固定したocgcore API 11.0のうち、coreがclient responseを待つ既知decision messageの全registryである。finite option、weighted selection、順序、自由card code入力をそれぞれ別のrequest typeとcodecで表現する。未知の将来messageを推測decodeせず、registry追加とversion更新を必要とする。

wire fieldの順序と幅は、固定core commit `158aebe...` の [`playerop.cpp`](https://github.com/edo9300/ygopro-core/blob/158aebe758be3c46249c75d602e3f16d63d2ef31/playerop.cpp) を一次情報とする。`SORT_*` responseが「元card indexごとの選択order」であることは、公式EDOPro commit `650ec7b...` の [`event_handler.cpp`](https://github.com/edo9300/edopro/blob/650ec7b2273f60733b178d238cf6fec46722d8b4/gframe/event_handler.cpp) と照合した。仮のlayoutや現行masterの推測値は使用しない。

## DecisionRequest identity

Candidate IDは1 request内の安定IDであり、coreへ直接送らない。responseに必要な値はdecoderが次のpayloadへcopyする。

```json
{"response_codec":"int32","response_value":1}
```

```json
{"response_codec":"card_indices","response_index":0}
```

card candidateの`card_ref`はcontroller、location、sequence、position、公開card codeのprimitive値だけを持つ。`request_signature`にはrequest type、player、Candidate identity、constraints、protocol/version metadata、decode済みcontextを含め、`request_id`と表示labelを含めない。したがって同じcore requestは別processでも同じ署名になり、UI文言変更では変化しない。

pointer、callback payload、C構造体、任意objectなどcanonical JSONへ変換できない値をRequest identityへ入れた場合、encoderはnative call前に`invalid_response`で停止する。

## Response encoding

encoderは次の順でfail-closeする。

1. Request identityがowned primitiveだけであることを検証する。
2. Actionのplayerとrequest signatureを照合する。
3. unknown candidate、選択数、重複、ordered selectionを検証する。
4. request typeに対応するversioned codecを選ぶ。
5. Candidate payloadからだけresponse bytesを構築する。
6. 空bufferと1 MiB超を拒否してから`OCG_DuelSetResponse`へ渡す。

single-value responseはlittle-endian `i32`である。card responseはupstream `parse_response_cards`の形式を使用し、index幅に応じてtype 2 (`u8`)、type 1 (`u16`)、type 0 (`u32`)を選ぶ。通常のprototype fixtureは次のtype 2を使用する。

```text
i32 type = 2
u32 count
u8[count] sorted_candidate_indices
```

cancelable card requestの空選択だけは`i32(-1)`を送る。非cancelableの空選択、native min/max違反、同じcore indexの重複を拒否する。`OcgcoreDuel`は`awaiting_response`状態の`respond_action()`だけを許可し、送信後ただちに`processing`へ進むため、同一requestへの二重responseはnative call前に拒否される。

## Replay trace

Replayはresponseを再構築するだけでなく、送信したraw responseもhexで保存してcodec driftを検出する。`EncodedResponse.to_trace_dict()`は次を出力する。

- codec version
- request typeとrequest signature
- selected candidate IDs
- response length、hex、SHA-256

再生時はRequestとActionから再encodeし、全trace fieldが一致してから送信する。表示labelはRequest signature、Action ID、response bytesのいずれにも影響しない。別processでのrequest signatureと最終state hash照合は既存prototype replay verifierが担当し、実core state hashへの置換は#90と#84で行う。

## 検証

`tests/golden/ocgcore_v11/codec_cases.json`は既存4種のmessage hex、request signature、response hexを後方互換fixtureとして固定する。`tests/test_ocgcore_protocol.py`は21種のregistry、weighted selection、order、mask、自由入力、label非依存、stale signature、unknown candidate、制約違反、cancel、非primitive payload、切断frame、version mismatchを検証する。`tests/test_ocgcore_lifecycle.py`はencode済みbufferの1回送信と二重response拒否を検証する。

```powershell
$env:PYTHONPATH='src'
python -m pytest tests\test_ocgcore_protocol.py tests\test_ocgcore_lifecycle.py -q
```
