# OCGCore action aggregation evidence

Status: lifecycle edges real-core verified for API 11.0; cancel remains an unreachable raw contract

Last updated: 2026-07-14

## Fixture

`action_aggregation_lifecycle_v1`は固定Lua scriptと同一カード2枚の開始手札を使う。player 0が1枚を召喚し、任意triggerをYesで発動して、残る手札をcostとして墓地へ送り、場のカードをtargetにして2択optionを選ぶ。script本文とSHA-256はReplay manifestへ保存される。

- Route: `route_32af1e3bdd1f7a3460f2e236439029dedb5002d0b44e7d51db31756b2124c52c`
- Action count: 14
- composite steps: `[4, 5, 6, 7]`
- roles: `[primary, cost, target, option]`
- evidence ID: `actaggev_f91b84f4ceef778388cf3a79a22cdeb4f0dd73ec1148fbcfc4e8251b975b3405`

## Evidence basis

cost step 5は選択card refと`MSG_MOVE`の移動前位置が一致し、reason `0x4080`が`REASON_COST=0x80`を含む。target step 6は要求batchの`MSG_HINT`が`HINT_SELECTMSG=3`かつ`HINTMSG_TARGET=551`である。option step 7は`MSG_SELECT_OPTION=14`から生成されたDecisionRequestである。同stepへの応答後、`MSG_CHAINED=71`を観測してgroupを閉じる。

Effect VeilerのCardScriptsはtarget選択前に`HINTMSG_FACEUP`を使うため、同じ`SELECT_CARD`でも`target`と断定せず`selection`へfallbackする。表示都合でカードテキストやscript関数名を解析しない。

## Validation

`derive_ocgcore_action_aggregation`は保存済みraw core frameとatomic Actionだけからgroup、role、根拠を再計算する。`presentation.validation.status: validated`のRouteではvalidatorが再計算結果との完全一致を要求する。role、group、frame根拠、evidence IDの改変は検証エラーになる。

## Lifecycle edge evidence

`docs/ocgcore/evidence/action_aggregation_edges.json`は、API 11.0 raw Replayから次を再計算する固定証跡である。evidence IDは`actaggedgeev_c9598b8286c18a69ae486404a8f76495a36d374acf396d663aa1bf59da523584`。

- cancel: cancelable selectionへの`DECLINE`で`[primary, control]` groupを閉じる。
- fizzle/disable: `MSG_CHAIN_DISABLED`後のActionをactivation groupへ含めない。
- multi-chain/negation: 2つのactivation groupを分離し、逆順解決と`MSG_CHAIN_NEGATED`後も後続Actionを吸収しない。
- multi-selection: 連続する2回のcost requestを同じactivation groupで`cost, cost`と記録する。
- resolution selection: `MSG_CHAIN_SOLVING`後のcard/option応答を、activation setupとは別の`resolution` groupへまとめる。

各raw fixtureは集約前後のatomic Replay digest一致を検証する。実コアcorpusでは、interruption matrixが`MSG_CHAIN_NEGATED`、`MSG_CHAIN_DISABLED`、2リンクを個別に固定する。`action_aggregation_selection_edges_v1`はRoute `route_0ec912d6b69cde4a3bce62d05937861afe932618b191504f9a5c3c148639a77b`で`[primary,cost,cost]`と独立した`[resolution,resolution]`を固定する。`action_aggregation_target_loss_v1`はcontrol Route `route_b03ee526064cbccbe4b5242875f313fd3ae4ce78545de5817ba195a714438553`からRoute `route_5c6737e3a888dc919dfdf6f19c0c9d1ea2178738a45eaa2aa7cdb933fd847b43`へforkし、対象cardのMZONEからbanishedへの`MSG_MOVE`とfield count 2から1への差分を固定する。各Routeはfixture script/hash、card database commit/hashと使用行、core identity、seedをmanifestへ保存し、fresh workerで再検証する。

固定対象はocgcore API 11.0である。2026-07-14のIssue #115監査でも、cancelable `MSG_SELECT_CARD`へnative cancel応答`ffffffff`を返すと`MSG_CHAINED`が生成された。最新releaseは`v11.0`のままであり、未release `master` commit `0764db0...`もAPI 11.0かつ該当source contractは同じである。ただし`master` binaryは実行していないため、source audit以上のclaimは行わない。cancelは引き続き`raw_replay_contract_core_unreachable`であり、custom core patchは採用しない。詳細は`docs/ocgcore/25_activation_rollback_audit.md`を参照する。

再生成コマンド:

```bash
python -m ygo_effect_dsl.spikes.action_aggregation_edge_evidence --out docs/ocgcore/evidence/action_aggregation_edges.json
python -m ygo_effect_dsl.spikes.activation_rollback_audit --audit-date 2026-07-14
```
