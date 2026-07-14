# Examples Gallery

完全な例は [minimal_route.yaml](../examples/route_dsl/minimal_route.yaml) を参照してください。

## Root

```yaml
dsl: ygo-route
schema_version: "0.1"
route_id: route_example_normal_summon
status: complete
experiment:
  experiment_id: fixed_hand_no_interruption
```

## Replay Event

```yaml
replay:
  schema_version: "0.3a"
  events:
    - step: 0
      request_signature: req_example_normal_summon
      action:
        action_id: act_example_normal_summon
        request_signature: req_example_normal_summon
        kind: NORMAL_SUMMON
        player: 0
        selections: []
```

eventとActionの `request_signature` は一致させます。Actionの表示名はReplay照合の根拠にしません。

## Checkpoint and Result

```yaml
checkpoints:
  - step: 0
    state_hash: state_after_normal_summon
    board_summary: {}
    evaluation:
      resource_balance: 1.0
result:
  success: true
  peak_board:
    checkpoint_step: 0
    state_hash: state_after_normal_summon
    score: 1.0
    evaluation:
      resource_balance: 1.0
```

Peak Boardはcheckpointを参照し、state hashを一致させます。評価内訳を変更して再評価してもReplay Action列は変更しません。

## Recovery Lineage

```yaml
interruptions:
  - interruption_id: ash_on_search_1
    at_step: 4
    status: applied
lineage:
  parent_route_id: route_without_interruption
  fork_step: 4
```

妨害が実際に使用可能かどうかはocgcoreで判定し、結果をRoute DSLへ記録します。
