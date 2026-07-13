# Representative Benchmark Policy

Status: V0.0 support document / retained for V0.1 input quality

## Migration Record

- Previous location: `README.md`
- New location: `docs/spec/v0.0/60_representative_benchmark.md`
- Document type: formal support document for benchmark and golden workflow
- Related change: V0.1 Project Charter / README reorganization

## Purpose

`tests/datasets/representative_cards/cards.jsonl` is the small benchmark used to keep transform behavior measurable while the parser is still changing. V0.1 keeps this benchmark because future engine/search work depends on stable Action and Target extraction.

Treat each row as a semantic slot first and as a card name second. A replacement is useful only when it keeps the same action, target, cost, or restriction pressure visible in the golden snapshot.

## Local Verification Prerequisites

Before changing `tests/datasets/representative_cards/cards.jsonl` or `tests/golden/representative_cards/expected.json`, confirm the local verification loop is available.

Required order:

1. Install Python 3.10 or newer.
2. Install the package in editable mode:

   ```bash
   pip install -e .
   ```

3. Run the full test suite:

   ```bash
   python -m pytest
   ```

4. For an intentional representative benchmark update, first run the representative golden test without updating the snapshot and review the failing diff:

   ```bash
   python -m pytest tests/test_representative_golden.py
   ```

5. Regenerate the representative golden snapshot only after the per-card DSL diff is intentional:

   ```powershell
   $env:YGO_UPDATE_GOLDEN="1"
   python -m pytest tests/test_representative_golden.py
   Remove-Item Env:\YGO_UPDATE_GOLDEN
   ```

6. Re-run the representative golden test and analyze checks, then inspect both `tests/golden/representative_cards/expected.json` and the analyze report impact before committing.

Stop condition: if `python`, `py`, or `pytest` is not available locally, do not change representative dataset or golden files. Keep work to README/docs/changelog notes, source-review planning, or other docs-only changes until the verification loop can run.

## Current Slot Coverage

| CID | Slot | Action coverage | Target coverage | Cost coverage | Restriction coverage |
| --- | --- | --- | --- | --- | --- |
| 9001 | simple draw | `draw` | none | none | none |
| 9002 | summon-triggered search | `add_to_hand` from Deck to hand | none | none | Normal Summon trigger, no restriction |
| 9003 | simple destroy | `destroy` | inline description, no declared target | none | none |
| 9004 | simple send | `send_to_gy` | inline monster description | none | none |
| 9005 | self summon | `special_summon` self | none | none | none |
| 9006 | summon from Deck | `special_summon` from Deck | inline LIGHT Spellcaster Tuner description | none | none |
| 9007 | banish from GY | `banish` | inline GY description | none | none |
| 9008 | targeted return to Extra Deck | `return_to_extra` | `targets[]` monster you control | none | target clause only |
| 9009 | targeted destroy | `destroy` | `targets[]` card your opponent controls | none | target clause only |
| 9010 | discard cost into draw | `draw` | none | `discard` 1 card | none |
| 9011 | once-per-turn classifier | `draw` | none | none | OPT text is detected as a restriction candidate; emitted global restriction is still empty |
| 9012 | generic monster search | `add_to_hand` from Deck to hand | inline monster description | none | none |
| 9013 | summon from GY | `special_summon` from GY | inline monster description | none | none |
| 9014 | summon from hand | `special_summon` from hand | inline monster description | none | none |
| 9015 | discard action | `discard` | inline monster description | none | none |
| 9016 | targeted shuffle to Deck | `return_to_deck` shuffle mode | `targets[]` card in either GY | none | target clause only |
| 9017 | negate | `negate` effect | implicit "that effect" | none | none |
| 9018 | targeted banish | `banish` | `targets[]` monster in your GY | none | target clause only |
| 9019 | multi-action sequence | `draw`, `send_to_gy` | inline monster description | none | none |
| 9020 | unmatched fragment sentinel | no action yet | hand phrase remains unmatched | none | none |

## Replacement Priorities

1. Replace slots whose real card text is short, famous, and mechanically narrow: draw, generic search, GY summon, destroy Spell/Trap, and send to GY.
2. Replace target-heavy slots after checking that the real text keeps the same `targets[]` shape.
3. Replace cost and restriction slots only when the golden diff is intentionally reviewed.
4. Keep one unmatched or partially unmatched real card slot for V0.0/V0.1 visibility.

Obvious real-card candidates to verify against local source data before editing the dataset:

- 9001 simple draw: `Pot of Greed`.
- 9012 generic monster search: `Reinforcement of the Army`.
- 9013 summon from GY: `Monster Reborn`.
- 9004 simple send: `Foolish Burial`.
- 9003 simple destroy: `Mystical Space Typhoon` or another short destroy card, depending on whether the slot should stay "card on the field" or narrow to Spell/Trap.
- 9017 negate: a short "negate that effect" response card, after confirming the surrounding trigger/cost text does not change the slot's role.

## Migration Checklist

- Keep each pull request to one small batch, preferably 2-4 low-risk slots.
- Start with simple action-only slots before target-heavy, cost, restriction, or unmatched-fragment slots.
- Use only short card names and source identifiers in docs or review notes; do not bulk-copy official effect text into repository documentation.
- Before changing `cards.jsonl`, record the expected slot role and the reason the real card should preserve or intentionally improve that role.
- After regenerating golden output, check both the representative golden diff and the analyze dashboard impact before treating the batch as complete.

Suggested first batches:

| Priority | Slots | Candidate names | Why this batch is safe |
| --- | --- | --- | --- |
| 1 | 9001, 9004, 9013 | `Pot of Greed`, `Foolish Burial`, `Monster Reborn` | Short, recognizable action-only cards that directly exercise draw, send-to-GY, and GY summon coverage. |
| 2 | 9003, 9012 | `Mystical Space Typhoon`, `Reinforcement of the Army` | Still narrow, but should be reviewed for target/type narrowing in the emitted DSL. |
| 3 | 9008, 9009, 9016, 9018 | Real cards with matching target clauses | Target slots should move after action-only replacements because they can change `targets[]` shape and target resolution metrics. |
| 4 | 9010, 9011, 9017, 9020 | Real cards selected for cost, OPT, negate, and unmatched canary behavior | These are closure-critical but riskier because they touch known rough edges in costs, restrictions, negation, and unmatched fragments. |

## Golden Update Workflow

When replacing a row, keep `tests/golden/representative_cards/expected.json` as a full snapshot and update it only as a deliberate second step:

1. Change one or a small batch of rows in `tests/datasets/representative_cards/cards.jsonl`.
2. Run `python -m pytest tests/test_representative_golden.py` once to see the failing diff.
3. Confirm the diff preserves or intentionally improves the slot's action, target, cost, restriction, diagnostics, and `meta.action_candidate_trace`.
4. Regenerate with `YGO_UPDATE_GOLDEN=1` only after that review.
5. Re-run the representative golden test and analyze checks, then inspect `tests/golden/representative_cards/expected.json` before committing.

Treat changes to empty-block ratio, target reference resolution, unmatched fragments, validation codes, or action type coverage as review items, not as mechanical golden churn.
