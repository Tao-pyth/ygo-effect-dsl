from __future__ import annotations
from typing import Any
from ygo_effect_dsl.ir.ir_v1 import IRCard, IREffect, IROp, IRBranch, IRBranchCase, IRNode

def compile_card_yaml_to_ir(card: dict[str, Any]) -> IRCard:
    cid = int(card.get("cid", 0) or 0)
    ir_effects: list[IREffect] = []
    for e in (card.get("effects") or []):
        ir_effects.append(_compile_effect(e))
    return IRCard(ir_version=1, cid=cid, effects=ir_effects)

def _compile_effect(eff: dict[str, Any]) -> IREffect:
    trig = eff.get("trigger") or {}
    ops: list[IRNode] = []
    for a in (eff.get("action") or []):
        if not isinstance(a, dict):
            continue
        ops.append(_compile_action(a))

    return IREffect(
        effect_id=str(eff.get("id", "") or ""),
        trigger_kind=str(trig.get("kind", "") or ""),
        restriction=list(eff.get("restriction") or []),
        condition=list(eff.get("condition") or []),
        cost=list(eff.get("cost") or []),
        ops=ops,
    )

def _compile_action(a: dict[str, Any]) -> IRNode:
    kind = str(a.get("kind", "") or "")
    if kind == "branch_from_draw":
        return _compile_branch(a)

    return IROp(
        op=kind,
        args=(a.get("args") if isinstance(a.get("args"), dict) else {}),
        store_as=str(a.get("store_as", "") or ""),
        note=str(a.get("note", "") or ""),
    )

def _compile_branch(a: dict[str, Any]) -> IRBranch:
    args = a.get("args") if isinstance(a.get("args"), dict) else {}
    branches_in = args.get("branches", [])
    cases: list[IRBranchCase] = []

    if isinstance(branches_in, list):
        for b in branches_in:
            if not isinstance(b, dict):
                continue
            when = str(b.get("when", "") or "")
            actions = b.get("actions", [])
            ops: list[IRNode] = []
            if isinstance(actions, list):
                for act in actions:
                    if isinstance(act, dict):
                        ops.append(_compile_action(act))
            cases.append(IRBranchCase(when=when, ops=ops))

    return IRBranch(branches=cases, note=str(a.get("note", "") or ""))
