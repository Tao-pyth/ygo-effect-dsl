# Package 1.0.0 Work Breakdown and Acceptance

Status: Issue-backed plan

Last updated: 2026-07-14

## Work items

| Order | Issue | Deliverable | Acceptance evidence |
|---|---|---|---|
| 1 | [#168](https://github.com/Tao-pyth/ygo-effect-dsl/issues/168) | platform/compatibility matrix | clean environment matrix、old artifact replay |
| 2 | [#91](https://github.com/Tao-pyth/ygo-effect-dsl/issues/91), [#169](https://github.com/Tao-pyth/ygo-effect-dsl/issues/169) | license decision/package metadata | approval record、LICENSE/NOTICE/metadata parity |
| 3 | [#170](https://github.com/Tao-pyth/ygo-effect-dsl/issues/170) | SBOM/notices/asset allowlist | artifact inventory、unknown binary rejection |
| 4 | [#171](https://github.com/Tao-pyth/ygo-effect-dsl/issues/171) | reproducible build/checksum/provenance | independent build comparison、attestation |
| 5 | [#172](https://github.com/Tao-pyth/ygo-effect-dsl/issues/172) | wheel/sdist/executable upgrade/rollback | clean venv/machine、migration/rollback matrix |
| 6 | [#173](https://github.com/Tao-pyth/ygo-effect-dsl/issues/173) | signed/gated GitHub Release | dry-run、approval、yank/rollback、action pinning |
| 7 | [#174](https://github.com/Tao-pyth/ygo-effect-dsl/issues/174) | schema/CLI/API/artifact compatibility policy | deprecation/migration/reject fixtures |
| 8 | [#127](https://github.com/Tao-pyth/ygo-effect-dsl/issues/127), [#175](https://github.com/Tao-pyth/ygo-effect-dsl/issues/175) | observability/redaction/retention | canary leak、metric/log/run correlation |
| 9 | [#176](https://github.com/Tao-pyth/ygo-effect-dsl/issues/176) | incident/rollback/DR runbooks | tabletop、backup restore drill、RPO/RTO |
| 10 | [#177](https://github.com/Tao-pyth/ygo-effect-dsl/issues/177) | threat model/dependency policy | risk register、security tests、update SLA |
| 11 | [#178](https://github.com/Tao-pyth/ygo-effect-dsl/issues/178) | long-duration soak/crash recovery | 24h+ resource/recovery evidence |
| 12 | [#179](https://github.com/Tao-pyth/ygo-effect-dsl/issues/179) | stable quickstart/support/final checklist | independent clean-machine walkthrough |

## Gate A: legal and artifact composition

- root licenseとpackage metadataが承認済みで一致する。
- ocgcore/CardScripts/BabelCDBおよび全dependencyのlicense/statusをinventory化する。
- asset allowlist外のDLL/CDB/Lua/large binaryをrelease artifactへ含めない。
- wheel/sdist/executableごとにSBOM、NOTICE、checksum、provenanceを生成する。
- #91未完了ならpublic publishを停止する。

## Gate B: compatibility and packaging

- supported matrixの全組合せでclean install/smokeを通す。
- editable installやrepository-relative pathへ依存しない。
- parent/worker import元とpackage versionが一致する。
- old Experiment/Route/Replay/catalogをpolicyどおりread/replay/migrate/rejectする。
- upgrade/rollback/uninstall/reinstall/offline runtimeを検証する。
- irreversible migrationのbackup/restore drillを通す。

## Gate C: build and release integrity

- source tag/commitとartifact provenanceを相互検証する。
- independent buildの再現性または説明済み差分がある。
- checksum/SBOM/NOTICE/provenanceがartifactと一致する。
- protected approvalなしにpublishできない。
- signed tag、release notes、changelog、package `--version`が一致する。
- failed releaseのyank/rollbackをdry-runする。

## Gate D: security and privacy

- threat modelのcritical/high riskが解消または明示承認されている。
- untrusted YDK/YAML/path/CDB/Lua/native/IPC/artifactのnegative testsを通す。
- unsafe Lua、root外script、runtime networkを既定無効にする。
- log/trace/crash dump/exportのhidden/secret canary leakがない。
- dependency/action pinとupdate policyがCIで検査される。

## Gate E: operations and soak

- metric/log/traceからrun/job/worker failureを追跡できる。
- retention/deleteとbackup/restoreが実際のstorageへ適用される。
- bad release、migration failure、corruption、crash storm、asset loss、disk fullのrunbook drillを行う。
- 24時間以上のmixed workloadでunbounded RSS/handle/process/file growthがない。
- injected crash/restart後にcommitted runのduplicate/lossがない。
- measured limit、RPO/RTO、known limitationを公開する。

## Gate F: final publication

- independent third partyがstable quickstartをclean machineで完走する。
- support channel、bug report template、security report、support windowを公開する。
- full test、GitHub Actions、self-hosted/manual evidence、license approval、SBOM、reviewを完了する。
- commit、push、PR、CI、merge、`main`同期後にtag/releaseを作る。
- release後にchecksum、artifact、docs、tag、package indexを再確認する。

## Release rejection conditions

- licenseまたはthird-party redistribution判断が未承認である。
- artifactにallowlist外assetやbuild secretが含まれる。
- schema migrationがsilent data lossまたはrollback不能を起こす。
- security critical/high、private information leak、unbounded resource growthが残る。
- clean install/upgrade/rollback/restore/soak evidenceがない。
- support対象や既知制約を曖昧にしたままstableを宣言する。
