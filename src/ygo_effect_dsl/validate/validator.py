from __future__ import annotations
from ygo_effect_dsl.errors import DslError

def validate_card_yaml(card: dict) -> list[DslError]:
    errs: list[DslError] = []
    if int(card.get("version", 0) or 0) != 3:
        errs.append(DslError("version", "unsupported_version", "version must be 3"))
    cid = card.get("cid", 0)
    if not isinstance(cid, int) or cid <= 0:
        errs.append(DslError("cid", "required", "cid must be positive integer"))
    effects = card.get("effects")
    if not isinstance(effects, list) or len(effects) == 0:
        errs.append(DslError("effects", "required", "effects must not be empty"))
    return errs
