# v1.0.0 Third-Party Notices

Status: Release payload notices for the current fail-closed composition.

## Release Payload

The v1.0.0 wheel, sdist, Windows executable, and installer composition currently approves no bundled third-party core, CDB, Lua script, card image, card text, native binary, or bootstrap executable payload.

Python package dependencies are listed in `v1_0_0_sbom.json`. Their license fields remain `NOASSERTION` until the exact release environment and resolver output are reviewed for the final artifact.

## Local-Only External Components

The following components may be acquired into the user's local cache by explicit setup flows, but they are not release payloads and are not approved for redistribution under policy `prototype-local-only-v1`:

| Component | License status | Redistribution status |
|---|---|---|
| ocgcore `v11.0` | AGPL-3.0-or-later | blocked pending legal review |
| ProjectIgnis CardScripts `20250420` | AGPL-3.0-or-later | blocked pending legal review |
| ProjectIgnis BabelCDB `20250419` | NOASSERTION | blocked; no license grant recorded |
| Lua commit `1ab3208a...` | MIT | not evaluated for release bundling |
| Premake `5.0.0-beta2` | BSD-3-Clause | not evaluated for release bundling |

This notice file is not legal approval. It is an engineering gate artifact that prevents silent bundling before #91, #169, and #170 evidence is complete.
