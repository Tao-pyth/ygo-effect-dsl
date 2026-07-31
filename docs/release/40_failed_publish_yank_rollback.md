# Failed publish yank and rollback runbook

## Scope

This runbook applies only after a v1.0.0 GitHub Release publish attempt fails or a draft release is found to contain incorrect artifacts, provenance, checksums, or notes. It does not authorize public publish before #91 and all v1.0.0 production distribution gates pass.

## Preconditions

- Identify the release tag, GitHub Release URL, workflow run, commit SHA, artifact checksums, and build provenance manifest.
- Stop promotion. Do not convert a draft release to public while investigation is open.
- Preserve the failed workflow artifacts, `release-checksums.json`, `windows-checksums.json`, and build provenance evidence.

## Draft release rollback

1. Mark the draft release as failed in the release issue or incident ticket.
2. Delete or replace draft-only assets after saving their checksums and provenance evidence.
3. Re-run the gated release workflow with `dry_run=true` and a separate dry-run version.
4. Compare the new dry-run checksums and provenance against the intended source tag.

## Public release yank

1. If a public release was accidentally published, immediately edit the release notes to state that the release is yanked.
2. Remove downloadable assets from the public release, or replace them with a clear yanked marker if deletion is disallowed by repository policy.
3. Do not delete the signed tag until maintainers decide whether downstream users need the immutable tag for audit.
4. Open a follow-up incident issue with the exact failed artifact hashes and workflow run URLs.
5. Publish a corrected release only from a new approved workflow run and a new signed tag or organization-approved signing equivalent.

## Rollback

Users should return to the previous released package or ZIP. Package rollback must not delete user cache/config/evidence. Any migration that cannot be rolled back requires pre-migration backup and explicit confirmation before it is enabled.
