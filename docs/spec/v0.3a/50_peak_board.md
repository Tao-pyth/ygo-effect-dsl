# Peak Board And Legal Stop Specification

Status: Frozen pre-search contract (ADR-0007)

Last updated: 2026-07-13

## Responsibility

Peak Board は探索中に到達した最良の停止可能盤面である。
Peak Board は「見た瞬間に強い盤面」ではない。
合法的にその状態で展開を終えられることを条件とする。

## STOP_LINE And END_TURN

`STOP_LINE` は探索上の停止宣言である。
`STOP_LINE` は core へ送る入力ではなく、現在 State が合法停止可能かを検査するための仮想 Action である。

`END_TURN` は core に送るターン終了入力である。
`END_TURN` 後はエンドフェイズ処理、誘発処理、一時効果の消滅、相手ターン開始処理が発生し得る。

Peak Board は `STOP_LINE` で評価し、Terminal Board は必要に応じて `END_TURN` 後の State として保存する。

## Legal Stop

合法停止可能 State は次を満たす。

- current player が任意行動をこれ以上行わずに進行できる。
- chain 中ではない。
- mandatory effect processing 中ではない。
- core が未応答 DecisionRequest を要求していない。
- phase transition または turn end が合法である。
- unresolved cost / target / selection が残っていない。
- timeout や unsupported message による停止ではない。

合法停止判定は Python の推測ではなく、core が提供する request / state / allowed control action に基づく。

## Stop API

後続実装では次の API を用意する。

```python
def can_stop(state: State, last_request: DecisionRequest | None) -> StopCheckResult:
    ...
```

`StopCheckResult` は次を持つ。

- `is_legal`: 停止可能か。
- `reason`: `ok`, `in_chain`, `mandatory_processing`, `pending_request`, `phase_locked`, `timeout`, `unsupported` など。
- `required_action`: 停止前に必要な Action。ない場合は `None`。

## Peak Update Timing

Peak Board は次のタイミングで更新候補にする。

- Action 適用後に `can_stop` が true になった時。
- `STOP_LINE` を選べる DecisionRequest が提示された時。
- `END_TURN` 前に current board を保存できる時。

chain 中、必須処理中、未応答 request 中、unsupported message 直前の State は Peak Board にしない。

## Tie Break

Peak Board の比較は次の順で行う。

1. success predicate を満たすか。
2. total score が高いか。
3. evaluation vector の lexicographic order。
4. action count が少ないか。
5. resource consumption が少ないか。
6. canonical state hash が小さいか。

最後の canonical state hash は deterministic tie break のためだけに使う。
盤面価値として解釈しない。

## Saved Fields

Peak Board には次を保存する。

- `state_hash`
- `search_hash`
- `evaluation_vector`
- `total_score`
- `success`
- `stop_reason`
- `action_path`
- `request_signature_at_stop`
- `turn`
- `phase`
- `board_summary`

これらはRoute DSLのcheckpointと `result.peak_board` に保存する。Peak BoardはReplay stepとstate hashでcheckpointを参照し、盤面情報をAction履歴から切り離さない。

Terminal Board には Peak Board の field に加えて、`end_turn_action_id`, `post_end_turn_state_hash`, `opponent_turn_start_state_hash` を保存できる。

## Opponent Turn Start

V0.3a の既定評価点は current player が合法停止できる Peak Board である。
相手ターン開始時点まで評価するかは Experiment が明示する。
`evaluate_at: legal_stop` を既定とし、`evaluate_at: opponent_turn_start` は `END_TURN` 後の自動処理を Replay に含められる場合のみ許可する。

## Durability Evaluation

展開直後の一時的な盤面と、End Phaseおよび次ターン開始時の必須処理を通過した盤面は別々に評価する。Experimentは `durability_evaluate_at` に後段の評価時点を保存する。V0.3aの実コアprototypeでは次を用いる。

- before: `legal_stop_before_end_turn`
- after: `opponent_main1_after_end_phase_and_turn_start_processing`

`result.durability` は `peak-durability-v1` として、before/afterが参照するcheckpoint、State hash、turn、phase、evaluation、score、successを保存する。さらにscoreとevaluation vectorの差分、State変化有無、成功条件を維持したかを保存する。afterはbeforeより後のturnでなければならず、各値は参照先checkpointと一致しなければならない。

この比較は盤面の見かけ上の最大値と、ルール処理後に残る価値を混同しないためのものである。`END_TURN` 後の全core応答とTurn/Phase frameをReplayに含められない場合、durability評価を確定値として保存してはならない。

## Acceptance Criteria

- `STOP_LINE` と `END_TURN` が別概念として定義されている。
- chain 中、必須処理中、未応答 request 中は停止不可と明記されている。
- Peak Board は合法停止可能 State のみ対象と明記されている。
- 同点比較規則が deterministic に定義されている。
- End Phase処理前後の評価時点と差分保存形式が定義されている。

## Future Contract Tests

- `test_peak_board_requires_legal_stop`
- `test_peak_board_rejects_state_inside_chain`
- `test_peak_board_rejects_pending_mandatory_processing`
- `test_peak_board_tie_break_is_deterministic`
- `test_end_turn_terminal_board_is_distinct_from_stop_line_peak`
