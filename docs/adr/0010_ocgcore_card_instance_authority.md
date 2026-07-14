# ADR-0010: ocgcore card instance authorityにLua CardIDを採用する

Status: Accepted, v1 frozen and v2 extended

Date: 2026-07-14

Decision Issues: #112, #116

Evidence: `docs/ocgcore/evidence/card_instance_identity.json`, `docs/ocgcore/evidence/card_instance_route_v2.json`, `docs/ocgcore/evidence/card_instance_movement_v2.json`

## Context

ocgcore API 11.0のQueryとraw messageはcard code、controller、location、sequence、positionを返すが、shuffleやsequence圧縮を越える永続個体IDを返さない。`instance_key=controller:location:slot`、`fieldid`、raw messageだけでは同一コード複数枚を安全に追跡できない。

source auditでは`card::cardid`がcard object登録時に一度だけ採番され、Lua `Card.GetCardID()`から取得できる。一方、`fieldid`は状態変化で再採番される。

## Decision

duel内の個体authorityに`Card.GetCardID()`を使う。raw値は公開せず、version付きscope、card code、ownerとcanonical digestを取り、`corecard_` IDへ変換する。v1 trace/evidenceは凍結し、実core Route統合はv2 schemaとして追加する。

v2は各core Request直後にnonce付き完全scanを同期実行する。card-bearing Requestはそのscanが完全である場合だけ`instance_id`と`owner`を付与する。snapshotでは座標`instance_key`と永続`persistent_instance_id`を別fieldとして保持する。

次の値はauthorityに採用しない。

- `fieldid` / `fieldid_r`: 状態変化で再採番される
- Query `instance_key`: 現在座標でありshuffle後に意味が変わる
- raw `MSG_MOVE` / `MSG_SHUFFLE_*`: 永続card IDを含まない
- pointer値: process外へ安全に保存できない

## Information Boundary

raw `cardid`とinstrumentation logはprivate sidecarに限定する。complete-information snapshotは`corecard_`を保持できる。PlayerViewは相手hidden cardのIDを除外し、相手公開cardにはviewer-scoped aliasを使う。公開からhiddenへ移動した後に再公開されたcardへは新しいaliasを発行する。

## Compatibility

- v1: `ocgcore-card-instance-trace-v1`, `ocgcore-card-instance-evidence-v1`, `card-instance-provenance-v1`
- v2: `ocgcore-card-instance-trace-v2`, `card-instance-provenance-v2`, `additional-card-attribution-v2`

無suffixの`build_additional_card_attribution()`はv1のままとし、v2は`build_additional_card_attribution_v2()`で提供する。v1の`duplicate_same_code_policy: reject_ambiguous`は変更しない。

## Consequences

- 同一コード複数枚、shuffle、sequence圧縮、token、相手所有card、control変更を個体単位で区別できる。
- Action、snapshot、Route、attributionが同じauthority IDを使用できる。
- draw/search/salvageとshuffle境界をmessage evidence付きで記録できる。
- Request scan欠落、未知core/source、`MSG_RELOAD_FIELD`、`Debug.ReloadFieldBegin`はfail-closeとなる。
- v2有効時は各Request境界で追加Lua scanを行うため、検証精度と引き換えに実行コストが増える。
