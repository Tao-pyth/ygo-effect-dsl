from __future__ import annotations

import copy
import re
from typing import Any

from ygo_effect_dsl.models import Rule


class RuleEngine:
    def __init__(self, overwrite: bool = False):
        self.overwrite = overwrite

    def apply_rules(
        self,
        text: str,
        rules: list[Rule],
        payload: dict[str, Any],
        norm_params: dict[str, list[Any]],
    ) -> tuple[dict[str, Any], list[str]]:
        out = copy.deepcopy(payload)
        hits: list[str] = []

        for rule in rules:
            match = re.search(rule.pattern, text)
            if not match:
                continue
            capture_ctx = self._build_capture_context(rule.capture, match, norm_params)
            emitted = self._resolve_template(rule.emit, capture_ctx)
            out = self._deep_merge(out, emitted)
            hits.append(rule.id)

        return out, hits

    def _build_capture_context(
        self,
        capture_map: dict[str, Any],
        match: re.Match[str],
        norm_params: dict[str, list[Any]],
    ) -> dict[str, Any]:
        ctx: dict[str, Any] = dict(match.groupdict())
        for key, expr in capture_map.items():
            ctx[key] = self._resolve_ref(expr, ctx, norm_params)
        return ctx

    def _resolve_ref(self, expr: Any, ctx: dict[str, Any], norm_params: dict[str, list[Any]]) -> Any:
        if isinstance(expr, list):
            return [self._resolve_ref(item, ctx, norm_params) for item in expr]
        if isinstance(expr, dict):
            return {k: self._resolve_ref(v, ctx, norm_params) for k, v in expr.items()}
        if not isinstance(expr, str):
            return expr

        if expr.startswith("$"):
            return ctx.get(expr[1:], "")

        token_match = re.fullmatch(r"([A-Z_]+)\[(\d+)\]", expr)
        if token_match:
            key, index_str = token_match.groups()
            index = int(index_str)
            bucket = norm_params.get(key, [])
            if 0 <= index < len(bucket):
                return bucket[index]
            return ""

        return expr

    def _resolve_template(self, value: Any, ctx: dict[str, Any]) -> Any:
        if isinstance(value, dict):
            return {k: self._resolve_template(v, ctx) for k, v in value.items()}
        if isinstance(value, list):
            return [self._resolve_template(v, ctx) for v in value]
        if isinstance(value, str) and value.startswith("$"):
            return ctx.get(value[1:], "")
        return value

    def _deep_merge(self, base: Any, patch: Any) -> Any:
        if isinstance(base, dict) and isinstance(patch, dict):
            out = dict(base)
            for key, p_value in patch.items():
                if key not in out:
                    out[key] = copy.deepcopy(p_value)
                    continue

                b_value = out[key]
                if isinstance(b_value, dict) and isinstance(p_value, dict):
                    out[key] = self._deep_merge(b_value, p_value)
                elif isinstance(b_value, list) and isinstance(p_value, list):
                    out[key] = b_value + [copy.deepcopy(v) for v in p_value]
                elif self.overwrite or b_value in (None, "", [], {}):
                    out[key] = copy.deepcopy(p_value)
            return out

        return copy.deepcopy(patch if self.overwrite else base)
