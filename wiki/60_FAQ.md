# FAQ

## DSLはカード効果を表しますか？

いいえ。現在のDSLは展開ルート情報を表します。カード効果はEDOPro Lua、合法手と状態遷移はocgcoreが担当します。

## なぜLuaをRoute DSLへ変換しないのですか？

Luaはカード固有処理を実行するプログラムであり、Route DSLは実行後の選択履歴と分析結果を保存するデータです。目的と抽象度が異なります。Luaを別言語へ変換して再実行すると、二重実装と裁定差異が生じます。

## ReplayとRoute DSLの違いは何ですか？

Replayは再実行のための初期条件とAction履歴です。Route DSLはReplayにcheckpoint、Peak Board、評価、妨害、lineageを加えた探索成果物です。

## 同じルートを別の基準で評価できますか？

できます。成功条件と評価器のversionを分離し、Replay Action列を変えずに再評価します。評価時に必要な状態がcheckpoint要約だけで不足する場合はReplayで状態を再構築します。

## `validate-route` はルートの合法性を保証しますか？

保証しません。schemaと参照整合性を検査します。合法性と状態遷移はReplay executorがocgcoreで検証します。

## `transform` が出力するYAMLはRoute DSLですか？

違います。v0.0の旧カードテキスト変換物です。互換確認用に残っていますが、探索runtimeへ接続しません。

## Route DSLは手書きしますか？

通常はSearch / Replay / Evaluationから自動生成します。手書きfixtureはcontract testと説明用に限定します。

## 実ocgcoreでルート探索できますか？

まだできません。現在はDecisionRequest、Action、Replay、Route DSLの最小契約まで実装済みで、実BridgeとReplay executorが次のマイルストーンです。
