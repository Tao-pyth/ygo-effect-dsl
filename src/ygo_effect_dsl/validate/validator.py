from __future__ import annotations

from ygo_effect_dsl.errors import DslError


EFFECT_REQUIRED_OBJECT_KEYS = ("trigger", "restriction", "condition", "cost")


def _is_empty(value: object) -> bool:
    return value in (None, "", [], {})


def validate_card_yaml(card: dict) -> list[DslError]:
    errs: list[DslError] = []

    if not isinstance(card.get("dsl_version"), str):
        errs.append(DslError("dsl_version", "required", "dsl_version must exist as string"))

    card_obj = card.get("card")
    if not isinstance(card_obj, dict):
        errs.append(DslError("card", "required", "card must be object"))
        card_obj = {}

    if "cid" not in card_obj or _is_empty(card_obj.get("cid")):
        errs.append(DslError("card.cid", "required", "card.cid must exist and must not be empty"))

    name_obj = card_obj.get("name")
    if not isinstance(name_obj, dict):
        errs.append(DslError("card.name", "required", "card.name must be object"))
    else:
        if "en" not in name_obj:
            errs.append(DslError("card.name.en", "required", "card.name.en key is required"))
        if "ja" not in name_obj:
            errs.append(DslError("card.name.ja", "required", "card.name.ja key is required"))

    effects = card.get("effects")
    if not isinstance(effects, list):
        errs.append(DslError("effects", "required", "effects must be list"))
        return errs

    for idx, effect in enumerate(effects):
        prefix = f"effects[{idx}]"
        if not isinstance(effect, dict):
            errs.append(DslError(prefix, "type", "effect item must be object"))
            continue

        if not isinstance(effect.get("id"), str):
            errs.append(DslError(f"{prefix}.id", "required", "effect.id must be string"))
        if not isinstance(effect.get("order"), int):
            errs.append(DslError(f"{prefix}.order", "required", "effect.order must be int"))

        for key in EFFECT_REQUIRED_OBJECT_KEYS:
            if key not in effect:
                errs.append(DslError(f"{prefix}.{key}", "required", f"{key} key is required"))
                continue
            if not isinstance(effect[key], dict):
                errs.append(DslError(f"{prefix}.{key}", "type", f"{key} must be object"))

        has_action = "action" in effect
        has_actions = "actions" in effect
        if not has_action and not has_actions:
            errs.append(DslError(f"{prefix}.actions", "required", "action or actions key is required"))
            continue

        if has_action and not isinstance(effect["action"], dict):
            errs.append(DslError(f"{prefix}.action", "type", "action must be object"))

        if has_actions:
            actions = effect["actions"]
            if not isinstance(actions, list):
                errs.append(DslError(f"{prefix}.actions", "type", "actions must be list"))
            else:
                for action_idx, action in enumerate(actions):
                    if not isinstance(action, dict):
                        errs.append(
                            DslError(
                                f"{prefix}.actions[{action_idx}]",
                                "type",
                                "actions item must be object",
                            )
                        )

    return errs
