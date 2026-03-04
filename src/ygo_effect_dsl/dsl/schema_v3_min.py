"""
DSL V3 最小スキーマ（YAML保存形）

- version/cid/name/text/meta/effects を固定
- effects は trigger→restriction→condition→cost→actions/action の骨を持つ
"""

from __future__ import annotations
from typing import Any, TypedDict, NotRequired


class Name(TypedDict):
    ja: str
    en: str


class Text(TypedDict):
    ja: str
    en: str


class Trigger(TypedDict):
    kind: str
    timing: str
    once: str
    note: str


class Block(TypedDict, total=False):
    kind: str
    args: dict[str, Any]
    value: str
    store_as: str
    note: str


class Effect(TypedDict):
    id: str
    label: str
    order: int
    trigger: Trigger
    restriction: dict[str, Any]
    condition: dict[str, Any]
    cost: dict[str, Any]
    actions: list[dict[str, Any]]
    action: NotRequired[dict[str, Any]]


class CardDSL(TypedDict):
    version: int
    cid: int
    name: Name
    text: Text
    meta: dict[str, Any]
    effects: list[Effect]
