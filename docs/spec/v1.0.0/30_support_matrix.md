# Package 1.0.0 Support Matrix

Status: Frozen target matrix; parent [#134](https://github.com/Tao-pyth/ygo-effect-dsl/issues/134), work item [#168](https://github.com/Tao-pyth/ygo-effect-dsl/issues/168)

Last updated: 2026-07-31

## Purpose

この文書は package `1.0.0` の stable claim に含める環境と互換境界を固定する。ここにない OS、architecture、runtime、asset、schema、CLI/API、install/upgrade/rollback 組合せは暗黙に support しない。未掲載または未検証の組合せは fail-closed で `unsupported` と扱う。

機械検証用の正本は [`docs/release/evidence/v1_0_0_support_matrix.json`](../../release/evidence/v1_0_0_support_matrix.json) である。clean environment matrix の公開 test link は [`tests/test_v1_support_matrix.py`](../../../tests/test_v1_support_matrix.py) で、少なくとも次を検証する。

- matrix の category と status 語彙が固定されている。
- support 対象が evidence reference または blocking issue を持つ。
- unsupported 行が理由を持つ。
- matrix に存在しない組合せを support として扱わない default policy がある。

## Status Vocabulary

| Status | Meaning |
|---|---|
| `supported` | `1.0.0` 最終 gate で fully usable として提供する対象。該当 row は evidence または evidence を完了させる blocking issue を持つ。 |
| `maintenance` | 既存 artifact の read、replay、migration、diagnostic の互換維持対象。新機能や新規配布先としては扱わない。 |
| `experimental` | 研究、検証、内部用途のみ。stable claim、quickstart、一般配布 UI へ出さない。 |
| `unsupported` | 使用不可または未検証。失敗時は明示的に reject し、黙って downgrade しない。 |

## Platform And Runtime

| Area | Combination | Status | Evidence / blocker | User claim |
|---|---|---|---|---|
| OS / architecture | Windows 11 x64, local desktop session | `supported` | #354, #355, #356, #357 | primary 1.0.0 desktop target |
| OS / architecture | Windows ARM64 native, macOS, Linux desktop package | `unsupported` | matrix rejection row | no 1.0.0 desktop support |
| Filesystem | local NTFS path outside cloud-sync rewrite | `supported` | #172, #176 | install, cache, corpus, rollback path |
| Filesystem | network share, symlink escape, cloud-sync controlled install/cache root | `unsupported` | security and rollback rejection rows | no stable claim |
| Locale / UI | Japanese UI with UTF-8 documents and `lang="ja"` | `supported` | `japanese-i18n-release-gate-v1` | primary UI language |
| Locale / UI | English or multi-locale UI switch | `unsupported` | v0.8.0 non-goal | no 1.0.0 claim |
| Python source runtime | CPython 3.13 x64 | `supported` | current host tests, #172 | source and wheel validation target |
| Python source runtime | CPython 3.10-3.12 x64 | `maintenance` | `pyproject.toml` lower bound, #172 | compatibility smoke only until requalified |
| Python source runtime | PyPy, 32-bit Python, Python 3.14+ | `unsupported` | matrix rejection row | explicit reject |

## Core And Assets

| Area | Combination | Status | Evidence / blocker | User claim |
|---|---|---|---|---|
| ocgcore | `ocgcore-v11.0-win-x64-msvc-v1`, API 11.0, user-acquired local runtime | `supported` | `ocgcore-platform-contract-v1`, `ocgcore-doctor-v2`, #354 | rules authority |
| ocgcore | API other than 11.0, unknown DLL, wrong architecture | `unsupported` | bootstrap fail-close tests | reject before worker start |
| CardScripts / CDB | `ocgcore-assets-202504-v1`, exact lock, user-acquired local assets | `supported` | asset lock, #358 | external asset setup target |
| CardScripts / CDB | bundled redistribution in wheel, sdist, exe, installer, CI artifact | `unsupported` | #91, #169, #170 | distribution prohibited unless explicitly approved |
| Runtime network | runtime download or mutation during normal execution | `unsupported` | lock policy | no network install at runtime |

## Schema, CLI, And API

| Area | Combination | Status | Evidence / blocker | User claim |
|---|---|---|---|---|
| Experiment / Scenario | current Experiment `0.4` and `scenario-v1` | `supported` | existing schema tests, #174 | read, validate, execute |
| Route / Replay | `search-run-result-v5`, `fresh-replay-verification-v1`, current committed Route artifacts | `supported` | 0.7.0 evidence, #174 | read, replay, reject incompatible |
| Old Route / Replay | `0.3a`, `0.3b`, source milestone artifacts | `maintenance` | legacy fixture tests, #172, #174 | read or replay where contract allows |
| Legacy card-text artifacts | old `dsl` / card text transformation pipeline | `unsupported` | project charter | not Route DSL input |
| CLI | `ygo-effect-dsl`, `ygo-effect-dsl-desktop`, documented diagnostic exit categories | `supported` | #172, #354, #359 | stable command surface after final gate |
| API | pywebview bridge method `invoke` inside packaged desktop | `supported` | `desktop-bridge-v1`, #354 | private local bridge only |
| API | public REST API, arbitrary Python bridge methods, debug-only bridge calls | `unsupported` | `desktop-bridge-v1` security policy | not public API |

## Install, Upgrade, Rollback, And Support Window

| Area | Combination | Status | Evidence / blocker | User claim |
|---|---|---|---|---|
| Clean install | Windows x64 desktop package without bundled third-party card assets | `supported` | #354, #355, #356, #357, #358 | primary install path |
| Upgrade | `0.8.0` source state to `1.0.0` package | `supported` | #172 | preserve user config/cache policy |
| Upgrade | `0.5.x` source artifact to `1.0.0` package | `maintenance` | #172 | read/migrate/reject explicitly |
| Rollback | `1.0.x` to previous `1.0.y` with backup/restore evidence | `supported` | #172, #176 | documented rollback path |
| Downgrade | arbitrary new data opened by old binary without policy | `unsupported` | #172, #174 | reject unknown required version |
| Uninstall/reinstall | same user data root after explicit backup/restore check | `supported` | #172, #176 | documented recovery path |

`1.0.x` active support lasts until `1.1.0` is released or 12 months after `1.0.0`, whichever is later. Security-only support lasts 6 additional months after active support ends. The final release notes must publish the concrete calendar dates once `1.0.0` ships.

## Release Gate Rule

The final `production-distribution-release-gate-v1` must reject release if any `supported` row has no passing evidence, if any `unsupported` row is exposed as stable UI/docs behavior, or if any third-party core/card asset is bundled without approval.
