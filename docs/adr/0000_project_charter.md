# ADR-0000: Project Charter を最上位方針にする

Status: Accepted

Date: 2026-07-13

## Context

このリポジトリは、v0.0 までカード効果テキストを DSL に変換し、検証と分析を行う研究 CORE として進んできた。一方で、長期的な目的は DSL 変換そのものではなく、遊戯王 OCG の展開探索、妨害耐性解析、リカバリ解析、デッキ評価を自動化することである。

従来の README は v0.0 安定化の説明が中心であり、将来の game engine / AI search へ向かう判断基準が読み取りにくかった。

## Decision

`docs/00_project_charter.md` を最上位文書として採用する。V0.1 では、この Charter を基準に README、Architecture、Roadmap、V0.1 spec を更新する。

以後の判断順序は次の通りとする。

```text
Project Charter
  ▼
Architecture
  ▼
Specifications
  ▼
ADR
  ▼
Implementation
```

## Consequences

採用する結果:

- プロジェクトは DDD ではなく「ゲームエンジン + AI 探索」として設計する。
- Python は遊戯王のルールを再実装しない。
- ocgcore / EDOPro Lua をルールの真実源とする。
- Replay、Action、Bridge、Evaluation、Search の責務境界を守る。
- 破壊的変更は許容するが、理由を Architecture または ADR に残す。

採用しない選択:

- 現行 DSL 変換ツールとしてだけ最適化し続ける。
- Python 側にルールを増やして短期的に動く engine を作る。
- README だけで長期方針を説明し、設計判断を ADR に残さない。

## Notes

V0.1 は完成したゲームエンジンではない。V0.1 は、今後の実装を Charter に従わせるための設計基盤確立である。
