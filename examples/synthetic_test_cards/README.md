# Synthetic Test Cards

This dataset contains 10 fictional cards for parser and pipeline verification.
It is intended to be safe for GitHub distribution: the card names, identifiers,
and effect text are original fixture data and are not copied from official card
database records.

This is a distributable smoke fixture for ingest/transform/validate checks. It
does not replace the representative-card benchmark, which should continue moving
toward real-card-centered coverage.

The rows cover the first practical v0.0 action patterns:

| CID | Synthetic card | Verification focus |
| --- | --- | --- |
| 10001 | Aether Ledger | draw count |
| 10002 | Grove Courier | Normal Summon trigger and Deck-to-hand search |
| 10003 | Switchyard Spark | destroy action |
| 10004 | Archive Dropper | send-to-GY action |
| 10005 | Wake Circuit | self Special Summon |
| 10006 | Prism Dispatcher | Special Summon from Deck with descriptive constraints |
| 10007 | Gate Scribe | banish from GY |
| 10008 | Compass Returner | target clause plus return to Extra Deck |
| 10009 | Mirror Breaker | target clause plus destroy action |
| 10010 | Toll Archivist | discard cost followed by draw action |

Run it with:

```bash
python -m ygo_effect_dsl ingest --dataset examples/synthetic_test_cards
python -m ygo_effect_dsl transform --dataset examples/synthetic_test_cards --out data/synthetic_dsl
python -m ygo_effect_dsl validate data/synthetic_dsl/yaml
python -m ygo_effect_dsl analyze data/synthetic_dsl/yaml --out data/synthetic_reports
```
