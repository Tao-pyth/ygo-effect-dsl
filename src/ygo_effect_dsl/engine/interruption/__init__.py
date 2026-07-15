"""Interruption target contracts with lazy Route comparison exports."""

from __future__ import annotations

from typing import Any

from ygo_effect_dsl.engine.interruption.target import (
    INTERRUPTION_TARGET_RESOLUTION_SCHEMA_VERSION,
    INTERRUPTION_TARGET_SCHEMA_VERSION,
    InterruptionTarget,
    InterruptionTargetResolution,
    InterruptionTargetResolutionError,
    resolve_interruption_target,
)
from ygo_effect_dsl.engine.interruption.validation import (
    OCGCORE_INTERRUPTION_VALIDATION_METHOD,
    OCGCORE_INTERRUPTION_VALIDATION_SCHEMA_VERSION,
    derive_ocgcore_interruption_validation,
)


_COMPARISON_EXPORTS = {
    "INTERRUPTION_COMPARISON_SCHEMA_VERSION",
    "RecoveryStatus",
    "build_interruption_comparison",
}
_ATTRIBUTION_EXPORTS = {
    "ADDITIONAL_CARD_ATTRIBUTION_SCHEMA_VERSION",
    "ADDITIONAL_CARD_ATTRIBUTION_V2_SCHEMA_VERSION",
    "CARD_INSTANCE_PROVENANCE_SCHEMA_VERSION",
    "CARD_INSTANCE_PROVENANCE_V2_SCHEMA_VERSION",
    "COUNTERFACTUAL_METHOD",
    "CardOriginKind",
    "build_additional_card_attribution",
    "build_additional_card_attribution_v2",
    "classify_card_origin",
}
_ADAPTER_EXPORTS = {
    "CORE_INTERRUPTION_CANDIDATE_POLICY_SCHEMA_VERSION",
    "CORE_INTERRUPTION_STEP_SCHEMA_VERSION",
    "CandidateSelector",
    "CoreInterruptionCandidatePolicy",
    "CoreInterruptionStep",
    "InterruptionCandidatePolicyError",
}
_TAXONOMY_EXPORTS = {
    "INTERRUPTION_SUPPORT_TAXONOMY_SCHEMA_VERSION",
    "InterruptionCandidateSupport",
    "InterruptionOutcomeStatus",
    "InterruptionSourceZone",
    "InterruptionTargetShape",
    "InterruptionTaxonomyDiagnostic",
    "InterruptionTaxonomyOutcome",
    "InterruptionValidationPolicy",
    "classify_interruption_candidates",
}
_COMPOSITION_CONTRACT_EXPORTS = {
    "BRANCHING_POLICY",
    "MULTI_INTERRUPTION_COMPOSITION_SCHEMA_VERSION",
    "MULTI_INTERRUPTION_LINEAGE_SCHEMA_VERSION",
    "MULTI_INTERRUPTION_OPPORTUNITY_SCHEMA_VERSION",
    "OPPONENT_ACTION_SCOPE",
    "OPPORTUNITY_POLICY",
    "PRIORITY_POLICY",
    "MultiInterruptionComposition",
    "MultiInterruptionDefinition",
    "MultiInterruptionDiagnostic",
    "build_multi_interruption_composition",
    "validate_multi_interruption_composition",
}


def __getattr__(name: str) -> Any:
    if name in _COMPOSITION_CONTRACT_EXPORTS:
        from ygo_effect_dsl.engine.interruption import composition

        return getattr(composition, name)
    if name in _ADAPTER_EXPORTS:
        from ygo_effect_dsl.engine.interruption import adapter

        return getattr(adapter, name)
    if name in _TAXONOMY_EXPORTS:
        from ygo_effect_dsl.engine.interruption import taxonomy

        return getattr(taxonomy, name)
    if name in _ATTRIBUTION_EXPORTS:
        from ygo_effect_dsl.engine.interruption import attribution

        return getattr(attribution, name)
    if name not in _COMPARISON_EXPORTS:
        raise AttributeError(name)
    from ygo_effect_dsl.engine.interruption import comparison

    return getattr(comparison, name)


__all__ = [
    "OCGCORE_INTERRUPTION_VALIDATION_METHOD",
    "OCGCORE_INTERRUPTION_VALIDATION_SCHEMA_VERSION",
    "ADDITIONAL_CARD_ATTRIBUTION_SCHEMA_VERSION",
    "ADDITIONAL_CARD_ATTRIBUTION_V2_SCHEMA_VERSION",
    "CARD_INSTANCE_PROVENANCE_SCHEMA_VERSION",
    "CARD_INSTANCE_PROVENANCE_V2_SCHEMA_VERSION",
    "COUNTERFACTUAL_METHOD",
    "CORE_INTERRUPTION_CANDIDATE_POLICY_SCHEMA_VERSION",
    "CORE_INTERRUPTION_STEP_SCHEMA_VERSION",
    "CandidateSelector",
    "BRANCHING_POLICY",
    "CoreInterruptionCandidatePolicy",
    "CoreInterruptionStep",
    "INTERRUPTION_COMPARISON_SCHEMA_VERSION",
    "INTERRUPTION_SUPPORT_TAXONOMY_SCHEMA_VERSION",
    "INTERRUPTION_TARGET_RESOLUTION_SCHEMA_VERSION",
    "INTERRUPTION_TARGET_SCHEMA_VERSION",
    "MULTI_INTERRUPTION_COMPOSITION_SCHEMA_VERSION",
    "MULTI_INTERRUPTION_LINEAGE_SCHEMA_VERSION",
    "MULTI_INTERRUPTION_OPPORTUNITY_SCHEMA_VERSION",
    "InterruptionTarget",
    "InterruptionTargetResolution",
    "InterruptionTargetResolutionError",
    "InterruptionCandidateSupport",
    "InterruptionCandidatePolicyError",
    "InterruptionOutcomeStatus",
    "InterruptionSourceZone",
    "InterruptionTargetShape",
    "InterruptionTaxonomyDiagnostic",
    "InterruptionTaxonomyOutcome",
    "InterruptionValidationPolicy",
    "MultiInterruptionComposition",
    "MultiInterruptionDefinition",
    "MultiInterruptionDiagnostic",
    "OPPONENT_ACTION_SCOPE",
    "OPPORTUNITY_POLICY",
    "PRIORITY_POLICY",
    "CardOriginKind",
    "RecoveryStatus",
    "build_interruption_comparison",
    "build_additional_card_attribution",
    "build_additional_card_attribution_v2",
    "classify_card_origin",
    "classify_interruption_candidates",
    "build_multi_interruption_composition",
    "derive_ocgcore_interruption_validation",
    "resolve_interruption_target",
    "validate_multi_interruption_composition",
]
