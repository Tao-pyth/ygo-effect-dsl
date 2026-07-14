# ADR-0006: Use one DecisionRequest response as the atomic search Action

Status: Accepted

Date: 2026-07-13

Decision Issue: #69

## Context

ocgcore can expose one human-visible operation as several response boundaries. Activating an effect may be followed by separate cost, target, option, order, and resolution-time requests. Conversely, one request can require several cards, zones, ordered values, or weighted allocations in a single response.

The search tree needs a boundary that preserves every legal branch and can be replayed byte-for-byte. Logs and UI need a coarser description that does not force a reader to interpret every low-level request independently. Using one representation for both concerns either hides legal branches or makes the presentation unnecessarily fragmented.

## Decision

The atomic search and Replay Action is exactly one response to one `DecisionRequest`.

- If ocgcore emits separate requests for activation, cost, target, option, or resolution-time choice, each response is a separate Action.
- If one request requires multiple candidates, quantities, or an order, all selections remain in one Action. Python must not split a native response into partial Actions.
- Automatic core processing that requires no Python response creates no Action. Its messages and resulting state remain observable through Replay events and checkpoints where applicable.
- `STOP_LINE` is the only synthetic search-control Action. It records a legal checkpoint and is never encoded as a core response. `END_TURN` remains a distinct native response.
- A human-facing composite operation may reference a contiguous span of atomic Action IDs. It is derived presentation data and must not replace Replay events, search edges, Action IDs, pruning identity, or interruption coordinates.

This boundary follows the actual core protocol, not a Python interpretation of card text or effect semantics.

## Tradeoffs

Benefits:

- Every branch where Python can make a different legal response remains visible to search.
- Replay can verify the request signature and encode one response at every step.
- Weighted and ordered multi-selection stays atomic, so an invalid partial response cannot enter the tree.
- Card-specific effect procedures remain owned by ocgcore and EDOPro Lua.

Costs:

- A single human concept can produce several Action records and deeper search paths.
- Raw logs are too detailed for routine UI use.
- Comparing routes requires a derived grouping layer in addition to atomic Action comparison.

The costs are accepted because grouping can be added without losing information, while reconstructing hidden intermediate branches from a composite search edge is not reliable.

## Rejected alternatives

### One composite Action per effect lifecycle

Rejected because later cost, target, and option requests can branch independently. Pre-composing them would require Python to predict core behavior and would prevent interruption or comparison at an intermediate request.

### One Action per selected candidate

Rejected because card sets, ordered lists, counter allocations, and sum selections are one native response. Individual candidate Actions would represent core inputs that are not legal on their own.

### One Action per card-text semantic operation

Rejected because it would reintroduce a Python card-rule model and diverge from EDOPro Lua. It also cannot represent protocol controls such as pass, phase transition, or ordering without special cases.

## Compatibility and migration

- Existing v0.3a Actions already follow this boundary; their schema and Action IDs do not change.
- Future composite records must store ordered references to existing atomic Action IDs and a separate aggregation schema version.
- Composite labels and summaries are display fields and are excluded from atomic Action identity.
- Replay readers that do not understand composite records can ignore them and still reproduce the route.
- If a future core version merges or splits requests, the atomic boundary follows that version's observed `DecisionRequest` sequence. Cross-version comparison uses aggregation, not fabricated atomic equivalence.

## Consequences

#70 can define stable IDs only for atomic Actions. #71 can build presentation spans without changing Replay or search semantics. Interruption targets and route forks continue to use atomic step and Action ID coordinates.
