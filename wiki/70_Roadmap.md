# Roadmap

正式な計画は [docs/20_roadmap.md](../docs/20_roadmap.md) を参照してください。

## Current

Route DSL 0.1の責務、schema、validator、fixtureを固めます。特にReplay event、checkpoint、Peak Board、Terminal Board、妨害lineageの参照規則を安定させます。

## Next

固定初手・先攻1ターン・妨害なしに限定して、実ocgcoreからRoute DSLを一つ生成し、別プロセスでReplayできる垂直スライスを作ります。

```text
ocgcore Bridge
  -> DecisionRequest / Action
  -> Replay executor
  -> legal stop / evaluation
  -> Route DSL
  -> replay verification
```

その後、Random Search、指定妨害、Recovery、複数初手集計、デッキ比較の順に拡張します。

## Legacy

旧カードテキスト変換は新runtimeの依存にせず、垂直スライス成立後に削除します。旧YAMLをRoute DSLへrenameするmigrationは作りません。
