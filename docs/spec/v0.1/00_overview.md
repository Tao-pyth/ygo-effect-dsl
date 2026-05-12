# ygoEffectDSL Spec v0.1 (Draft) - Overview

> Status: Draft / minimal semantics planning
> Last updated: 2026-05-13

v0.1 connects the v0.0 research conversion baseline to minimal state/action
semantics. It is not a game engine implementation. The purpose is to define the
smallest read-only state shape and action vocabulary that a later executor can
validate against representative card effects.

## Scope

v0.1 reads v0.0-style DSL payloads:

- `effects[].actions[]` is the canonical action source.
- `effects[].targets[]` is the canonical target declaration source.
- legacy `effect.action` may be read only as a compatibility fallback.
- `trigger`, `condition`, `cost`, and `restriction` remain mostly descriptive.

The first v0.1 milestone should answer one question: for a single action, can a
consumer identify the required objects and the expected one-step state delta?

## Documents

- [Minimal Semantics](10_minimal_semantics.md)
- [First 10 One-Step Applications](20_first_10_applications.md)

## Non-Goals

v0.1 does not define:

- chain/stack resolution
- full timing windows
- replacement effects
- continuous effects
- hidden-information choice enumeration
- full opponent response modeling
- legality details beyond narrow preconditions

## Readiness Criteria

A v0.1 action candidate is usable when:

1. its `type` is in the initial action vocabulary;
2. required count, source zone, destination zone, and controller can be inferred
   from the action or its target;
3. unresolved selector constraints are preserved instead of discarded;
4. the expected state delta can be described without mutating real runtime state.

The output of this draft is a contract for future validation and analysis, not
an executor.
