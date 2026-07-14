# Spec Status Matrix

基準日: 2026-07-14

| Area | Status | Evidence |
| --- | --- | --- |
| Project boundary | specified | Project Charter / Architecture |
| Python does not own rules | accepted | ADR-0002 |
| Route DSL responsibility | specified | ADR-0004 / Route DSL Overview |
| Route DSL 0.1 shape | minimally implemented | schema doc / validator / fixture |
| DecisionRequest signature | minimally implemented | engine/bridge + contract tests |
| Action ID | minimally implemented | engine/action + contract tests |
| Replay signature checks | minimally implemented | engine/replay + contract tests |
| Real ocgcore Bridge | MVP implemented | pinned runtime / fresh worker tests |
| Replay executor | MVP implemented | Replay v0.3a / General Search replay |
| State hash | implemented | canonical State ID / fresh Replay tests |
| Search / Peak tracking | Random Search MVP | SearchExecutor / 10万logical node evidence |
| Interruption / Recovery | taxonomy-limited MVP | fixed fixtures / specified interruption trace |
| Deck statistics | planned | after recovery slice |
| Legacy card-text conversion | implemented, removal target | v0.0 historical tests |

「MVP実装済み」と「production検証済み」を混同しません。pool別の実core性能、未検証妨害category、PlayerView Replay、一般公開配布は後続検証が必要です。
