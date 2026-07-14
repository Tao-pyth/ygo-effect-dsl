# Interruption Target Identity

Status: V0.1 implementation contract

Last updated: 2026-07-13

## Purpose

妨害対象をカード名や表示labelで指定すると、同名カードが複数存在する場合、同じ効果を複数回発動する場合、言語変更、Replay途中の位置変更で再解決できない。`interruption-target-v1`は既存のAction/Replay契約から妨害対象署名を派生し、Pythonでカード効果を推測せずReplay上の1実行を特定する。

## Identity fields

target IDは次のcanonical fieldをhash化する。

- semantic `action_id` と実行単位の `action_occurrence_id`
- DecisionRequestの`request_signature`
- 実行前exact `state_hash_before`
- Replay `step`、turn、`turn_action_index`、`chain_index`
- player
- 発動元CardRefのcontroller、owner、location、sequence、public card ID、instance ID
- EffectRefのcard identity、`effect_index`、once-per-turn key

`action_occurrence_id`はAction ID、step、実行前State、turn、turn内Action番号、chain番号から再計算して一致を必須とする。target IDではさらにrequest signatureと発動元/効果を束ねる。同じカードコードでもinstance IDまたは位置が異なるcopyは別targetとなり、同じinstance・同じeffect indexの反復もoccurrence座標により別targetとなる。

カード名、候補label、effect labelは表示専用でありidentityへ含めない。翻訳や表示変更でtarget IDを変えない。

## Replay resolution

`resolve_interruption_target`はReplayの全eventからtargetを再構築し、target IDが完全一致するeventを1件だけ返す。0件はstale/別Replayとして失敗し、複数件はambiguousとして失敗する。壊れたeventを読み飛ばして別eventへ誤解決せず、Replay自体をinvalidとして停止する。

解決結果はtarget ID、Action occurrence ID、Replay step、canonical resolution IDを持つ。Experimentの`interruption.definitions[]`や将来のRoute妨害結果へtarget documentを保存できるが、frozen Experiment 0.3a・Replay 0.3a・Route DSL 0.1の必須fieldは変更しない。

## Execution boundary

target解決は「どの実行機会を妨害するか」だけを決める。妨害カードがその時点で合法か、chainへ追加できるか、結果Stateがどうなるかはocgcoreが決定する。

Effect Veiler固定fixtureでは、base Routeでplayer 1がpassした `select_chain` Action occurrenceをtargetにする。interrupted runはtargetのrequest signature、実行前State、step、turn、turn内Action番号、chain番号を現在のcore requestと照合し、同じ機会でpassをcore提示のEffect Veiler候補へ置換する。通常召喚Actionをtargetにすると実際の分岐前にforkしたことになり、比較時に誤った再合流を生むため採用しない。

scripted/sampled実core適用はIssue #95で実装した。一般カードへの拡張では、同じtarget契約を保ちつつsource card固有の候補・cost・target選択をadapterへ追加する。
