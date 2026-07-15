# Multi-turn Lifecycle and Budget Ownership Contract

Status: Implemented for legal-stop 1/2/3-turn traversal; core duel-end runtime decoding remains [#229](https://github.com/Tao-pyth/ygo-effect-dsl/issues/229)

Last updated: 2026-07-15

## Scope

この契約は、Experiment `0.4`の`turn_limit`、ocgcoreが返すphase/draw/turn遷移、SearchExecutorの資源budget、legal `STOP_LINE`を分離する。Python側はphase、draw、turn counter、発動可否を推測しない。実装識別子は`multi-turn-lifecycle-v1`と`search-budget-ownership-v1`である。

## Ownership

| Owner | Controlled values | Rule |
|---|---|---|
| ocgcore | phase、draw、turn counter、duel end | native process/progress messageを唯一の根拠とする |
| scenario adapter | `turn_limit` | 最終許可turnで`END_TURN`を候補から除外する |
| SearchExecutor | `max_seconds`、`max_nodes`、`max_replays`、`max_depth` | strategyに依存しないhard budgetとして強制する |
| strategy | Action ordering/selection | lifecycleやbudget値を変更しない |

`search-budget-ownership-v1`のbudget優先順位は`max_seconds`、`max_nodes`、`max_replays`、`max_depth`、`turn_limit`で固定する。前3件は次nodeのReplay前、`max_depth`は観測済みnodeの展開前、`turn_limit`はfrontier Action公開前に判定する。この順序は異なる境界を同時刻に検出したと主張するものではなく、各所有者の判定地点を一意にする規則である。

一般prefix Replayの内部応答ガードは`search.max_nodes`を流用しない。prefix modeでは`max(32, prefix Action数 + 1)`を安全ガードとし、探索node budgetと1回のfresh Replayに必要な応答数を分離する。固定fixtureの従来guardは変更しない。

## Lifecycle evidence

各real-core frontierは`request.turn_lifecycle`へ次を保存する。

- `turn`、`phase`、`process_state`、`chain_count`: core観測値。
- `turn_limit`、`turn_limit_reached`: Experiment境界と一致する値。
- `legal_stop`、`forced_response`、`mandatory_response_pending`: 停止可否の根拠。
- `core_end_turn_offered`、`end_turn_allowed`: core提示とscenario filter後の区別。
- `duel_ended`: `process_state=ended`と必ず一致する。
- `boundary_reason`: `duel_end`、`turn_limit`、`legal_stop`、`pending_chain`、`mandatory_response`、`pending_process`のいずれか一つ。
- `lifecycle_id`: 上記semantic payloadのcontent ID。

adapterはschema、全field型、導出flag、`boundary_reason`、`lifecycle_id`を再計算する。欠落、改変、不整合はworker protocol failureとしてfail-closeする。

## Stop rules

1. `chain_count > 0`またはforced response中は、legal stopを作らずcore responseを継続する。
2. legal stopではRouteを記録できる。`STOP_LINE`は探索制御であり、coreへ送るActionではない。
3. `turn < turn_limit`のlegal main phaseでは、core提示`END_TURN`を通常Actionとして探索できる。
4. `turn == turn_limit`では`END_TURN`だけを除外し、同一turn内の他の合法Actionは維持する。legal Routeの`boundary_reason`は`turn_limit`となる。
5. `turn > turn_limit`となるprefix、最終turnからの`END_TURN`、duel終了後のActionは非retryのpath failureとする。
6. core duel endはActionなし、legal stop、`boundary_reason=duel_end`とする。DecisionRequestなしのterminal native batchをRoute化するruntime経路は#229までfail-closeを維持する。

## Evaluation, identity, and lineage

- evaluationは既存どおりcore由来legal checkpointで実行し、turn boundaryそのものを推測評価しない。
- State identityにはcore snapshotのturn/phase/process stateが含まれる。`turn_limit`やlifecycle reportをState hashへ混入しない。
- prefix cache keyはExperiment identityとAction ID列を維持する。native stateは再利用しない。
- `END_TURN`はAction IDとしてprefix/Replay/Route lineageへ残るため、異なるturn経路は同じcache entryにならない。
- `query_api_projection`は観測・集計専用であり、multi-turnでも枝削除に使用しない。
- legal Routeの`SearchRouteSummary.lifecycle_boundary`へ検証済みevidenceを保存する。したがってCLI Search reportはturn budget到達理由を一つの`boundary_reason`として保持する。

## Compatibility

Experiment `0.3a/0.3b`のread/Replay、既存Action、State、Route IDは変更しない。`lifecycle_boundary`は新しいreal-core frontierで生成したRoute summaryだけに追加する任意fieldであり、lifecycleを持たないsynthetic/legacy frontierのsemantic outputは変えない。

## Acceptance evidence

- 純粋契約testで最終turnの`END_TURN`除外、chain/forced継続、overflow failure、content ID改変拒否、duel-end理由を確認した。
- pinned inline deckのfresh worker Replayでturn limit 1/2/3を通し、各turnのmain1、0/1/2回の`END_TURN`、最終Route、State、fresh Replay一致を確認した。
- poolやworker sessionの状態共有は使用していない。
- 実coreによるLP 0/deck-out terminal vectorは#229の完了条件であり、本検証の主張に含めない。
