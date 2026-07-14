# Replay randomness and I/O trace

Status: V0.3a executable contract

Last updated: 2026-07-13

Direct RNG validation: [#93](https://github.com/Tao-pyth/ygo-effect-dsl/issues/93), transport follow-up: [#107](https://github.com/Tao-pyth/ygo-effect-dsl/issues/107)

## Purpose

Replayはseedだけでなく、Pythonからcoreへ送った全responseと、coreが返した全message frameを順序付きで保存する。再生時は同じresponse列を送り、Request署名とresulting State hashを照合する。

## Ordered I/O

`replay.initial_core_output`は最初のresponseより前にcoreが返したbatchである。各`replay.events[]`は次を持つ。

- `core_response`: そのstepで送ったsemantic response、選択Candidate列、binary response bytesとhash
- `core_input_ref`: `core_response`のcanonical hash
- `core_output`: response後にcoreが返した全raw frameとcore log、次Request署名、resulting State hash

eventの`step`がresponse順序である。`assert_complete_io_trace`は全eventにresponse/outputがあること、responseのRequest署名、`core_input_ref`、outputのState hashを検証する。

## Random Events

pinned ocgcore API 11.0で構造化するmessageは次である。

| Message | Type | Recorded outcome |
| --- | ---: | --- |
| `MSG_SHUFFLE_DECK` | 32 | playerと完全情報snapshotのdeck順 |
| `MSG_SHUFFLE_HAND` | 33 | player、reported card codes、hand順 |
| `MSG_SHUFFLE_SET_CARD` | 36 | shuffle前後のlocation列 |
| `MSG_SHUFFLE_EXTRA` | 39 | player、reported card codes、Extra Deck順 |
| `MSG_RANDOM_SELECTED` | 81 | playerと選ばれたlocation列 |
| `MSG_TOSS_COIN` | 130 | playerと0/1結果列 |
| `MSG_TOSS_DICE` | 131 | playerと1..6結果列 |
| instrumented script log | `OCG_LOG_TYPE_FROM_SCRIPT` | `Duel.GetRandomNumber`のdraw index、inclusive min/max、result |

raw frame由来の結果は`frame_index`と`message_type`、直接乱数は`log_index`、`log_sequence`、transportを持つ。両方とも`resulting_state_hash`とcanonical `random_event_id`を持つ。`replay.random_events`は初期batchと各response後batchの結果を`after_response_step`付きで連結したcanonical indexである。1 batch内ではscript-log乱数を`log_sequence`順、その後にraw-frame乱数を`frame_index`順で保存する。これは再現可能な格納順であり、同じ`OCG_DuelProcess`呼び出し内のlog callbackとmessage生成の相対時刻を推測するものではない。[cross-channel ordering evidence](../ocgcore/evidence/cross_channel_ordering.json)は、同一native callに両チャネルが存在するfixtureと固定core・監査時upstreamのsource auditを保存する。公開APIに共有sequenceまたはtimestampがないため、cross-channel実発生順は`unavailable`と確定した。raw payloadはhexとSHA-256、log messageはUTF-8文字列とSHA-256を保存する。

完全情報モードではshuffle後zone順を保存する。プレイヤー視点での非公開順序の保存・秘匿方針は#45に従う。

## Randomness Boundary

core seedは4-word値をmanifestへ保存し、`randomness.trace_policy`を`raw-core-frames-and-script-log-random-events-v3`へ固定する。Python randomを使う場合は別のPython seedを必須とする。

監査専用`ocgcore-cross-channel-ordering-v1`は`native_process_call_count=1`、channel別coordinate、canonical格納順、`cross_domain_chronology=unavailable`をfail-close検証する。この追加は既存`ocgcore-output-trace-v2`、`ocgcore-random-event-v2`、manifest trace policyを変更せず、過去Replayの意味も再解釈しない。

ocgcoreの`Duel.GetRandomNumber`自体は結果messageを生成しない。workerは元関数を1回だけ呼ぶLua wrapperをカードscriptより先にロードし、draw index、range、resultを1件の`Debug.Message` recordへ出す。core `logHandler`はこれをclient messageとは別経路でBridgeへ渡す。計装scriptのSHA-256、schema、record format、transport設定はmanifest identityへ含める。source auditとon/off同値証跡は[OCGCore direct random trace](../ocgcore/30_direct_random_trace.md)で定義する。

## Failure Policy

次はReplay破損としてfail-closeする。

- response欠落またはRequest署名不一致
- `core_input_ref`とresponse内容の不一致
- output欠落またはState hash不一致
- random eventが存在しないframeを参照する
- duplicate `random_event_id`
- `replay.random_events`の欠落、重複、順序変更
- coin/dice payloadの範囲外値またはtruncation
- direct Lua random logの書式不正、hash/sequence不一致、範囲外result、draw index不連続

## Contract Tests

- `test_core_output_trace_records_all_random_outcome_types_in_order`
- `test_core_output_trace_rejects_invalid_random_payload`
- `test_core_output_trace_records_direct_lua_random_range_result_and_order`
- `test_direct_random_evidence_matches_fresh_real_core_runs`
- `test_replay_smoke_validates_ordered_responses_and_random_index`
- `test_route_validation_rejects_tampered_replay_response_trace`
