# Anonymous Validation Format

This document defines how to report local YAML validation results without
publishing protected card data in GitHub Issues.

## Goals

- Validate real local YAML files.
- Publish only anonymized validation summaries.
- Store detailed diagnostics in local logs.
- Aggregate by validation rule instead of by card.
- Avoid exposing card names, effect text, raw YAML fragments, original file names,
  and source enum values.

## Issue-Safe Fields

The GitHub Issue may include only these fields:

| Field | Example | Notes |
| --- | --- | --- |
| `validation_run_id` | `validation-run-2026-05-13-001` | Stable local trace ID. |
| `source_alias` | `fixture-a.yaml` | Alias only. Do not use the original file name. |
| `scope` | `local-yaml` | Broad validation scope. |
| `severity` | `error` | One of `error`, `warning`, or `info`. |
| `rule` | `type` | Validation code or rule name. |
| `count` | `12` | Number of matching diagnostics. |
| `yaml_paths` | `effects[*].actions[*].target_id` | Generalized paths only. |
| `expected_shape` | `string` | Shape, type, or missing state only. |
| `actual_shape` | `object` | Shape, type, or missing state only. No source value. |

## Issue-Prohibited Fields

Do not put these in GitHub Issues:

- Card names.
- Effect text.
- Raw YAML snippets.
- Original dataset file names.
- Original enum/string values read from source YAML.
- Line numbers or column numbers.
- Per-card summaries.

## Source Aliasing

Use deterministic aliases for local files:

| Original local input | Issue alias |
| --- | --- |
| First validated YAML file | `fixture-a.yaml` |
| Second validated YAML file | `fixture-b.yaml` |
| Directory or batch input | `fixture-set-001` |

Keep the alias mapping in the local detailed log only.

## YAML Path Generalization

Published paths should identify the failing shape without identifying the card.

| Local diagnostic path | Issue-safe path |
| --- | --- |
| `effects[0].actions[2].type` | `effects[*].actions[*].type` |
| `effects[1].targets[0].selector.kind` | `effects[*].targets[*].selector.kind` |
| `card.name.ja` | `card.name.ja` |

Use a precise index only when the index is intrinsic to the schema and does not
identify source content. The default is to replace indexes with `[*]`.

## Rule-Level Summary Shape

Use this JSON shape for machine-readable summaries that are safe to copy into an
Issue:

```json
{
  "validation_run_id": "validation-run-2026-05-13-001",
  "source_alias": "fixture-a.yaml",
  "scope": "local-yaml",
  "totals": {
    "error": 0,
    "warning": 0,
    "info": 0
  },
  "rule_summary": [
    {
      "severity": "error",
      "rule": "type",
      "count": 3,
      "yaml_paths": [
        "effects[*].actions[*].target_id"
      ],
      "expected_shape": "string",
      "actual_shape": "non-string"
    }
  ],
  "local_trace": "validation-run-2026-05-13-001"
}
```

## Local Detailed Log Shape

Detailed logs stay local and may include enough information for the issue
creator to reproduce the validation run. Do not attach this log to a public
Issue.

```json
{
  "validation_run_id": "validation-run-2026-05-13-001",
  "created_at": "2026-05-13T00:00:00+09:00",
  "source_alias_map": [
    {
      "source_alias": "fixture-a.yaml",
      "local_path": "C:/local/private/path/original.yaml"
    }
  ],
  "diagnostics": [
    {
      "source_alias": "fixture-a.yaml",
      "yaml_path": "effects[0].actions[2].target_id",
      "generalized_yaml_path": "effects[*].actions[*].target_id",
      "severity": "error",
      "rule": "type",
      "expected_shape": "string",
      "actual_shape": "non-string"
    }
  ],
  "issue_summary": {
    "totals": {
      "error": 1,
      "warning": 0,
      "info": 0
    },
    "rule_summary": [
      {
        "severity": "error",
        "rule": "type",
        "count": 1,
        "yaml_paths": [
          "effects[*].actions[*].target_id"
        ],
        "expected_shape": "string",
        "actual_shape": "non-string"
      }
    ]
  }
}
```

## Issue Body Template

```md
## Summary

- Validation run: `validation-run-2026-05-13-001`
- Source alias: `fixture-a.yaml`
- Scope: Local YAML validation
- Result: `error: 1 / warning: 0 / info: 0`

## Rule Summary

| Severity | Rule | Count | Example YAML paths |
| --- | --- | ---: | --- |
| `error` | `type` | 1 | `effects[*].actions[*].target_id` |

## Notes For Triage

- Findings are grouped by validation rule.
- Detailed diagnostics are stored in the local validation log.

## Local Trace

作業者ログ：`validation-run-2026-05-13-001`
```
