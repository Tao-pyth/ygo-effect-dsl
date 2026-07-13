# ygoEffectDSL Spec v0.1 - Overview

Status: Historical baseline / legacy DSL CORE / no full engine implementation

Last updated: 2026-07-13

## Purpose

V0.1 recorded an earlier attempt to connect the existing v0.0 DSL conversion baseline to the long-term project direction defined in [Project Charter](../../00_project_charter.md).

V0.1 is not a complete game engine. Under the current Charter and ADR-0003, DSL conversion is not the input foundation for future Bridge, Replay, Search, or Evaluation work. The V0.1 spec remains as historical context for the legacy DSL CORE.

## What V0.1 Establishes

V0.1 establishes these project-level contracts:

1. `docs/00_project_charter.md` is the highest-level decision document.
2. The project direction is "game engine + AI search", not DDD-first domain modeling.
3. Python must not reimplement Yu-Gi-Oh! rules.
4. ocgcore / EDOPro Lua are the future rule truth source.
5. The current DSL conversion pipeline is a legacy compatibility layer.
6. Minimal state/action semantics are historical notes and must not drive new engine work.

## Current Implementation Layer

The current codebase is still centered on:

- ingest
- transform
- validate
- analyze
- representative golden tests

This remains only for compatibility with existing tests. The search engine must not depend on DSL Action and Target extraction.

## Engine Direction

The current primary runtime direction is:

```text
ocgcore / EDOPro Lua
  ▼
Bridge
  ▼
Replay
  ▼
Search
  ▼
Evaluation
  ▼
Statistics / Experiment
```

The V0.1 DSL candidate path is deprecated and does not execute real duels.

## Scope

V0.1 reads v0.0-style DSL payloads:

- `effects[].actions[]` is the canonical action source.
- `effects[].targets[]` is the canonical target declaration source.
- legacy `effect.action` may be read only as a compatibility fallback.
- `trigger`, `condition`, `cost`, and `restriction` remain mostly descriptive.

The first V0.1 technical question is:

> For a single action, can a consumer identify the required objects and the expected one-step state delta?

## Documents

- [Project Charter](../../00_project_charter.md)
- [Architecture](../../architecture.md)
- [Roadmap](../../roadmap.md)
- [Minimal Semantics](10_minimal_semantics.md)
- [First 10 One-Step Applications](20_first_10_applications.md)
- [Bridge Overview](../../bridge/overview.md)
- [Bridge Messages](../../bridge/messages.md)
- [Replay Overview](../../replay/overview.md)
- [Replay Format](../../replay/format.md)
- [ADR-0000: Project Charter](../../adr/0000_project_charter.md)
- [ADR-0001: Replay Baseline](../../adr/0001_replay_baseline.md)
- [ADR-0002: Python Does Not Own Rules](../../adr/0002_python_does_not_own_rules.md)

## Non-Goals

V0.1 does not define:

- full ocgcore bridge
- real duel execution
- chain/stack resolution
- full timing windows
- replacement effects
- continuous effects
- hidden-information choice enumeration
- full opponent response modeling
- legality details beyond narrow preconditions
- Python-side Yu-Gi-Oh! rule reimplementation

## Readiness Criteria

A V0.1 action candidate is usable when:

1. its `type` is in the initial action vocabulary;
2. required count, source zone, destination zone, and controller can be inferred from the action or its target;
3. unresolved selector constraints are preserved instead of discarded;
4. the expected state delta can be described without mutating real runtime state;
5. diagnostics still expose missing zones, unresolved targets, unknown actions, and compatibility fallbacks.

The output of V0.1 is not a contract for future engine boundary design. It is a legacy record and not an executor.
