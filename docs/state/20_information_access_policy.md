# Information Access Policy

Status: Implemented in Experiment 0.3b

Last updated: 2026-07-14

## Purpose

探索・評価が相手手札、伏せカード、未来のデッキ順を誤って参照すると、再現可能でも現実には選べないActionを高評価する。`information-policy-v1` は参照可能情報を明示し、`information-audit-v1` は評価中のaccessと拒否理由を保存する。

## Orthogonal Dimensions

可視性、デッキ順、初手条件を一つのenumへ混在させない。

- Visibility: `complete_information`, `player_view`, `sampled_private_state`
- Deck order: `known`, `unknown`
- Opening hand: `natural`, `fixed`, `probability_distribution`

`player_view` はviewer本人のprivate identityだけを許可する。`sampled_private_state` はsampling referenceで固定したsample内のprivate identityを許可する。`deck_order: unknown` はcomplete/sample/player viewに関係なく未来の順序参照を拒否する。`probability_distribution` はsampler idとseed等のsampling referenceを必須とする。

## Access Matrix

| Field | Complete | Player view | Sampled | Additional rule |
| --- | --- | --- | --- | --- |
| public state | allow | allow | allow | none |
| hand/set/private Extra identity | allow | viewer owner only | allow sampled value | owner required |
| deck order | allow | viewer owner only | allow sampled value | `deck_order: known` required |
| probability distribution | policy dependent | policy dependent | policy dependent | opening hand distribution required |

## Audit

各accessはsequence、field、owner、purpose、decisionを記録する。拒否理由は `denied_private_owner`, `denied_unknown_deck_order`, `denied_distribution_not_configured` を区別する。Evaluatorはaccess前にauditへ記録し、run完了前に `assert_no_leaks()` を通す。audit reportはpolicy ID、全access、leak一覧、canonical audit IDを持つ。

単に最終board summaryからprivate fieldを削るだけでは不十分である。候補生成、枝刈り、success判定、score計算の途中で禁止情報を読んだ場合もleakとして扱う。

## Experiment Boundary

Experiment `0.3a` はADR-0007でFrozen済みのため変更せず、明示migration先として `0.3b` を追加した。`0.3a` の `information_mode` だけからdeck orderやopening hand policyを暗黙推測しない。migration API/CLIは全policy次元の指定を要求する。

`0.3b` はcanonical policy IDを必須化し、viewerを `player.perspective` から導出する。実行結果ではExperiment、Replay、Replay manifest、information auditが同じpolicy IDを持ち、Route validatorが相互一致を検証する。

## Real-core Prototype Boundary

`sampled_private_state`のIssue #104 fixtureは、seed `20260714`とpolicy ID `handsampol_cd5607267725cd1baa1c2a4ae1c0c8eabdb837fea227b11d8c150dbc8d3248f4`からopening handを決定する。Replay manifestにはselected index `0`、player 1の結果`[14558127, 27204311, 73642296]`、sample ID `handsample_620208ec16527e3c45f61c82a7cbc95c6b7d8027ba04ff67bdc2036b0cee8d6e`を保存する。initial State identityは同じsampling referenceと選択済みprivate stateを識別する。validatorはmanifestの結果とState/auditのpolicy連携を再計算し、不一致を拒否する。

sampled controlはRoute `route_da4cb53e6394eaf1889f69a3e9fc08e8e7c425586bf765ad9015b7ab6f91ab0f`、同じ初手へ対象なし妨害を加えたRouteは`route_bfeddc3740c6172b11ac16d24c1db27aa655998e31de8394733c4f1796813655`である。両者の`interruption_sampling`は`null`であり、opening-hand samplingは妨害samplingから独立する。

一般policyとしての`player_view` access判定は実装済みだが、real-core prototypeはPlayerView Replayを出力しない。PlayerView指定をcomplete informationへ読み替えず、run開始前にfail-closeする。
