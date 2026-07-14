# OCGCore temporary modifier observation

Status: two representative End Phase resets verified

Last updated: 2026-07-13

## Decision

一時効果はカードテキストやPython側の推測だけでは永続値として評価しない。固定したLuaスクリプトのreset指定と、OCGCore queryによる適用前・適用中・境界通過後の3点観測がそろい、値がbaselineへ戻った場合だけ`observed_expired`とする。どちらかを取得できない場合は`unverified`のままdurable valueを0とする。

## Verified cases

実OCGCore API 11.0と固定アセットで、次の2ケースをRouteへ保存した。

- 一時攻撃力: 固定fixtureの`RESET_PHASE+PHASE_END`により、`attack - base_attack`が`0 → 500 → 0`となる。
- 効果無効: CardScriptsの《エフェクト・ヴェーラー》により、対象カードの`STATUS_DISABLED` bitが`0 → 1 → 0`となる。

両ケースともactive値は一時値として`raw`へ記録するが、相手ターンMain Phase 1のdurable評価では`excluded_temporary`へ移し、`durable: 0`とする。各観測点はcheckpoint step、turn、phase、exact State hashを保持する。

## Boundary normalization

OCGCoreのreset指定は、実際に境界後のquery transitionを観測できた場合に限り次のDSL境界へ正規化する。

| OCGCore reset | DSL boundary | 必須証跡 |
| --- | --- | --- |
| `RESET_CHAIN` | `end_of_chain` | chain解決後のquery |
| `RESET_PHASE`とEnd Phase以外のphase flag | `end_of_phase` | phase移行後のquery |
| `RESET_PHASE`と`PHASE_END` | `end_of_turn` | `END_TURN`処理後のquery |

turn countや自分・相手ターン条件を含むresetは、該当境界を実際に通過するfixtureを追加するまで`unverified`とする。公開API v11は任意のeffect/resetを列挙できないため、source pinだけで消滅を断定してはならない。

## Evidence

```powershell
$env:PYTHONPATH='src'
python -m ygo_effect_dsl.spikes.temporary_modifier_evidence --out docs/ocgcore/evidence/temporary_modifiers.json
```

- 攻撃力Route: `examples/prototype/real_core_temporary_atk.route.yaml`
- 効果無効Route: `examples/prototype/real_core_effect_veiler_interrupted.route.yaml`
- 集約証跡: `docs/ocgcore/evidence/temporary_modifiers.json`
- evidence ID: `tempevidence_fc5ef2d45da723175780db8a5fa5c89d4b2685d3663adc3490893341aa3c63f1`

`temporary_modifier_observation`自体をRoute validatorで再計算するため、観測値、境界、source ref、observation IDの改変は検証エラーになる。
