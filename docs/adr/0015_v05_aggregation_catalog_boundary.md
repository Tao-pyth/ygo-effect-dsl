# ADR 0015: Keep the v0.5 control plane in SQLite and analytics in Parquet

Status: accepted for v0.5

Date: 2026-07-15

## Context

v0.5 must support long-running search jobs, corpus ingestion, route comparison, and a Windows desktop dashboard on one developer workstation. The system already stores ordered raw events in JSONL, run and artifact references in SQLite, and derived route metrics in partitioned Parquet. Issue #157 requires an explicit decision before production assets or schema versions change.

The relevant workloads are structurally different. Job state needs small transactional updates and exact point lookup. Corpus analytics needs immutable bulk publication, column projection, scans, and grouping. UI projections must be replaceable because display bugs must never damage source evidence. A single embedded database for every role would reduce the number of files but would couple recovery, schema migration, and write contention across unrelated responsibilities.

## Decision

v0.5 uses the following authority boundary:

| Data role | Backend | Authority and mutation rule |
|---|---|---|
| Raw event and Route evidence | Versioned JSONL/YAML artifacts | Immutable source; append and seal |
| Run, job, lease, and artifact references | SQLite | Operational authority; one host and one catalog writer |
| Derived corpus metrics | Partitioned Parquet through PyArrow | Rebuildable analytical authority; publish immutable partitions |
| Desktop UI projection cache | Separate SQLite file | No authority; drop and rebuild from catalog and Parquet |
| Optional analytical accelerator | DuckDB reader | Deferred; may query evidence but must not own job state or the only copy |

The SQLite catalog remains the transaction boundary for job state and publication references. A Parquet artifact is first written to a temporary path, reread and verified, atomically renamed, and then referenced by a committed catalog transaction. Orphan temporary files are safe to remove. A catalog reference to a missing or hash-mismatched artifact is corruption and fails closed.

Schema ownership is explicit per artifact family. Catalog readers accept exactly their declared schema version. Parquet readers accept the current schema and only documented additive nullable columns within that schema family. An incompatible type, semantic, key, or partition change requires a new schema version and a new dataset root.

Migration and backfill use side-by-side artifacts:

1. Read and validate the old source without modifying it.
2. Write the new schema to a new path and record source IDs, tool version, counts, and hashes.
3. Verify semantic counts and references.
4. Switch the catalog reference in one transaction.
5. Retain the old root for one minor release; rollback switches the reference back.
6. Archive or delete old data only through an explicit maintenance operation.

Generic compatibility reads are not added. An explicit adapter may support the immediately preceding schema for one minor release, but it must produce a current artifact before normal query execution. Package-level Experiment and Route compatibility remains governed by their own release contracts.

Distributed execution, network filesystems, multiple catalog writers, and remote database operation are not v0.5 goals. The boundary must be reconsidered when execution spans hosts or requires concurrent writers. That future decision may add a service database without changing the raw and Parquet artifact contracts.

## Evidence

`docs/storage/evidence/aggregation_catalog_selection.json` records a Windows workload with 10,000 catalog rows and 100,000 analytical rows over three samples. It compares SQLite and DuckDB control-plane operations and compares SQLite, DuckDB, and Parquet analytical publication/grouping. All analytical candidates produce the same normalized result hash, and both catalog candidates produce the same lifecycle counts.

The benchmark is directional rather than a release threshold. It verifies role fitness, artifact size, result equivalence, transaction rollback, catalog schema mismatch rejection, and truncated Parquet rejection. Final 100,000-run/1,000,000-event calibration remains #167.

The measured evidence and existing packaging evidence support this selection because SQLite is part of Python and fits the single-writer control plane, while direct PyArrow already owns schema metadata and atomic Parquet publication. DuckDB is technically viable, but making it authoritative would add a binary dependency and a second operational migration surface without solving a v0.5 requirement.

## Consequences

Job orchestration can evolve transactionally without rewriting large analytical partitions. Analytics can compact or backfill data without mutating raw evidence. The desktop can discard its projection cache when versions disagree. Recovery logic has an explicit source of truth for every failure point.

The single SQLite writer is an intentional limit. Long analytical scans must not run through the operational catalog, and the UI must not hold write transactions. Query acceleration may later use DuckDB as a read-only implementation behind the query API, but adding it requires its own dependency, concurrency, and packaging evidence.
