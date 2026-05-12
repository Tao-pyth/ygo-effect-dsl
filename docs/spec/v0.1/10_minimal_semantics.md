# ygoEffectDSL Spec v0.1 (Draft) - Minimal Semantics

> Status: Draft / no engine implementation
> Last updated: 2026-05-13

v0.1 defines a read-only state model and a narrow action vocabulary. A v0.1
reader may produce candidate state deltas, but this spec does not require the
repo to execute those deltas.

## Read-Only State Model

State is a snapshot:

```yaml
state:
  Deck:
    you: []
    opponent: []
  Hand:
    you: []
    opponent: []
  Field:
    you: []
    opponent: []
  GY:
    you: []
    opponent: []
  Banished:
    you: []
    opponent: []
  Extra:
    you: []
    opponent: []
  Flags: {}
```

Zones contain opaque card references. A card reference must be stable enough for
analysis, but v0.1 does not require a full card object. `Flags` stores
turn-scoped or effect-scoped facts such as "normal_summoned_this_turn",
"negated_effect_ids", and "once_per_turn_used".

The model is read-only for v0.1 docs: an application candidate records the
expected delta instead of mutating the source snapshot.

## Target Records

v0.1 strengthens v0.0 `targets[]` into selector records:

| Field | Meaning | Required for v0.1 reader |
| --- | --- | --- |
| `selector.kind` | object class, such as `card`, `monster`, `spell`, `trap`, or `effect` | yes |
| `zones` | allowed zones, normalized to `Deck`, `Hand`, `Field`, `GY`, `Banished`, `Extra` | when the action needs a source |
| `controller` | `you`, `opponent`, or `either` | recommended; default is action-specific |
| `count` | number of objects to select | yes; may come from target `count` or action `n` |
| `constraints` | extra unresolved predicates, such as archetype, attribute, race, subtype, face-up, or text phrase | preserve when present |
| `targeting_mode` | `target`, `choose`, `select`, or `implicit` | recommended; default is `implicit` |

## Reading v0.0 `actions[]` and `targets[]`

For each `effects[].actions[]` item:

1. Read `action.type` as the semantic verb.
2. If `action.target_id` is present, resolve it against `effects[].targets[]`.
3. Read `count` from `target.count`; otherwise read `action.n`; otherwise use
   the action default.
4. Read zones from target `selector.zones`, then from action `from`/`to`, then
   from `action.desc` only as a low-confidence fallback.
5. Read controller from target `selector.controller`, then from phrases in
   `desc`/`raw`, then from the action default.
6. Preserve `constraints` from `selector.constraints` and any inline `desc` or
   `who` phrase that is not otherwise normalized.
7. Set `targeting_mode` from `selector.targeting_mode`; if absent, infer
   `target` when the raw clause uses "target", otherwise use `implicit`.

If `actions[]` is empty and legacy `action` is non-empty, the reader may produce
a compatibility candidate and should keep a diagnostic note. New v0.1 docs and
tests should prefer `actions[]`.

## Initial Action Vocabulary

The common action schema is:

```yaml
type: draw
count: 1
source: Deck
destination: Hand
controller: you
target:
  kind: card
  zones: [Deck]
  controller: you
  constraints: []
  targeting_mode: implicit
delta:
  moves: []
  flags: []
risks: []
```

### `draw`

Schema:

- `type: draw`
- `count`: from `action.n`, default `1`
- `controller`: default `you`
- source `Deck`, destination `Hand`

Preconditions:

- `Deck[controller]` has at least `count` cards.

State delta:

- move `count` unknown top cards from `Deck[controller]` to
  `Hand[controller]`.

### `add_to_hand`

Schema:

- `type: add_to_hand`
- `count`: from target or `action.n`, default `1`
- source: from `action.from` or target `zones`, usually `Deck`, `GY`, or
  `Banished`
- destination `Hand`
- target kind and constraints from target or inline `desc`

Preconditions:

- source zone contains at least `count` matching cards.
- if `targeting_mode: target`, selected cards must be legal targets at
  activation time.

State delta:

- move selected cards from source zone to `Hand[controller]`.

### `send_to_gy`

Schema:

- `type: send_to_gy`
- `count`: from target or `action.n`, default `1`
- source: from target `zones`, `action.from`, or inline phrase
- destination `GY`

Preconditions:

- source zone contains at least `count` matching cards.

State delta:

- move selected cards from source zone to `GY[owner]`.

### `destroy`

Schema:

- `type: destroy`
- `count`: from target or `action.n`, default `1`
- target kind default `card`
- source usually `Field`
- destination `GY`

Preconditions:

- matching card exists on `Field`.
- target is destructible; v0.1 records this as unresolved unless represented in
  constraints.

State delta:

- mark selected cards as destroyed.
- move destroyed cards from `Field[controller]` to `GY[owner]`.

### `special_summon`

Schema:

- `type: special_summon`
- `count`: from target or `action.n`, default `1`
- source: from `action.from`, target `zones`, `who: self`, or inline phrase
- destination `Field`
- summon controller default `you`

Preconditions:

- source has matching card.
- `Field[controller]` has available monster zone capacity; v0.1 keeps capacity
  as a `Flags` or external validation concern.

State delta:

- move selected monster from source to `Field[controller]`.
- add a summon event flag if a future analyzer needs it.

### `banish`

Schema:

- `type: banish`
- `count`: from target or `action.n`, default `1`
- source: from target `zones`, `action.from`, or inline phrase
- destination `Banished`

Preconditions:

- source zone contains at least `count` matching cards.

State delta:

- move selected cards from source zone to `Banished[owner]`.

### `negate`

Schema:

- `type: negate`
- target kind default `effect`
- target source: active or referenced effect, not a normal card zone
- destination: none

Preconditions:

- referenced effect exists and has not resolved or has a negatable status.

State delta:

- add or update `Flags.negated_effect_ids`.
- no zone movement unless another action says to destroy, banish, or send.

## Validation Notes

A candidate should be considered incomplete, not invalid, when:

- `selector.kind` is known but zones are missing;
- `controller` is missing but can be defaulted;
- `constraints` contain unresolved text;
- `targeting_mode` is inferred from raw text.

A candidate should be considered blocked when:

- action `type` is outside the v0.1 vocabulary;
- the action needs a target and neither target record nor inline selector is
  available;
- no source zone can be inferred for a move action.
