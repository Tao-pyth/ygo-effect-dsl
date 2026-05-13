# ygo-effect-dsl Versioning And Release Policy

This document defines the repository rules for project versions, Git tags,
release artifacts, and release-facing documentation.

## Version Format

`ygo-effect-dsl` uses Semantic Versioning in the form
`vMAJOR.MINOR.PATCH`.

Until the project declares a stable public contract, releases stay in the
`v0.MINOR.PATCH` line:

- increment `MINOR` for visible DSL, CLI, validation, analyzer, fixture, or
  documentation contract changes that contributors should notice
- increment `PATCH` for compatible fixes, documentation clarifications, or
  release workflow corrections
- reserve `v1.0.0` for the first release where the project is ready to treat
  its documented DSL and tool behavior as stable

## Tags And Distribution

A pushed Git tag is the official distribution signal.

Normal branch pushes and pull requests are review and verification events.
They may build and test the project, but they do not publish an official
release. A tag push for `vMAJOR.MINOR.PATCH` means the repository is asking
GitHub Actions to create the release-facing outputs for that exact version.

Tags should point at reviewed commits on the intended release branch. Moving
or reusing a published version tag is not allowed except for an explicitly
documented recovery action.

## GitHub Actions Responsibilities

For normal pushes and pull requests, GitHub Actions should:

- install the project in the supported test environment
- run the test suite and smoke checks
- verify representative golden/analyze behavior without rewriting fixtures
- report failures before code or documentation is merged

For `vMAJOR.MINOR.PATCH` tag pushes, GitHub Actions should additionally:

- run the same verification required for normal pushes
- build release artifacts from the tagged commit
- name artifacts with the project name and tag, for example
  `ygo-effect-dsl-v0.1.0`
- attach or publish only artifacts produced from the tagged commit
- make the tag-driven release the canonical downloadable distribution for
  that version

## Artifact Naming

Release artifacts must include both the project name and the release tag.
Use names that remain clear after download or extraction.

Recommended pattern:

```text
ygo-effect-dsl-vMAJOR.MINOR.PATCH[-kind][.ext]
```

Examples:

- `ygo-effect-dsl-v0.1.0.zip`
- `ygo-effect-dsl-v0.1.0-docs.zip`
- `ygo-effect-dsl-v0.1.0-sdist.tar.gz`

## Changelog Policy

Every release should have a human-readable changelog entry before the tag is
pushed. During the v0 line, the versioned spec changelog may remain the primary
record when the release mainly changes DSL behavior.

Changelog entries should group user-visible changes by intent, such as:

- DSL/spec behavior
- CLI, transform, validate, or analyze behavior
- dictionaries and rulesets
- examples, fixtures, and golden data
- documentation and release process

The changelog should describe what changed and whether contributors need to
adjust datasets, expectations, or downstream tooling.

## Future Version Separation

The repository version currently represents the whole project. Future releases
may separate these version lines when the boundaries are stable enough:

- App version: packaged application, CLI, UI, and release workflow behavior
- DSL Schema version: serialized DSL shape and validation contract
- Ruleset version: dictionary, parser rule, and interpretation rule behavior

Until that split is adopted, a repository release tag covers the app code, DSL
schema, rulesets, examples, and documentation present at the tagged commit.

## README And Documentation Updates

A release or versioning change should update the public-facing documents that
set contributor expectations. Review these targets when preparing a release:

- `README.md` for current version status, quickstart behavior, and release
  links
- `docs/documentation_policy.md` when release documentation ownership changes
- `docs/spec/` files when DSL behavior or compatibility changes
- `docs/spec/*/50_changelog.md` or a future top-level changelog for release
  notes
- GitHub Actions workflow documentation when tag or artifact behavior changes

Do not tag a release whose README, specs, changelog, or workflow notes describe
a different release behavior than the commit actually uses.
