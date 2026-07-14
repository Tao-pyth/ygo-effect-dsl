# Concepts

## Route DSL

Route DSLは展開ルートの保存・交換形式です。一つの文書に実験条件、Replay、途中盤面、Peak Board、Terminal Board、評価、妨害、親子ルート関係を保持します。

```text
Lua card behavior
  -> ocgcore execution
  -> DecisionRequest / Action
  -> Replay
  -> Evaluation
  -> Route DSL
```

## Lua and ocgcore

EDOPro Luaにはカードごとの処理が既に実装されています。ocgcoreはLuaを実行し、合法な候補と状態遷移を決めます。PythonはカードテキストやRoute DSLを読んで効果を再実装しません。

## DecisionRequest and Action

DecisionRequestは「どのカードを選ぶか」「効果を使うか」など、一回の意思決定要求です。Actionはその要求への応答です。効果発動、コスト選択、対象選択が別々のcore requestなら、別々のActionとして記録します。

## Replay

Replayは初期条件とAction履歴をocgcoreへ再適用し、同じDecisionRequestへ戻れることを検証します。Route DSLはReplayを内包し、ルートの説明・評価情報を追加します。

## Checkpoint

途中盤面の観測点です。Replay step、state hash、盤面要約、評価内訳を持ちます。すべての内部状態を人間向けに複製するものではありません。

## Peak Board and Terminal Board

Peak Boardは途中で到達した最良の合法停止可能盤面です。Terminal Boardは探索を実際に終了した盤面です。過剰展開で盤面が弱くなる場合があるため、両者を区別します。

## Interruption and Lineage

妨害後のリカバリルートは、元ルートのReplay prefixから分岐します。Route DSLは親route IDと分岐stepをlineageとして保存し、妨害前後を比較可能にします。

## Legacy Card-Text Artifact

v0.0で生成していたカード単位YAMLです。過去にはDSLと呼んでいましたが、現在のRoute DSLとは別物です。探索用Actionやルール判定には使用しません。
