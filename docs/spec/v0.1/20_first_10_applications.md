# ygoEffectDSL Spec v0.1 - First 10 One-Step Applications

> Status: Historical baseline / representative legacy candidates
> Last updated: 2026-07-13

This table maps the first 10 representative benchmark cards to historical V0.1 one-step application candidates. It uses the v0.0 DSL shape as input and records what the earlier DSL-reader idea attempted to infer before any real engine execution existed.

These rows are not duel simulations. Under ADR-0003, they are not a future engine boundary and must not be used as Search Engine input.

| CID | Card name | Main action | Required target information | Expected one-step state change | Unresolved risk |
| --- | --- | --- | --- | --- | --- |
| 9001 | Bench Draw Two | `draw` | `count=2`, `controller=you`, implicit source `Deck` | move 2 unknown top cards from `Deck[you]` to `Hand[you]` | deck order and hidden card identity are abstract |
| 9002 | Bench Search Spell | `add_to_hand` | `selector.kind=card`, `zones=[Deck]`, `controller=you`, `count=1`, `constraints=["White Forest", "Spell/Trap"]`, `targeting_mode=implicit` | move 1 matching card from `Deck[you]` to `Hand[you]` | archetype and Spell/Trap constraints are text constraints, not typed predicates yet |
| 9003 | Bench Destroy Field | `destroy` | `selector.kind=card`, `zones=[Field]`, `controller=either`, `count=1`, `constraints=["on the field"]`, `targeting_mode=implicit` | move 1 selected Field card to its owner's `GY` and mark it destroyed | no declared `targets[]`; destructibility and owner/controller split are unresolved |
| 9004 | Bench Send Monster | `send_to_gy` | `selector.kind=monster`, `zones=[Field]` or unresolved source, `controller=either`, `count=1`, `targeting_mode=implicit` | move 1 selected monster from inferred source to its owner's `GY` | source zone is not explicit in the text or current action |
| 9005 | Bench Summon Self | `special_summon` | `selector.kind=monster`, `zones=[Hand]` or current self zone, `controller=you`, `count=1`, `constraints=["self"]`, `targeting_mode=implicit` | move this card from its current legal source to `Field[you]` | "this card" requires caller context; source zone is not encoded |
| 9006 | Bench Summon Deck | `special_summon` | `selector.kind=monster`, `zones=[Deck]`, `controller=you`, `count=1`, `constraints=["LIGHT", "Spellcaster", "Tuner"]`, `targeting_mode=implicit` | move 1 matching monster from `Deck[you]` to `Field[you]` | Tuner is currently part of text, and Spellcaster may be confused with Spell in category extraction |
| 9007 | Bench Banish GY | `banish` | `selector.kind=card`, `zones=[GY]`, `controller=you`, `count=1`, `targeting_mode=implicit` | move 1 card from `GY[you]` to `Banished[owner]` | current action stores the source in `desc`, not structured `from` or `targets[]` |
| 9008 | Bench Target Return | out of vocabulary: `return_to_extra` | current `targets[]`: `selector.kind=monster`, `controller=you`, `count=1`; v0.1 would also want `zones=[Field]`, `targeting_mode=target` | no v0.1 action delta; future extension would move target from `Field[you]` to `Extra[owner]` | `return_to_extra` is not in the initial vocabulary and target zone/mode are partly inferred |
| 9009 | Bench Target Destroy | `destroy` | current `targets[]`: `selector.kind=card`, `controller=opponent` intended, `count=1`, plus inferred `zones=[Field]`, `targeting_mode=target` | move targeted card from opponent `Field` to its owner's `GY` and mark it destroyed | current golden output records `controller=you` despite raw "opponent controls"; reader should preserve raw mismatch as risk |
| 9010 | Bench Cost Discard Draw | `draw` after cost | action target: `count=2`, `controller=you`; cost target: discard `count=1` card from `Hand[you]` | cost candidate moves 1 card from `Hand[you]` to `GY[owner]`, then action candidate moves drawn cards from `Deck[you]` to `Hand[you]` | `discard` is kept in `cost` instead of `actions[]`; `draw.n=2` verifies fragment-local number binding |

## Reader Expectations

The first 10 cards deliberately include easy actions and rough edges:

- 9001-9007 should produce v0.1 action candidates with incomplete but usable
  target selectors.
- 9008 should remain visible as a vocabulary gap because `return_to_extra` is
  outside `draw`, `add_to_hand`, `send_to_gy`, `destroy`, `special_summon`,
  `banish`, and `negate`.
- 9009 should expose target controller mismatch instead of silently trusting the
  structured selector.
- 9010 should expose cost/action ordering without duplicating the cost in
  `actions[]`.

These candidates remain only as a historical record of the attempted bridge from v0.0 `actions[]` and `targets[]` to V0.1 state/action semantics. The current Primary Runtime Path is ocgcore / EDOPro Lua -> Bridge -> Replay / Search / Evaluation.
