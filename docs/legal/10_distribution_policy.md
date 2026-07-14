# License and distribution policy v1

This document is an engineering release gate, not legal advice. It records the most conservative decision supported by the pinned upstream materials as of 2026-07-13. The machine-readable source of truth is `src/ygo_effect_dsl/resources/distribution-policy-v1.json`.

## Current decision

- Local prototype: an explicit bootstrap command may acquire the pinned dependencies into the user's cache. Runtime implicit downloads, system-wide installation, and network access during duel execution remain disabled.
- Repository: dependency coordinates, commit and tree IDs, hashes, clean-room integration code, and generated route records may be checked in. Third-party source, binaries, Lua scripts, databases, and downloaded tools must not be checked in.
- Public release: blocked. No release artifact may bundle ocgcore, CardScripts, BabelCDB, Lua, or Premake under policy v1.
- Commercial bundle: not approved. BabelCDB is specifically blocked because the pinned tag has no discovered license grant. AGPL dependencies also remain blocked until project-license compatibility, notices, corresponding-source delivery, build information, and modification records have been reviewed.
- Project source: the repository has no root `LICENSE`, so policy v1 does not claim an express reuse grant or approve a packaged release.

`include_in_release: false` is a project policy decision. It does not mean every upstream license forbids distribution; it means this repository has not completed the compliance work required to authorize it.

## Dependency record

| Artifact | Pinned source | Recorded license | Policy v1 |
| --- | --- | --- | --- |
| ocgcore | `edo9300/ygopro-core` `v11.0` | AGPL-3.0-or-later, with upstream notices | local cache only; no bundle |
| CardScripts | `ProjectIgnis/CardScripts` `20250420` | AGPL-3.0-or-later | local cache only; no bundle |
| BabelCDB `cards.cdb` | `ProjectIgnis/BabelCDB` `20250419` | NOASSERTION | local cache only; redistribution blocked |
| Lua | commit `1ab3208...` | MIT | transitive build input; no bundle |
| Premake | `v5.0.0-beta2` | BSD-3-Clause | bootstrap tool in user cache; no bundle |

Primary sources:

- ocgcore license and bundled notices: <https://github.com/edo9300/ygopro-core/blob/v11.0/LICENSE>
- CardScripts license text: <https://github.com/ProjectIgnis/CardScripts/blob/20250420/COPYING>
- BabelCDB pinned tree: <https://github.com/ProjectIgnis/BabelCDB/tree/20250419>
- Lua pinned header and MIT notice: <https://github.com/lua/lua/blob/1ab3208a1fceb12fca8f24ba57d6e13c5bff15e3/lua.h>
- Premake BSD-3-Clause license: <https://github.com/premake/premake-core/blob/v5.0.0-beta2/LICENSE.txt>
- GNU AGPL v3 reference: <https://www.gnu.org/licenses/agpl-3.0.html>

## Gate to change this policy

Before any `include_in_release` value can become true:

1. Choose and add the project's own license.
2. Obtain an explicit BabelCDB license or written permission if `cards.cdb` will be distributed.
3. Produce a release bill of materials with exact versions and hashes.
4. Package all required copyright, license, disclaimer, and modification notices.
5. Define the corresponding-source and build-information delivery path for AGPL components.
6. Run a legal review of the exact release composition and intended commercial/public use.
7. Introduce a new policy schema/version and update the fail-closed tests. Policy v1 cannot authorize release bundling.

Until every applicable item is complete, releases must contain only this project's code and metadata and must not be represented as generally licensed for reuse.
