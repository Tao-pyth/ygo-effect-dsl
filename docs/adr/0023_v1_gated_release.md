# ADR 0023: v1.0.0 gated GitHub Release

## Status

Accepted for v1.0.0 production distribution qualification.

## Context

v1.0.0 must not publish publicly until #91 and all production distribution gates pass. The release workflow must verify version, changelog, tag, artifact, provenance, and checksum consistency before any public GitHub Release is created.

## Decision

The GitHub Release workflow is manually dispatched and uses the protected environment `v1-production-release`. Repository maintainers must configure that environment with manual approval before a non-dry-run release. The workflow defaults to `dry_run=true` and `1.0.0-dry-run`; dry-run builds release artifacts and uploads evidence but does not publish a public GitHub Release.

Before public publish, the workflow must:

- run `production-distribution-gate` without `--allow-failed`;
- verify the signed tag with `git tag -v`;
- verify the requested version appears in `CHANGELOG.md`;
- verify artifact provenance and checksum evidence exists;
- create only a draft GitHub Release first;
- keep release-checksums and build-provenance evidence with the release artifacts.

Signed tags are the default signing mechanism. If the organization later adopts Sigstore or another GitHub-native signing policy, this ADR must be updated and the workflow must keep equivalent source tag/commit traceability.

GitHub Actions must use current pinned major actions and avoid deprecated runtimes. `actions/checkout@v7`, `actions/setup-python@v6`, and `actions/upload-artifact@v7` are the allowed release workflow actions for this stage.

Failed publish is handled by the yank/rollback runbook in `docs/release/40_failed_publish_yank_rollback.md`. Public publication remains blocked until #91 and the parent production distribution gate are complete.
