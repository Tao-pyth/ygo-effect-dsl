# ADR 0020: v1.0.0 external asset setup

Status: Accepted for v1.0.0 asset setup gate

## Decision

The v1.0.0 Windows desktop package does not bundle ocgcore, CardScripts, BabelCDB, card images, or card text. These are external local-only assets until license and redistribution approval is recorded.

The first-run UX must guide the user through a user-owned external asset cache, then verify pinned commits, lock IDs, required file sizes, SHA-256 hashes, and license status before enabling dependent features. The runtime must not scrape card data, silently download assets during search, or install assets system-wide.

## Setup Flow

The supported CLI setup flow is:

1. `python -m ygo_effect_dsl external-asset-setup-status`
2. `python -m ygo_effect_dsl ocgcore-doctor`
3. `python -m ygo_effect_dsl ocgcore-bootstrap`
4. `python -m ygo_effect_dsl ocgcore-assets-bootstrap`
5. `python -m ygo_effect_dsl ocgcore-verify`
6. `python -m ygo_effect_dsl ocgcore-assets-verify`

Offline verification uses `ocgcore-bootstrap --offline`, `ocgcore-assets-bootstrap --offline`, `ocgcore-verify`, and `ocgcore-assets-verify`.

## Failure UX

`external-asset-setup-status` and desktop `system.external_asset_status` report blocked features when assets are missing or invalid. Card names and deck card options are blocked until CardScripts and BabelCDB pass lock verification. Search jobs are blocked until both ocgcore runtime and card assets pass verification. `card.get`, `deck.card_options`, `scenario.preflight`, and `job.enqueue_search` fail closed before worker startup when the verified local assets are unavailable.

## Release Boundary

Release artifacts may include only the policy, lock files, and setup diagnostics. They must not include ocgcore binaries, CardScripts Lua files, BabelCDB databases, card images, card text, downloaded bootstrap archives, or local cache contents.
