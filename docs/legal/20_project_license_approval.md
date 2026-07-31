# Project License Approval Status

Status: Approval required; tracked by [#169](https://github.com/Tao-pyth/ygo-effect-dsl/issues/169) and [#91](https://github.com/Tao-pyth/ygo-effect-dsl/issues/91)

Last updated: 2026-07-31

## Current Decision

The project root license is `NOASSERTION`. There is no root `LICENSE` file, and `pyproject.toml` intentionally has no `license`, `license-files`, or license classifier. This means the repository does not currently publish an express reuse grant and does not authorize a public wheel, sdist, executable, or installer distribution.

The machine-readable approval status is [`docs/release/evidence/project_license_approval_status.json`](../release/evidence/project_license_approval_status.json). The active distribution policy remains [`prototype-local-only-v1`](10_distribution_policy.md), which blocks release bundling until a new policy version is reviewed and tested.

## Required Approval Record

Before #169 can close, the repository must record all of the following:

- owner-approved root project license identifier and full license text in `LICENSE`;
- matching `pyproject.toml` license metadata, license files, and classifiers;
- NOTICE obligations for repository source, documentation, examples, and generated artifacts;
- compatibility review for ocgcore and CardScripts AGPL obligations if they are ever bundled;
- explicit BabelCDB redistribution license or written permission before any CDB/card text/card image distribution;
- exact release composition, artifact allowlist, SBOM, third-party notices, and release-audit evidence;
- legal review link or approval record for the intended public or commercial distribution shape.

## Gate Rule

Until the approval record is complete, release tooling must keep `project.release_status` as `blocked`, reject even an empty public distribution bundle, and reject every third-party payload outside an explicit future allowlist. Adding a root `LICENSE` without updating package metadata, NOTICE, distribution policy, and tests is not sufficient.
