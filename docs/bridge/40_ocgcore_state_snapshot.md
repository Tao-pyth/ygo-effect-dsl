# ocgcore state snapshots and legal stops

Status: API 11.0 prototype contract

Last updated: 2026-07-13

## Native query boundary

`OcgcoreDuel.query_field()`, `query_location()`, and `query()` copy the native buffer before another core call can invalidate it. Decoders return only Python integers, strings, lists, tuples, and mappings; no pointer or memory view survives the call.

The complete snapshot query matrix is fixed:

| Controller | Locations | API | Flags |
| --- | --- | --- | --- |
| 0 and 1 | deck, hand, monster zone, spell/trap zone, graveyard, banished, extra deck | `OCG_DuelQueryLocation` | `0x03ffffff` |
| field | LP, occupied zones, counts, current chain | `OCG_DuelQueryField` | n/a |
| 0 and 1 | each location count | `OCG_DuelQueryCount` | n/a |

A complete capture requires every canonical location exactly once. Monster and spell/trap zones must contain 7 and 8 slots respectively. Each decoded occupied-card count must match `OCG_DuelQueryCount`; truncated segments, missing `QUERY_END`, duplicate flags, trailing bytes, or count mismatches raise `OcgcoreSnapshotError`. A partial result is never hashed as a complete snapshot.

## Snapshot types

- `CompleteSnapshot` is the internal core-derived projection used for replay and hashing. It may contain hidden card data and must not be returned to an untrusted viewer.
- `VisibleSnapshot` applies viewer-specific redaction. Deck cards, opponent non-public cards, `QUERY_IS_HIDDEN` cards, and another player's pending request are removed or replaced by slot-only placeholders.
- `SearchProjection` selects complete or visible information mode. `exact_equivalence` is deliberately `false` in the prototype.
- `BoardSummary` contains viewer-safe counts, LP, public cards, and the source state hash for evaluator and Route DSL output.

These are separate types because a replay identity, an agent observation, a transposition key, and a display/evaluation summary have different disclosure and equivalence requirements.

## Identity and canonical hash

`CompleteSnapshot` maps into the versioned `ygo-state-id-v1` `CanonicalState`. The `state_` hash includes public field/process state, complete zone projection, constraints, history, pending request, information mode/completeness, and locked runtime/assets/seed environment. Query invocation order and `display_metadata` do not affect it. The serialized snapshot retains its query-shaped fields for diagnostics and also includes the canonical `state_identity` object. The checked fixed scenario proves that the same runtime, assets, seed, and actions produce the same state hash in a fresh process.

The API 11.0 query surface does not expose Lua globals, used-effect history, or every temporary summon/rule constraint. Therefore the current identity is explicitly marked `query_api_projection`; it must not be advertised as exact search-state equivalence. Issue #64 owns missing visibility/history/constraint representation and issue #65 owns exact versus approximate deduplication rules.

Query cardの`instance_key`は`controller:location:slot`から作る観測座標であり、永続instance IDではない。Issue #112のv1 authorityは凍結する。Issue #116のopt-in v2は、各Request直後のnonce付き完全scanから`persistent_instance_id`と`owner`をsnapshotへ付与し、座標keyと永続IDを別fieldとして保持する。計装traceが欠落する場合は`instance_key`やcard codeから補完しない。PlayerViewは相手hidden IDを除外し、再公開時は新しいviewer aliasを発行する。詳細は[card instance identity](../ocgcore/40_card_instance_identity.md)で定義する。

## Legal stop

Legal-stop evaluation uses only core progression state and core-derived controls:

| Condition | `can_stop` | Reason |
| --- | --- | --- |
| Current chain is non-empty | false | `chain_active` |
| Core is processing | false | `mandatory_processing` |
| Forced request is pending | false | `mandatory_request` |
| Non-idle request is pending | false | `pending_request` |
| Idle request has no end-turn control | false | `end_turn_unavailable` |
| Idle request exposes `control:end_turn` | true | `core_end_turn_available` |
| Duel has ended | true | `terminal` |

`STOP_LINE` is the search operation that records the current legal checkpoint. It does not send bytes to ocgcore. `END_TURN` is a real core action encoded from `control:end_turn`; stopping a line must not execute it. Every decision contains `{can_stop, reason, evidence}`, including state hash, process state, pending request type, and chain count, so issue #75 can log both accepted and rejected candidates.

## Replay evidence

Each Route DSL replay event stores request signature, action ID, state hashes before/after, and response codec trace. Checkpoints reference the event's post-action state hash. Peak Board is selected only from legal checkpoints; Terminal Board is the last explored route checkpoint and does not imply that the duel itself ended.
