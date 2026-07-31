# ADR 0024: v1.0.0 compatibility policy

## Status

Accepted for v1.0.0 production distribution qualification.

## Context

v1.0.0 needs a stable rule for package SemVer, schema/contract version, strategy version, evaluator version, cache/worker policy version, CLI/API payloads, Route artifacts, Replay artifacts, and migration behavior. A release must not reinterpret an incompatible artifact by guessing missing semantic data.

## Decision

Package SemVer covers the Python package, CLI, wheel, sdist, and Windows distribution. It does not automatically rewrite or bless schema/contract version boundaries. Experiment, Scenario, Route, Replay, Search, PlayerView, strategy version, evaluator version, cache/worker policy version, diagnostic code, and CLI exit category remain independently versioned compatibility contracts.

The v1.0.0 compatibility matrix is:

| Artifact | Version | Policy |
|---|---:|---|
| Experiment | 0.3a | backward read only as explicit migration input |
| Experiment | 0.3b | executable compatibility for existing real-core prototype fixtures |
| Experiment | 0.4 | current execution contract |
| Route DSL | 0.1 | validated strict Route contract |
| Replay | 0.3a and manifest contracts | Replay compatibility requires strict version identity and Experiment match |

Backward read means an older artifact can be parsed and diagnosed, not executed after silent conversion. `0.3a` Experiment files require `experiment-migrate` with explicit deck order, opening hand, and sampling reference choices. `0.3b` and `0.4` are the only Experiment versions accepted at current execution boundaries. Replay compatibility requires the Route, Experiment, Replay root, Replay manifest, and information audit to agree; a mismatched Experiment or Route schema is rejected.

forward rejection is mandatory. Unknown future schema versions, unknown required field, unsupported enum value, unsupported strategy version, unsupported evaluator version, unsupported cache/worker policy version, unknown Bridge message, unknown field, and unknown diagnostic code must not be silently ignored or normalized into a supported value. The safe result is a structured diagnostic and non-success CLI exit category, or a fail-closed artifact rejection before publication.

Deprecation warning and removal window rules:

- a breaking schema or payload change needs a new schema/contract version;
- the release note must identify the deprecation warning, migration command, and removal window;
- irreversible migration requires backup, dry-run where practical, explicit confirmation, and rollback or restore guidance;
- no silent migration is allowed in a run, replay, import, or publication path.

unknown field handling is strict for versioned contract objects that are persisted, replayed, or used as release evidence. Optional extension fields are allowed only when a named contract explicitly reserves that extension surface. Unsupported enum values are rejected at the validator boundary. Diagnostic code stability is part of the public CLI/API contract: known diagnostic code values and CLI exit category values may gain documented additions, but consumers must not infer success from an unknown diagnostic code.

## Consequences

v1.0.0 can claim compatibility only for the matrix rows that have committed fixtures and release evidence. Legacy `0.3a` artifacts remain readable for explicit migration, but incompatible input is not silently converted. Future artifacts fail closed until a new compatibility ADR, migration path, and tests are committed.
