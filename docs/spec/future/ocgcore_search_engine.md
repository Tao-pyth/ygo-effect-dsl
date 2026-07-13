# ocgcore-backed search engine requirements

Status: future architecture proposal

This document records the requirements for extending `ygo-effect-dsl` from card-effect structure analysis toward an automated Yu-Gi-Oh! combo and interruption research platform. It does not change the current v0.0 priority: stabilizing DSL transformation and validation remains the immediate project goal.

## 1. Goal

Build a research system that reuses the existing EDOPro card pool and Lua scripts while Python performs search, evaluation, logging, and statistical analysis.

Primary questions include:

- What lines are available from a given opening hand?
- Which line reaches the strongest stopping point?
- How often does a deck open a usable starter?
- If a specified effect receives a specified interruption, how far can the line recover?
- Which recovery route produces the best reachable board?

This is a game-tree research engine, not a replacement rules engine or a playable client.

## 2. Responsibility split

```text
Python
├─ search and branching
├─ state/action evaluation
├─ replay and experiment control
├─ logging and statistics
└─ result reporting
        │
        ▼
ocgcore
├─ rules and timing
├─ chains, costs, targets, and resolution
├─ legal action/selection requests
└─ execution of existing EDOPro Lua scripts
        │
        ▼
EDOPro card scripts and card data
```

Requirements:

- Python must not reimplement card rulings or core duel semantics.
- Existing EDOPro Lua scripts should be consumed without rewriting every card.
- Full-card-pool compatibility is a target, with compatibility determined by the selected ocgcore/script/data versions.
- Version combinations for core, scripts, card data, and constants must be recorded for reproducibility.

## 3. Python-to-core bridge

The bridge must expose enough of ocgcore to:

1. create and destroy a duel instance;
2. configure players, decks, seeds, and duel options;
3. advance processing until input is required or the duel ends;
4. read and decode core messages;
5. submit selections and responses;
6. load card data and Lua scripts;
7. reconstruct a duel from a recorded experiment.

Raw core messages must be converted into typed Python objects. Search code should not directly depend on binary message layouts.

```python
class DecisionRequest:
    request_type: str
    player: int
    candidates: list["Candidate"]
    constraints: dict[str, object]

class Action:
    kind: str
    source_card_id: int | None
    effect_index: int | None
    selections: tuple[object, ...]
```

The representation must distinguish at least:

- activating an effect;
- normal, special, and extra-deck summons;
- selecting cards, zones, positions, options, and numbers;
- paying costs;
- ordering simultaneous effects or cards;
- passing priority or declining an optional effect;
- ending the current phase or turn.

Stable action identity should use semantic fields such as card ID, controller, location, sequence, effect index, and request type rather than display text alone.

## 4. Search model

A search node represents a reproducible decision point, not only a visible board.

```python
class SearchNode:
    replay_key: str
    action_history: tuple[Action, ...]
    state_features: dict[str, object]
    state_score: float
    peak_score: float
    depth: int
```

The search loop is:

```text
reconstruct decision point
→ obtain legal decisions from ocgcore
→ convert responses into Actions
→ execute one Action
→ advance to the next decision point
→ evaluate and record
```

The engine must support trying each action from the same parent state independently.

## 5. State restoration and determinism

The initial implementation should use deterministic replay.

A replay record must include:

- core/script/card-data versions;
- duel configuration;
- deck order or sufficient shuffle seed information;
- all random seeds used by the core and Python;
- every submitted response and selection;
- interruption injection configuration;
- any external experiment parameters.

To explore sibling actions, the engine recreates the duel and replays the common history before applying the alternative action.

Future optimization may add snapshot or `clone_duel` support, but replay remains the reference implementation used to verify snapshot correctness.

A replayed history must be checked against expected request signatures. If the same history produces a different request, the run is non-reproducible and must not silently continue.

## 6. Exploration strategy

Exhaustive search is not assumed to be feasible. Exploration should progress in stages:

1. random or lightly constrained rollouts to collect transition data;
2. statistics for state and action outcomes;
3. best-first or beam search using accumulated estimates;
4. optional Monte Carlo tree search or learned policies after the baseline is trustworthy.

Random exploration must retain a non-zero probability for underexplored actions. Purely greedy reuse of early results could permanently hide strong but initially unlucky routes.

Suggested per state-action statistics:

- visit count;
- mean and maximum peak score;
- score variance;
- successful-route rate;
- terminal and failure categories;
- best known continuation;
- confidence or uncertainty estimate.

## 7. State evaluation and action evaluation

State value and action value are separate concepts.

- **State evaluation** estimates how desirable the current stopping point is.
- **Action evaluation** estimates the future outcome distribution after choosing an action from a state.

Initial state features may include:

- known interruptions or negations available on board;
- hand size and card identities where appropriate;
- field, graveyard, banished, and extra-deck resources;
- remaining normal summon;
- used once-per-turn effects and active restrictions;
- total attack and relevant battle pressure;
- follow-up and recoverable resources for the next turn;
- vulnerability indicators such as overcommitment.

Evaluation must be configurable by experiment. A combo endpoint, resource-preservation study, and damage test may require different weights or success predicates.

## 8. Peak Board and stopping decisions

The result of a route is not automatically the state reached after all legal actions are exhausted.

Every decision point must include an explicit stop action, conceptually `END_TURN` or `STOP_LINE`, whenever stopping is legally meaningful. This allows the search to preserve a strong board instead of consuming resources through unnecessary actions.

For each route, record both:

- **Peak Board**: the highest-evaluated legal stopping state encountered on the route;
- **Terminal Board**: the state where the rollout actually stopped or had no further selected continuation.

The route's primary result is its Peak Board. Required fields include:

- `peak_score`;
- `peak_state` or replay key;
- `peak_step`;
- actions up to the peak;
- terminal score/state;
- actions performed after the peak.

A temporary high-value state is only a valid Peak Board when the player can legally stop or pass into the intended endpoint from that state.

## 9. Pruning and loss cutting

Pruning should use evidence, not only a single hand-written score.

Possible pruning signals:

- the state is equivalent to a previously explored state with an equal or better resource profile;
- the optimistic upper bound cannot beat the current retained routes;
- historical continuation results are consistently poor with sufficient visits;
- the target predicate has become unreachable;
- resource and restriction conditions indicate a proven dead end;
- a beam-width or compute-budget limit has been reached.

Low-visit nodes should not be permanently discarded only because their estimated mean is low. Confidence-aware exploration or minimum-visit rules are required.

State deduplication should use canonical semantic state data where possible. Visible zones alone are insufficient because used effects, restrictions, chain context, and hidden/random information can change future legality.

## 10. Interruption experiments

Opponent interruption timing is supplied by the experiment; an autonomous opponent strategy is not required initially.

Workflow:

```text
run and record uninterrupted routes
→ select a recorded activation/decision point
→ configure the opponent hand and interruption
→ replay to that point
→ perform the legal interruption through ocgcore
→ resume search from the resolved interrupted state
→ compare the best recovery with the uninterrupted baseline
```

An interruption injection must identify a stable semantic target, for example:

- acting player's action number;
- source card ID and effect index;
- activation request signature;
- chain position;
- expected controller/location context.

The system must verify that the interruption is legally available at the requested point. It must not emulate negation by directly mutating Python state.

Initial target scenario:

> After sufficient uninterrupted search, apply Ash Blossom & Joyous Spring to a user-selected card effect and find the strongest legal recovery route.

Recorded results should include:

- baseline route and Peak Board;
- interrupted action and interruption card;
- post-resolution state;
- best recovery route and Peak Board;
- score and resource loss;
- whether the original target remains reachable;
- alternative endpoints discovered.

## 11. Outputs

Per opening hand or experiment:

- reproducible seed and version manifest;
- best route to Peak Board;
- terminal route for diagnostics;
- action tree or selected search trace;
- board/resource evaluation breakdown;
- interruption and recovery comparison.

Aggregated deck metrics may include:

- starter/opening success rate;
- brick rate under a configured success predicate;
- Peak Board score distribution;
- endpoint frequency;
- route diversity;
- recovery success rate for selected interruption tests;
- common interruption-sensitive actions;
- action-value and state-value statistics.

## 12. Logging and storage

The logger must preserve enough data to reproduce and audit every reported result.

Recommended logical entities:

- experiment;
- engine/version manifest;
- initial deal;
- decision request;
- action;
- transition;
- state feature snapshot;
- evaluation result;
- route;
- interruption case;
- aggregate statistic.

Large binary or engine-specific state should not be required for the first implementation. JSON Lines or SQLite are acceptable starting formats; storage interfaces should allow later migration.

## 13. Initial scope

The first useful milestone should remain narrow:

- one configured deck;
- first-player turn one;
- deterministic opening hands or fixed seeds;
- no opponent actions during baseline exploration;
- main-phase combo search;
- explicit stop action and Peak Board tracking;
- replay-based sibling exploration;
- one user-selected Ash Blossom interruption followed by recovery search.

The milestone is complete when one result can be reproduced from its manifest and action log, including the same selected interruption and recovery route.

## 14. Non-goals for the first milestone

- reimplementing ocgcore rules in Python;
- rewriting every card into a new Python or project-specific Lua format;
- autonomous opponent play;
- full-match win-rate estimation;
- perfect exhaustive search;
- reinforcement learning before deterministic replay and evaluation are validated;
- treating the current text-to-DSL output as authoritative game state semantics.

## 15. Relationship to the current DSL work

The current DSL pipeline remains useful for:

- human-readable effect structure;
- feature extraction for search and reports;
- grouping and explaining routes;
- candidate evaluation features;
- cross-checking card-script behavior against text-derived structure.

However, legal actions and rule resolution must come from ocgcore and its Lua scripts. The text-derived DSL must not override core legality in this architecture.

## 16. Open technical risks

- availability and stability of a suitable ocgcore C API;
- decoding all required message and response formats;
- reproducing every random decision across replays;
- version compatibility among core, Lua scripts, constants, and card data;
- combinatorial growth and misleading early rollout statistics;
- canonical state identity with hidden information and temporary restrictions;
- performance cost of replaying long common prefixes;
- licensing and redistribution obligations for external core, scripts, and data.

These risks should be validated with a small bridge prototype before the project commits to full-card-pool search.