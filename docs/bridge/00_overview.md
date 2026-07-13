# Bridge Overview

Status: V0.2 specification baseline

Last updated: 2026-07-13

## Purpose

Bridge は Python と ocgcore の境界である。V0.2 では実 ocgcore 接続を行わず、Message と Action-like object の変換責務だけを仕様として固定する。

この文書の目的は、後続の minimal Bridge interface / mock adapter 実装が、遊戯王ルール判断を Python に持ち込まないように境界を明確にすることである。

## Responsibilities

Bridge が担当すること:

- ocgcore 由来または mock 由来の Message dict を Python 側の Action-like dict に変換する。
- Python 側の Action-like dict を ocgcore へ渡せる core input dict に変換する。
- 変換不能な Message、未対応 Message、不正な shape を明確なエラーまたは診断として返す。
- raw message、変換後 action、core input の対応を Replay や logging が追跡できるようにする。

Bridge が担当しないこと:

- 合法手判定
- 状態遷移
- チェーン解決
- カード裁定
- Lua 実行
- Search Engine の分岐選択
- Replay の永続化

## V0.2 Boundary

V0.2 の Bridge は mock / interface baseline である。dynamic library loading、EDOPro Lua 実行、cards.cdb 読み込み、実 duel の進行は扱わない。

V0.2 で固定する変換方向は次の二つだけである。

```text
Message dict
  -> Action-like dict
```

```text
Action-like dict
  -> core input dict
```

この変換は「Python が理解しやすい形に整える」ためのものであり、「その行動が合法か」を判断するためのものではない。

## Relationship To Replay

Replay は Bridge に依存しなくても単体で成立する。一方で、Bridge が生成した Action-like dict は Replay に記録できる形でなければならない。

V0.2 では Bridge smoke test と Replay smoke test を分ける。Bridge mock が Message dict を Action-like dict に変換できることと、Replay が Action 履歴を保存・読込できることは別々に検証する。

## Future Work

以下は V0.2 の詳細化対象だが、この overview では実装しない。

- DecisionRequest への抽象化: #42
- Action granularity / Action ID: #43
- Deterministic replay guarantees: #44
- core version、Lua version、cards.cdb、request signature の照合
