# Package 1.0.0 Production and Distribution Contracts

Status: Contract design backlog

Last updated: 2026-07-14

## Compatibility matrix

stable matrixは次をsupported、maintenance、experimental、unsupportedへ分類する。

- OS/architecture/filesystem/locale
- Python runtime、wheel tag、Windows executable runtime
- ocgcore API/build lock、CardScripts/BabelCDB asset lock
- Experiment/Scenario/Route/Replay/Search/PlayerView/analytics schema
- CLI command/exit code/diagnostic、API endpoint/payload
- install、upgrade、rollback、offline runtime

matrixにない組合せを暗黙supportedにしない。旧Experiment/Route/Replayはread、replay、migrate、rejectのどれかをversionごとに明示する。

## License and asset boundary

- repository source、documentation、example、generated artifactのroot license範囲を確定する。
- `pyproject.toml` license/classifier、LICENSE、NOTICE、README、release metadataを一致させる。
- package同梱dependencyと利用者がlocal取得するassetを明確に分離する。
- asset allowlistはrepository、ref、commit、tree/hash、license status、redistribution可否、review dateを持つ。
- unknown binary、large DB、Lua tree、DLLのartifact混入をCIで拒否する。
- SBOMとthird-party noticeをrelease artifactごとに生成する。

license判断は技術的推測で代替せず、必要な法務承認記録へlinkする。

## Reproducible build and provenance

wheel、sdist、Windows executableごとにsource tag/commit、dependency lock、builder image/toolchain、environment、command、timestamp policyをmanifestへ保存する。独立した2環境でbuildし、hashが一致しない場合は差分fieldと許容理由を記録する。

releaseはSHA-256 checksum、SBOM、provenance/attestation、対応sourceを持つ。build時にcore/assetsをdownloadまたはbundleしない。

## Install, upgrade, and rollback

最低matrixはclean install、`0.5.x -> 1.0.0`、`1.0.x -> 1.0.y`、rollback、uninstall/reinstall、offline runtimeである。

- parent/worker subprocessのimport元を同一distributionへ固定する。
- user config/cache/corpus migrationはpreflight、backup、dry-run、rollback可否を持つ。
- irreversible migrationは明示確認とrestore手順を要求する。
- old binary/new data、new binary/old dataの扱いをmatrix化する。
- asset resolverはowned cacheを使い、system installやEDOPro installerへ暗黙依存しない。

## Stable version policy

- packageはSemVerを使用する。
- schema、strategy、evaluator、cache/worker policyは独立versionを維持する。
- breaking changeはmigration/reject/deprecation期間を伴う。
- unknown required field/enum/versionを黙って無視しない。
- diagnostic codeとCLI exit categoryの安定性を定義する。
- support windowとsecurity patch期間をrelease notesへ記載する。

## Observability and privacy

log/metric/traceはcorrelation ID、run/job/worker attempt、version、diagnostic codeを持つ。deck/player/private card/raw payload/secretはPlayerViewとsecurity policyに従ってredactする。

retentionはlocal、CI、production、crash dump、benchmark evidenceごとに期間と削除方法を定義する。debug可能性を理由にhidden raw payloadを既定保存しない。

## Operational recovery

runbookはbad release、migration failure、corpus corruption、worker crash storm、upstream asset loss、checksum mismatch、disk exhaustionを対象にする。各runbookはdetection、triage、containment、backup、rollback/restore、verification、postmortemを含む。

RPO/RTOは実測restore drillから設定し、存在しないbackupを前提にしない。

## Security contract

threat modelはuntrusted YDK/YAML/path、CDB、Lua、native DLL、worker IPC、artifact import/export、Actions supply chainを扱う。

- path traversal、symlink escape、malformed payload、resource exhaustionをtestする。
- unsafe Lua libraryと任意script rootを既定無効にする。
- dependency/actionはversionまたはcommitでpinし、更新cadenceとemergency patch手順を定義する。
- critical/high未対応riskをrelease blockerにする。
- build/release credentialをruntimeやartifactへ含めない。

## Release workflow

release workflowはversion/changelog/tag/artifact/checksum/SBOM/provenanceを照合し、protected approval後だけpublishする。署名tagまたは組織方針に沿う署名方式を用い、failed publish時のyank/rollbackをrunbook化する。GitHub Actions runtime deprecationとaction pinningをrelease前に解消する。
