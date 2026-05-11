# ygoEffectDSL Spec v0.0 (Draft) - Grammar

> Status: Draft / experimental research baseline
> Last updated: 2026-05-12

v0.0 defines the stable shape of transformed card-effect data. It is a research conversion format, not a full game engine contract.

## Design Principles

1. Required structural keys are emitted even when unresolved.
2. Structure is preferred over semantic completeness.
3. `actions[]` is the canonical effect-action representation.
4. Legacy fields may remain only as compatibility fallbacks and must be visible to validation/analyze.

## Root Object

```yaml
dsl_version: "0.0"
card:
  cid: 0
  name:
    en: ""
    ja: ""
  text:
    en: ""
    ja: ""
  props: {}
effects: []
meta: {}
```

`card.info` is not part of the v0.0 DSL. Raw ETL fields such as `card_info_en` may be normalized into compact `card.props` values during transform, but the raw info blob must not be exported under `card`.

## `card`

Required:

- `card.cid`: Konami/card identifier as integer or string.
- `card.name.en` / `card.name.ja`: present as strings; empty string is allowed.
- `card.text.en` / `card.text.ja`: present as strings; empty string is allowed.
- `card.props`: compact card metadata object. Empty object is allowed.

## `effects[]`

Each effect object has these fields:

| Field | Required | Type | Notes |
| --- | --- | --- | --- |
| `id` | yes | string | Recommended form: `{cid}_001` |
| `order` | yes | integer | 1-based effect order |
| `trigger` | yes | object | Empty object allowed |
| `restriction` | yes | object | Empty object allowed |
| `condition` | yes | object | Empty object allowed |
| `cost` | yes | object | Empty object allowed |
| `actions` | yes | list | Canonical action list; empty list allowed for unresolved text |
| `action` | compatibility | object | Legacy fallback mirroring the first action when present |
| `targets` | yes | list | Canonical target declarations; empty list allowed |

`action` is a legacy fallback. New consumers must read `actions[]`. Validators should warn when a payload has only `action` and no `actions[]`.

## `actions[]`

Each action is an object. The canonical minimum field is:

```yaml
type: "draw"
```

Common v0.0 action types:

- `draw`
- `add_to_hand`
- `send_to_gy`
- `destroy`
- `special_summon`
- `banish`
- `negate`

The current transformer may also emit compatibility/research action types such as `discard`, `return_to_deck`, and `return_to_extra`. Unknown action types are valid YAML shape but should be reported as validation warnings.

Actions may use inline selector fields such as `n`, `desc`, `from`, `to`, or `who`, or point to a declared target:

```yaml
actions:
  - type: "destroy"
    target_id: "t1"
```

## `targets[]`

Targets are declared separately so that action, cost, and condition blocks can refer to the same selection.

```yaml
targets:
  - id: "t1"
    count: 1
    selector:
      kind: "monster"
      zones: ["field"]
      controller: "opponent"
    raw: "target 1 monster your opponent controls"
```

Required target fields:

- `id`: string.
- `count`: integer.
- `selector`: object.
- `selector.kind`: non-empty string.

Recommended selector fields:

- `zones`: list of zones such as `deck`, `hand`, `field`, `gy`, `banished`, `extra`.
- `controller`: `you`, `opponent`, or `either`.
- `archetype`: archetype/name phrase when captured.
- `subtype`: subtype such as `synchro`, `fusion`, `xyz`, `link`, `ritual`, `normal`, `effect`.
- `constraints`: list/object for unresolved extra restrictions.
- `targeting_mode`: `target`, `choose`, or `select` when known.

`selector.kind: "unknown"` is structurally valid but should produce an `unresolved_target` warning.

## Empty Values

Use these empty values instead of omitting structural keys:

| Kind | Empty value |
| --- | --- |
| string | `""` |
| list | `[]` |
| object | `{}` |

## Validation Severity

Validators categorize diagnostics as:

- `error`: DSL shape is invalid for v0.0.
- `warning`: DSL shape is valid, but unresolved, ambiguous, or compatibility-only.
- `info`: parser/analysis note.

Standard diagnostic codes include:

- `unknown_action`
- `unresolved_target`
- `missing_selector`
- `legacy_action_fallback`

## Compatibility Policy

v0.0 is experimental, but this grammar is the baseline for golden tests and benchmark comparisons. Any intended DSL output change should update the representative-card golden files and the changelog in the same change.
