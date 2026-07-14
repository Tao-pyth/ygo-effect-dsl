# Glossary

Status: Route DSL baseline

## Action

一つのDecisionRequestに対する応答であり、探索の最小単位。ocgcore由来の候補からBridgeが構築する。Action IDはrequest署名と選択内容から決定的に生成する。

## Bridge

Pythonとocgcoreの境界。core MessageをDecisionRequestへ変換し、Actionをcore inputへ戻す。カードルールや合法性を独自判断しない。

## Checkpoint

Replay event適用後の主要状態を、step、state hash、盤面要約、評価内訳でRoute DSLへ記録したもの。

## DecisionRequest

ocgcoreがプレイヤーへ要求する一回の意思決定を正規化した契約。候補、選択数制約、文脈、安定したrequest署名を持つ。

## END_TURN

ocgcoreへ送るターン終了Action。エンドフェイズ処理などの状態遷移を発生させ得る。探索上の停止宣言 `STOP_LINE` とは異なる。

## Evaluation

状態またはAction pathの価値を測る責務。evaluation vector、total score、説明を返すが、状態遷移を実行しない。

## Experiment

デッキ、初手、先攻・後攻、ターン、禁止制限、妨害、探索予算、成功条件、評価器、versionを束ねる再現可能な検証条件。

## Legacy Card-Text Artifact

v0.0でカード効果テキストから生成していたYAML。過去にはDSLと呼んでいたが、現在のRoute DSLとは別形式であり、探索、Replay、合法手判定の入力にしない。

## Lineage

ルート間の親子関係。親route ID、分岐step、妨害IDなどにより、妨害なしルートとリカバリルートを関連付ける。

## ocgcore

遊戯王OCGの合法手判定、チェーン処理、状態遷移、Lua実行の真実源。

## Peak Board

探索途中で到達した、最も評価の高い合法停止可能盤面。Terminal Boardと区別してRoute DSLへ保存する。

## Replay

同じ環境、初期条件、Action履歴から同じDecisionRequestへ戻るための実行履歴。Route DSLに内包され、ルートの再現性を担保する。

## Route DSL

ocgcore / EDOPro Lua由来の展開ルートを保存、再生、比較、再評価、集計する構造化データ契約。カード効果を記述・実行しない。

## Search

Action候補を分岐させ、探索予算、枝刈り、停止を管理する責務。合法性はocgcore、価値判断はEvaluationへ委譲する。

## State Hash

`ygo-state-id-v1`のcanonical public/private state、constraints、history、pending request、engine state、information mode、completenessから生成する`state_` prefixのSHA-256 ID。`query_api_projection`は欠落項目をIDへ明示するが、exact search-state equivalenceを意味しない。

Replay照合や状態同一性に使う決定的な識別子。完全一致用canonical hashと、枝刈り用の近似search hashを区別する。

## STOP_LINE

現在盤面を候補として採用し、その展開ルートを止める探索上の仮想Action。coreへターン終了入力を送らない。合法停止可能な状態でのみ選べる。

## Success Predicate

実験の成功条件を真偽値で返すversion付き判定器。total scoreとは独立する。

## Terminal Board

予算終了、行動終了、END_TURN、失敗などで実際に探索を終えた盤面。正式な最良結果であるPeak Boardとは一致しない場合がある。
