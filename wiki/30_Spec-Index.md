# Spec Index

## Current Contracts

| Document | Responsibility |
| --- | --- |
| [Project Charter](../docs/00_project_charter.md) | 目的、原則、機能範囲 |
| [Architecture](../docs/10_architecture.md) | コンポーネント境界と依存方向 |
| [Route DSL Overview](../docs/route_dsl/00_overview.md) | DSLの責務と非責務 |
| [Route DSL Schema 0.1](../docs/route_dsl/10_schema.md) | root fieldと不変条件 |
| [DecisionRequest](../docs/spec/v0.3a/10_bridge_decision_request.md) | ocgcoreからの意思決定要求 |
| [Action](../docs/spec/v0.3a/20_action.md) | 選択応答と安定ID |
| [Replay](../docs/spec/v0.3a/30_replay_determinism.md) | 再実行と署名照合 |
| [State Identity](../docs/spec/v0.3a/40_state_identity.md) | canonical hashとsearch hash |
| [Peak Board](../docs/spec/v0.3a/50_peak_board.md) | 合法停止と最良途中盤面 |
| [Evaluation / Experiment](../docs/spec/v0.3a/60_evaluation_experiment.md) | score、success、実験条件 |

## Decisions

- [ADR-0001: Replay Baseline](../docs/adr/0001_replay_baseline.md)
- [ADR-0002: Python Does Not Own Rules](../docs/adr/0002_python_does_not_own_rules.md)
- [ADR-0003: Remove Card-Text Conversion from Runtime](../docs/adr/0003_deprecate_dsl_core.md)
- [ADR-0004: Route Information DSL](../docs/adr/0004_route_information_dsl.md)

## Historical Documents

`docs/spec/v0.0/` と `docs/spec/v0.1/` は旧カードテキスト変換の歴史資料です。そこに書かれた `actions[]`、`targets[]`、effect semanticsは現在のRoute DSLやengine Actionの契約ではありません。
