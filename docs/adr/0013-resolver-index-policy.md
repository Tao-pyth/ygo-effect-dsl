# ADR 0013: Keep the checked process-local CardScripts index

Status: accepted for v0.3

Date: 2026-07-15

## Decision

`resolver-index-policy-v1`は`checked_process_local`を維持する。asset-keyed serialized indexは、live directory identity、exact-case、case collision、reparse point、file identityを再検査するとfresh processでの優位を証明できていないため不採用とする。resident native workerはresolverだけならcold 0.252秒からwarm 0.120秒へ約2.09倍改善するが、duel state隔離、crash replacement、cleanup契約を変更するため`0.3.0`では採用しない。

現行indexはworker processだけが所有し、worker終了時に破棄する。directory identityが変化した場合は再構築し、case collision、reparse point、読み取り前後のfile identity不一致をfail-closeする。rollbackはworker終了であり、永続cache cleanupやmigrationは不要である。

## Evidence

- `real-core-replay-benchmark-v1`: 20,963 entry、名称推定558,452 bytes、RSS増分約1.9 MiB
- `resolver-index-policy-v1`: cross-process indexとresident workerの測定済み不採用
- mutation/concurrent-reader tests: content更新を再読込し、case collisionを読み取り前に拒否

この判断は高速化を永久に禁止しない。resident workerを採用する場合はnative duel isolationとcrash recoveryを別versionで再qualificationする。
