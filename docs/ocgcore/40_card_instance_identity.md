# OCGCore card instance identity

Status: v1 authority frozen / v2 real-core integration validated

Last updated: 2026-07-14

Validation Issues: [#112](https://github.com/Tao-pyth/ygo-effect-dsl/issues/112), [#116](https://github.com/Tao-pyth/ygo-effect-dsl/issues/116)

Decision: [ADR-0010](../adr/0010_ocgcore_card_instance_authority.md)

## Authority

永続個体のauthorityは、pinned ocgcore API 11.0のLua `Card.GetCardID()`である。Queryの`instance_key`は`controller:location:slot`という現在座標であり、shuffle、sequence圧縮、control変更を越える個体IDには使わない。raw `cardid`はduel内のprivate transportに限定し、core・asset・fixture・instrumentationを固定した`cardinstscope_`と組み合わせて`corecard_` IDへ変換する。

`ocgcore-card-instance-trace-v1`と既存evidenceは凍結する。v2は`ocgcore-card-instance-trace-v2`、`card-instance-provenance-v2`として別schemaを追加し、v1の意味やgoldenを変更しない。

## Request Boundary

v2は`runner.card_instance_provenance: v2`で明示的に有効化する。各`duel.process()`が`AWAITING_RESPONSE`へ到達した直後、専用`capture_card_instance_scan()`がnonce付きscanを`OCG_LoadScript`で同期実行する。trackerは最後の`BEGIN/CARD/END`が期待nonceと一致し、件数・scan ID・observation indexが連続している場合だけcard-bearing Requestをenrichする。

Request候補はscanの現在座標から一意に解決し、`CardRef.instance_id`と正しい`owner`を付与する。scan欠落、古いnonce、重複座標、重複card ID、code不一致、未観測候補はfail-closeする。`owner=controller`やcard codeだけのfallbackはv2では使用しない。

## Snapshot And Player View

完全情報snapshotでは、座標用`instance_key`を維持しつつ、別fieldの`persistent_instance_id`と`owner`を付与する。queryの`code`・`owner`はauthorityと完全一致させる。召喚処理中など、Lua field groupが一時的に列挙しないcardは、同じprocess batch内の直前event scanとqueryが一意に一致した場合だけsnapshotへ結合する。Request候補の解決条件は緩和しない。

PlayerViewでは相手のhidden cardを除外し、raw `cardid`、`corecard_`、probe logを公開しない。相手cardが公開領域へ戻った場合はviewer別aliasを新規発行し、hidden期間を越えて同一個体だと推測できないようにする。hidden card IDだけを入れ替えた場合、complete state hashは変化するがvisible hashは変化しない。

## Movement Ledger

v2 provenanceはscan間の個体移動を`movement_transitions`へ記録する。deckからhandへの移動は、同じRequest batchに`MSG_DRAW`があれば`draw`、なければ`search`とする。graveからhandは`salvage`、controller変更は`control_change`、同一location内のslot変更は`sequence_change`として記録する。hand/deck/set shuffleは`MSG_SHUFFLE_*`を`shuffle_boundaries`へ保存し、座標対応を推測しない。

実core fixtureはdraw、search、salvage、hand/deck/set shuffle、fieldからgrave/banishedへの移動、control変更、sequence圧縮を別Request batchで検証する。証跡は`docs/ocgcore/evidence/card_instance_movement_v2.json`である。

## Evidence

- v1 authority: `docs/ocgcore/evidence/card_instance_identity.json`
- v2 Route / attribution: `docs/ocgcore/evidence/card_instance_route_v2.json`
- v2 movement: `docs/ocgcore/evidence/card_instance_movement_v2.json`
- v2 attribution golden: `tests/golden/additional_card_attribution_v2.json`

v2 Route evidenceは4本のcontrol/interrupted Routeを別Python processで2回生成し、Action ID、全State hash、Request signature、Route ID、provenance ID、attribution IDが一致することを確認する。公開Route JSONにraw `card_id`キーとinstrumentation prefixが存在しないことも検査する。

## Unsupported Paths

`MSG_RELOAD_FIELD`はpersistent authorityを無効化するためprotocolで拒否する。card script内の`Debug.ReloadFieldBegin`もsource auditで拒否する。未知のcore API、binary、asset lock、未計装Request、scan不完全、overlayなどauthority未定義の候補は推測せずfail-closeする。
