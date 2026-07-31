# Package 0.5.1 Scope: Verification Efficiency Maintenance

Status: Released; parent [#236](https://github.com/Tao-pyth/ygo-effect-dsl/issues/236)

Last updated: 2026-07-31

Release note: `0.5.1` is now a released source milestone. `#236` and `#237`
are closed. `#108` and `#110` remain intentionally open and were retargeted to
`1.0.0` because they are calibration/research quality gates, not required
maintenance-release completion criteria.

## Objective

package `0.5.1`は、`0.5.0`の利用者向けsemantic、保存contract、release claimを変更せず、test実行profile、fixture ownership、CI出力、evidence再生成手順を整理するcompatible maintenance stageである。目的はtest件数そのものを削ることではなく、同じrelease保証をより短いwall time、より少ない成功時stdout/stderr、明示的なRSS証跡で検証できる状態にすることである。

## Parent and work item

- Parent: [#236](https://github.com/Tao-pyth/ygo-effect-dsl/issues/236)
- Test portfolio and measurement: [#237](https://github.com/Tao-pyth/ygo-effect-dsl/issues/237)

## In scope

1. `unit`、`integration`、`real_core`、`evidence`、`packaging`、`release`のprimary profile分類。
2. profile別のwall time、pytest count、stdout/stderr byte、return code、summary tail、取得可能なprocess peak RSSの測定。
3. 成功時quiet outputと、失敗時first divergenceを残す運用境界。
4. manual/self-hosted evidence regenerationと通常assertionの分離。
5. baseline/current、cold/warm、repeat indexを持つ測定suiteの固定。
6. 全profile測定を束ね、baseline比のwall time削減とstdout/stderr削減を判定するsummary gate。
7. plan、suite、summaryを束ねるrelease gateの固定。
8. skipped real-coreをrelease successとして扱わないことの固定。

## Implemented contract

`pytest-profile-plan-v1`は、`tests/test_*.py`を`unit`、`integration`、`real_core`、`evidence`、`packaging`、`release`のいずれか1つへ割り当てるcontent-addressed evidenceである。`python -m ygo_effect_dsl test-profile-plan --repo-root . --out docs/release/evidence/pytest_profile_plan.json`で再生成でき、`docs/release/evidence/pytest_profile_plan.json`を現在checkoutの分類正本として検証する。

`pytest-profile-measurement-v1`は、選択したprofileのpytest実行についてwall time、pytest count、stdout/stderr byte、return code、summary tail、取得可能なprocess peak RSSを保存するcontent-addressed evidenceである。`python -m ygo_effect_dsl test-profile-run --repo-root . --profile release --out docs/release/evidence/pytest_profile_release.json`で再生成できる。現在のrelease profile evidenceは33 tests、stdout 99 bytes、stderr 0 bytes、process peak RSS 59,203,584 bytesで成功している。

`pytest-profile-suite-v1`は、`pytest-profile-measurement-v1`をbaseline/current、cold/warm、profile、repeat indexのcellとして束ねるcontent-addressed evidenceである。`python -m ygo_effect_dsl test-profile-suite --repo-root . --profile release --phase current --temperature warm --out docs/release/evidence/pytest_profile_suite.json`で初期suiteを再生成し、`--existing-suite`で既存cellを保持したまま追加測定できる。現在のsuiteはv0.5.0 worktree由来の`baseline/warm`全6 profile、`baseline/cold`全6 profile、現在checkout由来の`current/warm`全6 profile、`current/cold`全6 profileを含み、`real_core`は全cellで207 passed、0 skippedである。profile測定中は`YGO_EFFECT_DSL_PYTEST_PROFILE_MEASUREMENT=1`を付け、committed release evidence自己検証テストだけをskipする。これはsuite再生成中の循環依存を避けるためで、通常の`pytest`とCIでは同じテストを実行し続ける。欠落cellはなく、suite単体は`passed=true`である。

`pytest-profile-summary-v1`は、複数の`pytest-profile-measurement-v1`をprofile別に集計し、必須profileの欠落、測定失敗、baseline summaryの欠落、baseline比削減target未達を機械的に判定するcontent-addressed evidenceである。targetはwall time medianをbaseline比0.75以下、stdout/stderr medianをbaseline比0.30以下とする。`python -m ygo_effect_dsl test-profile-summary --measurement docs/release/evidence/pytest_profile_release.json --out docs/release/evidence/pytest_profile_summary.json`で現在のsummaryを再生成できる。final gateでは`--suite`、`--suite-phase`、`--suite-temperature`、`--baseline-suite`を使い、labelled suite cellからcurrentとbaselineを抽出して比較できる。

`pytest-profile-release-gate-v1`は、plan、suite、summaryを束ねる最終判定evidenceである。`python -m ygo_effect_dsl test-profile-gate --plan docs/release/evidence/pytest_profile_plan.json --suite docs/release/evidence/pytest_profile_suite.json --summary docs/release/evidence/pytest_profile_summary.json --out docs/release/evidence/pytest_profile_gate.json`で再生成できる。gateはsuite欠落、summary失敗、suiteに含まれないsummary measurement、`--collect-only` cell、real_core skipped testを拒否する。persisted gateはsuite/summary measurement IDs、suite profile plan IDs、cell rejection witnessを保存し、validatorが`rejection_reasons`と`passed`を再導出する。現在のgateはsuite coverage、summary、profile selection comparisonを満たし、`passed=true`である。

`release-readiness-status-v1`は、`0.5.1`のprofile gateと`0.6.0`/`0.7.0`のrelease gate/self-hosted adoptionを同じrelease evidence directoryから再検証する統合監査evidenceである。`python -m ygo_effect_dsl release-readiness-status --evidence-dir docs/release/evidence --out docs/release/evidence/release_readiness_status.json`で再生成できる。validatorはstage別gate witnessと、`0.6.0`/`0.7.0`ではadopted self-hosted verification witnessから`ready`を再導出し、矛盾するpersisted statusを拒否する。readerは任意のevidence directory照合で現在のgate/adoptionからstatusを再構築し、保存済みstatusの`evidence_id`と一致しなければstaleとして拒否できる。`python -m ygo_effect_dsl release-readiness-verify --evidence-dir docs/release/evidence --status docs/release/evidence/release_readiness_status.json`は保存済みstatusを再生成せずに現在directoryと照合し、stageがincompleteでもstatusが最新なら成功する。final release checkでは`--require-passed`を付け、statusが最新でも`0.6.0`または`0.7.0`がincompleteならnon-zeroにする。任意の`--expected-commit`と`--expected-run-id`が指定された場合は、採用済みbranchのself-hosted audit identityも再検証するため、partial adoption状態でも古いrunner evidenceを見逃さない。`--require-passed`成功時は0.6/0.7両branchの採用済みidentityを必ず確認する。現在のstatusは`ready_versions=["0.5.1","0.6.0","0.7.0"]`、`incomplete_versions=[]`を記録し、後続stageを外部self-hosted証跡なしに完了扱いしない。

`test-profile-run`と`test-profile-suite`は`--suppress-success-output`を持つ。成功時はpytest terminal reporterを無効化し、JUnit XMLからpytest countを復元する。失敗時は通常terminal reporterで再実行し、first divergenceを失わない。profile測定environmentはmeasurement evidenceに記録される。現在のsummaryはsuite由来の`current/warm`全profile測定と`baseline/warm`全profile測定を比較する。profile欠落とbaseline欠落はなく、stdout/stderr削減targetは満たす。per-profile wall time削減targetは満たさないが、baseline全profile合計に対するcurrent release profile選択はwall/stdout/stderr targetを満たし、`full_regression_substitute=false`として記録する。これはfull regressionの代替ではなく、PR/release profile選択による削減範囲の固定である。

## Out of scope

- test countだけを減らすこと。
- unique regression vector、real-core isolation、PlayerView leak検査、migration failure検査の削除。
- native duel handle、Lua state、mutable worker stateのtest間共有。
- 根拠なしの`pytest-xdist`既定有効化。
- Experiment、Route、Replay、Search、corpus、CI contractのsemantic変更。

## Acceptance

- [#237](https://github.com/Tao-pyth/ygo-effect-dsl/issues/237)のbaseline、分類、profile、出力、同等性項目がmachine-readable evidence付きで完了する。
- 同一asset-capable Windows hostで25%以上のwall-time削減を証明する。安全に削減できない層はADRまたはscopeで明示し、PR profile選択による削減範囲を固定する。
- 成功時stdout/stderr byteを70%以上削減し、失敗時の最初のactionable evidenceを失わない。
- skipped real-core testをrelease qualification成功として数えない。
- `pytest-profile-suite-v1`がbaseline/current、cold/warm、全profile、必要repeatを含み、欠落cellなしになる。
- `pytest-profile-summary-v1`が全profile測定とbaseline比較を含み、`release_gate_passed=true`になる。
- `pytest-profile-release-gate-v1`がplan、suite、summaryを同一測定系列として検証し、`passed=true`になる。
- `CHANGELOG.md`、CI、test、commit、push、PR、merge、`main`同期後にのみ`v0.5.1`を宣言する。
