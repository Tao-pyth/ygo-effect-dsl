# OCGCore direct random trace

Status: logHandler transport, replay contract, and chronology boundary validated

Last updated: 2026-07-14

Implementation Issue: [#93](https://github.com/Tao-pyth/ygo-effect-dsl/issues/93)

Transport validation: [#107](https://github.com/Tao-pyth/ygo-effect-dsl/issues/107)

Chronology validation: [#111](https://github.com/Tao-pyth/ygo-effect-dsl/issues/111)

## Contract

`Duel.GetRandomNumber`はocgcore内部で乱数値を返すが、通常は結果messageを生成しない。実core workerは`constant.lua`と`utility.lua`の後、カードスクリプトを読み込む前に`ygo_effect_dsl_direct_random_trace.lua`をロードする。wrapperは元関数を同じ引数で1回だけ呼び、結果を受け取ってから`Debug.Message`へ記録し、同じ結果を呼び出し元へ返す。

1 drawは`YGO_EFFECT_DSL_RNG_V2|draw_index|minimum|maximum|result`形式の1 log recordで表す。coreの`logHandler`が`OCG_LOG_TYPE_FROM_SCRIPT`として受け取り、Bridgeはprocess batch内の`log_index`とsession全体の`log_sequence`を付けて`direct_lua_random` eventへ変換する。clientへ渡すduel messageは生成しない。prefix不一致の一般logは保持するだけだが、prefix一致recordの書式不正、int32範囲外、inclusive range外result、Replay全体で不連続なdraw indexは破損として拒否する。

Replay manifestの`environment.instrumentation.direct_random_trace`にはenabled、schema、script name、script SHA-256、record format、transport、canonical instrumentation IDを保存する。計装有無やscript変更はruntime identity差分になる。現行schemaはdirect trace `v2`、core output trace `v2`、random event `v2`、`randomness.trace_policy`は`raw-core-frames-and-script-log-random-events-v3`である。旧`MSG_HINT` type `199`のtraceはoutput trace `v1`として構造検証だけを残すが、現行manifestによるstrict replay対象には昇格しない。

## Real-card evidence

`docs/ocgcore/evidence/direct_random_trace.json`は固定BabelCDBの《エフェクト・ヴェーラー》(`97268402`)と固定CardScriptsの`official/c97268402.lua`を使い、合成card dataを追加しない。乱数境界の網羅は独立した監査用Lua probeをcontrol／instrumentedの両方へロードして行う。probe自体を実カード効果として扱わず、実DB・実scriptを読み込めるruntime上でtransportの非干渉性を検査するfixtureである。

- seed: `(1, 2, 3, 4)`
- calls: one-argument `[0,4]`、signed `[-2,2]`、repeated `[0,1]` 2回、int32最小・最大の固定range
- observed draw index: `[1, 2, 3, 4, 5, 6]`
- wrapper on/offで全core message bytes、Request署名、State遷移が完全一致
- wrapper onだけが6件のscript logと`direct_lua_random` eventを記録し、duel messageは0件追加
- synthetic card-data code: `[]`
- trace evidence ID: `rngtraceev_a5ae5e14fff54538d528f125fecaea2d7a1c59e50bf64118c4b6341f400bdb62`

card data source、CardScripts commit、実カードscriptとprobe scriptのSHA-256を証跡へ保存する。

## Transport source audit

`docs/ocgcore/evidence/direct_random_transport.json`は、対応EDOPro commit `650ec7b2273f60733b178d238cf6fec46722d8b4`、固定core commit `158aebe758be3c46249c75d602e3f16d63d2ef31`、監査時のupstream core commit `0764db0c75b3d1d574880d365aa3695ab1f13b43`をsource file hash付きで検査する。固定・upstream coreとも専用random hookは持たないが、`Debug.Message`から`OCG_LOG_TYPE_FROM_SCRIPT`と公開`logHandler`への経路を持つ。

旧hint type `199`は対応clientで名前付き定数や通常routeを持たない一方、duel clientへ直接注入するとswitch処理前のpanel confirmが走り得る。このため「未定義なので安全」とは扱わず廃止した。source auditは`Duel.GetRandomNumber`の内部RNG利用、`Debug.Message`のlog種別、`logHandler`公開経路が変わればfail-closeする。transport evidence IDは`rngtransportev_8f2b59ce4933c3d56cae59c2e176c258517af684582cb17cae833d0b346ab7b4`である。

## Cross-channel chronology boundary

`docs/ocgcore/evidence/cross_channel_ordering.json`は、startup operationが`Duel.GetRandomNumber(0,6)`と`Duel.TossCoin(0,1)`を連続実行するfixtureを固定runtimeで動かす。同じ1回のnative `OCG_DuelProcess`から`OCG_LOG_TYPE_FROM_SCRIPT`の直接乱数recordと`MSG_TOSS_COIN` frameを取得し、batch集約ではなくnative call単位で両チャネルの共存を検証した。

固定core commit `158aebe758be3c46249c75d602e3f16d63d2ef31`と監査時upstream commit `0764db0c75b3d1d574880d365aa3695ab1f13b43`では、`OCG_LogHandler`にsequence/timestampがなく、core messageは独立したqueueから`OCG_DuelProcess`後にbuffer化される。したがって公開APIで検証できるのは同一native callへの所属、log間の`log_sequence`順、frame間の`frame_index`順までであり、logとframeをまたぐ実発生順は復元できない。

監査schema `ocgcore-cross-channel-ordering-v1`はcanonical格納順を`script_log_callback_by_log_sequence`、`core_message_buffer_by_frame_index`と定義し、`canonical_storage_order_is_not_observed_emission_order`を明示する。厳密な全順序にはcore側の共通monotonic counterと公開API拡張が必要である。既存Replay schemaとtrace policyは変更していない。evidence IDは`crossordev_cc63af77cfd44803a17f735a9e8378b97739daec6dfd92c5347cd89131ef7d4f`である。
