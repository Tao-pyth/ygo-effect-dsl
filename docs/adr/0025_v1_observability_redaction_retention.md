# ADR 0025: v1.0.0 observability, redaction, and retention

## Status

Accepted for v1.0.0 production distribution qualification.

## Context

v1.0.0 needs enough observability to debug local, CI, and production distribution failures without publishing deck/card/player/private information, hidden state, raw Bridge payload, worker stdout/stderr, filesystem paths, process IDs, or crash dump contents by default. This policy must remain consistent with the PlayerView redaction contract and `information-access-audit-v2`.

## Decision

structured observability records use versioned schemas and carry correlation ID, run/job/worker attempt identity, package version, schema/contract version, diagnostic code, CLI exit category, status, and safe numeric counters. Metrics and traces may retain counts, durations, retry counts, artifact digests, and public route status. They must not retain raw hidden payload, private card identity, deck order, raw Bridge frame bytes, raw Lua or CDB payload, worker stdout/stderr text, absolute path, process ID, seed, request signature, complete state hash, source Route ID, source Replay digest, or crash dump body in public or committed release evidence.

Redaction is enforced before publication. PlayerView artifacts, verification reports, support-facing diagnostics, JSON exports, Parquet exports, UI payloads, CLI reports, and failure reports must pass `information-access-audit-v2` or an equivalent purpose-specific allowlist before atomic publication. canary leak tests are release evidence: private canary values must be absent from public artifacts and absent from the audit report itself.

Worker/core crash handling preserves debug value through safe failure category, retryability, return code where needed, stdout/stderr digests, and worker input digest only in internal attempt records. Public failure reports store safe failure code and `artifact_commit: not_published`. Raw crash dump files are not created by default. If an operator deliberately captures a crash dump, it is a local private artifact outside release evidence, must be retained only under explicit support consent, and must be deleted or archived according to the retention window below.

Retention policy:

| Surface | Default retention | Deletion rule |
|---|---:|---|
| local raw logs and private lineage | user controlled, not bundled | explicit user delete or support-bundle cleanup |
| local public reports and PlayerView artifacts | user controlled | delete with owning run/project |
| CI release evidence | retained with workflow artifact policy | delete expired artifacts through GitHub retention |
| committed release evidence | retained in git history | never include private/raw payload |
| production support artifacts | 30 days unless incident requires extension | delete after closure or documented extension |
| deliberate crash dumps | disabled by default | delete immediately after digest/repro summary unless user consents |

## Consequences

Debugging must rely on structured diagnostic code, failure category, correlation ID, safe counters, and content digests instead of raw hidden payload. A single canary leak or side-channel finding blocks artifact publication. Future observability fields need a schema/contract version and must be added to the canary audit or an exact reviewed allowlist before use.
