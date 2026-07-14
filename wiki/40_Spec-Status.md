# Spec Status Matrix

基準日: 2026-07-13

| Area | Status | Evidence |
| --- | --- | --- |
| Project boundary | specified | Project Charter / Architecture |
| Python does not own rules | accepted | ADR-0002 |
| Route DSL responsibility | specified | ADR-0004 / Route DSL Overview |
| Route DSL 0.1 shape | minimally implemented | schema doc / validator / fixture |
| DecisionRequest signature | minimally implemented | engine/bridge + contract tests |
| Action ID | minimally implemented | engine/action + contract tests |
| Replay signature checks | minimally implemented | engine/replay + contract tests |
| Real ocgcore Bridge | not implemented | next runtime milestone |
| Replay executor | not implemented | next runtime milestone |
| State hash | specified only | v0.3a state identity spec |
| Search / Peak tracking | specified only | runtime implementation pending |
| Interruption / Recovery | planned | after search vertical slice |
| Deck statistics | planned | after recovery slice |
| Legacy card-text conversion | implemented, removal target | v0.0 historical tests |

「仕様化済み」と「実行可能」を混同しません。現在のRoute DSL fixtureは契約確認用であり、実デュエル出力ではありません。
