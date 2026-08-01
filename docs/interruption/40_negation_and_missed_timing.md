# Negation and missed timing validation

Status: fixed real-core fixture validation

Last updated: 2026-08-01

## Scope

この検証は ocgcore API 11.0、core commit `158aebe758be3c46249c75d602e3f16d63d2ef31`、固定 CardScripts/CDB、seed `(1, 2, 3, 4)` で実行する。カード ID は固定 DB 行を使い、効果は `real_core.py` の埋め込み Lua で上書きする。任意カードの公式効果一般を検証するものではなく、core の chain、move、timing message と Bridge 境界の検証である。

| Case | Route ID | Core observation |
| --- | --- | --- |
| activation negation | `route_f9c0d6ffbbb3393105822935e1e4563c985b5a7d67cf0f48812c18705beb4585` | `MSG_CHAIN_NEGATED` |
| effect negation | `route_a5de35cd2d68a7d4f4ede3fe985f0e34b4d25f1e0307fe0171487b3ee7484fc1` | `MSG_CHAIN_DISABLED` |
| targeted multi-link | `route_969e43cf278d9451a8a421a12eddaf40632bee7f22f294546c21b642af2f5d61` | 2 targets and `MSG_CHAIN_DISABLED` |
| missed timing | `route_bdfc3b2c63822fd00988dc80a93db97b68753a56a4072c59dab073292c3bba0b` | `MSG_MISSED_EFFECT` |
| damage step | `route_19268ac39676f885d9fdb6016d5ddf7edfad880cc1d7031e64dfa51f480ae4e1` | hand `chain:0` exposed during battle damage processing |

## Boundaries

activation/effect negation の対照は player 1 手札の `14558127` を同じ step 5 で発動する。DecisionRequest、Action、source、手札から墓地への `REASON_COST` move は一致し、operation だけを `Duel.NegateActivation(ev)` と `Duel.NegateEffect(ev)` で切り替える。解決 frame は前者が message 75、後者が message 76 になるため、発動無効と発動済み効果の無効を Python 側で推測しない。

missed timing は core の `MSG_MISSED_EFFECT` と、直後の pass-only `select_chain` request を証跡にする。negative experiment は Python 側で候補を合成せず、実際の core request と指定 target の不一致を `path_failure + stop_path + retryable=false` として返す。

damage step は `real_core_interruption_damage_step.yaml` の固定 fixture だけを対象にする。Lua fixture は `EFFECT_FLAG_DAMAGE_STEP + EFFECT_FLAG_DAMAGE_CAL` と `PHASE_DAMAGE / PHASE_DAMAGE_CAL` 条件を持ち、証跡は core が step 16 の `select_chain` に手札 `14558127` の `chain:0` を出したこと、Action が source を保持したこと、cost move が墓地へ発生したことに限定する。Python 側では効果テキスト、合法性、timing を推測しない。

## Validator and evidence

`ocgcore-interruption-validation-v1` は Replay から chain lifecycle、move reason、missed-effect payload、chain/effect request、Action occurrence、State hash 遷移を再計算する。Route validator は `presentation.interruption_validation_evidence` の保存値と再計算値を比較し、改ざんを `ocgcore_interruption_validation_evidence_mismatch` として拒否する。

negation/missed timing 証跡は `docs/interruption/evidence/real_core_negation_timing.json`、evidence ID は `negtimeev_d27be785a4917eeae926d25ba1254580abb58e186cb9af21739364b9fb1b24c3` である。damage step 証跡は `docs/interruption/evidence/real_core_damage_step.json`、evidence ID は `damagestepev_3158b0ba058fbd5763a95656db85f71f98e1fc28c395dfa180a3d58fa5d02a16` である。damage step evidence は fresh real-core replay 2 回の route/replay 一致、分類器の登録済み fixture 限定 support、未登録 category と曖昧 candidate shape の fail-close を検査する。

## Production claim limit

production claim は固定 fixture、固定 core/API、固定 script hash、観測済み message/payload に限定する。`standard` は固定 fixture scope で検証済み、`damage_step` は pinned fixture scope で検証済みだが default false のままである。`damage_step` は明示的に validation policy へ登録した検証専用経路だけが通り、一般的な damage step 裁定を保証しない。

| Priority | Category | Current policy | Follow-up |
|---|---|---|---|
| 1 | damage step | verified pinned fixture; default fail-close | [#207](https://github.com/Tao-pyth/ygo-effect-dsl/issues/207) |
| 2 | simultaneous trigger ordering | fail-close | [#208](https://github.com/Tao-pyth/ygo-effect-dsl/issues/208) |
| 3 | mandatory trigger | fail-close | [#209](https://github.com/Tao-pyth/ygo-effect-dsl/issues/209) |
| 4 | SEGOC | fail-close | [#210](https://github.com/Tao-pyth/ygo-effect-dsl/issues/210) |

category を昇格するには、固定 core/API/source/asset hash、fresh real-core Replay 2 反復、Route/State lineage、DecisionRequest candidate と Action response の証跡、改ざん検知 validator が必要である。Python 側で効果、合法性、timing、ordering を推測してはならない。全 `EVENT_*` と任意カード固有裁定は、これら Issue を完了しても対象外であり、別の qualification が必要になる。
