# Package 0.7.0 Scope: Evidence-Driven Research Dashboard

## Current Qualification Gate

`research-dashboard-release-gate-v1` now validates `research-dashboard-qualification-v1` as content-addressed evidence instead of accepting an arbitrary `passed: true` JSON object. The required qualification checks are exactly committed artifact E2E, fresh Replay E2E, desktop screenshot/a11y, security/redaction, and resource-budget evidence; generation normalizes checks into the required order, while persisted evidence with missing, duplicate, unexpected, or reordered checks is rejected. A passing check must also carry check-specific structured witnesses for artifact identity/checksums, fresh worker Replay verification, screenshot/a11y outputs, security/redaction review, and resource-budget measurements, so a placeholder artifact path cannot satisfy the manual gate. Passing evidence also requires a redacted artifact manifest with filename-only labels, SHA-256 fingerprints, sorted unique artifact names, and `path_redacted: true`; path leaks, stray `path`/`*_path` fields, or missing manifests fail before the manual gate can pass. The `research-dashboard-qualification` CLI may receive local paths only in the working input manifest as `evidence_artifacts[].path`; it hashes those files relative to the checks file, fills missing check-specific SHA witnesses, and writes only filename/SHA pairs to the committed qualification evidence. Check-specific SHA witnesses must match the corresponding filename-only artifact entries: committed result/report/Route, fresh Replay report, viewport screenshots, security review, and resource-budget report digests are rejected if they diverge from `evidence_artifacts`. The release gate also requires the exact static Gate A-E check set and the exact manual `real-core-dashboard-qualification` check, rejects persisted evidence whose check pass states, duplicate `gate:check_id` entries, `passed`, and `rejection_reasons` disagree, and records the pinned desktop bridge and analytics query contract versions. The manual qualification witness is also path-redacted: persisted gate evidence stores only `source_path_name` plus `path_redacted: true`, and validation rejects `path`/`*_path` fields except those redaction witnesses, absolute paths, or manual pass states that disagree with the qualification rejection list. Static gate evidence includes payload-field, test/source existence, bridge-method, ADR, and UI-source witness flags; persisted gate validation recomputes each static check's `passed` value from those witnesses. The committed-result static check requires `job.result` to reject renderer path input and read only committed Route/report artifacts; typed scenario static checks require inline deck registration and scenario composition to reject renderer path input and renderer rule inference. The committed `docs/release/evidence/research_dashboard_qualification.json` and `docs/release/evidence/research_dashboard_gate.json` now come from adopted self-hosted qualification evidence and pass with all five required checks.

`research-dashboard-qualification-bundle` is the self-hosted handoff for that manual evidence. It consumes `research-dashboard-qualification-artifact-manifest-v1`, which names the local committed result/report/Route artifacts, fresh Replay report, three viewport screenshots, security review, and resource-budget report plus the measured artifact, Replay, desktop, security, and resource booleans. `research-dashboard-qualification-manifest-template` writes a starter manifest with the required artifact names, ID placeholders, and `null` pass-critical booleans, so operators must replace every measured witness before bundle generation can pass. Those pass-critical booleans are required manifest witnesses, not defaults: missing `renderer_path_input`, checksum/Route verification flags, fresh-worker Replay flags, screenshot/a11y flags, security/redaction flags, censor recording, or budget pass flags abort bundle generation. The bundle also reads the committed result view, SearchRun report, Route DSL artifact, fresh Replay report, viewport screenshots, security review, and resource-budget report before generating qualification evidence; invalid result-view schema, invalid SearchRun result/report schema, non-committed SearchRun artifact status, invalid `fresh-replay-verification-v1`, non-PNG screenshot files, screenshot dimensions that do not match their viewport labels, unreadable JSON review/budget reports, Route ID disagreement between manifest/report/Route/fresh Replay, security review values that contradict the redaction manifest, or resource-budget report values that contradict the manifest abort before the manual gate can be satisfied. The command builds the exact five required checks, optionally writes the generated working checks file, hashes local artifacts through the same redaction path as `research-dashboard-qualification`, and writes content-addressed qualification evidence with filename-only artifact labels.

The same `.github/workflows/release-self-hosted-evidence.yml` workflow can run the 0.7 handoff when supplied a runner-local artifact manifest path. The workflow passes that dispatch input to PowerShell through a step environment variable instead of injecting the raw string into the script body. After finalizing the sanitized summary, it runs `release-self-hosted-evidence-audit` with the current commit, run ID, and selected branch requirements before artifact upload; audit failure rewrites the summary to `failure` and fails the job. It uploads only `research_dashboard_qualification.json`, `research_dashboard_gate.json`, and the sanitized summary; generated checks, screenshots, result views, Routes, SearchRun reports, fresh Replay reports, and runner-local audit output remain runner-local so raw desktop qualification artifacts are not published by default.

Downloaded workflow artifacts are checked with `release-self-hosted-evidence-audit --require-research-dashboard` before replacing committed dashboard release evidence. The audit rejects unexpected raw files or directories, validates the qualification and gate documents, and requires the gate's manual qualification witness to match the qualification evidence ID and pass state. Downloaded audit `artifact_files` names only evidence JSON files, while `source_artifact_files` preserves the full workflow artifact file list including `summary.json`. Operators may also supply `--expected-commit` and `--expected-run-id` so dashboard artifacts from the wrong checkout or workflow run are rejected before adoption.

After audit, `release-self-hosted-evidence-adopt --adopt-research-dashboard` is the supported local adoption path for 0.7 workflow artifacts. It reruns the required passing audit, requires `summary.status: success` and `summary.research_dashboard: true`, copies only `research_dashboard_qualification.json` and `research_dashboard_gate.json` into `docs/release/evidence`, writes the matching selected-branch `release_self_hosted_evidence_audit.json`, and immediately verifies the copied directory against that saved audit. The adoption log prints both the audit evidence ID and the post-copy verification ID, so CI/operator logs can prove that copied dashboard evidence, not only downloaded artifacts, passed validation. That saved audit records the original workflow identity and source artifact list, but `artifact_files` only names copied dashboard evidence, so a combined 0.6/0.7 workflow run can still be adopted one branch at a time without pretending that `summary.json` was copied into release evidence. Saved audit file lists must be sorted, unique, and limited to the allowed release evidence filenames; `source_artifact_files` is mandatory for adopted evidence, must include `summary.json`, and must cover every copied `artifact_files` entry. `summary.json` is valid only in `source_artifact_files`, never in adopted `artifact_files`. The research-dashboard branch witness is schema-fixed to `gate_evidence_id`, `passed`, `qualification_evidence_id`, and `required_check_count` with the expected evidence ID prefixes; a passing branch must have a positive required check count, and any research-dashboard branch witness must agree with `summary.research_dashboard: true`. If another branch from the same workflow identity has already been adopted, the new adoption preserves and merges that existing branch into the saved audit; if the existing branch came from a different workflow identity, the partial merge is rejected before copying files. Failed or pending evidence files for an unadopted branch may remain visible, but unadopted passing branch evidence is rejected before adoption and during adopted-evidence verification. `release-self-hosted-evidence-verify-adopted --require-research-dashboard` can be rerun later; it verifies the adopted directory against that saved audit, including the audit evidence ID, the current qualification/gate witness, the audited copied-file list, the SHA-256 of every verified file, and the requested verification requirements/expected workflow identity, so a later stale or edited dashboard gate is rejected before release judgment. Persisted `release-self-hosted-evidence-verification-v1` JSON is also revalidated by content ID, exact requirement keys, branch witnesses, verified-file list, and optional adopted-file SHA-256 comparison; this prevents a stale copied dashboard gate from being hidden behind a reused verification log.

Desktop result hydration also revalidates candidate and coverage semantics after checking content IDs: `search-candidate-evidence-v1` counts are recomputed from candidate records, coverage counts must match candidate evidence, and a committed artifact cannot claim `frontier_exhausted` unless the status, termination reason, complete candidate accounting, pending frontier count, unknown candidate count, and unexplored/censored/pruned candidate counts all prove exhaustion. Otherwise the result remains fail-closed or conservatively `best_observed`.

The same committed result hydration path revalidates ranking semantics: `route_ranking.best_route_id`, the matching Top-K route summary, and the committed `best_route` must agree on Route ID, score, peak score, success, and the recomputed randomness summary before ranking evidence is exposed.

Terminal preference score hydration is also revalidated from the committed Route terminal board and immutable profile: the recorded `terminal-preference-evaluation-v1` must match recomputation, and `best_route.terminal_score` must equal the recomputed terminal composite score before the score breakdown is exposed.

`release-readiness-status-v1` treats `0.7.0` as ready only when `research_dashboard_gate.json` passes and the adopted self-hosted audit/verification proves the copied research-dashboard branch. The current committed readiness status passes with `0.5.1`, `0.6.0`, and `0.7.0` in `ready_versions`. This keeps static dashboard checks from being mistaken for the required real-core dashboard qualification.

Status: Released; parent [#276](https://github.com/Tao-pyth/ygo-effect-dsl/issues/276)

Last updated: 2026-07-31

Release note: `0.7.0` is now the current package/CLI source release. The
`v0.7.0` milestone is closed, all v0.7.0 work items are closed, and
`release-readiness-status-v1` records `0.7.0` as ready through adopted
research-dashboard qualification evidence.

## Objective

package `0.7.0`は、Windows desktopを固定profileの探索launcherから、実ocgcore探索の入力、評価、結果、再生、比較を監査できる研究dashboardへ昇格するstageである。`0.6.0`のbounded parallel Searchを前提に、実artifactだけを表示し、カード位置別terminal preferenceとRoute gameplay randomnessをversion付き成果物へ組み込み、最良Routeの意味と探索範囲を利用者が検証できることを完了条件とする。

## Current baseline

package `0.5.0`にはdeck catalog、YDK import、card detail、analytics、実preflight、SQLite job、real-core Search worker、Route/SearchRun atomic publicationが存在する。Experiment `0.4`はfixed/random/conditional hand、starting player、turn limit、version付きevaluator/success predicateを表現できる。ただしdesktop search composerは先攻、seeded random 5枚、turn limit 2、board-count系evaluatorを固定し、inline registration buttonと一部inputは未接続である。

最重要の欠落は、real jobが成功してもresult dialogが`route_fixture_5b7a2c10`等の固定synthetic値を開く点である。`job.status`はcommit済みartifact metadataを返すが、rendererは`best-route.yaml`と`search-report.json`を取得・検証・描画していない。fresh Replay CLIは存在するが、desktopから独立verification jobとして起動・確認できない。

## In scope

1. canonical terminal-board projectionとlocation/position/count predicate。
2. immutable、content-addressed terminal preference profileとlocal catalog。
3. base scoreと分離した位置別signed bonus/penalty、matched-instance score breakdown。
4. profileをExperiment、CLI、API、desktop、Route/SearchRun/Replayへ結ぶidentity。
5. ocgcore/EDOPro由来のgameplay randomness taxonomy、event、reliability、unknown evidence。
6. success、terminal preference、reliabilityを使うversion付きstable ranking。
7. verified job-artifact read serviceと、fixed synthetic値を使わないreal result view。
8. Route Action、terminal board、score、termination、best-observed/coverage表示。
9. conditional hand、認定済みevaluator/success preset、inline deck、指定妨害のdesktop input parity。
10. Search workerから独立したfresh Replay verification jobと差分artifact。
11. Top-K、diversity、candidate別node、unexplored/pruned/failed/censored evidence。
12. conditioned/random/fixed cohortを分離するdeck/run statisticsとexport parity。
13. bounded frontier exhaustion、coverage certificate、logical checkpoint/resume、adaptive budget。
14. Neuron URL/デッキコードは[ADR-0019](../../adr/0019_reject_neuron_direct_import_without_official_api.md)に従い、公式third-party APIが確認できるまでdirect importを実装しない。
15. real-core end-to-end、migration、security、redaction、accessibility、responsive、resource qualification。

## Product defaults

- UI presetは先攻の最初の盤面構築とする。starting playerとturn countを直近の一般入力にはしない。
- 終了はlegal `STOP_LINE`、`END_TURN`、成功条件、budget、frontier exhaustion、duel terminalを区別する。
- evaluator、success predicate、rankingは認定済みversion付きpresetを使用し、rendererから任意codeを実行しない。
- 結果はcoverage証明がない限り`best observed`と表示する。
- gameplay randomness不明は`unknown`であり、非randomとして優遇しない。
- node上限なしmodeは提供せず、長時間探索にもhard resource limitを課す。
- 代表カードをcard variant全体の代替にせず、効果を封殺するcost-card modeを利用者へ提供しない。具体カードとocgcoreの合法Actionを正本とする。

## Out of scope

- 後攻盤面入力、相手盤面editor、相手AI、全合法相手手探索。
- 複数turnリレー、対局完走、勝率予測、online duel client。
- native ocgcore duel handle/Lua state snapshot、process間共有、distributed worker。
- Pythonによるカード効果、合法性、timing、random probabilityの推測。
- symbolic/dummy card、代表カードによる探索完了判定、resource-only/full-potentialの利用者向けmode。
- 非公式Neuron scraping、credential収集、third-party asset同梱。
- public distribution、stable compatibility、security/operations support。これらは`1.0.0`に残す。

## Dependency order

```text
0.6.0 deterministic bounded parallel Search
  -> #277-#282 contracts
      -> #283-#293 backend and search evidence
          -> #294-#302 desktop and analytics
              -> #303 research decision + #304-#305 qualification
                  -> #306 source release gate
```

result truthfulnessの[#289](https://github.com/Tao-pyth/ygo-effect-dsl/issues/289)、[#294](https://github.com/Tao-pyth/ygo-effect-dsl/issues/294)はUI受入の最優先である。profile実装はterminal projection、randomness rankingはauthoritative event契約、desktop表示はtyped artifact serviceを先行条件とする。parallel executionの実装詳細を本stageで再定義しない。

## Uncertainties requiring evidence

| Question | Policy | Owner |
|---|---|---|
| どのState fieldでset/face-downを安定投影できるか | core queryとcard instance evidenceで検証し、推測しない | [#277](https://github.com/Tao-pyth/ygo-effect-dsl/issues/277), [#305](https://github.com/Tao-pyth/ygo-effect-dsl/issues/305) |
| random selectionと通常drawをどこまで直接検出できるか | direct trace/message/Action evidenceのあるcategoryだけcompleteとする | [#279](https://github.com/Tao-pyth/ygo-effect-dsl/issues/279), [#286](https://github.com/Tao-pyth/ygo-effect-dsl/issues/286) |
| profile scoreと既存Peak優先順位をどう移行するか | policy versionを分け、legacy goldenを保持する | [#280](https://github.com/Tao-pyth/ygo-effect-dsl/issues/280), [#288](https://github.com/Tao-pyth/ygo-effect-dsl/issues/288) |
| frontier exhaustionをどの範囲で証明できるか | exact frontier/candidate accountingがあるsmall fixtureから昇格する | [#282](https://github.com/Tao-pyth/ygo-effect-dsl/issues/282), [#292](https://github.com/Tao-pyth/ygo-effect-dsl/issues/292) |
| Neuronを公式に取り込めるか | ADR-0019でdirect importを不採用。公式third-party API、認証scope、公開/非公開deck privacy、rate limit、export schemaが揃うまで再評価しない | [#303](https://github.com/Tao-pyth/ygo-effect-dsl/issues/303) |

## Release boundary

`research-dashboard-release-gate-v1`はGate A-Eの静的contract evidenceを機械判定し、persisted evidenceでも同じstatic/manual check setを要求する。`python -m ygo_effect_dsl research-dashboard-qualification --checks docs/release/evidence/research_dashboard_qualification_checks_pending.json --out docs/release/evidence/research_dashboard_qualification.json`と`python -m ygo_effect_dsl research-dashboard-gate --repo-root . --qualification docs/release/evidence/research_dashboard_qualification.json --out docs/release/evidence/research_dashboard_gate.json`で再生成できる。現在の`docs/release/evidence/research_dashboard_gate.json`はcommitted result artifact service、独立Replay verification service、terminal preference、Route randomness/ranking、candidate/coverage drill-down、typed scenario/cohort UI、ADR-0019を検出する。ただしreal-core dashboard qualification evidenceはpending checkのみのため、gateは意図的にfailedである。

`0.7.0`はresearch source milestoneであり、一般利用者向けoptimizer、最適性証明、公開配布を意味しない。parent #276と30 child Issue、[work breakdown](20_work_breakdown_and_acceptance.md)、[ADR-0017](../../adr/0017_v07_research_dashboard_evaluation_and_reliability.md)、[ADR-0018](../../adr/0018_reject_representative_and_cost_card_modes.md)、[ADR-0019](../../adr/0019_reject_neuron_direct_import_without_official_api.md)を正本とし、全childとevidenceが完了するまでpackage versionやtagを先行変更しない。
