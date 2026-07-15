# Core Terminal Frontier Runtime

Status: Implemented and verified locally for pinned ocgcore API 11.0

Last updated: 2026-07-15

## Purpose

勝敗が確定した実ocgcore batchを、架空のDecisionRequestやActionを作らず、再生可能なterminal SearchFrontierとRouteへ変換する。対象Issueは[#229](https://github.com/Tao-pyth/ygo-effect-dsl/issues/229)である。

## Observed core contract

当初は`OCG_DuelProcess=END`をduel endのauthorityと想定していた。しかしpinned sourceではnative `END`はprocess stackが空のときのstatusであり、実測したLP 0/deck-outでは`AWAITING` batch内に`MSG_WIN`が現れた。さらに`MSG_WIN`後にselection messageが同じbufferへ残る場合がある。このため以下を固定する。

1. terminal authorityはmessage type 5の`MSG_WIN`である。
2. payloadの1 byte目をwinner、2 byte目をreason codeとして解析する。
3. winner 0/1は勝者、2はdrawとする。reason 1は`life_points_zero`、2は`deck_out`、その他は`core_defined`として数値を保持する。
4. `MSG_WIN`検出後は同一batch内のselection messageをAction候補として公開しない。
5. native `END`に`MSG_WIN`がない場合は、winner/reason evidence不足として拒否する。

## Public contracts

`SearchFrontier`は通常frontierとterminal frontierを排他的に表す。

- 通常: `request`あり、`terminal_observation=null`。
- 終端: `request=null`、`terminal_observation`あり、`actions=[]`、`legal_stop=true`、Routeあり。

`core-terminal-observation-v1`は`process_state=ended`、`pending_request=null`、terminal state ID、最終Action ID、`core-terminal-outcome-v1`、`multi-turn-lifecycle-v1`を保持する。terminal outcomeはwinner、reason、message count、全terminal event IDを保存する。同一batchの重複`MSG_WIN`はwinner/reason一致時だけ受理する。

Routeの最終ReplayEventは、勝敗を発生させたAction、core response、`MSG_WIN`を含むcore output、terminal state hashを一つのlineageとして保持する。terminal後にpending requestはないため、`result.final_request_signature`は`null`、`result.request_signatures`は実際に応答したrequestだけを含む。

## Fail-close rules

- Action 0件の初期batchで勝敗に到達した場合は`initial_duel_end_without_action`とし、空Routeを作らない。
- `MSG_WIN` payload不正、winner不正、競合する複数winner/reason、native `END`単独を拒否する。
- mandatory chainまたはforced response中は、`MSG_WIN`がない限りterminal扱いしない。
- terminal snapshotとDecisionRequest、Action、lifecycleの組合せが矛盾する場合はworker protocol failureとする。

## Acceptance evidence

- `terminal_lp_zero_v1`: fixture effectが相手LPを0にし、winner 0/reason 1を実coreから取得する。
- `terminal_deck_out_v1`: 空deckから相手にdrawさせ、winner 0/reason 2を実coreから取得する。
- 両Routeをfresh Replayし、Route ID、最終State、event countを照合する。
- Random Search、Beam Search、MCTSが同じRoute IDと`boundary_reason=duel_end`を報告する。
- focused regression: `68 passed`。

この検証は固定fixtureによるruntime契約のqualificationであり、任意の特殊勝利reasonを意味分類できるという主張ではない。未知reasonは数値を保持した`core_defined`として扱う。
