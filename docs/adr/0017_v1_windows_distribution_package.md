# ADR 0017: v1.0.0 Windows distribution package

Status: Accepted for v1.0.0 packaging gate

## Decision

The v1.0.0 Windows desktop distribution format is a portable ZIP named `ygo-effect-dsl-win64-portable.zip`. It contains a top-level `ygo-effect-dsl-win64` directory with the packaged CLI executable, packaged desktop executable, package README, third-party notices, and the fail-closed distribution policy.

This is the supported packaging channel for the v1.0.0 production gate until legal approval, Authenticode signing, update policy, and public release approval are complete. The public release remains blocked until the parent production distribution gate passes.

The package contract records install location, per-user behavior, uninstall behavior, upgrade behavior, rollback expectations, and clean-machine evidence.

## Rationale

The project does not yet have a root license approval record, Authenticode certificate, timestamp verification, installer signing policy, or public release approval. Producing an MSI or setup executable before those gates are complete would look more final than the evidence supports.

A portable ZIP is the smallest stable Windows package that can be built and smoked in GitHub Actions without requiring administrator privileges or machine-wide registry writes. It also keeps rollback and deletion behavior explicit and testable.

## Installation Model

The package is per-user and portable. The user extracts the ZIP to a user-owned directory such as `%LOCALAPPDATA%\Programs\ygo-effect-dsl` or another non-admin path. There is no machine-wide install, no service, no file association, no shell extension, and no auto-update mechanism in v1.0.0.

The WebView2 runtime is not bundled. The desktop executable performs runtime preflight and must present a user-facing failure path when WebView2 is missing or unusable.

The package must not include ocgcore binaries, CardScripts Lua files, BabelCDB data, card images, card text databases, WebView2 runtime payloads, downloaded bootstrap tools, or other third-party card assets.

## Uninstall

Uninstall is deleting the extracted `ygo-effect-dsl-win64` directory. User data, external assets, caches, and logs are intentionally outside the package directory and are governed by the later operations, redaction, backup, and rollback contracts.

## Upgrade

Upgrade is replacing the extracted `ygo-effect-dsl-win64` directory with a newer package after preserving the previous package directory or ZIP. The package does not silently migrate user data. Compatibility, migration, and reject behavior remain release gates for #172 and #174.

## Rollback

Rollback is restoring the previous extracted package directory or re-extracting the previous ZIP. The rollback path must not depend on network access, a system installer cache, or an auto-update service.

## Clean-Machine Evidence

The `Build Windows exe` workflow builds `ygo-effect-dsl.exe` and `ygo-effect-dsl-desktop.exe`, assembles `ygo-effect-dsl-win64-portable.zip`, extracts it into a clean `package_smoke` directory, runs CLI `--version`, runs desktop `--version`, runs desktop `--preflight-only`, and runs desktop `--bridge-smoke-out`.

The workflow uploads the portable ZIP together with the executable artifacts and smoke diagnostics. This verifies package assembly and clean-machine extraction semantics without publishing a public installer.
