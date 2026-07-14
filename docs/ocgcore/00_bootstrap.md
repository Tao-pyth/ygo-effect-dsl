# ocgcore bootstrap

End-to-endのoperator手順は[Real ocgcore operator walkthrough](50_operator_walkthrough.md)を参照する。この文書はbootstrapの設計判断と所有境界に限定する。

## Decision

The project provisions ocgcore with a project-owned, non-interactive bootstrap. The EDOPro installer is not a dependency: it installs a complete client and does not provide a stable, project-verifiable C API runtime contract. The upstream interactive `scripts/generate.bat` is also not called because it downloads Premake without checking a project-owned checksum.

The canonical source is `https://github.com/edo9300/ygopro-core.git`, pinned to tag `v11.0`, commit `158aebe758be3c46249c75d602e3f16d63d2ef31`. The bundled lock additionally pins the Git tree, Lua submodule, C API `11.0`, Premake archive and executable hashes, Windows x64 build target, and build properties. CardScripts and BabelCDB acquisition fetches the locked commit directly and checks it out detached; the recorded ref is provenance and is not required to remain movable or present. During a build, the disposable worktree is temporarily mounted at the locked `Y:` drive so compiler inputs do not contain machine-specific cache roots. The generated Release x64 project also receives `/Brepro` and omits path-dependent debug information from the runtime DLL. The bootstrap never replaces an existing `Y:` drive and always releases its own mapping. PDB files are build-only artifacts and are not copied into `runtime`.

## Explicit commands

```powershell
python -m ygo_effect_dsl ocgcore-doctor
python -m ygo_effect_dsl ocgcore-bootstrap
python -m ygo_effect_dsl ocgcore-verify
python -m ygo_effect_dsl ocgcore-assets-bootstrap
python -m ygo_effect_dsl ocgcore-assets-verify
```

`ocgcore-bootstrap` and `ocgcore-assets-bootstrap` are the only commands that may access the network. `--offline` prohibits network fallback and succeeds only when all pinned inputs are already cached. `--source-only` acquires and verifies core source without a compiler or Premake extraction.

## Layout and resolution

The default root is `%LOCALAPPDATA%\ygo-effect-dsl\external`; `YGO_EFFECT_DSL_EXTERNAL_ROOT` or `--external-root` selects the same alternate resolver path for development, CI, and an installed package. Each core lock has isolated `source`, `build`, `runtime`, `assets`, and `tools` paths. The pristine core Git checkout remains under `source`; compilation uses a disposable copy under `build`; only the verified DLL is copied to `runtime`. The separate asset lock places verified CardScripts and BabelCDB checkouts under `assets` and writes `asset-manifest.json`.

Runtime and asset resolvers perform no download or installation. The runtime resolver checks the lock hash, source commit/tree/submodules, DLL SHA-256, and exported `OCG_GetVersion`. The asset resolver checks both repository commits/trees and the required Lua/CDB file sizes and SHA-256 values.

## Ownership and cleanup

The bootstrap installs no system-wide software and requires no administrator privileges. It only replaces its own partial download, extraction, build, runtime, and manifest paths below the selected lock directory. A mismatched source checkout is rejected rather than deleted. Removing that one lock directory uninstalls project-owned artifacts; Visual Studio Build Tools and Git remain user-managed prerequisites.

The lock explicitly forbids binary redistribution. Local compilation and verification do not authorize bundling ocgcore, card databases, or CardScripts in a release; that remains gated by the licensing issue.
