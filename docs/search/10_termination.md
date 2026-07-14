# Search Termination

Status: V0.1 implementation contract

Last updated: 2026-07-13

## Responsibility

`SearchTerminationMonitor` は探索を止める理由を判定し、最初の停止理由を `search-termination-v1` として固定する。合法停止ActionやPeak Board判定は所有しない。Search frontierが空になった場合は `exhausted`、resourceまたはgoal条件で止める場合は対応するreasonを返す。

## Config

Experiment `0.3a` の既存境界を次のように使う。schemaへ新しい必須fieldは追加しない。

```yaml
search:
  strategy: exhaustive
  budget:
    max_nodes: 10000
    max_seconds: 60
  parameters:
    termination:
      max_depth: 40
      max_replays: 20000
      stagnation_nodes: 1000
      max_transition_repetitions: 3
      stop_on_success: false
      target_score: null
```

`max_nodes` と `max_seconds` は `search.budget` だけに置き、termination内での重複指定を拒否する。depthはrootを0とし、`depth >= max_depth` のnodeを展開しない。node/replay budgetは観測数がlimitへ到達した時点で停止する。

## Reasons

- `goal_reached`: success predicateまたはtarget scoreへ到達。
- `max_depth`, `max_nodes`, `max_replays`, `max_seconds`: resource上限。
- `stagnation`: strictなbest score改善が指定node数発生しない。
- `repeated_transition`: 同じ `(state_before, action_id, state_after)` が上限回数発生。
- `exhausted`: frontierが空になった。

同じAction IDを異なるStateで使っただけではloopと判定しない。Action名だけの反復検出は正常な召喚・選択を誤停止させるため禁止する。

## Determinism

depth/node/replay/goal/stagnation/transition budgetは同じ候補順と評価結果に対して決定的である。`max_seconds` はmachine負荷で探索範囲が変わるため、再現性を要求するbenchmarkの唯一budgetにしない。time budgetを使ったrunは停止decisionのelapsed time、node数、Replay数を保存し、同じbest Routeを保証する条件と「同じ時間で止まる」条件を混同しない。

停止decisionはreason、depth、nodes、replays、elapsed、best score、reason固有detail、canonical decision IDを持つ。一度停止したmonitorは後続観測でreasonを変更しない。
