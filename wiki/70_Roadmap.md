# Roadmap

正式な計画は [docs/20_roadmap.md](../docs/20_roadmap.md) を参照してください。

## Current

General Search MVP candidateまで実装済みです。Experiment `0.4`、YDK/inline preflight、実core frontier、決定論的Random Search、指定妨害taxonomy、10万logical node evidenceをCLI/APIから利用できます。

## Next

次はproduction claimに必要な実worker校正と互換性検証を行います。

```text
General Search MVP
  -> Experiment 0.4 scenario preflight
  -> real-core DecisionRequest / Action frontier
  -> deterministic Random Search
  -> best Route DSL / SearchRun report
  -> fresh worker replay verification
```

pool別の実core Replay throughput/RSS、damage step・mandatory trigger・SEGOC fixture、PlayerView Replay、大規模統計UI、Beam Search / MCTSは後続Issueで扱います。一般公開配布はライセンス・第三者成果物審査完了まで行いません。

## Legacy

旧カードテキスト変換は新runtimeの依存にせず、垂直スライス成立後に削除します。旧YAMLをRoute DSLへrenameするmigrationは作りません。
