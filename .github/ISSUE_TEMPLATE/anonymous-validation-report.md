---
name: Anonymous validation report
about: Report validation results from local YAML without publishing protected source data
title: "[validation] "
labels: validation
assignees: ""
---

## Summary

- Validation run: `validation-run-YYYY-MM-DD-001`
- Source alias: `fixture-a.yaml`
- Scope: Local YAML validation
- Result: `error: 0 / warning: 0 / info: 0`

## Rule Summary

| Severity | Rule | Count | Example YAML paths |
| --- | --- | ---: | --- |
| `error` | `required` | 0 | `effects[*].actions` |
| `error` | `type` | 0 | `effects[*].actions[*].target_id` |
| `warning` | `unknown_action` | 0 | `effects[*].actions[*].type` |
| `warning` | `unresolved_target` | 0 | `effects[*].targets[*].selector.kind` |
| `warning` | `missing_selector` | 0 | `effects[*].actions[*]` |
| `warning` | `legacy_action_fallback` | 0 | `effects[*].action` |

## Notes For Triage

- Group findings by validation rule, not by card.
- Do not include card names, effect text, raw YAML fragments, enum values from the source, or file names from the original dataset.
- Use source aliases such as `fixture-a.yaml`, `fixture-b.yaml`, or `fixture-set-001`.
- Use generalized YAML paths. Replace record indexes with `[*]` unless a precise anonymous path is needed for implementation.
- Keep detailed local logs outside the Issue.

## Local Trace

作業者ログ：`validation-run-YYYY-MM-DD-001`
