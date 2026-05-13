# Issue #13 First Batch Source Review

> Status: docs-only migration note
> Last updated: 2026-05-13

This note records the first low-risk source review batch for moving
`tests/datasets/representative_cards/cards.jsonl` toward real-card-centered
coverage. The current environment does not have `python`, `py`, or `pytest`
available, so this change intentionally does not edit
`tests/datasets/representative_cards/cards.jsonl` or
`tests/golden/representative_cards/expected.json`.

Do not copy large official card text into repo docs. Use the official database
URL as the source pointer, then review the regenerated representative golden
snapshot when Python is available.

Before applying this first batch, follow the
[Local Verification Prerequisites](../../../README.md#local-verification-prerequisites).
If Python 3.10+, editable install, pytest, representative golden regeneration,
or analyze report review cannot run locally, stop before changing
`tests/datasets/representative_cards/cards.jsonl` or
`tests/golden/representative_cards/expected.json`.

| Slot | Candidate | Official DB URL | Slot role | Why it fits | Expected action/target | Golden update check |
| --- | --- | --- | --- | --- | --- | --- |
| 9001 | `Pot of Greed` | https://www.db.yugioh-card.com/yugiohdb/card_search.action?cid=4844&ope=2&request_locale=en | simple draw | Short Normal Spell with no target, cost, trigger, or restriction pressure. | `draw`; target remains implicit/no `targets[]`. | Confirm count remains 2, no extra cost/restriction appears, and analyze action coverage still counts `draw`. |
| 9004 | `Foolish Burial` | https://www.db.yugioh-card.com/yugiohdb/card_search.action?cid=5236&ope=2&request_locale=en | simple send | Narrow Normal Spell that should exercise sending a monster from Deck to GY without target-clause complexity. | `send_to_gy`; target selector should describe 1 monster, with source Deck and destination GY if extracted. | Confirm the source changes from the synthetic slot's loose source to Deck intentionally, target diagnostics remain understandable, and no copied text enters docs. |
| 9013 | `Monster Reborn` | https://www.db.yugioh-card.com/yugiohdb/card_search.action?cid=4842&ope=2&request_locale=en | summon from GY | Recognizable Normal Spell for GY revival; adds declared target wording while preserving the GY summon role. | `special_summon`; target should be 1 monster in either GY. | Confirm `targets[]` is expected to appear or improve, controller/source semantics are reviewed, and target resolution/analyze metrics move intentionally. |

## Migration Notes

- This first batch is a candidate list only. Apply the dataset edit and golden
  regeneration as a separate change when Python tooling is available.
- Keep the replacement batch small: update slots 9001, 9004, and 9013 together
  only if the resulting golden diff remains easy to review.
- Review both the per-card DSL snapshot and analyze summary before closing
  Issue #13. In particular, check action type coverage, target reference
  resolution, unmatched fragments, validation codes, and empty-block ratio.
- Issue #13 should remain open after this docs-only note because the
  representative dataset and golden snapshot still contain the synthetic rows.
