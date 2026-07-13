# Replay Overview

Status: V0.2 specification baseline

Last updated: 2026-07-13

## Purpose

Replay は探索結果を再現、比較、説明するための独立した責務である。V0.2 では Search Engine より先に Replay の最小仕様を固定し、Action 履歴を保存・読込できる状態へ進む。

Replay は探索アルゴリズムを持たない。Replay は「何が起きたか」「どの選択を通ったか」「どの条件で再実行できるか」を保存する。

## Responsibilities

Replay が担当すること:

- seed、deck identifier、version metadata、notes を保存する。
- ActionRecord の順序付き履歴を保存する。
- JSON として deterministic に出力できる形式を定義する。
- 保存した履歴を読み戻し、同一内容として比較できる形にする。
- 将来の妨害注入、Recovery 探索、統計、実験レポートの参照点になる。

Replay が担当しないこと:

- Search Engine の分岐生成
- Evaluation score の計算
- Bridge message の変換
- ocgcore の状態遷移実行
- Lua 実行
- snapshot / clone_duel の実装

## Relationship To Bridge

Replay は Bridge なしでも単体で成立する。V0.2 の Replay smoke test は synthetic ActionRecord だけで成立させる。

Bridge が生成した Action-like dict は、後続で ActionRecord の `payload` または `source` に格納できる。ただし、Replay は Bridge の Message 解釈を行わない。

## Interruption And Recovery

妨害注入は、Replay の履歴中にある ActionRecord の位置を参照して行う。V0.2 では妨害注入そのものを実装しないが、Action 履歴を順序付きで保存することで後続実装の開始点を作る。

Recovery 探索は、妨害後に別ルートを探す処理であり、Replay の責務ではない。Replay は Recovery 探索に渡す再現条件を保持する。

## V0.2 Boundary

V0.2 では以下を扱う。

- human-readable JSON
- ActionRecord の最小フィールド
- ReplayHistory の最小フィールド
- deterministic dump / load の仕様
- invalid replay JSON の明確な扱い

V0.2 では以下を扱わない。

- binary replay format
- real card replay fixture
- ocgcore snapshot
- clone_duel
- Search Engine
- Peak Board
- END_TURN 探索
