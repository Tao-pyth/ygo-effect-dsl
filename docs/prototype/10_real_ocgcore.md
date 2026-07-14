# Real ocgcore interruption prototype

Status: executable validation slice

Last updated: 2026-07-14

## Scenario

固定したocgcore API 11.0 DLL、CardScripts `20250420`、BabelCDB `20250419`、seed `(1, 2, 3, 4)` を使う。妨害adapterはversion付き`core-interruption-candidate-policy-v1`に従い、activation、cost、target等をPythonで推測せず、各DecisionRequestでcoreが提示したcandidateだけを決定論的に選ぶ。候補数、request type、player、core制約がpolicyと一致しなければfail-closeする。

Issue #104のprototype matrixは同じstep 5のcore機会から、対象なし手札`14558127`、コストあり手札`27204311`、field発動かつ複数対象`10045474`を検証する。さらにsequence fixtureはcontrolへ1件目、stage1へ2件目の妨害を順に加え、複数のinterruption recordを保持する。

この範囲はfixtureで固定した実core validation sliceである。Issue #114で発動無効、効果無効、optional triggerのタイミング逸失を追加したが、固定DB行へ埋め込みLuaを上書きした代表fixtureに限る。任意カードの妨害探索や最適発動時点へ一般化済みとはみなさない。

General Search MVP（`#119 → #124 → #121 → #120 → #122/#123 → #105`）では、任意YDK/inlineのscenario preflight、決定論的Random Search、ユーザー指定カードの発動機会分岐、3 fixtureの10万logical node evidenceを接続した。妨害応答はcoreのDecisionRequest制約だけから生成し、未検証categoryはfail-closeする。pool別の実core Replay throughput/RSS、Beam Search / MCTS本体、PlayerView Replay、大規模統計UI、一般公開配布はMVP後とする。

## Commands

```powershell
python -m ygo_effect_dsl ocgcore-verify
python -m ygo_effect_dsl ocgcore-assets-verify
python -m ygo_effect_dsl experiment-run examples/experiments/real_core_effect_veiler.yaml --out data/base.route.yaml
python -m ygo_effect_dsl experiment-run examples/experiments/real_core_effect_veiler_interrupted.yaml --out data/interrupted.route.yaml
python -m ygo_effect_dsl experiment-run examples/experiments/real_core_interruption_matrix_targetless.yaml --out data/matrix-targetless.route.yaml
python -m ygo_effect_dsl experiment-run examples/experiments/real_core_interruption_sequence_stage2.yaml --out data/sequence-stage2.route.yaml
python -m ygo_effect_dsl experiment-run examples/experiments/real_core_interruption_effect_negation.yaml --out data/effect-negation.route.yaml
python -m ygo_effect_dsl experiment-run examples/experiments/real_core_interruption_missed_timing.yaml --out data/missed-timing.route.yaml
python -m ygo_effect_dsl experiment-run examples/experiments/real_core_interruption_matrix_sampled_targetless.yaml --out data/sampled-targetless.route.yaml
python -m ygo_effect_dsl experiment-run examples/experiments/real_core_temporary_atk.yaml --out data/temporary-atk.route.yaml
python -m ygo_effect_dsl experiment-run examples/experiments/real_core_action_aggregation.yaml --out data/action-aggregation.route.yaml
python -m ygo_effect_dsl experiment-replay examples/experiments/real_core_effect_veiler_interrupted.yaml data/interrupted.route.yaml
python -m ygo_effect_dsl.spikes.direct_random_trace_evidence --out docs/ocgcore/evidence/direct_random_trace.json
python -m ygo_effect_dsl.spikes.action_aggregation_edge_evidence --out docs/ocgcore/evidence/action_aggregation_edges.json
python -m ygo_effect_dsl.spikes.interruption_negation_timing_evidence
```

ctypesはchild worker内だけで使用する。Replay検証はfresh workerを開始し、request signature、Action ID、State hash、core I/O trace、manifest、評価、Route全体を比較する。

## Evidence

Issue #104 matrixのcontrolはRoute `route_7b90389762bd8ef5d86254c3657a3bb7fe765cb37ff12c4286563d7f810d7ff5`で、step 5をPASSする。3 variantはこのRouteのstep 5を親に持ち、対象なし、cost response、2対象responseをそれぞれ記録する。

段階sequenceのRoute IDとlineageは次のとおりである。

- control: `route_9967b36a2fe7c032765ecf1dcb3dfe677fdafc2eb10168694d0c24eb82d5cd36`
- stage1: `route_a12d4341b6781fbeca5b1fa96cd5c4f08fc89674222e371238147a2a6ef71f87`、controlのfork step 5
- stage2: `route_6932cc27ad8ddce92d78d14fb8c34dd2a172b73483fd808a5aa1d0698fd9bb82`、stage1のfork step 9

stage2はstage1の1件目を同一recordとして継承し、step 9の2件目とstep 10のcost responseを追加する。定義順または親Routeが一致しない場合は拒否するため、`control -> stage1 -> stage2`のlineageとReplay prefixは決定論的である。

- `examples/prototype/real_core_effect_veiler.route.yaml`: 妨害なし8 Action、Route `route_5cac80cf38a05052cfeccc0710bd54498ed96897003db7b2248ef9a63b8220f7`
- `examples/prototype/real_core_effect_veiler_interrupted.route.yaml`: scripted妨害13 Action、Route `route_ec560e9558b534852d8611ae05f55f497416e712ddb5bc3b483bb7ab1c7258fa`
- `examples/prototype/real_core_temporary_atk.route.yaml`: End Phase一時攻撃力8 Action、Route `route_47b95157fc40de5ea0f56ee248b6e52a320d209a3580b69a7105fddf3fdeaebb`
- `examples/prototype/real_core_action_aggregation.route.yaml`: cost/target/option集約14 Action、Route `route_32af1e3bdd1f7a3460f2e236439029dedb5002d0b44e7d51db31756b2124c52c`
- `examples/prototype/real_core_recovery_control_no_card.route.yaml`: 追加カードなしcontrol、success
- `examples/prototype/real_core_recovery_interrupted_no_card.route.yaml`: 追加カードなし妨害、failure
- `examples/prototype/real_core_recovery_control_with_card.route.yaml`: 追加カードありcontrol、success
- `examples/prototype/real_core_recovery_interrupted_with_card.route.yaml`: 追加カードあり妨害、success

両Routeはstep 0〜4が同じで、step 5にbaseのPASSとinterruptedの`ACTIVATE_EFFECT`が記録される。interrupted Routeはstep 6で`SELECT_CARD`を行い、lineageはbase Routeのfork step 5を指す。比較結果はRoute長+5、success維持、exact再合流なしの`goal_only`である。

interrupted RouteはEffect Veilerの`STATUS_DISABLED` bitを`0 → 1 → 0`、temporary ATK Routeは`attack - base_attack`を`0 → 500 → 0`として観測する。いずれもturn 1 End Phase後のturn 2 Main Phase 1でbaselineへ戻り、一時値はdurable評価から除外される。境界規則と集約証跡は`docs/ocgcore/10_temporary_modifiers.md`に記録する。

action aggregation Routeはraw core frameの`REASON_COST`、`HINTMSG_TARGET`、`SELECT_OPTION`、`MSG_CHAINED`からsteps 4〜7を`primary/cost/target/option`へ分類する。追加のversioned fixtureはtarget-loss fizzle、`MSG_CHAIN_NEGATED`、`MSG_CHAIN_DISABLED`、multi-chain、反復cost選択、resolution選択を実コアで固定する。Issue #115でcancelを再監査し、API 11.0 native response `ffffffff`後も`MSG_CHAINED`が出るため、到達不能なraw contract分類を維持した。根拠は`docs/ocgcore/20_action_aggregation.md`と`docs/ocgcore/25_activation_rollback_audit.md`に記録する。

negation/timing fixtureは、同じ手札source・自己cost・request/actionで`Duel.NegateActivation`と`Duel.NegateEffect`だけを切り替え、`MSG_CHAIN_NEGATED`と`MSG_CHAIN_DISABLED`を分離した。別の2-link chainでは非delay `EVENT_TO_GRAVE`が`MSG_MISSED_EFFECT`になり、直後のrequestがpass-onlyであることを固定した。Route ID、payload、negative path failure、適用範囲は`docs/interruption/40_negation_and_missed_timing.md`に記録する。

recovery attribution fixtureは追加カードなし/ありごとに別のexact targetを使い、4 Routeの2×2比較で必要性と十分性を検証する。追加カード`23434538`はstep 9で実際に発動し、妨害ありの結果だけをfailureからsuccessへ変える。schema、最小集合、instance identity制約は`docs/interruption/30_additional_card_attribution.md`に記録する。

全実core Routeは`Duel.GetRandomNumber` wrapperをロードし、計装schema、script SHA-256、core `logHandler` transportをState/Replay runtime identityへ含める。固定実カード・DB runtimeでのdraw値、on/off同値、対応client/core source auditは`docs/ocgcore/30_direct_random_trace.md`に記録する。旧Hint type `199` transportは廃止し、strict replay policyをv3へ更新した。

## Sampled Mode

`real_core_interruption_matrix_sampled_control.yaml`と`real_core_interruption_matrix_sampled_targetless.yaml`は`sampled_private_state`を使う。Replay manifestの`opening_hand_sampling`はseed `20260714`、policy ID `handsampol_cd5607267725cd1baa1c2a4ae1c0c8eabdb837fea227b11d8c150dbc8d3248f4`、selected index `0`、player 1の結果`[14558127, 27204311, 73642296]`、sample ID `handsample_620208ec16527e3c45f61c82a7cbc95c6b7d8027ba04ff67bdc2036b0cee8d6e`を保存する。initial State identityは同じsampling referenceと選択済みprivate stateを識別する。controlはRoute `route_da4cb53e6394eaf1889f69a3e9fc08e8e7c425586bf765ad9015b7ab6f91ab0f`、対象なし妨害はRoute `route_bfeddc3740c6172b11ac16d24c1db27aa655998e31de8394733c4f1796813655`である。

両Routeのopening-hand sampleは同一で、Replay manifestの`interruption_sampling`は`null`である。初手samplingと妨害definition samplingは独立したrandomness fieldであり、scripted妨害の有無で初手を引き直さない。`real_core_effect_veiler_sampled.yaml`の`interruption-sampling-v1`は妨害definitionをsampleする別契約である。

real-core prototypeはPlayerView Replayを出力しない。`player_view`を指定したrunは完全情報traceへ暗黙昇格せず、実行前にfail-closeする。

## Failure Boundary

unsupported definitionや不正なcandidate policyはExperiment path付きconfiguration errorとして`abort_experiment`にする。runtimeでcore candidateが消失・曖昧化した場合は`stop_path`とし、成功Routeや合法候補なしへ変換しない。worker crash/timeoutは`replace_worker`かつretryableとしてfresh workerで再試行し、分類とretry履歴は`ParallelTaskResult v2`へ保存する。
