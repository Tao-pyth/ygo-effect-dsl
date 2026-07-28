# ADR-0019: Reject NEURON Direct Import Without Official API

Status: Accepted

Date: 2026-07-17

Related milestone: [#276](https://github.com/Tao-pyth/ygo-effect-dsl/issues/276), [#303](https://github.com/Tao-pyth/ygo-effect-dsl/issues/303)

## Context

`0.7.0` research dashboard considered importing deck lists from Yu-Gi-Oh! NEURON URLs, public deck records, or deck codes. The product goal is valid: users should not have to retype a deck that already exists in an official KONAMI workflow. However, this project cannot add a data path that depends on unofficial scraping, credential capture, or unstable private endpoints.

Official sources checked on 2026-07-17:

- [Yu-Gi-Oh! NEURON official product page](https://www.konami.com/games/eu/en/products/yugioh_neuron/) describes deck transfer/editing, Card Database management, globally published deck search, and saving a deck to the Yu-Gi-Oh! TCG Card Database.
- [Yu-Gi-Oh! NEURON Terms of Use](https://legal.konami.com/games/neuron/terms/tou/en/) were last updated on 2025-04-14 and define NEURON as an application plus web services including KONAMI CARD GAME NETWORK and the TCG/Rush Duel Card Databases.
- The same Terms require KONAMI ID/Card Game ID linking for web service use, grant only a personal non-commercial license, prohibit reverse engineering, prohibit systematically downloading/storing Materials to create a database, and prohibit robot/spider/search-retrieval/scraping/data-mining access without express written consent.
- [KONAMI support for NEURON to MASTER DUEL](https://us-support.konami.com/hc/en-us/articles/4814044001687-Is-it-possible-to-import-Deck-Lists-from-Yu-Gi-Oh-NEURON-to-MASTER-DUEL-Additionally-is-it-also-possible-to-export-Deck-Lists-from-MASTER-DUEL-to-NEURON) states that a public NEURON deck can be imported into MASTER DUEL, but does not expose an API or export contract for third-party tools.
- [KONAMI NEURON troubleshooting](https://eu-support.konami.com/hc/en-gb/articles/9697629214871-Yu-Gi-Oh-Neuron-Troubleshooting) documents public/private deck settings, which means deck visibility is user-controlled data and must not be bypassed.

Within those official sources, no stable public API, OAuth scope, documented export format, rate limit, or developer permission model for third-party deck retrieval was found.

## Decision

1. Do not implement a NEURON URL, public-deck-code, or account-backed direct importer in `0.7.0`.
2. Do not scrape NEURON pages, Card Database pages, app traffic, private endpoints, or public-deck search results.
3. Do not ask for, store, proxy, or automate KONAMI ID, Card Game ID, NEURON, or platform credentials.
4. Keep supported deck input paths to user-provided YDK import, inline card-code registration, and future manual paste formats whose provenance is local to the user.
5. If a user provides a manually exported list in a documented plain-text format, parse it only as user-supplied local input and do not fetch remote NEURON resources.
6. If KONAMI later publishes an explicit third-party deck export API, revisit this ADR before implementation. Required evidence: official developer documentation, permitted use terms, authentication scopes, privacy behavior for public/private decks, rate limits, export schema, and a fail-closed test fixture.

## Consequences

- `0.7.0` can close #303 as a research decision without adding a network connector.
- The desktop dashboard remains offline-first and keeps the existing default-deny frontend network policy.
- User workflow cost is handled by inline deck registration and native YDK import instead of unofficial NEURON automation.
- Any future NEURON support must be a separate issue after official permission exists; it must not be smuggled into card presentation, analytics, or deck catalog code.

## Rejected Alternatives

- Scrape public deck pages: rejected because Terms prohibit scraping and systematic retrieval without express written consent.
- Reverse-engineer app or web endpoints: rejected because Terms prohibit reverse engineering and because endpoint stability/privacy cannot be verified.
- Browser automation with user credentials: rejected because it would collect or automate personal account access and bypass clear local-input boundaries.
- Treat MASTER DUEL import support as a reusable public export API: rejected because the support article documents an official product-to-product feature, not a third-party developer contract.
