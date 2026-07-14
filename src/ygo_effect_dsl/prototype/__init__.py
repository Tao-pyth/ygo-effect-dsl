"""Executable fixed-hand prototype built on the engine contracts.

The scripted core in this package is a test double. It does not implement
Yu-Gi-Oh! rules and must not be treated as an ocgcore replacement.
"""

from ygo_effect_dsl.prototype.runtime import (
    PrototypeVerificationResult,
    build_prototype_route,
    dump_route_document,
    load_prototype_scenario,
    verify_prototype_route,
)
from ygo_effect_dsl.prototype.real_core import (
    RealCoreWorkerProcessResult,
    RealCoreVerificationResult,
    build_real_core_route,
    invoke_real_core_worker_process,
    probe_activation_rollback_support,
    run_real_core_worker,
    verify_real_core_route,
)
from ygo_effect_dsl.prototype.real_core_stress import (
    REAL_CORE_STRESS_SCHEMA_VERSION,
    dump_real_core_stress_report,
    run_real_core_parallel_stress,
)

__all__ = [
    "PrototypeVerificationResult",
    "REAL_CORE_STRESS_SCHEMA_VERSION",
    "RealCoreVerificationResult",
    "RealCoreWorkerProcessResult",
    "build_prototype_route",
    "build_real_core_route",
    "dump_real_core_stress_report",
    "dump_route_document",
    "invoke_real_core_worker_process",
    "load_prototype_scenario",
    "probe_activation_rollback_support",
    "run_real_core_parallel_stress",
    "run_real_core_worker",
    "verify_prototype_route",
    "verify_real_core_route",
]
