# Package 1.0.0 Scope: Stable Production and Distribution

Status: Planned; parent [#134](https://github.com/Tao-pyth/ygo-effect-dsl/issues/134)

Last updated: 2026-07-14

## Objective

package `1.0.0`は、`0.3.0`から`0.6.0`でqualificationした機能を、明示的な互換性、license、build provenance、security、運用、support契約の下でstable releaseにするstageである。機能数ではなく、利用者がinstall、upgrade、rollback、監査、障害対応できることを完了条件にする。

## Entry criteria

- `0.5.1`の検証効率化と`0.6.0`のparallel-search performance gateを含む、core/search/PlayerView/analytics gateが完了している。
- package、schema、strategy、evaluator、asset/core lockのidentityをartifactから追跡できる。
- root project licenseとthird-party componentの審査を開始できるinventoryがある。
- clean install候補artifactとproduction-like benchmark corpusがある。

## In scope

1. supported OS/architecture/Python/core/assets/schema/API/CLI compatibility matrix。
2. root project license、package metadata、third-party legal review。
3. SBOM、third-party notices、asset allowlist、binary/asset混入検査。
4. reproducible build、checksum、attestation/provenance。
5. wheel/sdist/Windows executableのclean install、upgrade、rollback。
6. signed tagとgated GitHub Release workflow。
7. SemVer、schema、deprecation、migration、support window。
8. observability、redaction、retention。
9. incident、rollback、backup、disaster recovery runbook。
10. threat model、dependency/action update policy。
11. 24時間以上のsoakとcrash-recovery qualification。
12. stable quickstart、support policy、final checklist。

## Out of scope

- license未確認のthird-party asset配布
- 全OS/Python/core versionの無期限support
- managed cloud serviceまたはmulti-region SLA
- online duel client
- semantic compatibilityを破るsilent migration

## Distribution prohibition

現時点のroot project licenseは確定しておらず、BabelCDB lockはlicense `NOASSERTION`である。ocgcore/CardScriptsはAGPLであり、local integrationが成立しても再配布可否を自動的に意味しない。[#91](https://github.com/Tao-pyth/ygo-effect-dsl/issues/91)と[#169](https://github.com/Tao-pyth/ygo-effect-dsl/issues/169)の承認前にpublic package/executableへcore、CDB、Lua assetを同梱しない。

## Stable claim

`1.0.0`完了時に許される主張は、公開したsupport matrix、asset取得方針、compatibility window、operational limitの範囲に限る。unsupported環境や外部asset可用性を保証せず、licenseとsecurity上の制約をquickstart/release notesから隠さない。
