# ADR-0001: Replay を基準実装にする

Status: Accepted

Date: 2026-07-13

## Context

Project Charter は、探索結果を再現可能にし、Action 単位で探索し、妨害注入やリカバリ解析を後から比較できることを求めている。

探索エンジンを先に実装すると、なぜその結果になったか、どの選択を通ったか、どこで妨害を入れるべきかを後から検証しにくい。これは AI 探索の品質評価にも、デッキ評価にも、実験比較にも不利である。

## Decision

V0.2 以降の実装では Replay を基準実装として扱う。

Replay は seed、deck identifier、Action 履歴、選択履歴、version metadata、notes を保存し、探索・評価・実験を再現するための土台とする。

初期実装では、実 duel clone や ocgcore snapshot よりも、Action 履歴の deterministic な保存と読み戻しを優先する。

## Consequences

採用する結果:

- 探索結果を後から再実行、比較、説明しやすくなる。
- 妨害注入と Recovery 探索の開始点を明確にできる。
- Random Search、Beam Search、MCTS の比較で同じ入力条件を共有できる。
- ログ、統計、実験レポートの根拠を Replay に紐づけられる。

採用しない選択:

- Search Engine を Replay なしで先に実装する。
- Python の内部状態だけで探索過程を保持し、永続化しない。
- 初期段階から clone_duel / Snapshot を必須にする。

## Notes

Replay は探索アルゴリズムを持たない。Replay は再現性の責務に限定する。
