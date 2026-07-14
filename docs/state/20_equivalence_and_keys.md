# Exact and approximate State equivalence

Status: V0.3a executable contract

Last updated: 2026-07-13

## Exact Equivalence

2つのStateを完全同値と判定する必要十分条件は次である。

1. 両方が`completeness: exact`である。
2. State ID schema versionが一致する。
3. `information_mode`, `viewer`, `sampling_reference`が一致する。
4. canonical `state_id`が一致する。

`query_api_projection`や`missing_fields`を持つStateは、hashが同じでも完全同値とは判定しない。cross-information-mode比較はfalseではなく契約違反としてfail-closeする。

## Exact Key Uses

次はexact keyだけを使用する。

- Replay validation
- legal Action / legality cache
- branch pruningまたはnode mergeの最終判定
- exact transposition table

exact Stateを構成できない場合、これらを推測で継続せず`StateEquivalenceError`とする。

## Approximation Policy

近似keyはversioned `ygo-state-approximation-policy-v1`から生成する。policyはID、version、除外path、利用目的、risk notesを必須とし、policy identity自体をkeyへ含める。policy変更時は既存cache keyが自動的に変わる。

現在除外できるのは`private_state`配下だけである。`constraints`, `history`, `pending_request`, `engine_state`, information mode/completeness/schemaを除外してはならない。path欠落、重複、親子overlapはfail-closeする。

近似keyを利用できる目的は次に限定する。

- `transposition_hint`: exact比較候補を集めるbucket
- `evaluation_cache`: evaluator/Experimentが除外情報へ依存しないと明示したcache
- `search_ordering`: 展開順序のheuristic

`replay_validation`, `legality_cache`, `branch_pruning`へ近似policyを渡すことは禁止する。近似`StateKey.requires_exact_confirmation`は常にtrueであり、同じkeyだけを理由にnodeをmergeまたは削除してはならない。

## Risks

private deck orderを除外した2 Stateは現在盤面が同じでも次drawが異なる。未知手札やsample差を落とすと応答可能性や期待値が異なり得る。近似同値は探索量を減らす代わりに将来分岐差を隠すため、risk notesとExperiment policy ID/versionを結果へ保存する。

## Cache And Pruning Rules

- exact cacheは`state_id`を使用し、schema/information mode/completenessを暗黙に含む。
- approximate cacheは`search_state_` keyと`state_policy_` hashを併記する。
- evaluator versionや設定はState policyとは別にcache keyへ含める。
- approximate bucket hitは再利用候補であり、Action合法性やReplay一致を保証しない。
- pruning前はexact State比較またはcore再検証を必須とする。
- policy version変更時は旧approximate cacheを無効化する。

## Contract Tests

- `test_exact_equivalence_is_necessary_and_sufficient_for_same_identity`
- `test_exact_equivalence_rejects_incomplete_or_cross_mode_state`
- `test_approximate_key_can_group_private_order_but_requires_confirmation`
- `test_approximation_never_drops_constraints_or_enables_direct_pruning`
- `test_approximation_policy_version_invalidates_cache_key`
