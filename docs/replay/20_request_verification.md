# Replay request verification

Status: V0.3a executable contract

Last updated: 2026-07-13

## Signature identity

A `DecisionRequest.request_signature` is the canonical hash of:

- request schema version and request type
- acting player
- ordered candidate identities: candidate ID, kind, card/effect reference, and response payload
- selection constraints
- core-derived context, including chain, turn/priority player, source, version metadata, visible board, and protocol-specific extra fields

`request_id`, the signature string itself, and candidate display labels are excluded. Presentation metadata must not be inserted into context identity fields.

## Playback order

Strict playback verifies the reproducibility manifest before starting a worker. A core, Lua, CDB, rule, or seed difference raises `ReplayEnvironmentMismatchError`; request comparison is not attempted under a different environment.

For each replay step, the verifier compares the recorded and current request signatures. On mismatch it reconstructs both signature identities and reports the first canonical path with recorded/current values in `ReplaySignatureMismatchError`. Examples are `candidates[0].candidate_id`, `constraints.max_selections`, and `context.extra.message_type`. Event-count mismatch is reported as `events.length`.

The verifier does not guess a replacement candidate and does not continue after the first divergence. This keeps the failure attached to its true origin rather than producing misleading downstream state-hash differences.
