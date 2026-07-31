# v1.0.0 incident, rollback, backup, and disaster-recovery runbook

## Scope

This runbook covers v1.0.0 operational incidents for bad releases, schema migration failure, corpus corruption, worker crash storms, missing upstream external assets, checksum mismatch, and disk exhaustion. It is written for a beginner Python engineer who needs commands, expected results, and stop conditions.

## Severity and targets

| Scenario | Detection | Target RTO | Target RPO |
| --- | --- | --- | --- |
| bad release | failing CI, checksum drift, user report, failed support bundle evidence | 4 hours | previous published package and committed release evidence |
| schema migration failure | `validate-experiment` or migration command exits non-zero | 2 hours | latest pre-migration backup |
| corpus corruption | content digest mismatch, JSON/YAML validation failure, replay drift | 4 hours | last verified corpus export |
| worker crash storm | repeated worker crash diagnostics or timeout retries | 1 hour | no user data loss; failed jobs remain recoverable |
| asset upstream disappearance | `external-asset-setup-status` or verify command reports missing source | 1 business day | pinned local cache or documented unsupported state |
| checksum mismatch | build provenance, SBOM, or package checksum does not match release evidence | 1 hour | last signed or approved package artifact |
| disk exhaustion | write failure, SQLite/Parquet failure, or free-space warning | 1 hour | latest completed job/catalog checkpoint |

RTO is the time to restore a known safe state. RPO is the newest data point that must be recoverable without silent reconstruction.

## Backup targets

Back up only user-owned or operator-owned state before a destructive step:

- release package or portable ZIP currently in use;
- user data root, including `config`, `cache`, `catalog`, `evidence`, and `backups`;
- external asset root if it contains verified pinned ocgcore, CardScripts, or database assets;
- release evidence files under `docs/release/evidence` when diagnosing a release gate regression;
- job catalog SQLite files and Parquet/JSON export directories before repair or deletion.

Do not back up raw crash dumps, private deck contents, hidden payloads, or support bundles into committed evidence. Use `support-bundle` for redacted diagnostic sharing.

## Required safety confirmation

Before destructive operations, write down all of the following in the incident issue:

1. absolute target path;
2. backup path;
3. command to verify the backup exists;
4. command to verify the current package or data root;
5. person approving the destructive step.

Never delete a package, data root, asset root, catalog, or export directory until the backup and target path are both verified. On Windows, prefer a manual Explorer recycle-bin move for user directories unless an approved scripted operation is attached to the incident.

## Detection

Run the narrow check for the suspected incident first:

```powershell
python -m ygo_effect_dsl production-distribution-gate --repo-root . --evidence-dir docs/release/evidence --out docs/release/evidence/production_distribution_release_gate.json --allow-failed
python -m ygo_effect_dsl release-readiness-verify --status docs/release/evidence/release_readiness_status.json --repo-root .
python -m ygo_effect_dsl external-asset-setup-status
python -m ygo_effect_dsl support-bundle --out .support-bundle-local
```

Expected result: the command either exits zero or prints a specific failed check, diagnostic code, missing asset, or redacted bundle path. If the output contains a private value, stop and open a redaction bug before sharing the artifact.

## Triage

Classify the incident using the first failing boundary:

- release or checksum issue: compare GitHub workflow run, commit SHA, package hash, SBOM, and build provenance evidence;
- schema or migration issue: reproduce with a copied input artifact and keep the original read-only;
- corpus corruption: compare the stored digest, schema version, and validation output;
- worker crash storm: count repeated crash categories, retry counts, and timeout boundaries;
- external asset issue: distinguish missing local cache from upstream disappearance;
- disk exhaustion: record free space, largest data directories, and the command that failed.

Do not continue to rollback until the failing boundary is known. A rollback that targets the wrong boundary can hide the real defect and make postmortem evidence weaker.

## Containment

Containment must stop new damage while preserving evidence:

- stop promotion and do not publish or un-yank a release while an incident is open;
- pause large search jobs when disk exhaustion or worker crash storm is suspected;
- switch affected users back to a previous package or clean portable directory;
- set external asset setup to offline/cache-only when upstream assets are disappearing;
- keep failed workflow artifacts, checksums, support bundle redaction reports, and logs long enough for postmortem.

## Rollback

For package rollback, restore the previous wheel or portable ZIP without deleting user data:

```powershell
python -m pip uninstall ygo-effect-dsl
python -m pip install .\dist\previous\ygo_effect_dsl-<version>-py3-none-any.whl
```

For a portable ZIP, extract the previous package to a clean directory and start from that directory. Do not reuse a partially overwritten package directory.

Rollback success criteria:

- `python -m ygo_effect_dsl --version` shows the intended version;
- user data root, external asset root, cache, catalog, and evidence directories still exist;
- `python -m ygo_effect_dsl external-asset-setup-status` reports the expected supported or blocked state;
- the original failing command no longer fails for release/package defects, or is documented as unrelated to package rollback.

## Restore

Restore user data only from a verified backup and only after package rollback is complete:

```powershell
python -m ygo_effect_dsl validate-experiment .\copied-input.yaml
python -m ygo_effect_dsl ocgcore-assets-verify --external-root <external-root>
python -m ygo_effect_dsl ocgcore-verify --external-root <external-root>
```

For catalog or export restore, use a copied working directory first. Keep the corrupted source read-only until postmortem. For schema migration failure, restore the pre-migration backup and rerun migration on a copy before touching the original.

Restore success criteria:

- validation exits zero on a copied representative artifact;
- checksums or content digests match the expected evidence;
- restored data is outside the package directory;
- no raw private payload or absolute personal path is added to committed evidence.

## Verification

After containment, rollback, or restore, run:

```powershell
python -m pytest tests/test_production_distribution_release_gate.py -q
python -m ygo_effect_dsl production-distribution-gate --repo-root . --evidence-dir docs/release/evidence --out docs/release/evidence/production_distribution_release_gate.json --allow-failed
python -m ygo_effect_dsl release-readiness-verify --status docs/release/evidence/release_readiness_status.json --repo-root .
python -m ygo_effect_dsl.release_governance --check
```

Expected result: known unrelated v1 blockers may remain, but the incident-specific check must be either verified or explicitly recorded as blocked with a follow-up issue.

## Postmortem

Open a postmortem issue before closing the incident. Include:

- timeline from detection through verification;
- root cause and first failing boundary;
- exact commands used for detection, rollback, restore, and verification;
- RTO/RPO result against the target table;
- whether backup, target confirmation, tabletop exercise, or restore drill found a gap;
- follow-up issues for missing tests, docs, release evidence, or automation.

## Tabletop exercise

Before v1.0.0 release, complete a tabletop exercise using at least these cases:

- bad release with checksum mismatch;
- schema migration failure requiring pre-migration backup restore;
- worker crash storm requiring containment and redacted support bundle generation;
- disk exhaustion requiring backup and target confirmation before cleanup.

The exercise passes when a beginner Python engineer can identify the command, expected output, rollback or restore action, and stop condition without asking for hidden project knowledge.

## Restore drill

Before v1.0.0 release, complete a restore drill on disposable copies:

1. create a copied data root and copied external asset root;
2. verify both copies;
3. simulate a failed migration or corrupted corpus file in the copy;
4. restore from backup;
5. rerun validation, asset verification, production gate dry-run, and release readiness verification.

The drill passes only when no destructive command targets the original user data root and the restored copy produces the expected validation result.
