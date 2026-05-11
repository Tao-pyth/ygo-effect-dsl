from __future__ import annotations

from typing import Any


def _effect_actions_count(effect: dict[str, Any]) -> int:
    actions = effect.get("actions")
    if isinstance(actions, list):
        return sum(1 for row in actions if isinstance(row, dict) and row)

    action = effect.get("action")
    if isinstance(action, dict) and action:
        return 1
    return 0


def _effect_targets_count(effect: dict[str, Any]) -> int:
    targets = effect.get("targets")
    if not isinstance(targets, list):
        return 0
    return sum(1 for row in targets if isinstance(row, dict) and row)


def collect_stats(cards: list[dict[str, Any]]) -> dict[str, Any]:
    effects_count = sum(len(c.get("effects", [])) for c in cards if isinstance(c.get("effects"), list))

    actions_per_effect: list[int] = []
    targets_per_effect: list[int] = []
    cards_with_targets = 0
    action_type_counts: dict[str, int] = {}
    target_references = 0
    resolved_target_references = 0
    unmatched_fragments: dict[str, int] = {}
    for card in cards:
        effects = card.get("effects")
        if not isinstance(effects, list):
            continue
        card_has_targets = False
        for effect in effects:
            if isinstance(effect, dict):
                actions_per_effect.append(_effect_actions_count(effect))
                targets_count = _effect_targets_count(effect)
                targets_per_effect.append(targets_count)
                target_ids = set()
                targets = effect.get("targets")
                if isinstance(targets, list):
                    target_ids = {row.get("id") for row in targets if isinstance(row, dict) and isinstance(row.get("id"), str)}

                actions = effect.get("actions")
                if isinstance(actions, list) and actions:
                    action_rows = [row for row in actions if isinstance(row, dict)]
                else:
                    action = effect.get("action")
                    action_rows = [action] if isinstance(action, dict) and action else []

                for action in action_rows:
                    action_type = action.get("type")
                    if isinstance(action_type, str) and action_type:
                        action_type_counts[action_type] = action_type_counts.get(action_type, 0) + 1
                    target_id = action.get("target_id")
                    if isinstance(target_id, str):
                        target_references += 1
                        if target_id in target_ids:
                            resolved_target_references += 1

                if targets_count > 0:
                    card_has_targets = True
        if card_has_targets:
            cards_with_targets += 1

        trace = card.get("meta", {}).get("action_candidate_trace")
        if isinstance(trace, list):
            for row in trace:
                if isinstance(row, dict) and not row.get("matched_rule_ids"):
                    fragment = row.get("fragment")
                    if isinstance(fragment, str) and fragment:
                        unmatched_fragments[fragment] = unmatched_fragments.get(fragment, 0) + 1

    if actions_per_effect:
        avg = sum(actions_per_effect) / len(actions_per_effect)
        min_count = min(actions_per_effect)
        max_count = max(actions_per_effect)
    else:
        avg = 0.0
        min_count = 0
        max_count = 0

    targets_total = sum(targets_per_effect)
    targets_avg = (targets_total / len(targets_per_effect)) if targets_per_effect else 0.0
    target_resolution_rate = (resolved_target_references / target_references) if target_references else 1.0

    return {
        "cards": len(cards),
        "effects": effects_count,
        "action_type_coverage": dict(sorted(action_type_counts.items())),
        "actions_count": {
            "avg": avg,
            "min": min_count,
            "max": max_count,
        },
        "targets_count": {
            "total": targets_total,
            "avg": targets_avg,
            "cards_with_targets": cards_with_targets,
            "references": target_references,
            "resolved_references": resolved_target_references,
            "resolution_rate": target_resolution_rate,
        },
        "unmatched_fragments_top": [
            {"fragment": fragment, "count": count}
            for fragment, count in sorted(unmatched_fragments.items(), key=lambda item: (-item[1], item[0]))[:20]
        ],
    }
