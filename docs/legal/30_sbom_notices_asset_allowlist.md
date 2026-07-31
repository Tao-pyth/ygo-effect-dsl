# v1.0.0 SBOM, Notices, And Asset Allowlist

Status: Generated policy evidence; tracked by [#170](https://github.com/Tao-pyth/ygo-effect-dsl/issues/170)

Last updated: 2026-07-31

## Machine-Readable Evidence

- SBOM: [`docs/release/evidence/v1_0_0_sbom.json`](../release/evidence/v1_0_0_sbom.json)
- Third-party notices: [`docs/release/evidence/v1_0_0_third_party_notices.md`](../release/evidence/v1_0_0_third_party_notices.md)
- Asset allowlist: [`docs/release/evidence/v1_0_0_asset_allowlist.json`](../release/evidence/v1_0_0_asset_allowlist.json)
- Release artifact composition map: [`docs/release/evidence/v1_0_0_release_artifact_composition.json`](../release/evidence/v1_0_0_release_artifact_composition.json)

## Policy

The v1.0.0 release composition remains fail-closed. Wheel, sdist, Windows executable, and installer artifacts may contain this project's package code, package metadata, static desktop files, and checked-in JSON policy resources. They must not contain ocgcore binaries or copied source, CardScripts Lua files, BabelCDB database files, card images, card text databases, downloaded bootstrap executables, or any other unreviewed binary/large asset.

Third-party runtime and card assets are local-cache-only inputs until #91 and #169 complete. Their source coordinates, commits, trees, hashes, license status, and redistribution flags are recorded so operators can verify local acquisition without converting that local acquisition into redistribution approval.

## Release Gate Rule

Every release artifact must be associated with the SBOM, notices, and asset allowlist above. `python -m ygo_effect_dsl.release_audit <artifact...>` must pass before publication. The audit rejects unsafe archive paths, symbolic or special members, known third-party payload suffixes, known third-party path roots, enabled release payload policy, and oversized members that lack an explicit future allowlist.
