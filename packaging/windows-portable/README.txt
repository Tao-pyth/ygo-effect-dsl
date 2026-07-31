ygo-effect-dsl v1.0.0 Windows portable package

Contents
- ygo-effect-dsl.exe: command-line entrypoint.
- ygo-effect-dsl-desktop.exe: Windows desktop entrypoint.
- THIRD_PARTY_NOTICES.md: third-party notice evidence.
- DISTRIBUTION_POLICY.md: fail-closed distribution policy.

Install
Extract ygo-effect-dsl-win64-portable.zip to a user-owned directory, for example:
%LOCALAPPDATA%\Programs\ygo-effect-dsl

Run
Start ygo-effect-dsl-desktop.exe for the desktop UI, or run ygo-effect-dsl.exe from a terminal for CLI commands.

WebView2
The WebView2 runtime is not bundled. If it is missing or unusable, ygo-effect-dsl-desktop.exe must fail through the desktop preflight diagnostics instead of silently downloading or installing a runtime.

No third-party card assets
No third-party card assets are included. The package does not include ocgcore binaries, CardScripts Lua files, BabelCDB card databases, card images, card text databases, downloaded bootstrap tools, or the WebView2 runtime.

Uninstall
Delete the extracted ygo-effect-dsl-win64 directory. User data, external assets, caches, and logs are outside the portable package directory.

Upgrade
Keep the previous extracted directory or previous ZIP, then extract the newer package into a clean ygo-effect-dsl-win64 directory.

Rollback
Delete the current extracted directory and restore the previous extracted directory, or re-extract the previous ZIP.

Public release status
This package format is the v1.0.0 packaging decision, but public release remains blocked until the parent production distribution gate passes legal, signing, SBOM, support, and operations checks.
