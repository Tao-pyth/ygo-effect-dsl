# Negation and missed timing validation

Status: fixed real-core fixture validation

Last updated: 2026-07-14

## Scope

この検証はocgcore API 11.0、core commit `158aebe758be3c46249c75d602e3f16d63d2ef31`、固定CardScripts/CDB、seed `(1, 2, 3, 4)`で実行する。カードIDは固定DB行を使うが、効果は`real_core.py`の埋め込みLuaで上書きする。したがって、各カードの公式効果一般ではなく、coreのchain、move、timing messageとBridge境界の検証である。

検証対象は次の4 Routeである。

| Case | Route ID | Core observation |
| --- | --- | --- |
| activation negation | `route_f9c0d6ffbbb3393105822935e1e4563c985b5a7d67cf0f48812c18705beb4585` | `MSG_CHAIN_NEGATED` |
| effect negation | `route_a5de35cd2d68a7d4f4ede3fe985f0e34b4d25f1e0307fe0171487b3ee7484fc1` | `MSG_CHAIN_DISABLED` |
| targeted multi-link | `route_969e43cf278d9451a8a421a12eddaf40632bee7f22f294546c21b642af2f5d61` | 2 targets and `MSG_CHAIN_DISABLED` |
| missed timing | `route_bdfc3b2c63822fd00988dc80a93db97b68753a56a4072c59dab073292c3bba0b` | `MSG_MISSED_EFFECT` |

## Negation boundary

activation/effect negationの対照はplayer 1手札の`14558127`を同じstep 5で発動する。DecisionRequest、Action、source、手札から墓地への`REASON_COST` moveは一致し、operationだけを`Duel.NegateActivation(ev)`と`Duel.NegateEffect(ev)`で切り替える。解決frameは前者がmessage 75、後者がmessage 76となるため、発動無効と発動済み効果の無効を人間向け文言で推定しない。

targeted caseはplayer 1 SZONEの`10045474`からplayer 0 MZONEの2体をcore candidateとして選ぶ。sourceはSZONEに残りcost moveはなく、2 chain linkとmessage 76を観測する。このcaseは複数targetのBridge/Action境界を検証する対照であり、targetless effect-negation caseとは別のfixtureである。

## Missed timing boundary

player 0の`23434538`がchain link 1を作り、player 1 SZONEの`10045474`がchain link 2でplayer 0 MZONEの`91800273`を墓地へ送る。`91800273`はdelay flagを持たないoptional `EVENT_TO_GRAVE` triggerである。link 2解決後に未解決link 1へ戻ると、coreは次の順序を出力する。

`MSG_CHAIN_SOLVING(2) -> MSG_MOVE -> MSG_CHAIN_SOLVED(2) -> MSG_CHAIN_SOLVING(1) -> MSG_MISSED_EFFECT -> MSG_CHAIN_SOLVED(1) -> MSG_CHAIN_END`

message 120 payloadは`<BBIII>`として解析し、controller 0、graveyard location 16、code `91800273`を照合する。直後のplayer 0 requestは`select_chain`で候補が`control:pass`だけであり、同カードをsourceとするActionは存在しない。

negative experimentは同じstep 8で`91800273`の`select_effect_yes_no`を要求する。Python側で候補を合成せず、actual core requestとの不一致を`path_failure + stop_path + retryable=false`として返す。fresh worker 2回でFailureRecordとstdout digestは一致する。

## Validator and evidence

`ocgcore-interruption-validation-v1`はReplayからchain lifecycle、move reason、missed-effect payload、chain/effect request、Action occurrence、State hash遷移を再計算する。Route validatorは`presentation.interruption_validation_evidence`の保存値と再計算値を比較し、改ざんを`ocgcore_interruption_validation_evidence_mismatch`として拒否する。

証跡は`docs/interruption/evidence/real_core_negation_timing.json`、evidence IDは`negtimeev_d27be785a4917eeae926d25ba1254580abb58e186cb9af21739364b9fb1b24c3`である。11 verificationは全てtrueで、effect-negationとmissed-timing Routeはfresh worker再実行でReplayとRoute IDが一致する。

## Production claim limit

production claimは上記4 fixture、固定core/API、固定script hash、観測済みmessage/payloadに限定する。任意カードの効果文からnegation種別やmissed timingを推測する機能、全`EVENT_*`、damage step、simultaneous trigger ordering、mandatory trigger、SEGOC、実カード固有裁定は未検証である。これらを一般化する場合は別fixtureとIssueを追加する。
