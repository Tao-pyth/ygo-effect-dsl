# v1.0.0 threat model and dependency-update policy

## Scope

This threat model covers the supported v1.0.0 local Windows/Python distribution boundary: untrusted YDK, YAML, and Lua path inputs; SQLite/CDB reads; native DLL execution; worker IPC; artifact import/export; desktop bridge calls; and the GitHub Actions supply chain.

## Release blocker rule

Any unmitigated critical or high risk is a release blocker. A v1.0.0 release may proceed only when every critical/high risk has one of these states:

- mitigated by code and tests;
- mitigated by fail-closed release evidence;
- explicitly unsupported in the support matrix;
- blocked by a follow-up issue that keeps production distribution gated.

Medium and low residual risks may remain only when documented with owner, mitigation, and re-evaluation trigger.

## Trust boundaries and abuse cases

| Boundary | Abuse case | Impact | Mitigation | Residual risk |
| --- | --- | --- | --- | --- |
| untrusted YDK/YAML input | malformed document, oversized payload, unknown schema, silent migration | corrupted Route or misleading result | schema validation, explicit migration, unknown-field rejection, fail-closed compatibility policy | low |
| Lua script path | path traversal, symlink escape, case collision, arbitrary script root | load attacker-controlled Lua or wrong card script | `FilesystemScriptProvider` canonical path checks, strict CardScripts profile, root outside profile unsupported | low |
| unsafe Lua library option | enable unsafe libraries or native payload pointer | script gains filesystem/process capability | `DuelConfig` rejects unsafe Lua; `OCG_DuelOptions.enableUnsafeLibraries` remains zero; payload pointer is null | low |
| SQLite/CDB | missing row, malformed schema, writable database access | wrong card data or data corruption | read-only SQLite access, scalar conversion, missing data classified as asset error | medium |
| native DLL | malicious or incompatible DLL, crash, hang, malformed native payload | host process compromise or search corruption | isolated worker process, pinned lock ID/API, startup version check, deadline kill, pointer-free diagnostics | medium |
| worker IPC | oversize frame, truncated frame, malformed failure envelope, late result | worker crash or incorrect recovery | 1 MiB frame limit, schema/version checks, failure taxonomy, worker replacement | low |
| artifact import/export | zip traversal, symlink member, third-party payload smuggling, absolute path leak | package compromise or private data leak | release audit, asset allowlist default deny, redaction audit, content-addressed evidence | low |
| desktop bridge | arbitrary Python method, remote URL, local REST API | local code execution or data exfiltration | single allowlisted bridge, packaged static UI, default-deny CSP, no general REST API | low |
| GitHub Actions supply chain | deprecated action runtime, unpinned action major, unchecked release artifact | compromised build or unverifiable release | allowed action major policy, dry-run gated release, checksums, SBOM, build provenance, protected environment | medium |

The table above is the v1.0.0 trust boundaries register.

## Required security tests

The release evidence must keep tests for these negative cases:

- path traversal, symlink escape, case mismatch, duplicate resolution, and arbitrary CardScripts root rejection;
- unsafe Lua libraries disabled by both config validation and native manifest evidence;
- resource exhaustion through 1 MiB Lua/script/checkpoint/IPC or release archive limits;
- malformed native payloads, malformed selection frames, malformed worker failure envelopes, and unsupported schema/version handling;
- release artifact traversal, symbolic/special members, third-party payload suffixes, and oversized members;
- GitHub Actions action pinning and dry-run release gating.

## Dependency and action pinning

Runtime dependencies are intentionally narrow:

- required runtime dependency: `PyYAML>=6.0`;
- optional analytics dependency: `pyarrow==25.0.0`;
- optional desktop dependency: `pywebview==6.2.1`;
- GitHub Actions release workflows may use only the current allowed major actions recorded by the gated release evidence, including `actions/checkout@v7`, `actions/setup-python@v6`, and `actions/upload-artifact@v7`.

Native ocgcore, CardScripts, and card database assets are user-acquired external assets. They are not embedded in release artifacts and must be identified by lock ID, commit/tree/hash evidence, or local verification output.

## Vulnerability triage policy

When a dependency, GitHub Action, native asset, or workflow runner vulnerability is reported:

Policy identifier: vulnerability triage.

1. identify affected package/action/asset, version, exploitability, and supported user rows;
2. classify severity as critical, high, medium, or low;
3. mark critical/high as release blockers until mitigated or explicitly unsupported;
4. create a security issue or private advisory when public details would increase user risk;
5. run the narrow affected tests and the production distribution gate before release.

## Update cadence policy

- Check Python dependencies, optional extras, GitHub Actions majors, and native asset locks before every production release.

Policy identifier: update cadence.
- Review security-only updates at least monthly while v1.0.0 is supported.
- Keep emergency patch scope narrow: dependency/action update, affected test, release evidence, and user-facing advisory.
- Do not silently widen support to remote roots, arbitrary script roots, unsafe Lua libraries, or public REST APIs during a patch.

## Emergency patch

Emergency patches must:

- keep unsafe Lua libraries disabled by default;
- keep arbitrary script root and root escape rejected by default;
- preserve build provenance, SBOM, checksums, and release audit evidence;
- include a rollback note and affected-version statement;
- rerun `v1-security-threat-model`, `production-distribution-gate`, and the affected negative tests.

## Approval

The v1.0.0 threat model is approved only when `v1-security-threat-model` evidence has `passed: true`, all critical/high rows are mitigated or explicitly unsupported, and production distribution no longer reports `security_threat_model_approved` as missing or failed.
