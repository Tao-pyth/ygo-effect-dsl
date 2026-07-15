# Package 0.5.1 Scope: Verification Efficiency Maintenance

Status: Planned; parent [#236](https://github.com/Tao-pyth/ygo-effect-dsl/issues/236)

Last updated: 2026-07-15

## Objective

package `0.5.1`は`0.5.0`の利用者向けsemantic、保存contract、release claimを変更せず、test実行profile、fixture ownership、CI出力、evidence再生成境界を整理するcompatible maintenance stageである。2026-07-15時点の`716 tests collected`を基準とし、test件数を目的指標にせず、同一workloadのwall time、RSS、stdout/stderr byte、失敗検出能力を比較する。

## Parent and work item

- Parent: [#236](https://github.com/Tao-pyth/ygo-effect-dsl/issues/236)
- Test portfolio and measurement: [#237](https://github.com/Tao-pyth/ygo-effect-dsl/issues/237)

## In scope

1. `unit`、`integration`、`real_core`、`evidence`、`packaging`、`release`のprimary profile分類。
2. cold/warm実行時間、test count、skip reason、p50/p95 duration、RSS、出力byteのbaseline。
3. immutable fixture構築、subprocess bootstrap、checked evidence読取の重複調査。
4. normal assertionとmanual/self-hosted evidence regenerationの分離。
5. source moduleからowner test profileへのfail-open対応表。
6. 成功時quiet summaryと、失敗時first divergence・traceback・artifact pathの保持。
7. fixed failure-injection corpusによる旧full commandと新release profileの同等性検証。

## Out of scope

- test countだけを減らすこと。
- unique regression vector、real-core isolation、PlayerView leak検査、migration failure検査の削除。
- native duel handle、Lua state、mutable worker stateのtest間共有。
- 根拠なしの`pytest-xdist`有効化。
- Experiment、Route、Replay、Search、corpus、UI contractのsemantic変更。

## Acceptance

- [#237](https://github.com/Tao-pyth/ygo-effect-dsl/issues/237)のbaseline、分類、profile、出力、同等性項目がmachine-readable evidence付きで完了する。
- 同一asset-capable Windows hostで25%以上のwall-time削減を証明する。または安全に削減できない層をADRで明示し、PR profile選択による削減範囲を固定する。
- 成功時stdout/stderr byteを70%以上削減し、失敗時の最初のactionable evidenceを失わない。
- skipped real-core testをrelease qualification成功として数えない。
- `CHANGELOG.md`、CI、test、commit、push、PR、merge、`main`同期後にのみ`v0.5.1`を宣言する。
