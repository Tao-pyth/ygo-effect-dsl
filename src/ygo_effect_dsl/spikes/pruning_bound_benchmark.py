from __future__ import annotations

import argparse
from functools import lru_cache
import json
import math
from pathlib import Path
import random
import statistics
from typing import Any, Sequence

from ygo_effect_dsl.engine.canonical import stable_digest, to_canonical_data
from ygo_effect_dsl.engine.search import (
    LEGACY_PRUNING_BOUND_METHOD,
    PRUNING_BOUND_METHOD,
)
from ygo_effect_dsl.route_dsl import load_route_document


PRUNING_BOUND_BENCHMARK_SCHEMA_VERSION = "pruning-bound-benchmark-v1"
EMPIRICAL_BERNSTEIN_METHOD = "empirical_bernstein_raw_reference_v0"
PERCENTILE_BOOTSTRAP_METHOD = "percentile_bootstrap_raw_reference_v0"
RANGE_ONLY_METHOD = "bounded_score_range_v1"
_ROUTE_FILENAMES = (
    "real_core_action_aggregation.route.yaml",
    "real_core_effect_veiler.route.yaml",
    "real_core_effect_veiler_interrupted.route.yaml",
    "real_core_temporary_atk.route.yaml",
)
_SCENARIOS = (
    ("iid_100x1", 100, 1),
    ("correlated_20x20", 20, 20),
    ("correlated_10x100", 10, 100),
    ("perfectly_correlated_1x1000", 1, 1000),
)


def _clip_interval(
    mean: float, radius: float, lower: float, upper: float
) -> tuple[float, float]:
    return max(lower, mean - radius), min(upper, mean + radius)


def _hoeffding_interval(
    scores: Sequence[float],
    *,
    confidence_delta: float,
    lower: float,
    upper: float,
    family_wise: bool,
) -> tuple[float, float]:
    log_term = math.log(
        (4 if family_wise else 2) / confidence_delta
    )
    radius = (upper - lower) * math.sqrt(log_term / (2 * len(scores)))
    return _clip_interval(statistics.fmean(scores), radius, lower, upper)


def _empirical_bernstein_interval(
    scores: Sequence[float],
    *,
    confidence_delta: float,
    lower: float,
    upper: float,
) -> tuple[float, float]:
    if len(scores) == 1:
        return lower, upper
    variance = statistics.variance(scores)
    log_term = math.log(6 / confidence_delta)
    radius = math.sqrt(2 * variance * log_term / len(scores)) + (
        3 * (upper - lower) * log_term / len(scores)
    )
    return _clip_interval(statistics.fmean(scores), radius, lower, upper)


@lru_cache(maxsize=None)
def _binomial_quantiles(
    sample_count: int, successes: int, tail_probability: float
) -> tuple[int, int]:
    if successes == 0:
        return 0, 0
    if successes == sample_count:
        return sample_count, sample_count
    probability = successes / sample_count
    log_p = math.log(probability)
    log_q = math.log1p(-probability)
    probabilities = [
        math.exp(
            math.lgamma(sample_count + 1)
            - math.lgamma(value + 1)
            - math.lgamma(sample_count - value + 1)
            + value * log_p
            + (sample_count - value) * log_q
        )
        for value in range(sample_count + 1)
    ]
    total = math.fsum(probabilities)
    lower_quantile = 0
    upper_quantile = sample_count
    cumulative = 0.0
    lower_found = False
    for value, mass in enumerate(probabilities):
        cumulative += mass / total
        if not lower_found and cumulative >= tail_probability:
            lower_quantile = value
            lower_found = True
        if cumulative >= 1 - tail_probability:
            upper_quantile = value
            break
    return lower_quantile, upper_quantile


def _binary_percentile_bootstrap_interval(
    scores: Sequence[float],
    *,
    confidence_delta: float,
) -> tuple[float, float]:
    low = min(scores)
    high = max(scores)
    if low == high:
        return low, high
    if any(score not in (low, high) for score in scores):
        raise ValueError("reference bootstrap accepts binary benchmark scores only")
    successes = sum(score == high for score in scores)
    lower_count, upper_count = _binomial_quantiles(
        len(scores), successes, confidence_delta / 4
    )
    span = high - low
    return (
        low + span * lower_count / len(scores),
        low + span * upper_count / len(scores),
    )


def _method_intervals(
    raw_candidate: Sequence[float],
    raw_incumbent: Sequence[float],
    cluster_candidate: Sequence[float],
    cluster_incumbent: Sequence[float],
    *,
    confidence_delta: float,
    lower: float,
    upper: float,
) -> dict[str, tuple[tuple[float, float], tuple[float, float]]]:
    return {
        LEGACY_PRUNING_BOUND_METHOD: (
            _hoeffding_interval(
                raw_candidate,
                confidence_delta=confidence_delta,
                lower=lower,
                upper=upper,
                family_wise=False,
            ),
            _hoeffding_interval(
                raw_incumbent,
                confidence_delta=confidence_delta,
                lower=lower,
                upper=upper,
                family_wise=False,
            ),
        ),
        PRUNING_BOUND_METHOD: (
            _hoeffding_interval(
                cluster_candidate,
                confidence_delta=confidence_delta,
                lower=lower,
                upper=upper,
                family_wise=True,
            ),
            _hoeffding_interval(
                cluster_incumbent,
                confidence_delta=confidence_delta,
                lower=lower,
                upper=upper,
                family_wise=True,
            ),
        ),
        EMPIRICAL_BERNSTEIN_METHOD: (
            _empirical_bernstein_interval(
                raw_candidate,
                confidence_delta=confidence_delta,
                lower=lower,
                upper=upper,
            ),
            _empirical_bernstein_interval(
                raw_incumbent,
                confidence_delta=confidence_delta,
                lower=lower,
                upper=upper,
            ),
        ),
        PERCENTILE_BOOTSTRAP_METHOD: (
            _binary_percentile_bootstrap_interval(
                raw_candidate, confidence_delta=confidence_delta
            ),
            _binary_percentile_bootstrap_interval(
                raw_incumbent, confidence_delta=confidence_delta
            ),
        ),
        RANGE_ONLY_METHOD: ((lower, upper), (lower, upper)),
    }


def _run_scenario(
    *,
    scenario_id: str,
    independent_units: int,
    block_size: int,
    trials: int,
    seed: int,
    confidence_delta: float,
) -> dict[str, Any]:
    rng = random.Random(seed)
    lower = 0.0
    upper = 100.0
    rare_success_probability = 0.2
    incumbent_score = 15.0
    false_prunes = {
        method: 0
        for method in (
            LEGACY_PRUNING_BOUND_METHOD,
            PRUNING_BOUND_METHOD,
            EMPIRICAL_BERNSTEIN_METHOD,
            PERCENTILE_BOOTSTRAP_METHOD,
            RANGE_ONLY_METHOD,
        )
    }
    success_histogram = {str(count): 0 for count in range(independent_units + 1)}
    for _ in range(trials):
        cluster_candidate = [
            upper if rng.random() < rare_success_probability else lower
            for _ in range(independent_units)
        ]
        cluster_incumbent = [incumbent_score] * independent_units
        successes = sum(score == upper for score in cluster_candidate)
        success_histogram[str(successes)] += 1
        raw_candidate = [
            score for score in cluster_candidate for _ in range(block_size)
        ]
        raw_incumbent = [incumbent_score] * len(raw_candidate)
        intervals = _method_intervals(
            raw_candidate,
            raw_incumbent,
            cluster_candidate,
            cluster_incumbent,
            confidence_delta=confidence_delta,
            lower=lower,
            upper=upper,
        )
        for method, (candidate_interval, incumbent_interval) in intervals.items():
            if candidate_interval[1] < incumbent_interval[0]:
                false_prunes[method] += 1
    raw_count = independent_units * block_size
    return {
        "block_correlation_model": {
            "between_block_correlation": 0,
            "design_effect": block_size,
            "within_block_correlation": 1 if block_size > 1 else None,
        },
        "false_prune_results": {
            method: {
                "count": count,
                "rate": round(count / trials, 6),
            }
            for method, count in false_prunes.items()
        },
        "independent_unit_count": independent_units,
        "known_effective_sample_size": independent_units,
        "raw_score_count": raw_count,
        "scenario_id": scenario_id,
        "success_count_histogram": success_histogram,
        "true_means": {
            "candidate": rare_success_probability * upper,
            "incumbent": incumbent_score,
        },
        "within_unit_repetitions": block_size,
    }


def _real_trace_inventory(repo_root: Path) -> dict[str, Any]:
    records = []
    prototype_dir = repo_root / "examples" / "prototype"
    for filename in _ROUTE_FILENAMES:
        route = load_route_document(prototype_dir / filename)
        experiment = route["experiment"]
        peak = route["result"]["peak_board"]
        records.append(
            {
                "deck_id": experiment["deck"]["id"],
                "filename": filename,
                "route_id": route["route_id"],
                "scenario_id": experiment["prototype"]["scenario_id"],
                "score": peak["score"],
            }
        )
    return {
        "action_score_correlation": None,
        "independent_unit_count": None,
        "reason": "no sibling Action score samples from repeated root trials",
        "records": records,
        "statistically_usable": False,
        "unique_deck_count": len({record["deck_id"] for record in records}),
        "unique_scenario_count": len(
            {record["scenario_id"] for record in records}
        ),
    }


def run_pruning_bound_benchmark(
    *,
    trials: int = 5_000,
    seed: int = 98_049,
    confidence_delta: float = 0.05,
    repo_root: str | Path | None = None,
) -> dict[str, Any]:
    if trials < 1:
        raise ValueError("trials must be at least 1")
    if not 0 < confidence_delta < 1:
        raise ValueError("confidence_delta must be between 0 and 1")
    root = (
        Path(repo_root).resolve()
        if repo_root is not None
        else Path(__file__).resolve().parents[3]
    )
    scenarios = [
        _run_scenario(
            scenario_id=scenario_id,
            independent_units=independent_units,
            block_size=block_size,
            trials=trials,
            seed=seed + index,
            confidence_delta=confidence_delta,
        )
        for index, (scenario_id, independent_units, block_size) in enumerate(
            _SCENARIOS
        )
    ]
    real_trace_inventory = _real_trace_inventory(root)
    limitations = {
        "production_default_calibration": "not_supported_by_current_corpus",
        "required_follow_up": {
            "issue": 110,
            "scope": (
                "multi-deck repeated sibling-Action traces with root-seed provenance"
            ),
        },
        "synthetic_model": (
            "perfect within-block dependence; independent between blocks"
        ),
    }
    recommendation = {
        "confidence_delta": 0.01,
        "minimum_independent_units": 20,
        "parameter_status": "conservative_provisional",
        "prune_margin": 0,
        "score_bounds": "exact evaluator range; fail on out-of-range score",
    }
    semantic_identity = to_canonical_data(
        {
            "confidence_delta": confidence_delta,
            "decision": {
                "default_method": PRUNING_BOUND_METHOD,
                "legacy_method": LEGACY_PRUNING_BOUND_METHOD,
                "legacy_status": "deprecated_explicit_compatibility_only",
                "missing_independence_metadata": "keep_without_interval",
            },
            "limitations": limitations,
            "real_trace_inventory": real_trace_inventory,
            "recommendation": recommendation,
            "scenarios": scenarios,
            "schema_version": PRUNING_BOUND_BENCHMARK_SCHEMA_VERSION,
            "seed": seed,
            "trials": trials,
        }
    )
    return {
        **semantic_identity,
        "benchmark_id": stable_digest(semantic_identity, prefix="prunebench_"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="compare pruning bounds under correlated score samples"
    )
    parser.add_argument("--trials", type=int, default=5_000)
    parser.add_argument("--seed", type=int, default=98_049)
    parser.add_argument("--confidence-delta", type=float, default=0.05)
    parser.add_argument("--repo-root", type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    report = run_pruning_bound_benchmark(
        trials=args.trials,
        seed=args.seed,
        confidence_delta=args.confidence_delta,
        repo_root=args.repo_root,
    )
    serialized = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.out is None:
        print(serialized, end="")
    else:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(serialized, encoding="utf-8")
        print(
            f"pruning-bound-benchmark: wrote {args.out} "
            f"benchmark_id={report['benchmark_id']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
