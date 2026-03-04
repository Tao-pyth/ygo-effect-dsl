from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from ygo_effect_dsl.pipeline import count_action_types


class TransformReporter:
    def __init__(self) -> None:
        self.total = 0
        self.success = 0
        self.failures: list[dict[str, Any]] = []
        self.stage_hits = Counter()
        self.stage_total = Counter()
        self.unmatched = Counter()
        self.cards: list[dict[str, Any]] = []
        self.candidates_count = Counter()

    def record_success(self, card: dict[str, Any], outcomes: dict[str, Any]) -> None:
        self.total += 1
        self.success += 1
        self.cards.append(card)
        meta = card.get("meta", {}) if isinstance(card, dict) else {}
        candidate_counts = meta.get("candidates_count", {}) if isinstance(meta, dict) else {}
        if isinstance(candidate_counts, dict):
            for key in ("sentences", "restriction", "cost", "action"):
                value = candidate_counts.get(key, 0)
                if isinstance(value, int):
                    self.candidates_count[key] += value

        for stage, outcome in outcomes.items():
            self.stage_total[stage] += 1
            if outcome.matched:
                self.stage_hits[stage] += 1

            unmatched_details = getattr(outcome, "unmatched_details", [])
            if unmatched_details:
                for row in unmatched_details:
                    fragment = row.get("fragment", "")
                    classified_as = row.get("classified_as", "sentence")
                    mapped_action_index = row.get("mapped_action_index") if stage == "action" else None
                    self.unmatched[(stage, classified_as, fragment, mapped_action_index)] += 1
                continue

            unmatched_fragments = getattr(outcome, "unmatched_fragments", [])
            if unmatched_fragments:
                for fragment in unmatched_fragments:
                    self.unmatched[(stage, "sentence", fragment, None)] += 1
            elif outcome.unmatched_fragment:
                self.unmatched[(stage, "sentence", outcome.unmatched_fragment, None)] += 1

    def record_failure(self, cid: str, error: str) -> None:
        self.total += 1
        self.failures.append({"cid": cid, "error": error})

    def build_summary(self) -> dict[str, Any]:
        stage_hit_rate = {}
        for stage, total in self.stage_total.items():
            hit = self.stage_hits[stage]
            stage_hit_rate[stage] = {"hit": hit, "total": total, "ratio": (hit / total if total else 0.0)}

        unmatched_top = [
            {
                "stage": stage,
                "classified_as": classified_as,
                "fragment": fragment,
                "mapped_action_index": mapped_action_index,
                "count": count,
            }
            for (stage, classified_as, fragment, mapped_action_index), count in self.unmatched.most_common(50)
        ]

        action_counts = []
        for card in self.cards:
            for effect in card.get("effects", []):
                if not isinstance(effect, dict):
                    continue
                actions = effect.get("actions")
                if isinstance(actions, list):
                    action_counts.append(sum(1 for row in actions if isinstance(row, dict) and row))
                else:
                    fallback = effect.get("action")
                    action_counts.append(1 if isinstance(fallback, dict) and fallback else 0)

        summary_actions_count = {
            "avg": (sum(action_counts) / len(action_counts)) if action_counts else 0.0,
            "min": min(action_counts) if action_counts else 0,
            "max": max(action_counts) if action_counts else 0,
        }
        return {
            "input_count": self.total,
            "success_count": self.success,
            "failure_count": len(self.failures),
            "stage_hit_rate": stage_hit_rate,
            "action_type_ranking": count_action_types(self.cards),
            "actions_count": summary_actions_count,
            "candidates_count": dict(self.candidates_count),
            "unmatched_top": unmatched_top,
        }

    def write_reports(self, out_root: str, include_unmatched: bool = True) -> None:
        report_dir = Path(out_root) / "reports"
        report_dir.mkdir(parents=True, exist_ok=True)

        summary_path = report_dir / "summary.json"
        summary_path.write_text(json.dumps(self.build_summary(), ensure_ascii=False, indent=2), encoding="utf-8")

        if include_unmatched:
            unmatched_path = report_dir / "unmatched_fragments.jsonl"
            with unmatched_path.open("w", encoding="utf-8") as f:
                for (stage, classified_as, fragment, mapped_action_index), count in self.unmatched.most_common():
                    row = {
                        "stage": stage,
                        "classified_as": classified_as,
                        "fragment": fragment,
                        "mapped_action_index": mapped_action_index,
                        "count": count,
                    }
                    f.write(json.dumps(row, ensure_ascii=False) + "\n")

        failures_path = report_dir / "failures.jsonl"
        with failures_path.open("w", encoding="utf-8") as f:
            for row in self.failures:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
