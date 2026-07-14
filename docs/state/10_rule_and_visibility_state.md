# Rule history, constraints, and visibility state

Status: V0.3a executable contract

Last updated: 2026-07-13

## Responsibility

Stateは将来の合法手に影響するcore由来情報を保持するが、その情報からPythonがカードルールを実行しない。`RuleState`と`VisibilityState`は観測値のcanonical保存形式であり、合法性の正本はocgcore / EDOPro Luaである。

## Rule State

`ygo-rule-state-v1`は次を保持する。

- player別`normal_summons_remaining`, `extra_normal_summons`, `special_summon_allowed`
- `usage_key`, player, uses/limit, reset境界を持つeffect usage
- stable `constraint_id`, kind, player, source, payloadを持つactive constraint
- constraintの`starts_at`と`expires_at`

召喚権、使用済み効果、constraintはID順にcanonicalizeし、player/key/ID重複を拒否する。これらの値が異なるStateは別`state_id`になる。

## Coordinates And Expiration

開始座標はturn、phase、chain index、turn内Action indexを持つ。期限境界は次を表現できる。

- `end_of_chain`
- `end_of_phase`
- `end_of_turn`
- `start_of_turn`
- `duel_end`
- `absolute_coordinate`

phase境界はphase、turn境界はturn、absolute境界はturnとphaseを必須とする。期限を表示・比較できることが責務であり、期限到達時の制約解除処理はcoreが所有する。

## Visibility State

`ygo-visibility-state-v1`はplayer別の`known_private_by_player`と`unknown_private_by_player`を分離する。

- `complete_information`: viewerとunknown private stateを許可せず、必要な非公開情報をknown側へ保持する。
- `player_view`: viewerを必須とし、別playerのprivate stateをknown側へ入れることを拒否する。公開済み情報はpublic stateへ置く。
- `sampled_private_state`: viewerを持たず、sampler ID/version/seed等の`sampling_reference`を必須とする。

情報モードごとの詳細な実験・評価リーク方針は#45で追跡する。

## Query API Projection

現在のocgcore Query API snapshotはchainと盤面を取得できるが、effect usage、残り召喚権、全てのLua constraintを取得できない。したがってcanonical sectionへ`unavailable_from_ocgcore_query_api`を保存し、`missing_fields`と`query_api_projection` completenessを維持する。空値を「制約なし」「未使用」と解釈してはならない。

## Contract Tests

- `test_state_hash_changes_when_normal_summon_right_changes`
- `test_state_hash_changes_when_once_per_turn_key_changes`
- `test_constraint_expiration_preserves_start_and_end_boundaries`
- `test_visibility_state_enforces_information_mode_boundaries`
