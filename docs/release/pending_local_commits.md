# Pending Local Commits Checklist

Status: support note

## Migration Record

- Previous location: `README.md`
- New location: `docs/release/pending_local_commits.md`
- Document type: release and publishing support note
- Related change: V0.1 Project Charter / README reorganization

Use this checklist before publishing pending local commits. When `git status --short --branch` reports `main...origin/main [ahead N]`, GitHub Actions cannot verify those commits until they are pushed.

1. Confirm `git status --short --branch` still reports the expected ahead count and review the pending local commits.
2. Confirm there are no unintended user changes mixed into the publish set.
3. Push the pending local commits or open a PR from the prepared branch only after the intended scope is clear.
4. Wait for GitHub Actions to run the pytest workflow on the published commits.
5. Continue dependent benchmark or golden work only after CI is green.
