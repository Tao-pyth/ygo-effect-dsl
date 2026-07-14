# V0.3a Boundary Specification Overview

Status: Frozen pre-search contract (ADR-0007)

Last updated: 2026-07-13

## Purpose

V0.3a は探索アルゴリズムを実装する前に、境界、再現性、状態表現を固定する仕様フェーズである。
Random Search、Beam Search、MCTS、妨害リカバリの品質は、Bridge、Action、Replay、State の契約が安定していることに依存する。
これらの探索成果はRoute DSLとして保存する。したがってV0.3a境界仕様とRoute DSL 0.1を合わせて、後続実装者が型、保存形式、署名、停止条件、評価設定、成果物の参照関係を追加判断なしで実装できる状態を完了条件とする。

## Priority

V0.3a で最優先に仕様化する領域は次の順である。

1. Bridge / DecisionRequest
2. Action
3. Replay determinism
4. State identity
5. Peak Board / legal stop
6. Evaluation / Experiment
7. Route DSL

この順序は依存関係である。
ActionはDecisionRequestへの応答であり、ReplayはDecisionRequestとActionの履歴であり、StateはReplayと探索の同値判定対象であり、Peak BoardとEvaluationはStateの意味に依存する。Route DSLはこれらを一つの探索成果物として関連付ける。

## Non-Goals

V0.3a では次を実装しない。

- full ocgcore bridge
- real duel execution
- Random Search / Beam Search / MCTS
- interruption injection
- recovery search
- Python-only rule executor
- production search runtime

Python はルールを所有しない。
合法性、状態遷移、チェーン処理、カード効果解決の真実源は ocgcore / EDOPro Lua に置く。

## Completion Definition

V0.3a は次を満たした時点で完了とする。

- DecisionRequest の必須フィールド、署名、応答形式が文書で固定されている。
- Action の粒度、識別子、Replay 用表現、表示用表現が分離されている。
- 表示用複合Actionから原子的Actionへの対応とRoute差分keyが定義されている。
- Replay が「同じ履歴なら同じ DecisionRequest に戻る」ことを最上位保証として定義している。
- State の完全同値 hash と探索用近似 hash が別物として定義されている。
- Peak Board が合法的に停止できる State のみを対象にすると定義されている。
- Experiment が success predicate と score evaluator を分離している。
- Route DSLがReplay、checkpoint、Peak Board、Terminal Board、評価、妨害lineageを関連付けている。
- 各仕様書に後続実装で必要な契約テスト名が列挙されている。

## Acceptance Criteria

- V0.3a が探索実装ではなく境界仕様フェーズであることが明記されている。
- 6領域の優先順位と依存関係が明記されている。
- Route DSLが境界仕様の成果を保存する契約として位置付けられている。
- Python がルールを所有しない方針が維持されている。
- V0.3a の非目標が明記されている。
- 後続実装で必要な契約テストの最低限の一覧がある。

## Future Contract Tests

V0.3a 後の実装で最低限必要な契約テストは次である。

- `test_bridge_decision_request_contract`
- `test_bridge_message_decode_fixture`
- `test_action_round_trip`
- `test_replay_returns_to_same_decision_request`
- `test_replay_rejects_request_signature_mismatch`
- `test_state_canonical_hash_is_stable`
- `test_state_search_hash_is_declared_approximate`
- `test_peak_board_requires_legal_stop`
- `test_experiment_schema_validation`
- `test_evaluator_cache_key_changes_with_evaluator_version`
- `test_minimal_route_example_is_valid`
- `test_route_rejects_checkpoint_replay_state_mismatch`
