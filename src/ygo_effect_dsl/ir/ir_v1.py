from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Literal

IRNodeType = Literal["op", "branch"]

@dataclass(frozen=True)
class IROp:
    type: Literal["op"] = "op"
    op: str = ""                 # action.kind
    args: dict[str, Any] = field(default_factory=dict)
    store_as: str = ""
    note: str = ""

@dataclass(frozen=True)
class IRBranchCase:
    when: str = ""
    ops: list["IRNode"] = field(default_factory=list)

@dataclass(frozen=True)
class IRBranch:
    type: Literal["branch"] = "branch"
    kind: str = "branch_from_draw"
    branches: list[IRBranchCase] = field(default_factory=list)
    note: str = ""

IRNode = IROp | IRBranch

@dataclass(frozen=True)
class IREffect:
    effect_id: str
    trigger_kind: str
    restriction: list[dict[str, Any]] = field(default_factory=list)
    condition: list[dict[str, Any]] = field(default_factory=list)
    cost: list[dict[str, Any]] = field(default_factory=list)
    ops: list[IRNode] = field(default_factory=list)

@dataclass(frozen=True)
class IRCard:
    ir_version: int
    cid: int
    effects: list[IREffect] = field(default_factory=list)
