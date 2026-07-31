ygo-effect-dsl v1.0.0 Windows portable package

Contents
- ygo-effect-dsl.exe: command-line entrypoint.
- ygo-effect-dsl-desktop.exe: Windows desktop entrypoint.
- THIRD_PARTY_NOTICES.md: third-party notice evidence.
- DISTRIBUTION_POLICY.md: fail-closed distribution policy.

Install
Extract ygo-effect-dsl-win64-portable.zip to a user-owned directory, for example:
%LOCALAPPDATA%\Programs\ygo-effect-dsl

Clean install
Create a new ygo-effect-dsl-win64 directory and extract this package into that empty directory. Do not extract over a previous package directory.

Run
Start ygo-effect-dsl-desktop.exe for the desktop UI, or run ygo-effect-dsl.exe from a terminal for CLI commands.

WebView2
The WebView2 runtime is not bundled. If it is missing or unusable, ygo-effect-dsl-desktop.exe must fail through the desktop preflight diagnostics instead of silently downloading or installing a runtime.

Offline runtime
The desktop can start only when the required local runtime is already present. The package does not fetch WebView2, ocgcore, CardScripts, BabelCDB, card images, or card text while offline. External game assets are obtained and verified only through the owned cache resolver outside the package directory.

No third-party card assets
No third-party card assets are included. The package does not include ocgcore binaries, CardScripts Lua files, BabelCDB card databases, card images, card text databases, downloaded bootstrap tools, or the WebView2 runtime.

Uninstall
Delete the extracted ygo-effect-dsl-win64 directory. User data, external assets, caches, logs, and evidence are outside the portable package directory.

Reinstall
Delete the extracted package directory, then extract the same package again into a clean ygo-effect-dsl-win64 directory. Reinstalling package files must not delete user data, external assets, caches, logs, or evidence.

Upgrade
Keep the previous extracted directory or previous ZIP as a backup, then extract the newer package into a clean ygo-effect-dsl-win64 directory. Do not overwrite the previous package directory in place.

Patch upgrade
For a v1.0.x patch package, keep the current v1.0.x extracted directory or ZIP, then extract the patch package into a clean directory. User data, external assets, caches, logs, and evidence remain outside the package directory.

Rollback
Delete the current extracted directory and restore the previous extracted directory, or re-extract the previous ZIP. Any rollback that would change user cache/config/evidence requires a pre-migration backup and explicit confirmation before the migration starts.

Public release status
This package format is the v1.0.0 packaging decision, but public release remains blocked until the parent production distribution gate passes legal, signing, SBOM, support, and operations checks.
