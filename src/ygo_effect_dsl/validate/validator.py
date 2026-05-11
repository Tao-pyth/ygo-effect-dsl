from __future__ import annotations

from ygo_effect_dsl.errors import DslError


EFFECT_REQUIRED_OBJECT_KEYS = ("trigger", "restriction", "condition", "cost")
KNOWN_ACTION_TYPES = {
    "add_to_hand",
    "banish",
    "destroy",
    "discard",
    "draw",
    "negate",
    "return_to_deck",
    "return_to_extra",
    "send_to_gy",
    "special_summon",
}


def _diagnostic(path: str, code: str, message: str, severity: str = "error") -> DslError:
    return DslError(path, code, message, severity)  # type: ignore[arg-type]


def _is_empty(value: object) -> bool:
    return value in (None, "", [], {})


def _validate_target(prefix: str, target: dict, errs: list[DslError]) -> None:
    if not isinstance(target.get("id"), str):
        errs.append(_diagnostic(f"{prefix}.id", "required", "target.id must be string"))

    count = target.get("count")
    if not isinstance(count, int):
        errs.append(_diagnostic(f"{prefix}.count", "required", "target.count must be int"))

    selector = target.get("selector")
    if not isinstance(selector, dict):
        errs.append(_diagnostic(f"{prefix}.selector", "required", "target.selector must be object"))
        return

    kind = selector.get("kind")
    if not isinstance(kind, str) or not kind:
        errs.append(_diagnostic(f"{prefix}.selector.kind", "required", "target.selector.kind must be non-empty string"))
    elif kind == "unknown":
        errs.append(
            _diagnostic(
                f"{prefix}.selector.kind",
                "unresolved_target",
                "target selector kind is unresolved",
                "warning",
            )
        )


def _validate_action(prefix: str, action: dict, errs: list[DslError]) -> None:
    action_type = action.get("type")
    if not isinstance(action_type, str) or not action_type:
        errs.append(_diagnostic(f"{prefix}.type", "missing_action_type", "action.type is missing", "warning"))
        return

    if action_type not in KNOWN_ACTION_TYPES:
        errs.append(
            _diagnostic(
                f"{prefix}.type",
                "unknown_action",
                f"action.type is not in the v0.0 known vocabulary: {action_type}",
                "warning",
            )
        )

    if action_type in {"add_to_hand", "banish", "destroy", "send_to_gy", "special_summon"}:
        if "target_id" not in action and not any(key in action for key in ("desc", "who")):
            errs.append(
                _diagnostic(
                    prefix,
                    "missing_selector",
                    "action has neither target_id nor inline selector fields",
                    "warning",
                )
            )


def validate_card_yaml(card: dict) -> list[DslError]:
    errs: list[DslError] = []

    if not isinstance(card.get("dsl_version"), str):
        errs.append(_diagnostic("dsl_version", "required", "dsl_version must exist as string"))

    card_obj = card.get("card")
    if not isinstance(card_obj, dict):
        errs.append(_diagnostic("card", "required", "card must be object"))
        card_obj = {}

    if "cid" not in card_obj or _is_empty(card_obj.get("cid")):
        errs.append(_diagnostic("card.cid", "required", "card.cid must exist and must not be empty"))

    name_obj = card_obj.get("name")
    if not isinstance(name_obj, dict):
        errs.append(_diagnostic("card.name", "required", "card.name must be object"))
    else:
        if "en" not in name_obj:
            errs.append(_diagnostic("card.name.en", "required", "card.name.en key is required"))
        if "ja" not in name_obj:
            errs.append(_diagnostic("card.name.ja", "required", "card.name.ja key is required"))

    effects = card.get("effects")
    if not isinstance(effects, list):
        errs.append(_diagnostic("effects", "required", "effects must be list"))
        return errs

    for idx, effect in enumerate(effects):
        prefix = f"effects[{idx}]"
        if not isinstance(effect, dict):
            errs.append(_diagnostic(prefix, "type", "effect item must be object"))
            continue

        if not isinstance(effect.get("id"), str):
            errs.append(_diagnostic(f"{prefix}.id", "required", "effect.id must be string"))
        if not isinstance(effect.get("order"), int):
            errs.append(_diagnostic(f"{prefix}.order", "required", "effect.order must be int"))

        for key in EFFECT_REQUIRED_OBJECT_KEYS:
            if key not in effect:
                errs.append(_diagnostic(f"{prefix}.{key}", "required", f"{key} key is required"))
                continue
            if not isinstance(effect[key], dict):
                errs.append(_diagnostic(f"{prefix}.{key}", "type", f"{key} must be object"))

        has_action = "action" in effect
        has_actions = "actions" in effect
        if not has_action and not has_actions:
            errs.append(_diagnostic(f"{prefix}.actions", "required", "action or actions key is required"))
            continue

        if has_action and not isinstance(effect["action"], dict):
            errs.append(_diagnostic(f"{prefix}.action", "type", "action must be object"))
        elif has_action and not has_actions and isinstance(effect["action"], dict) and effect["action"]:
            errs.append(
                _diagnostic(
                    f"{prefix}.action",
                    "legacy_action_fallback",
                    "legacy action fallback used; prefer actions[]",
                    "warning",
                )
            )
            _validate_action(f"{prefix}.action", effect["action"], errs)

        if has_actions:
            actions = effect["actions"]
            if not isinstance(actions, list):
                errs.append(_diagnostic(f"{prefix}.actions", "type", "actions must be list"))
            else:
                for action_idx, action in enumerate(actions):
                    if not isinstance(action, dict):
                        errs.append(
                            _diagnostic(
                                f"{prefix}.actions[{action_idx}]",
                                "type",
                                "actions item must be object",
                            )
                        )
                        continue
                    if "target_id" in action and not isinstance(action.get("target_id"), str):
                        errs.append(_diagnostic(f"{prefix}.actions[{action_idx}].target_id", "type", "target_id must be string"))
                    _validate_action(f"{prefix}.actions[{action_idx}]", action, errs)

        if "targets" in effect:
            targets = effect["targets"]
            if not isinstance(targets, list):
                errs.append(_diagnostic(f"{prefix}.targets", "type", "targets must be list"))
            else:
                for target_idx, target in enumerate(targets):
                    target_prefix = f"{prefix}.targets[{target_idx}]"
                    if not isinstance(target, dict):
                        errs.append(_diagnostic(target_prefix, "type", "targets item must be object"))
                        continue
                    _validate_target(target_prefix, target, errs)

        if "target_id" in effect.get("cost", {}) and not isinstance(effect["cost"].get("target_id"), str):
            errs.append(_diagnostic(f"{prefix}.cost.target_id", "type", "target_id must be string"))
        if "target_id" in effect.get("condition", {}) and not isinstance(effect["condition"].get("target_id"), str):
            errs.append(_diagnostic(f"{prefix}.condition.target_id", "type", "target_id must be string"))

    return errs
