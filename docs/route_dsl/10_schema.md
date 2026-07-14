# Route DSL Schema 0.1

Status: Authoritative baseline

Last updated: 2026-07-13

## Root

Route DSL 0.1のroot fieldは次の通りとする。

| Field | Required | Meaning |
| --- | --- | --- |
| `dsl` | yes | 固定値 `ygo-route` |
| `schema_version` | yes | 固定値 `0.1` |
| `route_id` | yes | ルート識別子 |
| `status` | yes | `complete`, `partial`, `failed` |
| `experiment` | yes | 実験条件と識別子 |
| `replay` | yes | 再実行可能な初期条件とAction履歴 |
| `presentation` | no | Replayから導出したAction集約などの表示データ |
| `checkpoints` | yes | Replay stepに対応する主要状態と評価 |
| `result` | yes | success、Peak Board、Terminal Board |
| `interruptions` | no | 指定妨害と適用結果 |
| `lineage` | no | 親ルートと分岐位置 |

## Invariants

- `replay.events[].step` は0から始まる連番とする。
- eventと、そのevent内のActionは同じ `request_signature` を持つ。
- I/O traceを持つReplayでは、全eventの`core_response`, `core_input_ref`, `core_output`とordered `random_events`が整合する。
- `presentation.action_aggregation`がある場合、全Replay eventはちょうど1つのgroupとlinkに対応する。
- `checkpoints[].step` は存在するReplay eventを参照する。
- checkpointの `state_hash` は対応するReplay eventの `state_hash_after` と一致する。
- Peak BoardとTerminal Boardはcheckpointを参照し、`state_hash` が一致する。
- `status: complete` はPeak BoardとTerminal Boardを必須とする。
- interruptionの `at_step` は存在するReplay eventを参照する。
- 表示名、時刻、説明文をReplay決定性やRoute同一性の根拠にしない。

`presentation`はReplayから再生成できる派生データであり、`route_id`のidentity inputへ含めない。Action集約の意味roleが未検証の場合は`presentation.validation.status: provisional`と追跡Issueを保存する。

## Evaluation

`checkpoints[].evaluation` と `result.*.evaluation` は評価内訳であり、カードルールではない。評価器のID、version、設定は `experiment` に保存する。成功条件とscoreは別フィールドとして扱い、再評価時に元のReplayを変更しない。

## Interruption and Recovery

妨害なしルートから分岐した妨害・リカバリルートは、`lineage.parent_route_id` と `lineage.fork_step` で元ルートを参照する。妨害内容は `interruptions[]` に記録する。妨害が合法だったかどうかはocgcore実行結果を保存し、Route DSL validatorがカードルールを推測して判定してはならない。

## Validation Scope

`validate-route` は構造と参照整合性を検査する。次は検査対象外である。

- Actionが遊戯王ルール上合法か
- state hashが実際のocgcore状態と一致するか
- 妨害カードがそのタイミングで使用可能か
- 評価値が盤面を正しく評価しているか

これらはBridge契約テスト、Replay実行、ocgcore、Evaluatorテストで検証する。
