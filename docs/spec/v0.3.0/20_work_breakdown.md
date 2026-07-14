# Package 0.3.0 Work Breakdown

Status: Issue-backed plan

Last updated: 2026-07-14

## Parent

Parent stage: [#131 Complete real ocgcore / EDOPro Lua integration and calibration](https://github.com/Tao-pyth/ygo-effect-dsl/issues/131)

## Work items

| Order | Issue | Deliverable | Depends on | Evidence |
|---|---|---|---|---|
| 1 | [#135](https://github.com/Tao-pyth/ygo-effect-dsl/issues/135) | supported platform/toolchain matrix | current lock | doctor matrix、unsupported diagnostics |
| 2 | [#136](https://github.com/Tao-pyth/ygo-effect-dsl/issues/136) | clean ocgcore bootstrap | #135 | `ocgcore-clean-bootstrap-qualification-v1`、5 build、idempotency、interrupt recovery、per-build hash |
| 3 | [#137](https://github.com/Tao-pyth/ygo-effect-dsl/issues/137) | BabelCDB ref/commit判断とclean asset bootstrap | #135 | upstream ref record、empty-cache transcript、ADRまたはlock維持根拠 |
| 4 | [#140](https://github.com/Tao-pyth/ygo-effect-dsl/issues/140) | EDOPro helper/card script load境界 | #137 | path/error/unsafe-library corpus |
| 5 | [#139](https://github.com/Tao-pyth/ygo-effect-dsl/issues/139) / [#194](https://github.com/Tao-pyth/ygo-effect-dsl/issues/194) | 3 real deckのYDK/inline preflight-to-Replayとsanitized qualification index | #137, #140, #192, #193 | scenario/SearchRun/Route/Replay manifest、反復witness、artifact SHA-256 |
| 6 | [#141](https://github.com/Tao-pyth/ygo-effect-dsl/issues/141) | unknown Message/Decision shape corpus | #139 | supported/unsupported registry、raw payload hash |
| 7 | [#123](https://github.com/Tao-pyth/ygo-effect-dsl/issues/123) | negation/timing fixture拡張 | #139 | damage step/mandatory trigger/SEGOC等の分類 |
| 8 | [#142](https://github.com/Tao-pyth/ygo-effect-dsl/issues/142) | worker crash/timeout/retry/quarantine acceptance | #136, #139 | fault injection report、process cleanup、atomicity |
| 9 | [#105](https://github.com/Tao-pyth/ygo-effect-dsl/issues/105) | multi-deck cache/memory再校正 | #139 | prefix/entry/hit/eviction/main RSS evidence |
| 10 | [#128](https://github.com/Tao-pyth/ygo-effect-dsl/issues/128) | pool別実Replay throughput/worker RSS | #105, #142 | 100k node、pool 1/2/4/8/16、crash recovery |
| 11 | [#110](https://github.com/Tao-pyth/ygo-effect-dsl/issues/110) | pruning multi-deck trace校正 | #139 | false prune/guardrail report |
| 12 | [#108](https://github.com/Tao-pyth/ygo-effect-dsl/issues/108) | evaluator weight校正 | #139 | alternative Route ranking evidence |
| 13 | [#138](https://github.com/Tao-pyth/ygo-effect-dsl/issues/138) | self-hosted real-core smoke | #136, #137, #142 | workflow run、asset非同梱監査 |
| 14 | [#143](https://github.com/Tao-pyth/ygo-effect-dsl/issues/143) | bootstrap-to-search-to-replay guide | #138 | clean-user walkthrough |
| 15 | [#144](https://github.com/Tao-pyth/ygo-effect-dsl/issues/144) | contract/default policy release ADR | all above | compatibility表、version判断、release checklist |

## Parallelization

- #135とBabelCDB upstream調査は並行できる。
- #140のfake/negative corpusは#137完了前に作れるが、実asset evidenceは#137後に確定する。
- #141と#123は3 deckから観測したshapeを共有するが、Message codecとtiming taxonomyを別成果物にする。
- #105/#110/#108は同じqualified Route corpusを再利用できる。raw evidenceは共有しても、cache、pruning、evaluationの判断を一つのIssueへ混在させない。
- #128は実worker測定のためself-hosted Windows hostを占有する。logical benchmark結果で代替しない。

## Asset-change rule

このstageのIssue作成時点ではcore lock、asset lock、CDB、Luaを変更しない。変更が必要になった場合は、該当Issueに次を先に添付する。

1. 現行lockで再現する失敗。
2. upstream ref/commit/treeとlicense状態。
3. candidate lockのcontent diff。
4. 既存fixture/Search/Replayへの影響。
5. rollback方法。

asset変更PRは検証Issueとは分けてもよいが、親Issueとrelease decisionから追跡可能にする。

## Related but not blocking

[#117](https://github.com/Tao-pyth/ygo-effect-dsl/issues/117)はupstream ocgcore version変更時にactivation rollback auditを再実行するtrigger Issueである。`v11.0` lockを維持する通常の`0.3.0`作業では完了を要求しない。
