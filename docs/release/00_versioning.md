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

The current package and CLI version is `0.5.0`, published from the reviewed
`v0.5.0` source tag. The implemented 0.4.0 stage was not tagged separately;
its cumulative changes are included in 0.5.0. The single source of truth is
`ygo_effect_dsl.version.__version__`; setuptools reads that value as dynamic
project metadata and the CLI exposes it through `--version`.

The active compatible maintenance target is `0.5.1`. The planned `0.6.0`
minor release adds deterministic node-level parallel search and requires
measured latency reduction without changing old Experiment semantics. The
planned `0.7.0` release adds an evidence-driven research dashboard with
truthful real artifacts, immutable location-aware terminal preferences,
Route gameplay-randomness provenance, and independent fresh Replay. The
`1.0.0` target remains the separate stable compatibility, licensing,
distribution, security, and operations gate.

## Tags And Distribution

A pushed Git tag is the official source milestone signal for the package
version. It does not by itself claim production support or authorize
redistribution of third-party binaries, card databases, or scripts.

Normal branch pushes and pull requests are review and verification events.
They may build and test the project, but they do not publish a source
milestone. A tag push for `vMAJOR.MINOR.PATCH` asks GitHub Actions to test and
build the exact tagged source. General distribution remains fail-closed until
the license and production gates in issues `#91` and `#127` are complete.

Tags should point at reviewed commits on the intended release branch. Moving
or reusing a published version tag is not allowed except for an explicitly
documented recovery action.

## GitHub Actions Responsibilities

For normal pushes and pull requests, GitHub Actions should:

- install the project in the supported test environment
- run the test suite and smoke checks
- verify representative golden/analyze behavior without rewriting fixtures
- report failures before code or documentation is merged

For `vMAJOR.MINOR.PATCH` tag pushes, the current GitHub Actions workflows:

- run the same verification required for normal pushes
- build the Windows executable smoke artifact from the tagged commit
- do not bundle ocgcore, CardScripts, BabelCDB, or other third-party assets

Wheel, sdist, checksums, provenance, long-term artifact retention, and a
GitHub Release publication workflow are production work tracked by `#127`.
Until that gate is complete, a tag is reproducible source identification, not
a supported general-public binary distribution.

## Artifact Naming

Release artifacts must include both the project name and the release tag.
Use names that remain clear after download or extraction.

Recommended pattern:

```text
ygo-effect-dsl-vMAJOR.MINOR.PATCH[-kind][.ext]
```

Examples:

- `ygo-effect-dsl-v0.2.0.zip`
- `ygo-effect-dsl-v0.2.0-docs.zip`
- `ygo-effect-dsl-v0.2.0-sdist.tar.gz`

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

The mandatory entry categories, target-version notation, exemptions, release
cut procedure, and pull-request checks are defined in
[`10_changelog_and_issue_governance.md`](10_changelog_and_issue_governance.md).

## GitHub Issue And Milestone Policy

Every managed work item has exactly one `version:X.Y.Z` label and the matching
`vX.Y.Z` milestone. Parent and child issues normally share the same target;
cross-release work is split into independently accepted child issues. The
machine-readable mapping is `.github/release-governance.yml`, and drift is
checked with `python -m ygo_effect_dsl.release_governance --check`.

Historical issues before the configured management baseline retain their
original labels and milestones. A released milestone is closed and is not
reopened for later fixes; compatible follow-up work targets a patch milestone.

## Release And Contract Version Separation

Package and functional contract version lines are intentionally independent:

- Package version uses SemVer for the Python package, CLI, documentation, and
  repository-wide release scope.
- Contract versions identify the compatibility of serialized artifacts and
  APIs such as Experiment, Route DSL, Replay, SearchRun, and aggregation.
- Runtime lock IDs identify exact ocgcore, CardScripts, and card database
  inputs; they are not package versions.

A package release can include multiple contract versions for compatibility.
For example, package `0.3.0` writes Experiment `0.4`, executes `0.3b`, reads
legacy `0.3a`, and writes Route DSL `0.1`. A package version bump does not
automatically bump these contracts. A contract version changes only when its
shape or semantics cross the documented compatibility boundary.

The current matrix is maintained in `README.md` and `docs/20_roadmap.md`.

## README And Documentation Updates

A release or versioning change should update the public-facing documents that
set contributor expectations. Review these targets when preparing a release:

- `README.md` for current version status, quickstart behavior, and release
  links
- `docs/20_roadmap.md` for the current contract matrix and release-based
  implementation plan
- `CHANGELOG.md` for user-visible changes in the package release
- `docs/40_documentation_policy.md` when release documentation ownership changes
- `docs/spec/` files when DSL behavior or compatibility changes
- `docs/spec/*/50_changelog.md` or a future top-level changelog for release
  notes
- GitHub Actions workflow documentation when tag or artifact behavior changes

Do not tag a release whose README, specs, changelog, or workflow notes describe
a different release behavior than the commit actually uses.
