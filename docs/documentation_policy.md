# Documentation Policy

This project separates formal contracts from supporting notes so contributors
can tell which documents define behavior and which documents explain context.

## Purpose

`ygo-effect-dsl` is being stabilized as a research CORE for converting
Yu-Gi-Oh! effect text into DSL, validating the result, and analyzing conversion
quality. Documentation therefore has two jobs:

- preserve formal contracts that tests, golden snapshots, and releases depend on
- keep design notes and Japanese explanations easy to read while the project is
  still changing quickly

## docs/ Is The Formal Area

Use `docs/` for material that defines or constrains project behavior.

Examples:

- DSL grammar and schema expectations
- transform, validate, and analyze contracts
- dictionary and ruleset format
- v0.0 and v0.1 semantics
- ADRs that record accepted technical decisions
- release-facing documentation that should be reviewed with code changes

Changes under `docs/` should be treated as reviewable project behavior. If a
change alters DSL shape, diagnostics, golden fixtures, analyzer output, or
release policy, update the relevant spec or changelog in the same work item.

Recommended formal structure:

```text
docs/
  adr/
  contract/
  spec/
    v0.0/
    v0.1/
  release/
  validation/
```

The existing `docs/spec/` tree is the source of truth for versioned DSL behavior.
Future GitHub Pages publishing should prefer `docs/` as the input tree because
it is versioned, reviewable, and tied to releases.

## wiki/ Is The Supporting Area

Use `wiki/` for context that helps people understand the project without
turning every note into a formal contract.

Examples:

- Japanese onboarding notes
- roadmap explanations
- brainstorming summaries
- contributor guides
- design background
- examples written for learning rather than specification

The repository `wiki/` directory is not assumed to sync automatically with
GitHub Wiki. Treat it as versioned supporting material stored in the repo.

Recommended supporting structure:

```text
wiki/
  japanese/
  roadmap/
  design_notes/
  contributor_notes/
  examples/
```

## Migration Rule

Do not delete existing Markdown while reorganizing documentation. Move or link
documents in small batches, and preserve enough redirect/context text that a new
Japanese contributor can follow why the file moved.

When moving a document, record:

- previous location
- new location
- whether the document is formal contract or supporting explanation
- related issue or pull request

## GitHub Pages Direction

GitHub Pages should eventually publish the formal documentation from `docs/`.
The first Pages version should be simple: a static site generated from the
versioned spec and contract files. Publishing `wiki/` can be considered later,
but it should not be required for formal DSL contract review.

## Practical Rule For Contributors

If a document answers "what does the tool promise?", put it in `docs/`.
If it answers "why are we thinking this way?" or "how should I learn this?",
put it in `wiki/`.
