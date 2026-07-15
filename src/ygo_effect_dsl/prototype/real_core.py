from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field, replace
import hashlib
import itertools
import json
from pathlib import Path
import subprocess
import sys
from typing import Any, Mapping, Sequence

from ygo_effect_dsl.engine.action import (
    OCGCORE_ACTION_AGGREGATION_METHOD,
    Action,
    ActionKind,
    CardRef,
    Selection,
    assert_valid_activation_rollback_probe,
    build_activation_rollback_probe,
    derive_ocgcore_action_aggregation,
)
from ygo_effect_dsl.runtime_imports import current_checkout_environment
from ygo_effect_dsl.engine.bridge.ocgcore import (
    CARD_INSTANCE_PROVENANCE_V2_SCHEMA_VERSION,
    CARD_INSTANCE_TRACE_V2_LOG_PREFIX,
    CARD_INSTANCE_TRACE_V2_LUA_SOURCE,
    CARD_INSTANCE_TRACE_V2_SCHEMA_VERSION,
    CARD_INSTANCE_TRACE_V2_SCRIPT_NAME,
    CardInstanceAuditedScriptProvider,
    CardInstanceTrackerV2,
    CardScriptsProvider,
    DecodedMessageBatch,
    DIRECT_RANDOM_TRACE_LUA_SOURCE,
    DIRECT_RANDOM_TRACE_SCRIPT_NAME,
    DuelConfig,
    NewCard,
    OcgcoreLibrary,
    OcgcoreMessageDecoder,
    PlayerConfig,
    ResolvedScript,
    SQLiteCardDataProvider,
    assert_public_card_instance_document,
    build_board_summary,
    build_card_instance_scope_id_v2,
    build_core_output_trace,
    card_scripts_profile_for_experiment_schema,
    direct_random_trace_metadata,
    evaluate_legal_stop,
    filter_card_instance_trace_logs,
    resolve_script,
)
from ygo_effect_dsl.engine.bridge.ocgcore.errors import (
    OcgcoreWorkerCrashError,
    OcgcoreWorkerProtocolError,
    OcgcoreWorkerTimeoutError,
)
from ygo_effect_dsl.engine.bridge.ocgcore.protocol import PROTOCOL_VERSION
from ygo_effect_dsl.engine.bridge.ocgcore.state import SNAPSHOT_SCHEMA_VERSION
from ygo_effect_dsl.engine.canonical import (
    canonical_json,
    stable_digest,
    to_canonical_data,
)
from ygo_effect_dsl.engine.evaluation import (
    BoundaryEvidence,
    EvaluationInput,
    EvaluationResult,
    EvaluationValueComponent,
    ValuePermanence,
    build_default_evaluator_registry,
    build_temporary_modifier_observation,
    build_temporary_effect_report,
)
from ygo_effect_dsl.engine.failures import (
    FailureRecord,
    FailureRecordError,
    classify_failure,
)
from ygo_effect_dsl.engine.information import (
    DeckOrderKnowledge,
    InformationAccessAudit,
    InformationAccessPolicy,
    InformationField,
    OpeningHandPolicy,
    audit_information_artifact,
    build_opening_hand_sampling_evidence,
    build_player_view_canary_registry,
)
from ygo_effect_dsl.engine.peak import (
    DURABLE_EVALUATION_TIMING,
    build_durability_report,
)
from ygo_effect_dsl.engine.interruption import (
    INTERRUPTION_SUPPORT_TAXONOMY_SCHEMA_VERSION,
    CoreInterruptionCandidatePolicy,
    InterruptionCandidatePolicyError,
    InterruptionTarget,
    MultiInterruptionRuntimeError,
    build_interruption_opportunity_id,
    build_multi_interruption_composition,
    build_multi_interruption_frontier,
    derive_ocgcore_interruption_validation,
    InterruptionValidationPolicy,
    classify_interruption_candidates,
    resolve_multi_interruption_definition,
)
from ygo_effect_dsl.engine.state import (
    ConstraintExpiration,
    ExpirationBoundary,
    InformationMode,
    StateCoordinate,
)
from ygo_effect_dsl.engine.replay import (
    PLAYER_VIEW_PROJECTOR_ID,
    PlayerViewProjectionInput,
    ReplayEventV03a,
    ReplayHistoryV03a,
    ReplayManifestIncompleteError,
    ReplayManifestV03a,
    assert_complete_io_trace,
    assert_replay_request_signatures,
    assert_manifest_matches,
    assert_valid_player_view_replay,
    build_player_view_replay,
)
from ygo_effect_dsl.engine.replay.manifest import RANDOM_TRACE_POLICY
from ygo_effect_dsl.external.ocgcore import (
    load_ocgcore_asset_lock,
    load_ocgcore_lock,
    resolve_ocgcore_assets,
    resolve_ocgcore_runtime,
    verify_ocgcore,
)
from ygo_effect_dsl.experiment import (
    INTERRUPTION_SAMPLING_SCHEMA_VERSION,
    assert_current_experiment,
    preflight_scenario,
)
from ygo_effect_dsl.route_dsl import assert_valid_route_document


REAL_CORE_SCENARIO_ID = "real_core_effect_veiler_normal_summon_v1"
ACTIVATION_ROLLBACK_SCENARIO_ID = "real_core_activation_rollback_probe_v1"
RECOVERY_ATTRIBUTION_SCENARIO_ID = "real_core_recovery_attribution_v1"
INTERRUPTION_MATRIX_SCENARIO_ID = "real_core_interruption_candidate_matrix_v1"
INTERRUPTION_EFFECT_NEGATION_SCENARIO_ID = (
    "real_core_interruption_effect_negation_v1"
)
INTERRUPTION_SEQUENCE_SCENARIO_ID = "real_core_interruption_sequence_v1"
INTERRUPTION_TIMING_SCENARIO_ID = "real_core_interruption_missed_timing_v1"
TARGET_LOSS_SCENARIO_ID = "real_core_action_aggregation_target_loss_v1"
EFFECT_VEILER_CODE = 97268402
RECOVERY_PRIMARY_CODE = 14558127
RECOVERY_CARD_CODE = 23434538
RECOVERY_TOKEN_CODE = 176393
INTERRUPTION_PRIMARY_CODE = 23434538
INTERRUPTION_TARGETLESS_HAND_CODE = 14558127
INTERRUPTION_COST_HAND_CODE = 27204311
INTERRUPTION_COST_CARD_CODE = 73642296
INTERRUPTION_FIELD_CODE = 10045474
INTERRUPTION_SUPPORT_CODE = 91800273
DUEL_SEED = (1, 2, 3, 4)
LOCATION_HAND = 0x02
LOCATION_DECK = 0x01
LOCATION_MZONE = 0x04
LOCATION_SZONE = 0x08
LOCATION_GRAVE = 0x10
LOCATION_REMOVED = 0x20
LOCATION_EXTRA = 0x40
POSITION_FACEUP_ATTACK = 0x01
POSITION_FACEDOWN_ATTACK = 0x02
POSITION_FACEUP_DEFENSE = 0x04
POSITION_FACEDOWN_DEFENSE = 0x08
WORKER_TIMEOUT_SECONDS = 30.0
WORKER_FAILURE_ENVELOPE_SCHEMA_VERSION = "real-core-worker-failure-v1"
REAL_CORE_EXPERIMENT_ID = "prototype_real_core_fixed_hand_normal_summon"
INTERRUPTION_SAMPLER_ID = "stable-digest-mod-v1"
EFFECT_VEILER_INTERRUPTION_TYPE = "effect_veiler"
TEMPORARY_ATK_FIXTURE_ID = "temporary_atk_end_phase_v1"
ACTION_AGGREGATION_FIXTURE_ID = "action_aggregation_lifecycle_v1"
ACTION_AGGREGATION_SELECTION_FIXTURE_ID = "action_aggregation_selection_edges_v1"
ACTIVATION_ROLLBACK_FIXTURE_ID = "action_activation_rollback_probe_v1"
RECOVERY_ATTRIBUTION_FIXTURE_ID = "recovery_attribution_v1"
INTERRUPTION_MATRIX_FIXTURE_ID = "interruption_candidate_matrix_v1"
INTERRUPTION_EFFECT_NEGATION_FIXTURE_ID = "interruption_effect_negation_v1"
INTERRUPTION_SEQUENCE_FIXTURE_ID = "interruption_sequence_v1"
INTERRUPTION_TIMING_FIXTURE_ID = "interruption_missed_timing_v1"
TARGET_LOSS_FIXTURE_ID = "action_aggregation_target_loss_v1"
GENERIC_INTERRUPTION_FIXTURE_IDS = frozenset(
    {
        INTERRUPTION_MATRIX_FIXTURE_ID,
        INTERRUPTION_EFFECT_NEGATION_FIXTURE_ID,
        INTERRUPTION_SEQUENCE_FIXTURE_ID,
        INTERRUPTION_TIMING_FIXTURE_ID,
        TARGET_LOSS_FIXTURE_ID,
    }
)
ACTION_AGGREGATION_FIXTURE_IDS = frozenset(
    {
        ACTION_AGGREGATION_FIXTURE_ID,
        ACTION_AGGREGATION_SELECTION_FIXTURE_ID,
        ACTIVATION_ROLLBACK_FIXTURE_ID,
    }
)
REAL_CORE_DOCUMENT_KINDS = frozenset(
    {"route", "activation_rollback_probe", "player_view", "search_frontier"}
)
REAL_CORE_FRONTIER_SCHEMA_VERSION = "real-core-frontier-v2"
REAL_CORE_PLAYER_VIEW_RESULT_SCHEMA_VERSION = "real-core-player-view-result-v2"
PLAYER_VIEW_LINEAGE_SCHEMA_VERSION = "player-view-lineage-v1"
PLAYER_VIEW_VERIFICATION_SCHEMA_VERSION = "player-view-verification-v1"
STATUS_DISABLED = 0x0001
TEMPORARY_ATK_FIXTURE_SCRIPT = """local s,id=GetID()
function s.initial_effect(c)
    local e1=Effect.CreateEffect(c)
    e1:SetType(EFFECT_TYPE_SINGLE)
    e1:SetCode(EFFECT_UPDATE_ATTACK)
    e1:SetValue(500)
    e1:SetReset(RESET_PHASE+PHASE_END)
    c:RegisterEffect(e1)
end
"""
ACTION_AGGREGATION_FIXTURE_SCRIPT = """local s,id=GetID()
function s.initial_effect(c)
    local e1=Effect.CreateEffect(c)
    e1:SetDescription(70)
    e1:SetType(EFFECT_TYPE_SINGLE+EFFECT_TYPE_TRIGGER_O)
    e1:SetCode(EVENT_SUMMON_SUCCESS)
    e1:SetProperty(EFFECT_FLAG_CARD_TARGET)
    e1:SetCountLimit(1,id)
    e1:SetCost(s.cost)
    e1:SetTarget(s.target)
    e1:SetOperation(s.operation)
    c:RegisterEffect(e1)
end
function s.cost(e,tp,eg,ep,ev,re,r,rp,chk)
    if chk==0 then
        return Duel.IsExistingMatchingCard(Card.IsDiscardable,tp,LOCATION_HAND,0,1,nil)
    end
    Duel.Hint(HINT_SELECTMSG,tp,HINTMSG_DISCARD)
    local g=Duel.SelectMatchingCard(tp,Card.IsDiscardable,tp,LOCATION_HAND,0,1,1,nil)
    Duel.SendtoGrave(g,REASON_COST+REASON_DISCARD)
end
function s.target(e,tp,eg,ep,ev,re,r,rp,chk,chkc)
    if chkc then
        return chkc:IsControler(tp) and chkc:IsLocation(LOCATION_MZONE)
    end
    if chk==0 then
        return Duel.IsExistingTarget(aux.TRUE,tp,LOCATION_MZONE,0,1,nil)
    end
    Duel.Hint(HINT_SELECTMSG,tp,HINTMSG_TARGET)
    local g=Duel.SelectTarget(tp,aux.TRUE,tp,LOCATION_MZONE,0,1,1,nil)
    Duel.SetOperationInfo(0,CATEGORY_ATKCHANGE,g,1,0,0)
    e:SetLabel(Duel.SelectOption(tp,70,71))
end
function s.operation(e,tp,eg,ep,ev,re,r,rp)
    local tc=Duel.GetFirstTarget()
    if not tc or not tc:IsRelateToEffect(e) then return end
    local e1=Effect.CreateEffect(e:GetHandler())
    e1:SetType(EFFECT_TYPE_SINGLE)
    e1:SetCode(EFFECT_UPDATE_ATTACK)
    e1:SetValue(e:GetLabel()==0 and 100 or 200)
    e1:SetReset(RESET_PHASE+PHASE_END)
    tc:RegisterEffect(e1)
end
"""
ACTION_AGGREGATION_SELECTION_FIXTURE_SCRIPT = """local s,id=GetID()
function s.initial_effect(c)
    local e1=Effect.CreateEffect(c)
    e1:SetDescription(70)
    e1:SetType(EFFECT_TYPE_SINGLE+EFFECT_TYPE_TRIGGER_O)
    e1:SetCode(EVENT_SUMMON_SUCCESS)
    e1:SetCountLimit(1,id)
    e1:SetCost(s.cost)
    e1:SetOperation(s.operation)
    c:RegisterEffect(e1)
end
function s.cost(e,tp,eg,ep,ev,re,r,rp,chk)
    if chk==0 then
        return Duel.GetMatchingGroupCount(Card.IsDiscardable,tp,LOCATION_HAND,0,nil)>=2
    end
    Duel.Hint(HINT_SELECTMSG,tp,HINTMSG_DISCARD)
    local g1=Duel.SelectMatchingCard(tp,Card.IsDiscardable,tp,LOCATION_HAND,0,1,1,nil)
    Duel.SendtoGrave(g1,REASON_COST+REASON_DISCARD)
    Duel.Hint(HINT_SELECTMSG,tp,HINTMSG_DISCARD)
    local g2=Duel.SelectMatchingCard(tp,Card.IsDiscardable,tp,LOCATION_HAND,0,1,1,nil)
    Duel.SendtoGrave(g2,REASON_COST+REASON_DISCARD)
end
function s.operation(e,tp,eg,ep,ev,re,r,rp)
    Duel.Hint(HINT_SELECTMSG,tp,HINTMSG_TARGET)
    Duel.SelectMatchingCard(tp,aux.TRUE,tp,LOCATION_GRAVE,0,1,1,nil)
    Duel.SelectOption(tp,70,71)
end
"""
ACTIVATION_ROLLBACK_FIXTURE_SCRIPT = """local s,id=GetID()
function s.initial_effect(c)
    local e1=Effect.CreateEffect(c)
    e1:SetDescription(70)
    e1:SetType(EFFECT_TYPE_SINGLE+EFFECT_TYPE_TRIGGER_O)
    e1:SetCode(EVENT_SUMMON_SUCCESS)
    e1:SetCountLimit(1,id)
    e1:SetCost(s.cost)
    e1:SetOperation(s.operation)
    c:RegisterEffect(e1)
end
function s.cost(e,tp,eg,ep,ev,re,r,rp,chk)
    if chk==0 then
        return Duel.IsExistingMatchingCard(Card.IsDiscardable,tp,LOCATION_HAND,0,1,e:GetHandler())
    end
    Duel.Hint(HINT_SELECTMSG,tp,HINTMSG_DISCARD)
    local g=Duel.SelectMatchingCard(tp,Card.IsDiscardable,tp,LOCATION_HAND,0,1,1,true,e:GetHandler())
    if not g then return end
    Duel.SendtoGrave(g,REASON_COST+REASON_DISCARD)
end
function s.operation(e,tp,eg,ep,ev,re,r,rp)
end
"""
RECOVERY_PRIMARY_FIXTURE_SCRIPT = f"""local s,id=GetID()
function s.initial_effect(c)
    local e1=Effect.CreateEffect(c)
    e1:SetDescription(70)
    e1:SetType(EFFECT_TYPE_SINGLE+EFFECT_TYPE_TRIGGER_O)
    e1:SetCode(EVENT_SUMMON_SUCCESS)
    e1:SetCountLimit(1,id)
    e1:SetOperation(s.operation)
    c:RegisterEffect(e1)
end
function s.operation(e,tp,eg,ep,ev,re,r,rp)
    if Duel.GetLocationCount(tp,LOCATION_MZONE)<=0 then return end
    local token=Duel.CreateToken(tp,{RECOVERY_TOKEN_CODE})
    Duel.SpecialSummon(token,0,tp,tp,false,false,POS_FACEUP_ATTACK)
end
"""
RECOVERY_CARD_FIXTURE_SCRIPT = """local s,id=GetID()
function s.initial_effect(c)
    local e1=Effect.CreateEffect(c)
    e1:SetDescription(70)
    e1:SetType(EFFECT_TYPE_FIELD+EFFECT_TYPE_TRIGGER_O)
    e1:SetCode(EVENT_CHAIN_END)
    e1:SetRange(LOCATION_HAND)
    e1:SetCountLimit(1,id)
    e1:SetCondition(s.condition)
    e1:SetOperation(s.operation)
    c:RegisterEffect(e1)
end
function s.condition(e,tp,eg,ep,ev,re,r,rp)
    return Duel.IsExistingMatchingCard(Card.IsDisabled,tp,LOCATION_MZONE,0,1,nil)
end
function s.operation(e,tp,eg,ep,ev,re,r,rp)
    local c=e:GetHandler()
    if c:IsRelateToEffect(e) and Duel.GetLocationCount(tp,LOCATION_MZONE)>0 then
        Duel.SpecialSummon(c,0,tp,tp,false,false,POS_FACEUP_ATTACK)
    end
end
"""
INTERRUPTION_PRIMARY_FIXTURE_SCRIPT = """local s,id=GetID()
function s.initial_effect(c)
    local e1=Effect.CreateEffect(c)
    e1:SetDescription(70)
    e1:SetType(EFFECT_TYPE_SINGLE+EFFECT_TYPE_TRIGGER_O)
    e1:SetCode(EVENT_SUMMON_SUCCESS)
    e1:SetCountLimit(1,id)
    e1:SetOperation(s.operation)
    c:RegisterEffect(e1)
end
function s.operation(e,tp,eg,ep,ev,re,r,rp)
end
"""
INTERRUPTION_TARGETLESS_HAND_FIXTURE_SCRIPT = """local s,id=GetID()
function s.initial_effect(c)
    local e1=Effect.CreateEffect(c)
    e1:SetDescription(70)
    e1:SetType(EFFECT_TYPE_FIELD+EFFECT_TYPE_QUICK_O)
    e1:SetCode(EVENT_CHAINING)
    e1:SetRange(LOCATION_HAND)
    e1:SetCountLimit(1,id)
    e1:SetCondition(s.condition)
    e1:SetCost(s.cost)
    e1:SetOperation(s.operation)
    c:RegisterEffect(e1)
end
function s.condition(e,tp,eg,ep,ev,re,r,rp)
    return rp==1-tp and re:IsActiveType(TYPE_MONSTER)
end
function s.cost(e,tp,eg,ep,ev,re,r,rp,chk)
    local c=e:GetHandler()
    if chk==0 then return c:IsAbleToGraveAsCost() end
    Duel.SendtoGrave(c,REASON_COST)
end
function s.operation(e,tp,eg,ep,ev,re,r,rp)
    Duel.NegateActivation(ev)
end
"""
INTERRUPTION_COST_HAND_FIXTURE_SCRIPT = """local s,id=GetID()
function s.initial_effect(c)
    local e1=Effect.CreateEffect(c)
    e1:SetDescription(70)
    e1:SetType(EFFECT_TYPE_FIELD+EFFECT_TYPE_QUICK_O)
    e1:SetCode(EVENT_CHAINING)
    e1:SetRange(LOCATION_HAND)
    e1:SetCountLimit(1,id)
    e1:SetCondition(s.condition)
    e1:SetCost(s.cost)
    e1:SetOperation(s.operation)
    c:RegisterEffect(e1)
end
function s.condition(e,tp,eg,ep,ev,re,r,rp)
    return rp==1-tp and re:IsActiveType(TYPE_MONSTER)
end
function s.cost(e,tp,eg,ep,ev,re,r,rp,chk)
    if chk==0 then
        return Duel.IsExistingMatchingCard(Card.IsDiscardable,tp,LOCATION_HAND,0,1,e:GetHandler())
    end
    Duel.Hint(HINT_SELECTMSG,tp,HINTMSG_DISCARD)
    local g=Duel.SelectMatchingCard(tp,Card.IsDiscardable,tp,LOCATION_HAND,0,1,1,e:GetHandler())
    Duel.SendtoGrave(g,REASON_COST+REASON_DISCARD)
end
function s.operation(e,tp,eg,ep,ev,re,r,rp)
    Duel.NegateActivation(ev)
end
"""
INTERRUPTION_EFFECT_NEGATION_HAND_FIXTURE_SCRIPT = """local s,id=GetID()
function s.initial_effect(c)
    local e1=Effect.CreateEffect(c)
    e1:SetDescription(70)
    e1:SetType(EFFECT_TYPE_FIELD+EFFECT_TYPE_QUICK_O)
    e1:SetCode(EVENT_CHAINING)
    e1:SetRange(LOCATION_HAND)
    e1:SetCountLimit(1,id)
    e1:SetCondition(s.condition)
    e1:SetCost(s.cost)
    e1:SetOperation(s.operation)
    c:RegisterEffect(e1)
end
function s.condition(e,tp,eg,ep,ev,re,r,rp)
    return rp==1-tp and re:IsActiveType(TYPE_MONSTER)
end
function s.cost(e,tp,eg,ep,ev,re,r,rp,chk)
    local c=e:GetHandler()
    if chk==0 then return c:IsAbleToGraveAsCost() end
    Duel.SendtoGrave(c,REASON_COST)
end
function s.operation(e,tp,eg,ep,ev,re,r,rp)
    Duel.NegateEffect(ev)
end
"""
INTERRUPTION_FIELD_FIXTURE_SCRIPT = """local s,id=GetID()
function s.initial_effect(c)
    local e1=Effect.CreateEffect(c)
    e1:SetDescription(70)
    e1:SetType(EFFECT_TYPE_FIELD+EFFECT_TYPE_QUICK_O)
    e1:SetCode(EVENT_CHAINING)
    e1:SetRange(LOCATION_SZONE)
    e1:SetProperty(EFFECT_FLAG_CARD_TARGET)
    e1:SetCountLimit(1,id)
    e1:SetCondition(s.condition)
    e1:SetTarget(s.target)
    e1:SetOperation(s.operation)
    c:RegisterEffect(e1)
end
function s.condition(e,tp,eg,ep,ev,re,r,rp)
    return rp==1-tp and re:IsActiveType(TYPE_MONSTER)
end
function s.target(e,tp,eg,ep,ev,re,r,rp,chk,chkc)
    if chkc then
        return chkc:IsControler(1-tp) and chkc:IsLocation(LOCATION_MZONE)
    end
    if chk==0 then
        return Duel.IsExistingTarget(Card.IsFaceup,tp,0,LOCATION_MZONE,2,nil)
    end
    Duel.Hint(HINT_SELECTMSG,tp,HINTMSG_FACEUP)
    Duel.SelectTarget(tp,Card.IsFaceup,tp,0,LOCATION_MZONE,2,2,nil)
end
function s.operation(e,tp,eg,ep,ev,re,r,rp)
    local g=Duel.GetTargetCards(e)
    for tc in aux.Next(g) do
        local e1=Effect.CreateEffect(e:GetHandler())
        e1:SetType(EFFECT_TYPE_SINGLE)
        e1:SetCode(EFFECT_DISABLE)
        e1:SetReset(RESET_EVENT+RESETS_STANDARD+RESET_PHASE+PHASE_END)
        tc:RegisterEffect(e1)
    end
end
"""
INTERRUPTION_BLANK_FIXTURE_SCRIPT = """local s,id=GetID()
function s.initial_effect(c)
end
"""
INTERRUPTION_SECONDARY_FIXTURE_SCRIPT = """local s,id=GetID()
function s.initial_effect(c)
    local e1=Effect.CreateEffect(c)
    e1:SetDescription(70)
    e1:SetType(EFFECT_TYPE_FIELD+EFFECT_TYPE_TRIGGER_O)
    e1:SetCode(EVENT_CHAIN_END)
    e1:SetRange(LOCATION_MZONE)
    e1:SetCountLimit(1,id)
    e1:SetCondition(s.condition)
    e1:SetOperation(s.operation)
    c:RegisterEffect(e1)
end
function s.condition(e,tp,eg,ep,ev,re,r,rp)
    return Duel.GetTurnPlayer()==tp
end
function s.operation(e,tp,eg,ep,ev,re,r,rp)
end
"""
INTERRUPTION_MISSED_TRIGGER_FIXTURE_SCRIPT = """local s,id=GetID()
function s.initial_effect(c)
    local e1=Effect.CreateEffect(c)
    e1:SetDescription(70)
    e1:SetType(EFFECT_TYPE_SINGLE+EFFECT_TYPE_TRIGGER_O)
    e1:SetCode(EVENT_TO_GRAVE)
    e1:SetCountLimit(1,id)
    e1:SetOperation(s.operation)
    c:RegisterEffect(e1)
end
function s.operation(e,tp,eg,ep,ev,re,r,rp)
end
"""
INTERRUPTION_TIMING_FIELD_FIXTURE_SCRIPT = f"""local s,id=GetID()
function s.initial_effect(c)
    local e1=Effect.CreateEffect(c)
    e1:SetDescription(70)
    e1:SetType(EFFECT_TYPE_FIELD+EFFECT_TYPE_QUICK_O)
    e1:SetCode(EVENT_CHAINING)
    e1:SetRange(LOCATION_SZONE)
    e1:SetCountLimit(1,id)
    e1:SetCondition(s.condition)
    e1:SetTarget(s.target)
    e1:SetOperation(s.operation)
    c:RegisterEffect(e1)
end
function s.condition(e,tp,eg,ep,ev,re,r,rp)
    return rp==1-tp and re:IsActiveType(TYPE_MONSTER)
end
function s.filter(c)
    return c:IsFaceup() and c:IsCode({INTERRUPTION_SUPPORT_CODE})
        and c:IsAbleToGrave()
end
function s.target(e,tp,eg,ep,ev,re,r,rp,chk)
    if chk==0 then
        return Duel.IsExistingMatchingCard(
            s.filter,tp,0,LOCATION_MZONE,1,nil)
    end
end
function s.operation(e,tp,eg,ep,ev,re,r,rp)
    local tc=Duel.GetFirstMatchingCard(
        s.filter,tp,0,LOCATION_MZONE,nil)
    if tc then Duel.SendtoGrave(tc,REASON_EFFECT) end
end
"""
TARGET_LOSS_PRIMARY_FIXTURE_SCRIPT = f"""local s,id=GetID()
function s.initial_effect(c)
    local e1=Effect.CreateEffect(c)
    e1:SetDescription(70)
    e1:SetType(EFFECT_TYPE_SINGLE+EFFECT_TYPE_TRIGGER_O)
    e1:SetCode(EVENT_SUMMON_SUCCESS)
    e1:SetProperty(EFFECT_FLAG_CARD_TARGET)
    e1:SetCountLimit(1,id)
    e1:SetTarget(s.target)
    e1:SetOperation(s.operation)
    c:RegisterEffect(e1)
end
function s.filter(c)
    return c:IsFaceup() and c:IsCode({INTERRUPTION_SUPPORT_CODE})
end
function s.target(e,tp,eg,ep,ev,re,r,rp,chk,chkc)
    if chkc then
        return chkc:IsControler(tp) and chkc:IsLocation(LOCATION_MZONE) and s.filter(chkc)
    end
    if chk==0 then
        return Duel.IsExistingTarget(s.filter,tp,LOCATION_MZONE,0,1,nil)
    end
    Duel.Hint(HINT_SELECTMSG,tp,HINTMSG_TARGET)
    Duel.SelectTarget(tp,s.filter,tp,LOCATION_MZONE,0,1,1,nil)
end
function s.operation(e,tp,eg,ep,ev,re,r,rp)
    local tc=Duel.GetFirstTarget()
    if not tc or not tc:IsRelateToEffect(e) then return end
    local e1=Effect.CreateEffect(e:GetHandler())
    e1:SetType(EFFECT_TYPE_SINGLE)
    e1:SetCode(EFFECT_UPDATE_ATTACK)
    e1:SetValue(100)
    e1:SetReset(RESET_EVENT+RESETS_STANDARD+RESET_PHASE+PHASE_END)
    tc:RegisterEffect(e1)
end
"""
TARGET_LOSS_FIELD_FIXTURE_SCRIPT = f"""local s,id=GetID()
function s.initial_effect(c)
    local e1=Effect.CreateEffect(c)
    e1:SetDescription(70)
    e1:SetType(EFFECT_TYPE_FIELD+EFFECT_TYPE_QUICK_O)
    e1:SetCode(EVENT_CHAINING)
    e1:SetRange(LOCATION_SZONE)
    e1:SetProperty(EFFECT_FLAG_CARD_TARGET)
    e1:SetCountLimit(1,id)
    e1:SetCondition(s.condition)
    e1:SetTarget(s.target)
    e1:SetOperation(s.operation)
    c:RegisterEffect(e1)
end
function s.condition(e,tp,eg,ep,ev,re,r,rp)
    return rp==1-tp and re:IsActiveType(TYPE_MONSTER)
end
function s.filter(c)
    return c:IsFaceup() and c:IsCode({INTERRUPTION_SUPPORT_CODE}) and c:IsAbleToRemove()
end
function s.target(e,tp,eg,ep,ev,re,r,rp,chk,chkc)
    if chkc then
        return chkc:IsControler(1-tp) and chkc:IsLocation(LOCATION_MZONE) and s.filter(chkc)
    end
    if chk==0 then
        return Duel.IsExistingTarget(s.filter,tp,0,LOCATION_MZONE,1,nil)
    end
    Duel.Hint(HINT_SELECTMSG,tp,HINTMSG_REMOVE)
    Duel.SelectTarget(tp,s.filter,tp,0,LOCATION_MZONE,1,1,nil)
end
function s.operation(e,tp,eg,ep,ev,re,r,rp)
    local tc=Duel.GetFirstTarget()
    if tc and tc:IsRelateToEffect(e) then
        Duel.Remove(tc,POS_FACEUP,REASON_EFFECT)
    end
end
"""
REAL_CORE_EVALUATOR = {
    "id": "real_core_board_count",
    "version": "1",
    "config": {
        "hand_weight": 1,
        "missing_value_policy": "error",
        "monster_weight": 10,
        "temporary_value_policy": "exclude_expired_or_unverified_v1",
    },
}
_EVALUATORS = build_default_evaluator_registry()


@dataclass(frozen=True)
class RealCoreWorkerProcessResult:
    document: dict[str, Any] | None
    process_id: int
    returncode: int
    timed_out: bool
    terminated: bool
    failure_category: str | None
    stdout_digest: str
    stderr_digest: str
    diagnostic: str
    failure_record: FailureRecord | None = None

    @property
    def succeeded(self) -> bool:
        return self.document is not None and self.failure_category is None

    def to_evidence_dict(self) -> dict[str, Any]:
        diagnostic_lines = self.diagnostic.splitlines()
        evidence = {
            "diagnostic_tail": diagnostic_lines[-1] if diagnostic_lines else "",
            "failure_category": self.failure_category,
            "process_id": self.process_id,
            "returncode": self.returncode,
            "stderr_digest": self.stderr_digest,
            "stdout_digest": self.stdout_digest,
            "terminated": self.terminated,
            "timed_out": self.timed_out,
        }
        if self.failure_record is not None:
            evidence["failure"] = self.failure_record.to_dict()
        return evidence


@dataclass(frozen=True)
class _InterruptionPlan:
    mode: str
    definition: Mapping[str, Any]
    definition_index: int
    target: InterruptionTarget
    base_route_id: str
    sampling_evidence: Mapping[str, Any] | None
    candidate_policy: CoreInterruptionCandidatePolicy
    explicit_candidate_policy: bool


@dataclass
class _InterruptionExecution:
    plan: _InterruptionPlan
    activated: bool = False
    activation_step: int | None = None
    response_index: int = 0
    target_selection_step: int | None = None
    response_steps: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class _OpeningHandPlan:
    hands: Mapping[str, list[int]]
    snapshot_kind: str
    sampling_evidence: Mapping[str, Any] | None = None


def _resolve_opening_hand_plan(
    policy: InformationAccessPolicy,
    default_hands: Mapping[str, list[int]],
) -> _OpeningHandPlan:
    hands = {player: list(cards) for player, cards in default_hands.items()}
    if policy.information_mode == InformationMode.COMPLETE_INFORMATION:
        return _OpeningHandPlan(
            hands=to_canonical_data(hands),
            snapshot_kind=InformationMode.COMPLETE_INFORMATION.value,
        )
    if policy.information_mode != InformationMode.SAMPLED_PRIVATE_STATE:
        raise ValueError(
            "real-core prototype does not emit PlayerView Replay traces"
        )
    reference = policy.sampling_reference
    assert isinstance(reference, Mapping)
    sampling_evidence = build_opening_hand_sampling_evidence(
        reference,
        information_policy_id=str(policy.to_dict()["policy_id"]),
    )
    result = sampling_evidence["result"]
    for player, hand in result["hands_by_player"].items():
        hands[str(player)] = list(hand)
    return _OpeningHandPlan(
        hands=to_canonical_data(hands),
        snapshot_kind=InformationMode.SAMPLED_PRIVATE_STATE.value,
        sampling_evidence=sampling_evidence,
    )


class _StressFailingCardDataProvider:
    def get_card(self, code: int) -> Any:
        raise RuntimeError(f"stress-injected DataReader failure for card {code}")


class _FixtureScriptProvider:
    def __init__(self, delegate: Any, card_scripts: Mapping[int, bytes]) -> None:
        self.delegate = delegate
        self.card_scripts = dict(card_scripts)

    def get_script(self, name: str) -> bytes:
        return self.resolve_script(name).content

    @property
    def script_resolution_profile_id(self) -> str:
        return str(
            getattr(
                self.delegate,
                "script_resolution_profile_id",
                "custom-script-provider-v1",
            )
        )

    def resolve_script(self, name: str) -> ResolvedScript:
        basename = name.replace("\\", "/").rsplit("/", 1)[-1]
        for code, script in self.card_scripts.items():
            if basename == f"c{code}.lua":
                return ResolvedScript.from_bytes(
                    requested_name=name,
                    resolved_path=f"fixture/{basename}",
                    source_kind="fixture",
                    content=script,
                )
        return resolve_script(self.delegate, name)


def _interruption_error(path: str, message: str) -> ValueError:
    return ValueError(f"{path}: {message}")


def _validate_interruption_definition(
    value: Any,
    index: int,
    *,
    legacy_target_card_code: int,
) -> tuple[
    Mapping[str, Any],
    InterruptionTarget,
    str,
    CoreInterruptionCandidatePolicy,
    bool,
]:
    path = f"$.interruption.definitions[{index}]"
    if not isinstance(value, Mapping):
        raise _interruption_error(path, "must be a mapping")
    definition_id = value.get("id")
    if not isinstance(definition_id, str) or not definition_id:
        raise _interruption_error(f"{path}.id", "must be a non-empty string")
    interruption_type = value.get("interruption_type")
    if not isinstance(interruption_type, str) or not interruption_type:
        raise _interruption_error(
            f"{path}.interruption_type", "must be a non-empty string"
        )
    source_player = value.get("source_player")
    if source_player not in {0, 1} or isinstance(source_player, bool):
        raise _interruption_error(
            f"{path}.source_player", "must be player 0 or 1"
        )
    source_card_code = value.get("source_card_code")
    if (
        not isinstance(source_card_code, int)
        or isinstance(source_card_code, bool)
        or source_card_code <= 0
    ):
        raise _interruption_error(
            f"{path}.source_card_code", "must be a positive card code"
        )
    raw_candidate_policy = value.get("candidate_policy")
    explicit_candidate_policy = raw_candidate_policy is not None
    if raw_candidate_policy is None:
        if interruption_type != EFFECT_VEILER_INTERRUPTION_TYPE:
            raise _interruption_error(
                f"{path}.interruption_type",
                f"unsupported interruption type {interruption_type!r} without "
                "an explicit candidate_policy",
            )
        if source_player != 1:
            raise _interruption_error(
                f"{path}.source_player",
                "Effect Veiler legacy adapter requires source_player 1",
            )
        if source_card_code != EFFECT_VEILER_CODE:
            raise _interruption_error(
                f"{path}.source_card_code",
                f"Effect Veiler legacy adapter requires card code {EFFECT_VEILER_CODE}",
            )
        candidate_policy = CoreInterruptionCandidatePolicy.targeted_hand_activation(
            source_player=source_player,
            source_card_code=source_card_code,
            target_player=0,
            target_card_code=legacy_target_card_code,
        )
    else:
        try:
            candidate_policy = CoreInterruptionCandidatePolicy.from_dict(
                raw_candidate_policy,
                path=f"{path}.candidate_policy",
            )
        except InterruptionCandidatePolicyError as exc:
            raise _interruption_error(exc.path, str(exc).split(": ", 1)[-1]) from exc
        activation = candidate_policy.activation
        activation_card_ref = activation.selector.card_ref
        if activation.player != source_player:
            raise _interruption_error(
                f"{path}.candidate_policy.activation.player",
                "must match definition.source_player",
            )
        if not isinstance(activation_card_ref, Mapping):
            raise _interruption_error(
                f"{path}.candidate_policy.activation.selector.card_ref",
                "must identify the source card",
            )
        if activation_card_ref.get("controller") != source_player:
            raise _interruption_error(
                f"{path}.candidate_policy.activation.selector.card_ref.controller",
                "must match definition.source_player",
            )
        if activation_card_ref.get("public_card_id") != source_card_code:
            raise _interruption_error(
                f"{path}.candidate_policy.activation.selector.card_ref.public_card_id",
                "must match definition.source_card_code",
            )
    base_route_id = value.get("base_route_id")
    if not isinstance(base_route_id, str) or not base_route_id.startswith("route_"):
        raise _interruption_error(f"{path}.base_route_id", "must be a Route ID")
    try:
        target = InterruptionTarget.from_dict(value.get("target"))
    except (TypeError, ValueError) as exc:
        raise _interruption_error(f"{path}.target", str(exc)) from exc
    return (
        to_canonical_data(value),
        target,
        base_route_id,
        candidate_policy,
        explicit_candidate_policy,
    )


def _resolve_interruption_plans(
    experiment: Mapping[str, Any],
) -> tuple[_InterruptionPlan, ...]:
    interruption = experiment.get("interruption")
    if not isinstance(interruption, Mapping):
        raise _interruption_error("$.interruption", "must be a mapping")
    mode = interruption.get("mode")
    raw_definitions = interruption.get("definitions")
    if not isinstance(raw_definitions, list):
        raise _interruption_error("$.interruption.definitions", "must be a list")
    if mode == "none":
        return ()
    if mode not in {"scripted", "sampled"}:
        raise _interruption_error("$.interruption.mode", "must be none, scripted, or sampled")
    if not raw_definitions:
        raise _interruption_error(
            "$.interruption.definitions",
            f"must contain at least one definition for {mode} mode",
        )
    fixture_script_id = _fixture_script_id(experiment)
    legacy_target_card_code = (
        RECOVERY_PRIMARY_CODE
        if fixture_script_id == RECOVERY_ATTRIBUTION_FIXTURE_ID
        else EFFECT_VEILER_CODE
    )
    validated_definitions = [
        _validate_interruption_definition(
            definition,
            index,
            legacy_target_card_code=legacy_target_card_code,
        )
        for index, definition in enumerate(raw_definitions)
    ]
    definition_ids = [
        str(definition[0]["id"]) for definition in validated_definitions
    ]
    if len(set(definition_ids)) != len(definition_ids):
        raise _interruption_error(
            "$.interruption.definitions", "definition ids must be unique"
        )

    sampling_evidence: Mapping[str, Any] | None = None
    if mode == "scripted":
        if (
            len(raw_definitions) > 1
            and fixture_script_id
            not in {
                INTERRUPTION_SEQUENCE_FIXTURE_ID,
                INTERRUPTION_TIMING_FIXTURE_ID,
            }
        ):
            raise _interruption_error(
                "$.interruption.definitions",
                "multiple real-core scripted definitions require "
                "a staged interruption fixture",
            )
        if len(validated_definitions) > 1 and any(
            not definition[4] for definition in validated_definitions
        ):
            raise _interruption_error(
                "$.interruption.definitions",
                "multiple scripted interruptions require explicit candidate policies",
            )
        for index in range(1, len(validated_definitions)):
            previous = validated_definitions[index - 1]
            current = validated_definitions[index]
            if current[1].step <= previous[1].step:
                raise _interruption_error(
                    f"$.interruption.definitions[{index}].target.step",
                    "must be greater than the previous interruption target step",
                )
            if current[2] == previous[2]:
                raise _interruption_error(
                    f"$.interruption.definitions[{index}].base_route_id",
                    "must reference the previous staged Route, not the same parent",
                )
        selected_indexes = tuple(range(len(validated_definitions)))
        if "sampling" in interruption:
            raise _interruption_error(
                "$.interruption.sampling", "is only valid for sampled mode"
            )
    else:
        sampling = interruption.get("sampling")
        if not isinstance(sampling, Mapping):
            raise _interruption_error(
                "$.interruption.sampling", "must be a mapping for sampled mode"
            )
        if sampling.get("schema_version") != INTERRUPTION_SAMPLING_SCHEMA_VERSION:
            raise _interruption_error(
                "$.interruption.sampling.schema_version",
                f"must be {INTERRUPTION_SAMPLING_SCHEMA_VERSION!r}",
            )
        if sampling.get("sampler_id") != INTERRUPTION_SAMPLER_ID:
            raise _interruption_error(
                "$.interruption.sampling.sampler_id",
                f"must be {INTERRUPTION_SAMPLER_ID!r}",
            )
        seed = sampling.get("seed")
        if not isinstance(seed, int) or isinstance(seed, bool) or seed < 0:
            raise _interruption_error(
                "$.interruption.sampling.seed", "must be an integer >= 0"
            )
        sample_identity = to_canonical_data(
            {
                "definition_ids": definition_ids,
                "sampler_id": INTERRUPTION_SAMPLER_ID,
                "schema_version": INTERRUPTION_SAMPLING_SCHEMA_VERSION,
                "seed": seed,
            }
        )
        sample_digest = stable_digest(sample_identity, prefix="intsample_")
        definition_index = int(sample_digest.removeprefix("intsample_"), 16) % len(
            raw_definitions
        )
        selected_indexes = (definition_index,)
        sampling_evidence = {
            **sample_identity,
            "sample_id": sample_digest,
            "selected_definition_id": definition_ids[definition_index],
            "selected_index": definition_index,
        }

    return tuple(
        _InterruptionPlan(
            mode=str(mode),
            definition=to_canonical_data(validated_definitions[index][0]),
            definition_index=index,
            target=validated_definitions[index][1],
            base_route_id=validated_definitions[index][2],
            sampling_evidence=sampling_evidence,
            candidate_policy=validated_definitions[index][3],
            explicit_candidate_policy=validated_definitions[index][4],
        )
        for index in selected_indexes
    )


def _default_real_experiment() -> dict[str, Any]:
    information_policy = InformationAccessPolicy(
        information_mode="complete_information",
        deck_order=DeckOrderKnowledge.KNOWN,
        opening_hand=OpeningHandPolicy.FIXED,
    )
    return {
        "schema_version": "0.3b",
        "experiment_id": REAL_CORE_EXPERIMENT_ID,
        "objective": "fixed_hand_runtime_slice",
        "deck": {
            "id": "effect_veiler_two_player_fixture",
            "source": "fixed",
        },
        "player": {"perspective": 0, "starting_player": 0},
        "turn_limit": 2,
        "information_mode": "complete_information",
        "information_policy": information_policy.to_experiment_dict(),
        "evaluate_at": "legal_stop",
        "durability_evaluate_at": DURABLE_EVALUATION_TIMING,
        "success_predicate": {
            "id": "real_core_min_monster_count",
            "version": "1",
            "config": {"player": 0, "zone": "monster_zone", "min_count": 1},
        },
        "evaluator": {
            **REAL_CORE_EVALUATOR,
            "config": dict(REAL_CORE_EVALUATOR["config"]),
        },
        "search": {"strategy": "scripted_real_core", "budget": {"max_nodes": 16}},
        "interruption": {"definitions": [], "mode": "none"},
        "replay": {"strict_versions": True},
    }


def _fixture_script_id(experiment: Mapping[str, Any]) -> str | None:
    runner = experiment.get("runner")
    if not isinstance(runner, Mapping):
        return None
    value = runner.get("fixture_script_id")
    if value is None:
        return None
    if value not in {
        TEMPORARY_ATK_FIXTURE_ID,
        ACTION_AGGREGATION_FIXTURE_ID,
        ACTION_AGGREGATION_SELECTION_FIXTURE_ID,
        ACTIVATION_ROLLBACK_FIXTURE_ID,
        RECOVERY_ATTRIBUTION_FIXTURE_ID,
        INTERRUPTION_MATRIX_FIXTURE_ID,
        INTERRUPTION_EFFECT_NEGATION_FIXTURE_ID,
        INTERRUPTION_SEQUENCE_FIXTURE_ID,
        INTERRUPTION_TIMING_FIXTURE_ID,
        TARGET_LOSS_FIXTURE_ID,
    }:
        raise ValueError(f"unsupported runner.fixture_script_id {value!r}")
    return str(value)


def _fixture_scripts(fixture_script_id: str | None) -> dict[int, bytes]:
    source_by_code: dict[int, str] = {}
    if fixture_script_id == TEMPORARY_ATK_FIXTURE_ID:
        source_by_code = {EFFECT_VEILER_CODE: TEMPORARY_ATK_FIXTURE_SCRIPT}
    elif fixture_script_id == ACTION_AGGREGATION_FIXTURE_ID:
        source_by_code = {EFFECT_VEILER_CODE: ACTION_AGGREGATION_FIXTURE_SCRIPT}
    elif fixture_script_id == ACTION_AGGREGATION_SELECTION_FIXTURE_ID:
        source_by_code = {
            EFFECT_VEILER_CODE: ACTION_AGGREGATION_SELECTION_FIXTURE_SCRIPT
        }
    elif fixture_script_id == ACTIVATION_ROLLBACK_FIXTURE_ID:
        source_by_code = {
            EFFECT_VEILER_CODE: ACTIVATION_ROLLBACK_FIXTURE_SCRIPT
        }
    elif fixture_script_id == RECOVERY_ATTRIBUTION_FIXTURE_ID:
        source_by_code = {
            RECOVERY_PRIMARY_CODE: RECOVERY_PRIMARY_FIXTURE_SCRIPT,
            RECOVERY_CARD_CODE: RECOVERY_CARD_FIXTURE_SCRIPT,
            RECOVERY_TOKEN_CODE: "",
        }
    elif fixture_script_id == INTERRUPTION_MATRIX_FIXTURE_ID:
        source_by_code = {
            INTERRUPTION_PRIMARY_CODE: INTERRUPTION_PRIMARY_FIXTURE_SCRIPT,
            INTERRUPTION_TARGETLESS_HAND_CODE: (
                INTERRUPTION_TARGETLESS_HAND_FIXTURE_SCRIPT
            ),
            INTERRUPTION_COST_HAND_CODE: INTERRUPTION_COST_HAND_FIXTURE_SCRIPT,
            INTERRUPTION_COST_CARD_CODE: INTERRUPTION_BLANK_FIXTURE_SCRIPT,
            INTERRUPTION_FIELD_CODE: INTERRUPTION_FIELD_FIXTURE_SCRIPT,
            INTERRUPTION_SUPPORT_CODE: INTERRUPTION_BLANK_FIXTURE_SCRIPT,
        }
    elif fixture_script_id == INTERRUPTION_EFFECT_NEGATION_FIXTURE_ID:
        source_by_code = {
            INTERRUPTION_PRIMARY_CODE: INTERRUPTION_PRIMARY_FIXTURE_SCRIPT,
            INTERRUPTION_TARGETLESS_HAND_CODE: (
                INTERRUPTION_EFFECT_NEGATION_HAND_FIXTURE_SCRIPT
            ),
            INTERRUPTION_COST_HAND_CODE: INTERRUPTION_COST_HAND_FIXTURE_SCRIPT,
            INTERRUPTION_COST_CARD_CODE: INTERRUPTION_BLANK_FIXTURE_SCRIPT,
            INTERRUPTION_FIELD_CODE: INTERRUPTION_FIELD_FIXTURE_SCRIPT,
            INTERRUPTION_SUPPORT_CODE: INTERRUPTION_BLANK_FIXTURE_SCRIPT,
        }
    elif fixture_script_id == INTERRUPTION_SEQUENCE_FIXTURE_ID:
        source_by_code = {
            INTERRUPTION_PRIMARY_CODE: INTERRUPTION_PRIMARY_FIXTURE_SCRIPT,
            INTERRUPTION_TARGETLESS_HAND_CODE: (
                INTERRUPTION_TARGETLESS_HAND_FIXTURE_SCRIPT
            ),
            INTERRUPTION_COST_HAND_CODE: INTERRUPTION_COST_HAND_FIXTURE_SCRIPT,
            INTERRUPTION_COST_CARD_CODE: INTERRUPTION_BLANK_FIXTURE_SCRIPT,
            INTERRUPTION_FIELD_CODE: INTERRUPTION_FIELD_FIXTURE_SCRIPT,
            INTERRUPTION_SUPPORT_CODE: INTERRUPTION_SECONDARY_FIXTURE_SCRIPT,
        }
    elif fixture_script_id == INTERRUPTION_TIMING_FIXTURE_ID:
        source_by_code = {
            INTERRUPTION_PRIMARY_CODE: INTERRUPTION_PRIMARY_FIXTURE_SCRIPT,
            INTERRUPTION_SUPPORT_CODE: (
                INTERRUPTION_MISSED_TRIGGER_FIXTURE_SCRIPT
            ),
            INTERRUPTION_FIELD_CODE: INTERRUPTION_TIMING_FIELD_FIXTURE_SCRIPT,
        }
    elif fixture_script_id == TARGET_LOSS_FIXTURE_ID:
        source_by_code = {
            INTERRUPTION_PRIMARY_CODE: TARGET_LOSS_PRIMARY_FIXTURE_SCRIPT,
            INTERRUPTION_FIELD_CODE: TARGET_LOSS_FIELD_FIXTURE_SCRIPT,
            INTERRUPTION_SUPPORT_CODE: INTERRUPTION_BLANK_FIXTURE_SCRIPT,
        }
    return {code: source.encode("utf-8") for code, source in source_by_code.items()}


def _fixture_script_bytes(fixture_script_id: str | None) -> bytes | None:
    scripts = _fixture_scripts(fixture_script_id)
    if not scripts:
        return None
    if fixture_script_id in {
        TEMPORARY_ATK_FIXTURE_ID,
        *ACTION_AGGREGATION_FIXTURE_IDS,
    }:
        return scripts[EFFECT_VEILER_CODE]
    return b"".join(
        f"c{code}.lua\0".encode("ascii") + scripts[code]
        for code in sorted(scripts)
    )


def _fixture_script_metadata(
    fixture_script_id: str | None,
    fixture_script_bytes: bytes | None,
) -> dict[str, Any] | None:
    if fixture_script_id is None or fixture_script_bytes is None:
        return None
    metadata: dict[str, Any] = {
        "id": fixture_script_id,
        "name": f"c{EFFECT_VEILER_CODE}.lua",
        "sha256": hashlib.sha256(fixture_script_bytes).hexdigest(),
    }
    if fixture_script_id == TEMPORARY_ATK_FIXTURE_ID:
        metadata["reset_expression"] = "RESET_PHASE+PHASE_END"
    elif fixture_script_id in ACTION_AGGREGATION_FIXTURE_IDS:
        metadata["purpose"] = {
            ACTION_AGGREGATION_FIXTURE_ID: "cost_target_option_action_aggregation",
            ACTION_AGGREGATION_SELECTION_FIXTURE_ID: (
                "repeated_cost_and_resolution_selection_action_aggregation"
            ),
            ACTIVATION_ROLLBACK_FIXTURE_ID: (
                "native_activation_setup_cancellation_probe"
            ),
        }[fixture_script_id]
    elif fixture_script_id == RECOVERY_ATTRIBUTION_FIXTURE_ID:
        scripts = _fixture_scripts(fixture_script_id)
        metadata["name"] = "multiple"
        metadata["purpose"] = "additional_card_counterfactual_recovery"
        metadata["scripts"] = [
            {
                "card_code": code,
                "name": f"c{code}.lua",
                "sha256": hashlib.sha256(scripts[code]).hexdigest(),
            }
            for code in sorted(scripts)
        ]
    elif fixture_script_id == TARGET_LOSS_FIXTURE_ID:
        scripts = _fixture_scripts(fixture_script_id)
        metadata["name"] = "multiple"
        metadata["purpose"] = "target_loss_fizzle_action_aggregation"
        metadata["scripts"] = [
            {
                "card_code": code,
                "name": f"c{code}.lua",
                "sha256": hashlib.sha256(scripts[code]).hexdigest(),
            }
            for code in sorted(scripts)
        ]
    else:
        scripts = _fixture_scripts(fixture_script_id)
        metadata["name"] = "multiple"
        metadata["purpose"] = "generic_core_interruption_candidate_matrix"
        metadata["scripts"] = [
            {
                "card_code": code,
                "name": f"c{code}.lua",
                "sha256": hashlib.sha256(scripts[code]).hexdigest(),
            }
            for code in sorted(scripts)
        ]
    return metadata


def _fixture_metadata_with_card_rows(
    fixture_script_id: str | None,
    metadata: Mapping[str, Any] | None,
    card_data: SQLiteCardDataProvider,
) -> dict[str, Any] | None:
    if metadata is None:
        return None
    enriched = dict(metadata)
    if fixture_script_id in {
        ACTION_AGGREGATION_SELECTION_FIXTURE_ID,
        ACTIVATION_ROLLBACK_FIXTURE_ID,
        TARGET_LOSS_FIXTURE_ID,
    }:
        enriched["card_database_rows"] = [
            card_data.get_database_row(code)
            for code in sorted(_fixture_scripts(fixture_script_id))
        ]
    return enriched


def _recovery_card_present(experiment: Mapping[str, Any]) -> bool:
    runner = experiment.get("runner")
    if not isinstance(runner, Mapping):
        return False
    value = runner.get("recovery_card_present", False)
    if not isinstance(value, bool):
        raise ValueError("runner.recovery_card_present must be boolean")
    return value


def _card_instance_provenance_version(experiment: Mapping[str, Any]) -> str:
    runner = experiment.get("runner")
    if runner is None:
        return "v1"
    if not isinstance(runner, Mapping):
        raise ValueError("real-core experiment runner must be a mapping")
    value = runner.get("card_instance_provenance", "v1")
    if value not in {"v1", "v2"}:
        raise ValueError("runner.card_instance_provenance must be v1 or v2")
    return str(value)


def _scenario_id(fixture_script_id: str | None) -> str:
    if fixture_script_id == ACTIVATION_ROLLBACK_FIXTURE_ID:
        return ACTIVATION_ROLLBACK_SCENARIO_ID
    if fixture_script_id == RECOVERY_ATTRIBUTION_FIXTURE_ID:
        return RECOVERY_ATTRIBUTION_SCENARIO_ID
    if fixture_script_id == INTERRUPTION_MATRIX_FIXTURE_ID:
        return INTERRUPTION_MATRIX_SCENARIO_ID
    if fixture_script_id == INTERRUPTION_EFFECT_NEGATION_FIXTURE_ID:
        return INTERRUPTION_EFFECT_NEGATION_SCENARIO_ID
    if fixture_script_id == INTERRUPTION_SEQUENCE_FIXTURE_ID:
        return INTERRUPTION_SEQUENCE_SCENARIO_ID
    if fixture_script_id == INTERRUPTION_TIMING_FIXTURE_ID:
        return INTERRUPTION_TIMING_SCENARIO_ID
    if fixture_script_id == TARGET_LOSS_FIXTURE_ID:
        return TARGET_LOSS_SCENARIO_ID
    return REAL_CORE_SCENARIO_ID


def _fixed_hands(
    fixture_script_id: str | None,
    *,
    recovery_card_present: bool,
) -> dict[str, list[int]]:
    if fixture_script_id == RECOVERY_ATTRIBUTION_FIXTURE_ID:
        player0 = [RECOVERY_PRIMARY_CODE]
        if recovery_card_present:
            player0.append(RECOVERY_CARD_CODE)
        return {"0": player0, "1": [EFFECT_VEILER_CODE]}
    if fixture_script_id == INTERRUPTION_TIMING_FIXTURE_ID:
        return {
            "0": [INTERRUPTION_PRIMARY_CODE],
            "1": [],
        }
    if fixture_script_id in {
        INTERRUPTION_MATRIX_FIXTURE_ID,
        INTERRUPTION_EFFECT_NEGATION_FIXTURE_ID,
        INTERRUPTION_SEQUENCE_FIXTURE_ID,
        TARGET_LOSS_FIXTURE_ID,
    }:
        return {
            "0": [INTERRUPTION_PRIMARY_CODE],
            "1": [
                INTERRUPTION_TARGETLESS_HAND_CODE,
                INTERRUPTION_COST_HAND_CODE,
                INTERRUPTION_COST_CARD_CODE,
            ],
        }
    player0_count = {
        ACTION_AGGREGATION_FIXTURE_ID: 2,
        ACTION_AGGREGATION_SELECTION_FIXTURE_ID: 3,
        ACTIVATION_ROLLBACK_FIXTURE_ID: 2,
    }.get(fixture_script_id, 1)
    return {
        "0": [EFFECT_VEILER_CODE] * player0_count,
        "1": [EFFECT_VEILER_CODE],
    }


def _fixture_initial_field(
    fixture_script_id: str | None,
) -> list[dict[str, int]]:
    if fixture_script_id == INTERRUPTION_TIMING_FIXTURE_ID:
        return [
            {
                "code": INTERRUPTION_SUPPORT_CODE,
                "controller": 0,
                "location": LOCATION_MZONE,
                "position": POSITION_FACEUP_ATTACK,
                "sequence": 0,
            },
            {
                "code": INTERRUPTION_FIELD_CODE,
                "controller": 1,
                "location": LOCATION_SZONE,
                "position": POSITION_FACEUP_ATTACK,
                "sequence": 0,
            },
        ]
    if fixture_script_id not in {
        INTERRUPTION_MATRIX_FIXTURE_ID,
        INTERRUPTION_EFFECT_NEGATION_FIXTURE_ID,
        INTERRUPTION_SEQUENCE_FIXTURE_ID,
        TARGET_LOSS_FIXTURE_ID,
    }:
        return []
    return [
        {
            "code": INTERRUPTION_SUPPORT_CODE,
            "controller": 0,
            "location": LOCATION_MZONE,
            "position": POSITION_FACEUP_ATTACK,
            "sequence": 0,
        },
        {
            "code": INTERRUPTION_FIELD_CODE,
            "controller": 1,
            "location": LOCATION_SZONE,
            "position": POSITION_FACEUP_ATTACK,
            "sequence": 0,
        },
    ]


def _resolved_real_experiment(
    experiment: Mapping[str, Any] | None,
) -> dict[str, Any]:
    resolved = (
        _default_real_experiment()
        if experiment is None
        else deepcopy(dict(experiment))
    )
    assert_current_experiment(resolved)
    information_policy = InformationAccessPolicy.from_experiment(resolved)
    complete_policy = InformationAccessPolicy(
        information_mode="complete_information",
        deck_order=DeckOrderKnowledge.KNOWN,
        opening_hand=OpeningHandPolicy.FIXED,
    )
    sampled_policy = (
        information_policy.information_mode
        == InformationMode.SAMPLED_PRIVATE_STATE
        and information_policy.deck_order == DeckOrderKnowledge.UNKNOWN
        and information_policy.opening_hand
        == OpeningHandPolicy.PROBABILITY_DISTRIBUTION
    )
    if information_policy != complete_policy and not sampled_policy:
        raise ValueError(
            "real-core prototype requires either complete_information with known "
            "fixed hands or sampled_private_state with an unknown deck order and "
            "an opening-hand probability distribution; PlayerView traces are not "
            "emitted"
        )
    runner = resolved.get("runner")
    if isinstance(runner, Mapping) and runner.get("adapter") != "real_core_prototype":
        raise ValueError("real-core worker requires runner.adapter=real_core_prototype")
    fixture_script_id = _fixture_script_id(resolved)
    card_instance_provenance_version = _card_instance_provenance_version(resolved)
    recovery_card_present = _recovery_card_present(resolved)
    if (
        isinstance(runner, Mapping)
        and runner.get("scenario_id") != _scenario_id(fixture_script_id)
    ):
        raise ValueError(
            f"real-core fixture requires runner.scenario_id="
            f"{_scenario_id(fixture_script_id)}"
        )
    expected_deck_id = {
        RECOVERY_ATTRIBUTION_FIXTURE_ID: "recovery_attribution_fixture",
        ACTIVATION_ROLLBACK_FIXTURE_ID: "activation_rollback_probe_fixture",
        INTERRUPTION_MATRIX_FIXTURE_ID: "interruption_candidate_matrix_fixture",
        INTERRUPTION_EFFECT_NEGATION_FIXTURE_ID: (
            "interruption_effect_negation_fixture"
        ),
        INTERRUPTION_SEQUENCE_FIXTURE_ID: "interruption_sequence_fixture",
        INTERRUPTION_TIMING_FIXTURE_ID: "interruption_missed_timing_fixture",
        TARGET_LOSS_FIXTURE_ID: "action_aggregation_target_loss_fixture",
    }.get(fixture_script_id, "effect_veiler_two_player_fixture")
    if resolved["deck"] != {"id": expected_deck_id, "source": "fixed"}:
        raise ValueError(
            f"real-core fixture {fixture_script_id!r} requires deck.id={expected_deck_id}"
        )
    if (
        fixture_script_id != RECOVERY_ATTRIBUTION_FIXTURE_ID
        and recovery_card_present
    ):
        raise ValueError(
            "runner.recovery_card_present is supported only by recovery_attribution_v1"
        )
    if resolved["player"] != {"perspective": 0, "starting_player": 0}:
        raise ValueError("real-core prototype supports only player 0 going first")
    if resolved["turn_limit"] < 2:
        raise ValueError("real-core durability scenario requires turn_limit >= 2")
    if resolved["search"].get("strategy") != "scripted_real_core":
        raise ValueError("real-core prototype requires search.strategy=scripted_real_core")
    _resolve_interruption_plans(resolved)
    if (
        fixture_script_id is not None
        and fixture_script_id
        not in {
            RECOVERY_ATTRIBUTION_FIXTURE_ID,
            INTERRUPTION_MATRIX_FIXTURE_ID,
            INTERRUPTION_EFFECT_NEGATION_FIXTURE_ID,
            INTERRUPTION_SEQUENCE_FIXTURE_ID,
            INTERRUPTION_TIMING_FIXTURE_ID,
            TARGET_LOSS_FIXTURE_ID,
        }
        and resolved["interruption"].get("mode") != "none"
    ):
        raise ValueError("this fixture script does not support interruption mode")
    if (
        resolved["success_predicate"].get("id")
        != "real_core_min_monster_count"
        or resolved["success_predicate"].get("version") != "1"
    ):
        raise ValueError("real-core prototype requires real_core_min_monster_count@1")
    min_count = resolved["success_predicate"].get("config", {}).get("min_count")
    expected_min_count = 2 if fixture_script_id in {
            RECOVERY_ATTRIBUTION_FIXTURE_ID,
            INTERRUPTION_MATRIX_FIXTURE_ID,
            INTERRUPTION_EFFECT_NEGATION_FIXTURE_ID,
            INTERRUPTION_SEQUENCE_FIXTURE_ID,
            TARGET_LOSS_FIXTURE_ID,
        } else 1
    if min_count != expected_min_count:
        raise ValueError(
            f"real-core fixture requires success_predicate.config.min_count="
            f"{expected_min_count}"
        )
    resolved["prototype"] = {
        "adapter": "ocgcore-v11",
        "scenario_id": _scenario_id(fixture_script_id),
        "validated_contracts": [
            "binary_decision_decode",
            "binary_response_encode",
            "core_state_query",
            "core_derived_legal_stop",
            "card_instance_identity",
            "exact_search_state_equivalence",
            "end_phase_durability",
            "fresh_process_replay",
            "configured_interruption_execution",
            "sampled_interruption_manifest",
            "pluggable_evaluator_registry",
            "score_breakdown_persistence",
            "temporary_effect_evaluation_policy",
            "ocgcore_temporary_effect_observation",
            "ocgcore_action_aggregation_roles",
            *(
                ["card_instance_provenance_v2"]
                if card_instance_provenance_version == "v2"
                else []
            ),
            *(
                ["additional_card_counterfactual_recovery"]
                if fixture_script_id == RECOVERY_ATTRIBUTION_FIXTURE_ID
                else []
            ),
            *(
                ["generic_core_interruption_candidate_policy"]
                if fixture_script_id
                in {
                    INTERRUPTION_MATRIX_FIXTURE_ID,
                    INTERRUPTION_EFFECT_NEGATION_FIXTURE_ID,
                    INTERRUPTION_SEQUENCE_FIXTURE_ID,
                    INTERRUPTION_TIMING_FIXTURE_ID,
                }
                else []
            ),
        ],
        "pending_validation": [],
    }
    return resolved


@dataclass(frozen=True)
class RealCoreVerificationResult:
    route_id: str
    event_count: int
    final_state_hash: str


def _selected_candidate(
    request: Any,
    *,
    fixture_script_id: str | None,
    summoned: bool,
    end_turn_submitted: bool,
    interruption_executions: list[_InterruptionExecution],
    aggregation_effect_activated: bool,
    aggregation_cost_count: int,
    aggregation_target_selected: bool,
    aggregation_resolution_card_selected: bool,
    aggregation_option_selected: bool,
    recovery_primary_activated: bool,
    recovery_card_activated: bool,
    matrix_primary_activated: bool,
    matrix_secondary_activated: bool,
    events: list[ReplayEventV03a],
    state_hash_before: str,
    turn: int,
    turn_action_index: int,
    chain_index: int,
) -> tuple[tuple[Any, ...], str | None]:
    pending_responses = [
        execution
        for execution in interruption_executions
        if execution.activated
        and execution.response_index
        < len(execution.plan.candidate_policy.responses)
    ]
    if len(pending_responses) > 1:
        raise ValueError("multiple interruption response sequences are active")
    if pending_responses:
        execution = pending_responses[0]
        plan = execution.plan
        response = plan.candidate_policy.responses[execution.response_index]
        path = (
            f"$.interruption.definitions[{plan.definition_index}]"
            f".candidate_policy.responses[{execution.response_index}]"
        )
        return (
            response.select(request, path=path),
            f"interruption_response:{plan.definition_index}:"
            f"{execution.response_index}:{response.role}",
        )
    for execution in interruption_executions:
        if execution.activated:
            continue
        plan = execution.plan
        target = plan.target
        if target.step < len(events):
            raise _interruption_error(
                f"$.interruption.definitions[{plan.definition_index}].target.step",
                "configured interruption opportunity was missed",
            )
        if target.step > len(events):
            continue
        opportunity = {
            "chain_index": chain_index,
            "player": request.player,
            "request_signature": request.request_signature,
            "state_hash_before": state_hash_before,
            "step": len(events),
            "turn": turn,
            "turn_action_index": turn_action_index,
        }
        expected = {
            "chain_index": target.chain_index,
            "player": target.player,
            "request_signature": target.request_signature,
            "state_hash_before": target.state_hash_before,
            "step": target.step,
            "turn": target.turn,
            "turn_action_index": target.turn_action_index,
        }
        if opportunity != expected:
            differing = next(key for key in expected if opportunity[key] != expected[key])
            raise _interruption_error(
                f"$.interruption.definitions[{plan.definition_index}]",
                f"target opportunity mismatch at {differing}: "
                f"expected {expected[differing]!r}, got {opportunity[differing]!r}",
            )
        return (
            plan.candidate_policy.activation.select(
                request,
                path=(
                    f"$.interruption.definitions["
                    f"{plan.definition_index}]"
                    ".candidate_policy.activation"
                ),
            ),
            f"interruption_activation:{plan.definition_index}",
        )
    if request.request_type == "select_idle_command":
        if (
            fixture_script_id in ACTION_AGGREGATION_FIXTURE_IDS
            and summoned
            and not aggregation_option_selected
        ):
            raise ValueError(
                "action aggregation fixture returned to idle before its effect completed"
            )
        if (
            fixture_script_id == RECOVERY_ATTRIBUTION_FIXTURE_ID
            and summoned
            and not recovery_primary_activated
        ):
            raise ValueError(
                "recovery attribution fixture returned to idle before primary activation"
            )
        if fixture_script_id in GENERIC_INTERRUPTION_FIXTURE_IDS and not summoned:
            primary_candidate = next(
                (
                    candidate
                    for candidate in request.candidates
                    if isinstance(candidate.card_ref, Mapping)
                    and candidate.card_ref.get("public_card_id")
                    == INTERRUPTION_PRIMARY_CODE
                ),
                None,
            )
            if primary_candidate is None:
                raise ValueError(
                    "interruption matrix fixture exposed no primary summon candidate"
                )
            return (primary_candidate,), None
        candidate_id = "control:end_turn" if summoned else "normal_summon:0"
    elif request.request_type == "select_place":
        if fixture_script_id in {
            RECOVERY_ATTRIBUTION_FIXTURE_ID,
            *GENERIC_INTERRUPTION_FIXTURE_IDS,
        }:
            if not request.candidates:
                raise ValueError("real-core fixture exposed no available zone")
            return (request.candidates[0],), None
        candidate_id = "zone:0:4:0"
    elif (
        request.request_type == "select_effect_yes_no"
        and fixture_script_id == RECOVERY_ATTRIBUTION_FIXTURE_ID
        and summoned
        and not recovery_primary_activated
        and request.player == 0
    ):
        activation_candidate = next(
            (
                candidate
                for candidate in request.candidates
                if candidate.candidate_id == "choice:1"
                and candidate.kind == "effect"
            ),
            None,
        )
        if activation_candidate is None:
            raise ValueError(
                "recovery attribution fixture exposed no primary effect candidate"
        )
        return (activation_candidate,), "recovery_primary_activation"
    elif (
        request.request_type == "select_effect_yes_no"
        and fixture_script_id in GENERIC_INTERRUPTION_FIXTURE_IDS
        and summoned
        and not matrix_primary_activated
        and request.player == 0
    ):
        activation_candidate = next(
            (
                candidate
                for candidate in request.candidates
                if candidate.candidate_id == "choice:1"
                and candidate.kind == "effect"
            ),
            None,
        )
        if activation_candidate is None:
            raise ValueError(
                "interruption matrix fixture exposed no primary effect candidate"
        )
        return (activation_candidate,), "matrix_primary_activation"
    elif (
        request.request_type == "select_effect_yes_no"
        and fixture_script_id == INTERRUPTION_SEQUENCE_FIXTURE_ID
        and summoned
        and matrix_primary_activated
        and not matrix_secondary_activated
        and request.player == 0
    ):
        activation_candidate = next(
            (
                candidate
                for candidate in request.candidates
                if candidate.candidate_id == "choice:1"
                and candidate.kind == "effect"
            ),
            None,
        )
        if activation_candidate is None:
            raise ValueError(
                "interruption sequence fixture exposed no secondary effect candidate"
            )
        return (activation_candidate,), "matrix_secondary_activation"
    elif (
        request.request_type == "select_effect_yes_no"
        and fixture_script_id in ACTION_AGGREGATION_FIXTURE_IDS
        and summoned
        and not aggregation_effect_activated
        and request.player == 0
    ):
        activation_candidate = next(
            (
                candidate
                for candidate in request.candidates
                if candidate.candidate_id == "choice:1"
                and candidate.kind == "effect"
            ),
            None,
        )
        if activation_candidate is None:
            raise ValueError(
                "action aggregation fixture exposed no affirmative effect candidate"
            )
        return (activation_candidate,), "aggregation_activation"
    elif request.request_type == "select_chain":
        if (
            fixture_script_id in GENERIC_INTERRUPTION_FIXTURE_IDS
            and summoned
            and not matrix_primary_activated
            and request.player == 0
        ):
            primary_candidate = next(
                (
                    candidate
                    for candidate in request.candidates
                    if candidate.kind == "effect"
                    and isinstance(candidate.card_ref, Mapping)
                    and candidate.card_ref.get("public_card_id")
                    == INTERRUPTION_PRIMARY_CODE
                ),
                None,
            )
            if primary_candidate is not None:
                return (primary_candidate,), "matrix_primary_activation"
        if (
            fixture_script_id == INTERRUPTION_SEQUENCE_FIXTURE_ID
            and summoned
            and matrix_primary_activated
            and not matrix_secondary_activated
            and request.player == 0
        ):
            secondary_candidate = next(
                (
                    candidate
                    for candidate in request.candidates
                    if candidate.kind == "effect"
                    and isinstance(candidate.card_ref, Mapping)
                    and candidate.card_ref.get("public_card_id")
                    == INTERRUPTION_SUPPORT_CODE
                ),
                None,
            )
            if secondary_candidate is not None:
                return (secondary_candidate,), "matrix_secondary_activation"
        if (
            fixture_script_id == RECOVERY_ATTRIBUTION_FIXTURE_ID
            and recovery_primary_activated
            and not recovery_card_activated
            and request.player == 0
        ):
            recovery_candidate = next(
                (
                    candidate
                    for candidate in request.candidates
                    if candidate.kind == "effect"
                    and isinstance(candidate.card_ref, Mapping)
                    and candidate.card_ref.get("public_card_id")
                    == RECOVERY_CARD_CODE
                ),
                None,
            )
            if recovery_candidate is not None:
                return (recovery_candidate,), "recovery_card_activation"
        if (
            fixture_script_id in ACTION_AGGREGATION_FIXTURE_IDS
            and summoned
            and not aggregation_effect_activated
            and request.player == 0
        ):
            effect_candidate = next(
                (
                    candidate
                    for candidate in request.candidates
                    if candidate.kind == "effect"
                    and isinstance(candidate.card_ref, Mapping)
                    and candidate.card_ref.get("public_card_id") == EFFECT_VEILER_CODE
                ),
                None,
            )
            if effect_candidate is not None:
                return (effect_candidate,), "aggregation_activation"
        candidate_id = "control:pass"
    elif (
        request.request_type == "select_card"
        and fixture_script_id == ACTIVATION_ROLLBACK_FIXTURE_ID
        and aggregation_effect_activated
        and aggregation_cost_count == 0
        and request.player == 0
    ):
        if request.context.extra.get("cancelable") is not True:
            raise ValueError(
                "activation rollback fixture requires a cancelable select_card"
            )
        return (), "activation_rollback_cancel"
    elif (
        request.request_type == "select_card"
        and fixture_script_id == ACTION_AGGREGATION_FIXTURE_ID
        and aggregation_effect_activated
        and aggregation_cost_count == 0
        and request.player == 0
    ):
        cost_candidate = next(
            (
                candidate
                for candidate in request.candidates
                if isinstance(candidate.card_ref, Mapping)
                and candidate.card_ref.get("controller") == 0
                and candidate.card_ref.get("location") == LOCATION_HAND
            ),
            None,
        )
        if cost_candidate is None:
            raise ValueError("action aggregation fixture exposed no hand cost candidate")
        return (cost_candidate,), "aggregation_cost"
    elif (
        request.request_type == "select_card"
        and fixture_script_id == ACTION_AGGREGATION_FIXTURE_ID
        and aggregation_cost_count == 1
        and not aggregation_target_selected
        and request.player == 0
    ):
        target_candidate = next(
            (
                candidate
                for candidate in request.candidates
                if isinstance(candidate.card_ref, Mapping)
                and candidate.card_ref.get("controller") == 0
                and candidate.card_ref.get("location") == 0x04
            ),
            None,
        )
        if target_candidate is None:
            raise ValueError("action aggregation fixture exposed no field target candidate")
        return (target_candidate,), "aggregation_target"
    elif (
        request.request_type == "select_card"
        and fixture_script_id == TARGET_LOSS_FIXTURE_ID
        and matrix_primary_activated
        and not aggregation_target_selected
        and request.player == 0
    ):
        target_candidate = next(
            (
                candidate
                for candidate in request.candidates
                if isinstance(candidate.card_ref, Mapping)
                and candidate.card_ref.get("controller") == 0
                and candidate.card_ref.get("location") == LOCATION_MZONE
                and candidate.card_ref.get("public_card_id")
                == INTERRUPTION_SUPPORT_CODE
            ),
            None,
        )
        if target_candidate is None:
            raise ValueError("target-loss fixture exposed no primary target candidate")
        return (target_candidate,), "aggregation_target"
    elif (
        request.request_type == "select_card"
        and fixture_script_id == ACTION_AGGREGATION_SELECTION_FIXTURE_ID
        and aggregation_effect_activated
        and aggregation_cost_count < 2
        and request.player == 0
    ):
        cost_candidate = next(
            (
                candidate
                for candidate in request.candidates
                if isinstance(candidate.card_ref, Mapping)
                and candidate.card_ref.get("controller") == 0
                and candidate.card_ref.get("location") == LOCATION_HAND
            ),
            None,
        )
        if cost_candidate is None:
            raise ValueError(
                "selection edge fixture exposed no repeated hand cost candidate"
            )
        return (cost_candidate,), "aggregation_cost"
    elif (
        request.request_type == "select_card"
        and fixture_script_id == ACTION_AGGREGATION_SELECTION_FIXTURE_ID
        and aggregation_cost_count == 2
        and not aggregation_resolution_card_selected
        and request.player == 0
    ):
        resolution_candidate = next(
            (
                candidate
                for candidate in request.candidates
                if isinstance(candidate.card_ref, Mapping)
                and candidate.card_ref.get("controller") == 0
                and candidate.card_ref.get("location") == 0x10
            ),
            None,
        )
        if resolution_candidate is None:
            raise ValueError(
                "selection edge fixture exposed no graveyard resolution candidate"
            )
        return (resolution_candidate,), "aggregation_resolution_card"
    elif (
        request.request_type == "select_option"
        and fixture_script_id == ACTION_AGGREGATION_FIXTURE_ID
        and aggregation_target_selected
        and not aggregation_option_selected
        and request.player == 0
    ):
        if not request.candidates:
            raise ValueError("action aggregation fixture exposed no option candidate")
        return (request.candidates[0],), "aggregation_option"
    elif (
        request.request_type == "select_option"
        and fixture_script_id == ACTION_AGGREGATION_SELECTION_FIXTURE_ID
        and aggregation_resolution_card_selected
        and not aggregation_option_selected
        and request.player == 0
    ):
        if not request.candidates:
            raise ValueError("selection edge fixture exposed no resolution option")
        return (request.candidates[0],), "aggregation_option"
    else:
        raise ValueError(
            f"fixed real-core scenario encountered unsupported request {request.request_type!r}"
        )
    for candidate in request.candidates:
        if candidate.candidate_id == candidate_id:
            return (candidate,), None
    raise ValueError(
        f"fixed real-core scenario expected candidate {candidate_id!r} in "
        f"{request.request_type!r}"
    )


def _action_kind(request: Any, candidate: Any) -> ActionKind:
    raw_kind = candidate.payload.get("action_kind")
    if raw_kind is not None:
        return ActionKind(str(raw_kind))
    fallback = {
        "announce_attribute": ActionKind.ANNOUNCE_ATTRIBUTE,
        "announce_card": ActionKind.ANNOUNCE_CARD,
        "announce_number": ActionKind.ANNOUNCE_NUMBER,
        "announce_race": ActionKind.ANNOUNCE_RACE,
        "distribute_counters": ActionKind.DISTRIBUTE_COUNTERS,
        "rock_paper_scissors": ActionKind.ROCK_PAPER_SCISSORS,
        "select_card": ActionKind.SELECT_CARD,
        "select_disabled_field": ActionKind.SELECT_ZONE,
        "select_option": ActionKind.SELECT_OPTION,
        "select_place": ActionKind.SELECT_ZONE,
        "select_position": ActionKind.SELECT_POSITION,
        "select_sum": ActionKind.SELECT_SUM,
        "select_tribute": ActionKind.SELECT_TRIBUTE,
    }.get(request.request_type)
    if fallback is None:
        raise ValueError(
            f"request {request.request_type!r} candidate has no Action kind"
        )
    return fallback


def _candidate_card_ref(
    candidate: Any,
    *,
    require_instance: bool = False,
) -> CardRef | None:
    raw = candidate.card_ref
    if not isinstance(raw, Mapping):
        return None
    controller = raw.get("controller")
    location = raw.get("location")
    sequence = raw.get("sequence")
    if not all(
        isinstance(value, int) and not isinstance(value, bool)
        for value in (controller, location, sequence)
    ):
        return None
    location_name = {
        0x02: "hand",
        0x04: "monster_zone",
        0x10: "graveyard",
    }.get(location, f"core_location_{location}")
    public_card_id = raw.get("public_card_id")
    owner = raw.get("owner", controller)
    instance_id = raw.get("instance_id")
    if not isinstance(owner, int) or isinstance(owner, bool) or owner not in (0, 1):
        raise ValueError("card candidate has no valid owner")
    if require_instance and (
        not isinstance(instance_id, str) or not instance_id.startswith("corecard_")
    ):
        raise ValueError("card instance v2 candidate has no persistent instance_id")
    return CardRef(
        controller=controller,
        owner=owner,
        location=location_name,
        sequence=sequence,
        public_card_id=(
            public_card_id
            if isinstance(public_card_id, int) and not isinstance(public_card_id, bool)
            else None
        ),
        instance_id=instance_id if isinstance(instance_id, str) else None,
    )


def _frontier_actions(request: Any, *, limit: int) -> tuple[Action, ...]:
    if not isinstance(limit, int) or isinstance(limit, bool) or limit < 1:
        raise ValueError("search.parameters.max_frontier_actions must be >= 1")
    grouped: dict[ActionKind, list[Any]] = {}
    for candidate in request.candidates:
        kind = _action_kind(request, candidate)
        grouped.setdefault(kind, []).append(candidate)
    constraints = request.constraints
    actions: list[Action] = []
    for kind, candidates in sorted(grouped.items(), key=lambda item: item[0].value):
        if kind == ActionKind.FINISH_SELECTION:
            counts = (1,)
        else:
            minimum = max(1, constraints.min_selections)
            maximum = min(constraints.max_selections, len(candidates))
            counts = range(minimum, maximum + 1)
        for count in counts:
            groups = (
                itertools.permutations(candidates, count)
                if constraints.ordered
                else itertools.combinations(candidates, count)
            )
            for selected in groups:
                card_refs = tuple(_candidate_card_ref(candidate) for candidate in selected)
                actions.append(
                    Action(
                        kind=kind,
                        player=request.player,
                        selections=tuple(
                            Selection(
                                candidate_id=candidate.candidate_id,
                                card_ref=card_ref,
                                order=index if constraints.ordered else None,
                                payload_ref="candidate.payload",
                            )
                            for index, (candidate, card_ref) in enumerate(
                                zip(selected, card_refs, strict=True)
                            )
                        ),
                        request_signature=request.request_signature,
                    )
                )
                if len(actions) > limit:
                    raise ValueError(
                        f"core frontier exceeds max_frontier_actions={limit}"
                    )
    if not actions:
        raise ValueError(
            f"core request {request.request_type!r} exposed no supported Action"
        )
    return tuple(sorted(actions, key=lambda action: action.action_id))


def _prefix_candidates(
    request: Any,
    expected_action: Mapping[str, Any],
    *,
    specified_interruption: bool = False,
) -> tuple[tuple[Any, ...], None]:
    if expected_action.get("request_signature") != request.request_signature:
        raise ValueError("search prefix request signature changed during fresh Replay")
    raw_selections = expected_action.get("selections")
    if not isinstance(raw_selections, list) or not raw_selections:
        raise ValueError("search prefix Action must contain selections")
    by_id = {candidate.candidate_id: candidate for candidate in request.candidates}
    selected: list[Any] = []
    for index, raw_selection in enumerate(raw_selections):
        if not isinstance(raw_selection, Mapping):
            raise ValueError(f"search prefix selection {index} must be a mapping")
        candidate_id = raw_selection.get("candidate_id")
        candidate = by_id.get(candidate_id)
        if candidate is None:
            if specified_interruption:
                raise MultiInterruptionRuntimeError(
                    "candidate_disappeared",
                    "recorded core candidate disappeared during fresh Replay",
                    path_failure=True,
                    context={
                        "candidate_id": candidate_id,
                        "request_signature": request.request_signature,
                    },
                )
            raise ValueError(
                f"search prefix candidate {candidate_id!r} disappeared during fresh Replay"
            )
        selected.append(candidate)
    kinds = {_action_kind(request, candidate) for candidate in selected}
    if len(kinds) != 1 or next(iter(kinds)).value != expected_action.get("kind"):
        raise ValueError("search prefix Action kind no longer matches core candidates")
    return tuple(selected), None


def _decode_batch(
    decoder: OcgcoreMessageDecoder,
    batch: Any,
    step: int,
    *,
    scenario_id: str = REAL_CORE_SCENARIO_ID,
    card_instance_tracker: CardInstanceTrackerV2 | None = None,
    card_instance_duel: Any | None = None,
) -> DecodedMessageBatch:
    decoded = decoder.decode_batch(
        b"".join(batch.messages),
        request_id=f"{scenario_id}:{step}",
        logs=batch.logs,
    )
    if decoded.request is None:
        raise ValueError("ocgcore reached an awaiting state without a supported request")
    if card_instance_tracker is not None:
        if card_instance_duel is None:
            raise ValueError("card instance v2 requires the active duel")
        scan_label = f"request_{step}"
        scan_logs = card_instance_duel.capture_card_instance_scan(
            scan_nonce=scan_label
        )
        combined_logs = (*batch.logs, *scan_logs)
        request = card_instance_tracker.synchronize_request(
            combined_logs,
            decoded.request,
            expected_scan_label=scan_label,
            message_types=[frame.message_type for frame in decoded.frames],
        )
        decoded = replace(
            decoded,
            request=request,
            logs=filter_card_instance_trace_logs(combined_logs),
        )
    return decoded


def _evaluation(
    board: Mapping[str, Any],
    *,
    experiment: Mapping[str, Any],
    state_hash: str,
    turn: int,
    phase: str,
) -> tuple[EvaluationResult, bool]:
    result = _EVALUATORS.evaluate_experiment(
        experiment,
        EvaluationInput(
            state_hash=state_hash,
            board_summary=board,
            turn=turn,
            phase=phase,
            information_mode=str(experiment["information_mode"]),
        ),
    )
    predicate = experiment["success_predicate"]
    if predicate.get("id") == "real_core_min_monster_count" and predicate.get(
        "version"
    ) == "1":
        success_config = predicate["config"]
        if (
            success_config.get("player") != 0
            or success_config.get("zone") != "monster_zone"
        ):
            raise ValueError("real-core success predicate supports player 0 monster_zone")
        min_count = success_config.get("min_count")
        if (
            not isinstance(min_count, int)
            or isinstance(min_count, bool)
            or min_count < 0
        ):
            raise ValueError("success predicate min_count must be a non-negative integer")
        return result, int(result.vector["field_count"]) >= min_count
    if predicate.get("id") == "real_core_board_break" and predicate.get(
        "version"
    ) == "1":
        config = predicate.get("config")
        if not isinstance(config, Mapping):
            raise ValueError("board-break success config must be a mapping")
        supported_config = {
            "actor_player",
            "max_opponent_graveyard",
            "max_opponent_monsters",
            "max_opponent_spell_traps",
            "min_opponent_banished",
        }
        unknown_config = sorted(set(config) - supported_config)
        if unknown_config:
            raise ValueError(
                f"board-break success has unknown config keys: {unknown_config}"
            )
        actor = config.get("actor_player", 0)
        if (
            not isinstance(actor, int)
            or isinstance(actor, bool)
            or actor not in (0, 1)
        ):
            raise ValueError("board-break success actor_player must be 0 or 1")
        counts = board.get("zone_counts", {}).get(str(1 - actor))
        if not isinstance(counts, Mapping):
            raise ValueError("board-break success has no opponent zone counts")
        limits = {
            "max_opponent_monsters": "monster_zone",
            "max_opponent_spell_traps": "spell_trap_zone",
            "max_opponent_graveyard": "graveyard",
        }
        checks = []
        for field, zone in limits.items():
            if field not in config:
                continue
            limit = config[field]
            if not isinstance(limit, int) or isinstance(limit, bool) or limit < 0:
                raise ValueError(f"board-break success {field} must be an integer >= 0")
            observed = counts.get(zone, 0)
            if (
                not isinstance(observed, int)
                or isinstance(observed, bool)
                or observed < 0
            ):
                raise ValueError(f"board-break success {zone} count is invalid")
            checks.append(observed <= limit)
        if "min_opponent_banished" in config:
            minimum = config["min_opponent_banished"]
            if (
                not isinstance(minimum, int)
                or isinstance(minimum, bool)
                or minimum < 0
            ):
                raise ValueError(
                    "board-break success min_opponent_banished must be an integer >= 0"
                )
            observed = counts.get("banished", 0)
            if (
                not isinstance(observed, int)
                or isinstance(observed, bool)
                or observed < 0
            ):
                raise ValueError("board-break success banished count is invalid")
            checks.append(observed >= minimum)
        if not checks:
            raise ValueError("board-break success requires at least one threshold")
        return result, all(checks)
    raise ValueError("unsupported real-core success predicate")


def _frontier_document(
    *,
    request: Any,
    actions: Sequence[Action],
    snapshot: Any,
    checkpoint_snapshots: Sequence[tuple[Any, int, str]],
    experiment: Mapping[str, Any],
    turn: int,
    phase: str,
    legal_stop: Any,
    route_document: Mapping[str, Any] | None,
    action_prefix: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    board = build_board_summary(snapshot, viewer=0).to_dict()
    evaluation, success = _evaluation(
        board,
        experiment=experiment,
        state_hash=snapshot.state_hash,
        turn=turn,
        phase=phase,
    )
    peak_score = evaluation.total_score
    for checkpoint_snapshot, checkpoint_turn, checkpoint_phase in checkpoint_snapshots:
        checkpoint_board = build_board_summary(checkpoint_snapshot, viewer=0).to_dict()
        checkpoint_evaluation, _ = _evaluation(
            checkpoint_board,
            experiment=experiment,
            state_hash=checkpoint_snapshot.state_hash,
            turn=checkpoint_turn,
            phase=checkpoint_phase,
        )
        peak_score = max(peak_score, checkpoint_evaluation.total_score)
    interruption_taxonomy = []
    interruption_composition = None
    interruption_opportunities = None
    interruption = experiment.get("interruption", {})
    composition = None
    if interruption.get("mode") == "specified":
        composition = build_multi_interruption_composition(interruption)
        interruption_composition = composition.to_dict()
    if (
        interruption.get("mode") == "specified"
        and request.request_type == "select_chain"
    ):
        assert composition is not None
        runtime_frontier = build_multi_interruption_frontier(
            composition=composition,
            request_signature=request.request_signature,
            actions=actions,
            action_prefix=action_prefix,
        )
        for definition in interruption["definitions"]:
            source_code = int(definition["source_card_code"])
            matching_ids = tuple(
                opportunity.candidate_id
                for opportunity in runtime_frontier.opportunities
                if opportunity.definition_id == definition["id"]
            )
            if not matching_ids:
                continue
            verified = definition.get("verified_fixture_categories", [])
            policy = InterruptionValidationPolicy().register_verified(*verified)
            outcome = classify_interruption_candidates(
                request,
                source_card_code=source_code,
                source_player=int(definition["source_player"]),
                source_zone=definition.get("source_zone", "hand"),
                policy=policy,
                expected_candidate_ids=matching_ids,
                validation_categories=definition.get("validation_categories"),
            )
            interruption_taxonomy.append(
                {"definition_id": definition["id"], **outcome.to_dict()}
            )
            if not outcome.supported:
                raise MultiInterruptionRuntimeError(
                    "unsupported_activation_taxonomy",
                    "specified interruption activation failed taxonomy",
                    path_failure=outcome.status == "path_failure",
                    context={
                        "definition_id": definition["id"],
                        "taxonomy": outcome.to_dict(),
                    },
                )
        actions = runtime_frontier.actions
        interruption_opportunities = runtime_frontier.to_dict()
    elif interruption.get("mode") == "specified":
        assert composition is not None
        active_definition = None
        activation_index = None
        for index in range(len(action_prefix) - 1, -1, -1):
            resolved = resolve_multi_interruption_definition(
                composition, action_prefix[index]
            )
            if resolved is not None:
                active_definition = resolved
                activation_index = index
                break
        if active_definition is not None and activation_index is not None:
            definition = next(
                item
                for item in interruption["definitions"]
                if item["id"] == active_definition.definition_id
            )
            source_code = active_definition.source_card_code
            response_index = len(action_prefix) - activation_index - 1
            roles = definition.get("response_roles", [])
            if response_index < len(roles):
                request_document = request.to_dict()
                extra = request_document["context"].setdefault("extra", {})
                extra["interruption_role"] = roles[response_index]
                extra["interruption_source"] = {
                    "card_code": source_code,
                    "player": active_definition.source_player,
                    "zone": active_definition.source_zone,
                }
                verified = definition.get("verified_fixture_categories", [])
                policy = InterruptionValidationPolicy().register_verified(*verified)
                outcome = classify_interruption_candidates(
                    request_document,
                    source_card_code=source_code,
                    source_player=active_definition.source_player,
                    source_zone=active_definition.source_zone,
                    policy=policy,
                    validation_categories=definition.get("validation_categories"),
                )
                interruption_taxonomy.append(
                    {"definition_id": definition["id"], **outcome.to_dict()}
                )
                if not outcome.supported:
                    raise MultiInterruptionRuntimeError(
                        "unsupported_response_taxonomy",
                        "specified interruption response failed taxonomy",
                        path_failure=outcome.status == "path_failure",
                        context={
                            "definition_id": definition["id"],
                            "taxonomy": outcome.to_dict(),
                        },
                    )
    return {
        "actions": [action.to_dict() for action in actions],
        "interruption_composition": interruption_composition,
        "interruption_opportunities": interruption_opportunities,
        "legal_stop": legal_stop.to_dict(),
        "interruption_taxonomy": interruption_taxonomy,
        "peak_score": peak_score,
        "replay_count": 1,
        "request": request.to_dict(),
        "route_document": to_canonical_data(route_document),
        "schema_version": REAL_CORE_FRONTIER_SCHEMA_VERSION,
        "score": evaluation.total_score,
        "state_completeness": snapshot.identity_completeness,
        "state_id": snapshot.state_hash,
        "success": success,
    }


def _specified_interruption_trace(
    experiment: Mapping[str, Any], replay: Mapping[str, Any]
) -> list[dict[str, Any]]:
    if experiment.get("interruption", {}).get("mode") != "specified":
        return []
    events = replay.get("events")
    if not isinstance(events, list):
        raise ValueError("specified interruption trace requires Replay events")
    normalized_events: list[tuple[int, Mapping[str, Any]]] = []
    for index, event in enumerate(events):
        if not isinstance(event, Mapping) or not isinstance(
            event.get("action"), Mapping
        ):
            raise ValueError(f"Replay event {index} has no Action")
        step = event.get("step")
        if not isinstance(step, int) or isinstance(step, bool):
            raise ValueError(f"Replay event {index} has no integer step")
        normalized_events.append((step, event["action"]))

    trace: list[dict[str, Any]] = []
    interruption = experiment["interruption"]
    composition = build_multi_interruption_composition(interruption)
    composition_definitions = {
        definition.definition_id: definition
        for definition in composition.definitions
    }
    definitions = interruption["definitions"]
    for definition in definitions:
        source_code = int(definition["source_card_code"])
        roles = tuple(definition.get("response_roles", ()))
        occurrence_index = 0
        for event_index, (step, action) in enumerate(normalized_events):
            if action.get("kind") != ActionKind.ACTIVATE_EFFECT.value:
                continue
            selections = action.get("selections")
            if not isinstance(selections, list):
                raise ValueError("specified activation Action has no selections")
            resolved_definition = resolve_multi_interruption_definition(
                composition, action
            )
            if (
                resolved_definition is None
                or resolved_definition.definition_id != definition["id"]
            ):
                continue
            occurrence_index += 1
            response_steps = []
            for response_index, role in enumerate(roles):
                next_index = event_index + response_index + 1
                if next_index >= len(normalized_events):
                    raise ValueError(
                        f"specified interruption {definition['id']!r} is missing "
                        f"the explicit {role!r} response"
                    )
                response_step, response_action = normalized_events[next_index]
                response_selections = response_action.get("selections")
                if not isinstance(response_selections, list):
                    raise ValueError("specified response Action has no selections")
                response_steps.append(
                    {
                        "action_id": response_action.get("action_id"),
                        "action_step": response_step,
                        "candidate_ids": [
                            selection.get("candidate_id")
                            for selection in response_selections
                            if isinstance(selection, Mapping)
                        ],
                        "response_index": response_index,
                        "role": role,
                    }
                )
            activation_candidate_ids = [
                selection.get("candidate_id")
                for selection in selections
                if isinstance(selection, Mapping)
            ]
            prefix_action_ids = [
                prefix_action.get("action_id")
                for _prefix_step, prefix_action in normalized_events[:event_index]
            ]
            composition_definition = composition_definitions[str(definition["id"])]
            opportunity_id = build_interruption_opportunity_id(
                composition_id=composition.composition_id,
                definition_id=composition_definition.definition_id,
                occurrence_index=occurrence_index,
                request_signature=str(action.get("request_signature")),
                candidate_id=str(activation_candidate_ids[0]),
                prefix_action_ids=prefix_action_ids,
            )
            record = {
                "activation": {
                    "action_id": action.get("action_id"),
                    "action_step": step,
                    "candidate_ids": activation_candidate_ids,
                    "request_signature": action.get("request_signature"),
                },
                "composition_id": composition.composition_id,
                "definition_id": definition["id"],
                "max_activations": composition_definition.max_activations,
                "occurrence_index": occurrence_index,
                "opportunity_id": opportunity_id,
                "prefix_action_ids": prefix_action_ids,
                "priority": composition_definition.priority,
                "response_steps": response_steps,
                "source_card_code": source_code,
                "source_player": definition["source_player"],
                "source_zone": definition.get("source_zone", "hand"),
                "status": "applied_by_core",
                "taxonomy_schema_version": (
                    INTERRUPTION_SUPPORT_TAXONOMY_SCHEMA_VERSION
                ),
            }
            record["trace_id"] = stable_digest(
                record, prefix="specifiedinterruption_"
            )
            trace.append(record)
    return trace


def _apply_progress_events(
    trace: Mapping[str, Any], current_turn: int, current_phase: str
) -> tuple[int, str]:
    for event in trace.get("progress_events", []):
        if not isinstance(event, Mapping):
            raise ValueError("core progress event must be a mapping")
        outcome = event.get("outcome")
        if not isinstance(outcome, Mapping):
            raise ValueError("core progress event outcome must be a mapping")
        if event.get("kind") == "new_turn":
            current_turn += 1
            current_phase = "turn_start"
        elif event.get("kind") == "new_phase":
            phase_name = outcome.get("phase_name")
            if not isinstance(phase_name, str) or not phase_name:
                raise ValueError("new_phase event must include phase_name")
            current_phase = phase_name
        else:
            raise ValueError(f"unsupported core progress event {event.get('kind')!r}")
    return current_turn, current_phase


def _real_replay_manifest(
    *,
    core_lock: Any,
    asset_lock: Any,
    build: Mapping[str, Any],
    information_policy_id: str,
    interruption_sampling: Mapping[str, Any] | None,
    initial_snapshot_hash: str,
    opening_hand_sampling: Mapping[str, Any] | None = None,
    snapshot_kind: str = "complete_information",
    deck_order_in_snapshot: bool = True,
    player0_hand_count: int = 1,
    fixed_hands: Mapping[str, list[int]] | None = None,
    initial_field: list[Mapping[str, int]] | None = None,
    fixture_script: Mapping[str, Any] | None = None,
    direct_random_trace: Mapping[str, Any] | None = None,
) -> ReplayManifestV03a:
    scripts = asset_lock.repositories["card_scripts"]
    database = asset_lock.repositories["card_database"]
    script_files = scripts["required_files"]
    database_files = database["required_files"]
    environment = {
        "project": {
            "replay_schema": "0.3a",
            "bridge_protocol": PROTOCOL_VERSION,
            "snapshot_schema": SNAPSHOT_SCHEMA_VERSION,
        },
        "core": {
            "api": f"{core_lock.api['major']}.{core_lock.api['minor']}",
            "binary_sha256": build["binary"]["sha256"],
            "custom_patches": [],
            "lock_id": core_lock.lock_id,
            "source_commit": core_lock.source["commit"],
        },
        "assets": {
            "lock_id": asset_lock.lock_id,
            "card_scripts_commit": scripts["commit"],
            "card_database_commit": database["commit"],
            "constant_sha256": script_files["constant.lua"]["sha256"],
            "utility_sha256": script_files["utility.lua"]["sha256"],
            "database_sha256": database_files["cards.cdb"]["sha256"],
        },
        "instrumentation": {
            "direct_random_trace": to_canonical_data(
                direct_random_trace
                if direct_random_trace is not None
                else direct_random_trace_metadata(enabled=True)
            )
        },
    }
    if fixture_script is not None:
        environment["fixture_script"] = to_canonical_data(fixture_script)
    randomness = {
        "core_seed": list(DUEL_SEED),
        "interruption_sampling": interruption_sampling,
        **(
            {"opening_hand_sampling": to_canonical_data(opening_hand_sampling)}
            if opening_hand_sampling is not None
            else {}
        ),
        "python_random_used": False,
        "python_seed": None,
        "trace_policy": RANDOM_TRACE_POLICY,
    }
    resolved_hands = (
        to_canonical_data(fixed_hands)
        if fixed_hands is not None
        else {
            "0": [EFFECT_VEILER_CODE] * player0_hand_count,
            "1": [EFFECT_VEILER_CODE],
        }
    )
    initial_conditions = {
        "deck_order_in_snapshot": deck_order_in_snapshot,
        **(
            {
                "opening_hand_kind": "probability_distribution",
                "sampled_hands": resolved_hands,
            }
            if snapshot_kind == InformationMode.SAMPLED_PRIVATE_STATE.value
            else {"fixed_hands": resolved_hands}
        ),
        "information_policy_id": information_policy_id,
        **(
            {"initial_field": to_canonical_data(initial_field)}
            if initial_field is not None
            else {}
        ),
        "snapshot_hash": initial_snapshot_hash,
        "snapshot_kind": snapshot_kind,
        "starting_player": 0,
    }
    return ReplayManifestV03a(
        environment=environment,
        randomness=randomness,
        rules={
            "duel_flags": 0,
            "forbidden_limited_list": "none-fixed-scenario",
            "master_rule": "ocgcore-duel-flags:0",
            "unsafe_lua_libraries": False,
        },
        initial_conditions=initial_conditions,
    )


def _snapshot_card_fields(
    snapshot: Any,
    *,
    controller: int,
    location: int,
    slot: int = 0,
) -> dict[str, Any]:
    zone = next(
        (
            zone
            for zone in snapshot.zones
            if zone.get("controller") == controller
            and zone.get("location") == location
        ),
        None,
    )
    if not isinstance(zone, Mapping):
        raise ValueError("temporary observation could not find query zone")
    cards = zone.get("cards")
    if not isinstance(cards, (list, tuple)) or not 0 <= slot < len(cards):
        raise ValueError("temporary observation query slot is unavailable")
    card = cards[slot]
    if not isinstance(card, Mapping):
        raise ValueError("temporary observation query slot has no card")
    fields = {
        item["name"]: item["value"]
        for item in card.get("fields", [])
        if isinstance(item, Mapping)
        and isinstance(item.get("name"), str)
        and "value" in item
    }
    required = {"attack", "base_attack", "code", "status"}
    if not required <= set(fields):
        raise ValueError(
            f"temporary observation is missing query fields: {sorted(required - set(fields))}"
        )
    return {
        "attack": fields["attack"],
        "base_attack": fields["base_attack"],
        "code": fields["code"],
        "controller": controller,
        "instance_key": card.get("instance_key"),
        "location": location,
        "slot": slot,
        "status": fields["status"],
    }


def _temporary_observation_point(
    snapshot: Any,
    *,
    checkpoint_step: int,
    turn: int,
    phase: str,
    location: int,
    value_kind: str,
) -> dict[str, Any]:
    card = _snapshot_card_fields(
        snapshot,
        controller=0,
        location=location,
    )
    if value_kind == "attack_delta":
        value = int(card["attack"]) - int(card["base_attack"])
    elif value_kind == "effect_disabled":
        value = 1 if int(card["status"]) & STATUS_DISABLED else 0
    else:
        raise ValueError(f"unsupported temporary observation kind {value_kind!r}")
    return {
        "card": card,
        "checkpoint_step": checkpoint_step,
        "phase": phase,
        "state_hash": snapshot.state_hash,
        "turn": turn,
        "value": value,
    }


def _build_real_core_temporary_observation(
    *,
    fixture_script_id: str | None,
    fixture_script_metadata: Mapping[str, Any] | None,
    interruption_plan: _InterruptionPlan | None,
    initial_snapshot: Any,
    checkpoint_snapshots: list[tuple[Any, int, str]],
    temporary_checkpoint_step: int,
    terminal_step: int,
    card_script_bytes: bytes,
    card_scripts_commit: str,
) -> dict[str, Any] | None:
    if fixture_script_id in {
        *ACTION_AGGREGATION_FIXTURE_IDS,
        RECOVERY_ATTRIBUTION_FIXTURE_ID,
        INTERRUPTION_MATRIX_FIXTURE_ID,
        INTERRUPTION_EFFECT_NEGATION_FIXTURE_ID,
        INTERRUPTION_SEQUENCE_FIXTURE_ID,
        INTERRUPTION_TIMING_FIXTURE_ID,
    }:
        return None
    if (
        interruption_plan is not None
        and interruption_plan.definition.get("interruption_type")
        != EFFECT_VEILER_INTERRUPTION_TYPE
    ):
        return None
    if fixture_script_id is None and interruption_plan is None:
        return None
    active_snapshot, active_turn, active_phase = checkpoint_snapshots[
        temporary_checkpoint_step
    ]
    expired_snapshot, expired_turn, expired_phase = checkpoint_snapshots[terminal_step]
    expiration = ConstraintExpiration(
        boundary=ExpirationBoundary.END_OF_TURN,
        turn=1,
    )
    if fixture_script_id is not None:
        assert fixture_script_metadata is not None
        baseline = _temporary_observation_point(
            initial_snapshot,
            checkpoint_step=-1,
            turn=1,
            phase="main1",
            location=LOCATION_HAND,
            value_kind="attack_delta",
        )
        modifier_kind = "attack_delta"
        metric = "attack"
        source_ref = {
            **to_canonical_data(fixture_script_metadata),
            "evidence_kind": "pinned_fixture_script_plus_query_transition",
        }
    else:
        assert interruption_plan is not None
        baseline_step = max(0, interruption_plan.target.step - 1)
        baseline_snapshot, baseline_turn, baseline_phase = checkpoint_snapshots[
            baseline_step
        ]
        baseline = _temporary_observation_point(
            baseline_snapshot,
            checkpoint_step=baseline_step,
            turn=baseline_turn,
            phase=baseline_phase,
            location=0x04,
            value_kind="effect_disabled",
        )
        modifier_kind = "effect_disabled"
        metric = "effect_disabled"
        source_ref = {
            "card_code": EFFECT_VEILER_CODE,
            "card_scripts_commit": card_scripts_commit,
            "evidence_kind": "pinned_card_script_plus_query_transition",
            "reset_expression": "RESETS_STANDARD_PHASE_END",
            "script_name": f"c{EFFECT_VEILER_CODE}.lua",
            "script_sha256": hashlib.sha256(card_script_bytes).hexdigest(),
            "status_mask": STATUS_DISABLED,
        }
    active = _temporary_observation_point(
        active_snapshot,
        checkpoint_step=temporary_checkpoint_step,
        turn=active_turn,
        phase=active_phase,
        location=0x04,
        value_kind=modifier_kind,
    )
    expired = _temporary_observation_point(
        expired_snapshot,
        checkpoint_step=terminal_step,
        turn=expired_turn,
        phase=expired_phase,
        location=0x04,
        value_kind=modifier_kind,
    )
    observation = build_temporary_modifier_observation(
        component_id=(
            "attack:temporary_fixture"
            if fixture_script_id is not None
            else "effect_disabled:effect_veiler"
        ),
        modifier_kind=modifier_kind,
        metric=metric,
        baseline=baseline,
        active=active,
        expired=expired,
        expiration=expiration,
        source_ref=source_ref,
    )
    if observation["boundary_evidence"] != "observed_expired":
        raise ValueError(
            "real-core temporary fixture did not produce an observed active/expired transition"
        )
    return observation


def run_real_core_worker(
    *,
    external_root: str | Path | None = None,
    experiment: Mapping[str, Any] | None = None,
    experiment_path: str | Path | None = None,
    action_prefix: Sequence[Mapping[str, Any]] = (),
    source_route: Mapping[str, Any] | None = None,
    viewer: int = 0,
    stress_failure: str | None = None,
    document_kind: str = "route",
) -> dict[str, Any]:
    if document_kind not in REAL_CORE_DOCUMENT_KINDS:
        raise ValueError(f"unsupported real-core document kind {document_kind!r}")
    if stress_failure not in {None, "callback_error"}:
        raise ValueError(f"unsupported real-core stress failure {stress_failure!r}")
    frontier_mode = document_kind == "search_frontier"
    player_view_mode = document_kind == "player_view"
    prefix_mode = frontier_mode or player_view_mode
    if player_view_mode:
        if viewer not in (0, 1):
            raise ValueError("PlayerView viewer must be 0 or 1")
        if not isinstance(source_route, Mapping):
            raise ValueError("PlayerView requires a complete source Route")
    elif source_route is not None:
        raise ValueError("source_route is only valid for PlayerView generation")
    scenario_manifest = None
    if prefix_mode:
        if experiment is None:
            raise ValueError("prefix replay requires an Experiment 0.4 document")
        experiment = deepcopy(dict(experiment))
        assert_current_experiment(experiment)
        preflight = preflight_scenario(
            experiment,
            experiment_path=experiment_path,
            external_root=external_root,
        )
        if not preflight.ok or preflight.manifest is None:
            raise ValueError(
                "scenario preflight failed: "
                + canonical_json(preflight.to_dict())
            )
        scenario_manifest = preflight.manifest
        if experiment["information_mode"] != "complete_information":
            raise ValueError(
                "fresh complete-information Replay is required before PlayerView projection"
            )
        if experiment["interruption"].get("mode") not in {"none", "specified"}:
            raise ValueError(
                "arbitrary-deck frontier supports interruption.mode=none or specified"
            )
    else:
        experiment = _resolved_real_experiment(experiment)
    fixture_script_id = _fixture_script_id(experiment)
    card_instance_provenance_version = _card_instance_provenance_version(experiment)
    card_instance_v2_enabled = card_instance_provenance_version == "v2"
    if document_kind == "activation_rollback_probe":
        if fixture_script_id != ACTIVATION_ROLLBACK_FIXTURE_ID:
            raise ValueError(
                "activation rollback probe requires "
                f"runner.fixture_script_id={ACTIVATION_ROLLBACK_FIXTURE_ID}"
            )
    elif fixture_script_id == ACTIVATION_ROLLBACK_FIXTURE_ID:
        raise ValueError(
            "activation rollback fixture produces probe evidence, not a Route"
        )
    fixture_scripts = _fixture_scripts(fixture_script_id)
    fixture_script_bytes = _fixture_script_bytes(fixture_script_id)
    fixture_script_metadata = _fixture_script_metadata(
        fixture_script_id,
        fixture_script_bytes,
    )
    direct_random_instrumentation = direct_random_trace_metadata(enabled=True)
    recovery_card_present = _recovery_card_present(experiment)
    specified_definitions = (
        list(experiment["interruption"]["definitions"])
        if prefix_mode and experiment["interruption"].get("mode") == "specified"
        else []
    )
    specified_hand_cards = [
        int(definition["source_card_code"])
        for definition in specified_definitions
        if definition.get("source_player") == 1
        and definition.get("source_zone", "hand") == "hand"
    ]
    default_hands = (
        {"0": list(scenario_manifest.opening_hand), "1": specified_hand_cards}
        if scenario_manifest is not None
        else _fixed_hands(
            fixture_script_id,
            recovery_card_present=recovery_card_present,
        )
    )
    initial_field = _fixture_initial_field(fixture_script_id)
    if scenario_manifest is not None and scenario_manifest.initial_state is not None:
        location_values = {
            "monster_zone": LOCATION_MZONE,
            "spell_trap_zone": LOCATION_SZONE,
            "graveyard": LOCATION_GRAVE,
            "banished": LOCATION_REMOVED,
        }
        position_values = {
            "face_up_attack": POSITION_FACEUP_ATTACK,
            "face_down_attack": POSITION_FACEDOWN_ATTACK,
            "face_up_defense": POSITION_FACEUP_DEFENSE,
            "face_down_defense": POSITION_FACEDOWN_DEFENSE,
        }
        for card in scenario_manifest.initial_state["public_cards"]:
            initial_field.append(
                {
                    "code": int(card["card_code"]),
                    "controller": int(card["controller"]),
                    "location": location_values[str(card["location"])],
                    "owner": int(card["owner"]),
                    "position": position_values[str(card["position"])],
                    "sequence": int(card["sequence"]),
                }
            )
    if prefix_mode:
        for definition in specified_definitions:
            if definition.get("source_zone", "hand") != "field":
                continue
            location = definition.get("core_location")
            if location not in {LOCATION_MZONE, LOCATION_SZONE}:
                raise ValueError(
                    "specified field interruption requires core_location 4 or 8"
                )
            initial_field.append(
                {
                    "code": int(definition["source_card_code"]),
                    "controller": int(definition["source_player"]),
                    "location": int(location),
                    "position": int(
                        definition.get("position", POSITION_FACEUP_ATTACK)
                    ),
                    "sequence": int(definition.get("sequence", 0)),
                }
            )
    scenario_id = (
        f"general_search:{experiment['experiment_id']}"
        if prefix_mode
        else _scenario_id(fixture_script_id)
    )
    interruption_plans = [] if prefix_mode else _resolve_interruption_plans(experiment)
    interruption_executions = [
        _InterruptionExecution(plan=plan) for plan in interruption_plans
    ]
    interruption_by_definition = {
        execution.plan.definition_index: execution
        for execution in interruption_executions
    }
    information_policy = InformationAccessPolicy.from_experiment(experiment)
    opening_hand_plan = _resolve_opening_hand_plan(information_policy, default_hands)
    fixed_hands = opening_hand_plan.hands
    player0_hand_count = len(fixed_hands["0"])
    information_policy_id = str(information_policy.to_dict()["policy_id"])
    information_audit = InformationAccessAudit(information_policy)
    if information_policy.information_mode == InformationMode.COMPLETE_INFORMATION:
        information_audit.require(
            InformationField.DECK_ORDER,
            owner=0,
            purpose="initialize fixed real-core deck order",
        )
    else:
        information_audit.require(
            InformationField.PROBABILITY_DISTRIBUTION,
            owner=None,
            purpose="sample hidden real-core opening hand",
        )
    information_audit.require(
        InformationField.HAND_IDENTITY,
        owner=0,
        purpose="initialize fixed real-core opening hand",
    )
    information_audit.require(
        InformationField.HAND_IDENTITY,
        owner=1,
        purpose=(
            "initialize fixed or sampled real-core interruption hand"
            if opening_hand_plan.sampling_evidence is not None
            else "initialize fixed real-core interruption hand"
        ),
    )
    information_audit.require(
        InformationField.PUBLIC_STATE,
        owner=None,
        purpose="capture and evaluate replay checkpoints",
    )
    response_budget = int(experiment["search"]["budget"].get("max_nodes", 32))
    core_lock = load_ocgcore_lock()
    asset_lock = load_ocgcore_asset_lock()
    core_verification = verify_ocgcore(external_root=external_root)
    runtime = resolve_ocgcore_runtime(external_root=external_root)
    assets = resolve_ocgcore_assets(external_root=external_root)
    build = core_verification["build"]
    if build is None:
        raise ValueError("the fixed real-core scenario requires a built ocgcore runtime")
    version_metadata = {
        "ocgcore_api": f"{core_lock.api['major']}.{core_lock.api['minor']}",
        "ocgcore_binary_sha256": build["binary"]["sha256"],
        "ocgcore_lock_id": core_lock.lock_id,
        "asset_lock_id": asset_lock.lock_id,
        "card_scripts_commit": asset_lock.repositories["card_scripts"]["commit"],
        "card_database_commit": asset_lock.repositories["card_database"]["commit"],
        "decision_protocol": PROTOCOL_VERSION,
        "snapshot_schema": SNAPSHOT_SCHEMA_VERSION,
        "direct_random_trace": direct_random_instrumentation,
    }
    if scenario_manifest is not None:
        version_metadata["scenario_manifest"] = scenario_manifest.to_dict()
    card_instance_scope_id: str | None = None
    card_instance_tracker: CardInstanceTrackerV2 | None = None
    if card_instance_v2_enabled:
        card_instance_scope_id = build_card_instance_scope_id_v2(
            {
                "asset_lock_id": asset_lock.lock_id,
                "core_lock_id": core_lock.lock_id,
                "fixture_script_sha256": (
                    fixture_script_metadata["sha256"]
                    if fixture_script_metadata is not None
                    else None
                ),
                "initial_field": initial_field,
                "instrumentation_sha256": hashlib.sha256(
                    CARD_INSTANCE_TRACE_V2_LUA_SOURCE
                ).hexdigest(),
                "ocgcore_binary_sha256": build["binary"]["sha256"],
                "scenario_id": scenario_id,
                "seed": list(DUEL_SEED),
            }
        )
        card_instance_tracker = CardInstanceTrackerV2(
            scope_id=card_instance_scope_id
        )
        version_metadata["card_instance_provenance"] = {
            "provenance_schema": CARD_INSTANCE_PROVENANCE_V2_SCHEMA_VERSION,
            "scope_id": card_instance_scope_id,
            "trace_schema": CARD_INSTANCE_TRACE_V2_SCHEMA_VERSION,
            "instrumentation_sha256": hashlib.sha256(
                CARD_INSTANCE_TRACE_V2_LUA_SOURCE
            ).hexdigest(),
        }
    if fixture_script_metadata is not None:
        version_metadata["fixture_script_id"] = fixture_script_metadata["id"]
        version_metadata["fixture_script_sha256"] = fixture_script_metadata["sha256"]
    environment = {
        **version_metadata,
        "scenario_id": scenario_id,
        "seed": list(DUEL_SEED),
    }
    player = PlayerConfig(
        starting_lp=8000,
        starting_draw_count=0,
        draw_count_per_turn=0,
    )
    decoder = OcgcoreMessageDecoder()
    events: list[ReplayEventV03a] = []
    checkpoint_snapshots: list[tuple[Any, int, str]] = []
    request_signatures: list[str] = []

    with OcgcoreLibrary(runtime) as library:
        with SQLiteCardDataProvider(assets.database_path) as card_data:
            fixture_script_metadata = _fixture_metadata_with_card_rows(
                fixture_script_id,
                fixture_script_metadata,
                card_data,
            )
            scripts = CardScriptsProvider(
                assets.scripts_root,
                profile_id=card_scripts_profile_for_experiment_schema(
                    str(experiment["schema_version"])
                ),
            )
            base_scripts = (
                _FixtureScriptProvider(scripts, fixture_scripts)
                if fixture_scripts
                else scripts
            )
            effective_scripts = (
                CardInstanceAuditedScriptProvider(base_scripts)
                if card_instance_v2_enabled
                else base_scripts
            )
            representative_code = (
                scenario_manifest.sections["main"][0]
                if scenario_manifest is not None
                else EFFECT_VEILER_CODE
            )
            card_script_bytes = effective_scripts.get_script(
                f"c{representative_code}.lua"
            )
            config = DuelConfig(seed=DUEL_SEED, team1=player, team2=player)
            effective_card_data = (
                _StressFailingCardDataProvider()
                if stress_failure == "callback_error"
                else card_data
            )
            with library.create_duel(
                config, effective_card_data, effective_scripts
            ) as duel:
                duel.load_script_resolution(
                    resolve_script(effective_scripts, "constant.lua")
                )
                duel.load_script_resolution(
                    resolve_script(effective_scripts, "utility.lua")
                )
                duel.load_script(
                    DIRECT_RANDOM_TRACE_SCRIPT_NAME,
                    DIRECT_RANDOM_TRACE_LUA_SOURCE,
                )
                if card_instance_v2_enabled:
                    duel.load_script(
                        CARD_INSTANCE_TRACE_V2_SCRIPT_NAME,
                        CARD_INSTANCE_TRACE_V2_LUA_SOURCE,
                    )
                for controller in (0, 1):
                    for sequence, code in enumerate(fixed_hands[str(controller)]):
                        duel.add_card(
                            NewCard(
                                team=controller,
                                duelist=0,
                                code=code,
                                controller=controller,
                                location=LOCATION_HAND,
                                sequence=sequence,
                                position=POSITION_FACEUP_ATTACK,
                            )
                        )
                if scenario_manifest is not None:
                    remaining_main = list(scenario_manifest.sections["main"])
                    for code in fixed_hands["0"]:
                        try:
                            remaining_main.remove(code)
                        except ValueError as exc:
                            raise ValueError(
                                f"opening hand card {code} is absent from normalized main deck"
                            ) from exc
                    for sequence, code in enumerate(remaining_main):
                        duel.add_card(
                            NewCard(
                                team=0,
                                duelist=0,
                                code=code,
                                controller=0,
                                location=LOCATION_DECK,
                                sequence=sequence,
                                position=POSITION_FACEDOWN_DEFENSE,
                            )
                        )
                    for sequence, code in enumerate(
                        scenario_manifest.sections["extra"]
                    ):
                        duel.add_card(
                            NewCard(
                                team=0,
                                duelist=0,
                                code=code,
                                controller=0,
                                location=LOCATION_EXTRA,
                                sequence=sequence,
                                position=POSITION_FACEDOWN_DEFENSE,
                            )
                        )
                for card in initial_field:
                    duel.add_card(
                        NewCard(
                            team=card.get("owner", card["controller"]),
                            duelist=0,
                            code=card["code"],
                            controller=card["controller"],
                            location=card["location"],
                            sequence=card["sequence"],
                            position=card["position"],
                        )
                    )
                duel.start()
                initial_batch = _decode_batch(
                    decoder,
                    duel.process(),
                    0,
                    scenario_id=scenario_id,
                    card_instance_tracker=card_instance_tracker,
                    card_instance_duel=duel,
                )
                request = initial_batch.request
                assert request is not None
                current_snapshot = duel.capture_snapshot(
                    pending_request=request,
                    environment=environment,
                    information_mode=information_policy.information_mode,
                    sampling_reference=information_policy.sampling_reference,
                )
                if card_instance_tracker is not None:
                    current_snapshot = card_instance_tracker.enrich_snapshot(
                        current_snapshot
                    )
                initial_snapshot_object = current_snapshot
                initial_snapshot = current_snapshot.to_dict()
                initial_core_output = build_core_output_trace(
                    initial_batch,
                    snapshot=initial_snapshot,
                )
                current_turn, current_phase = _apply_progress_events(
                    initial_core_output, 0, "pre_duel"
                )
                initial_turn = current_turn
                initial_phase = current_phase
                if (
                    not prefix_mode
                    and (current_turn != 1 or current_phase != "main1")
                ):
                    raise ValueError(
                        "fixed real-core scenario did not start at turn 1 main1; "
                        f"observed turn={current_turn} phase={current_phase!r}"
                    )
                replay_manifest = _real_replay_manifest(
                    core_lock=core_lock,
                    asset_lock=asset_lock,
                    build=build,
                    information_policy_id=information_policy_id,
                    interruption_sampling=(
                        next(
                            (
                                plan.sampling_evidence
                                for plan in interruption_plans
                                if plan.sampling_evidence is not None
                            ),
                            None,
                        )
                    ),
                    initial_snapshot_hash=current_snapshot.state_hash,
                    opening_hand_sampling=opening_hand_plan.sampling_evidence,
                    snapshot_kind=opening_hand_plan.snapshot_kind,
                    deck_order_in_snapshot=(
                        information_policy.deck_order == DeckOrderKnowledge.KNOWN
                    ),
                    player0_hand_count=player0_hand_count,
                    fixed_hands=(
                        fixed_hands
                        if opening_hand_plan.sampling_evidence is not None
                        or fixture_script_id
                        in {
                            RECOVERY_ATTRIBUTION_FIXTURE_ID,
                            *GENERIC_INTERRUPTION_FIXTURE_IDS,
                        }
                        else None
                    ),
                    initial_field=(
                        initial_field
                        if fixture_script_id in GENERIC_INTERRUPTION_FIXTURE_IDS
                        else None
                    ),
                    fixture_script=fixture_script_metadata,
                    direct_random_trace=direct_random_instrumentation,
                )
                if scenario_manifest is not None:
                    replay_manifest = ReplayManifestV03a(
                        environment={
                            **replay_manifest.environment,
                            "scenario_manifest": scenario_manifest.to_dict(),
                        },
                        randomness=replay_manifest.randomness,
                        rules=replay_manifest.rules,
                        initial_conditions={
                            **replay_manifest.initial_conditions,
                            "normalized_deck_sha256": scenario_manifest.deck_sha256,
                        },
                    )
                summoned = False
                end_turn_submitted = False
                aggregation_effect_activated = False
                aggregation_cost_count = 0
                aggregation_target_selected = False
                aggregation_resolution_card_selected = False
                aggregation_option_selected = False
                recovery_primary_activated = False
                recovery_card_activated = False
                matrix_primary_activated = False
                matrix_secondary_activated = False
                temporary_checkpoint_step: int | None = None
                turn_action_index = 0
                frontier_actions_at_stop: tuple[Action, ...] = ()
                frontier_legal_stop = None
                frontier_limit = int(
                    experiment["search"].get("parameters", {}).get(
                        "max_frontier_actions", 256
                    )
                )
                while True:
                    if len(events) >= response_budget:
                        raise ValueError(
                            "fixed real-core scenario exceeded its response budget"
                        )
                    legal_stop = evaluate_legal_stop(current_snapshot)
                    available_frontier_actions = (
                        _frontier_actions(request, limit=frontier_limit)
                        if frontier_mode
                        else ()
                    )
                    if prefix_mode and len(events) == len(action_prefix):
                        if legal_stop.can_stop and events:
                            final_request_signature = request.request_signature
                            temporary_checkpoint_step = len(events) - 1
                            if frontier_mode:
                                frontier_actions_at_stop = available_frontier_actions
                                frontier_legal_stop = legal_stop
                            break
                        if player_view_mode:
                            raise ValueError(
                                "source Route Action prefix did not reach a legal stop"
                            )
                        return _frontier_document(
                            request=request,
                            actions=available_frontier_actions,
                            snapshot=current_snapshot,
                            checkpoint_snapshots=checkpoint_snapshots,
                            experiment=experiment,
                            turn=current_turn,
                            phase=current_phase,
                            legal_stop=legal_stop,
                            route_document=None,
                            action_prefix=action_prefix,
                        )
                    if summoned and legal_stop.can_stop:
                        if not end_turn_submitted:
                            if not events:
                                raise ValueError(
                                    "temporary legal stop has no replay checkpoint"
                                )
                            temporary_checkpoint_step = len(events) - 1
                        elif current_turn >= 2 and current_phase == "main1":
                            final_request_signature = request.request_signature
                            break
                    if prefix_mode:
                        if len(events) >= len(action_prefix):
                            raise ValueError("Action prefix Replay advanced past its target")
                        expected_action = action_prefix[len(events)]
                        if not isinstance(expected_action, Mapping):
                            raise ValueError("Action prefix entries must be mappings")
                        candidates, selection_role = _prefix_candidates(
                            request,
                            expected_action,
                            specified_interruption=(
                                experiment.get("interruption", {}).get("mode")
                                == "specified"
                            ),
                        )
                    else:
                        candidates, selection_role = _selected_candidate(
                            request,
                            fixture_script_id=fixture_script_id,
                            summoned=summoned,
                            end_turn_submitted=end_turn_submitted,
                            interruption_executions=interruption_executions,
                            aggregation_effect_activated=aggregation_effect_activated,
                            aggregation_cost_count=aggregation_cost_count,
                            aggregation_target_selected=aggregation_target_selected,
                            aggregation_resolution_card_selected=(
                                aggregation_resolution_card_selected
                            ),
                            aggregation_option_selected=aggregation_option_selected,
                            recovery_primary_activated=recovery_primary_activated,
                            recovery_card_activated=recovery_card_activated,
                            matrix_primary_activated=matrix_primary_activated,
                            matrix_secondary_activated=matrix_secondary_activated,
                            events=events,
                            state_hash_before=current_snapshot.state_hash,
                            turn=current_turn,
                            turn_action_index=turn_action_index,
                            chain_index=int(current_snapshot.field_state["chain_count"]),
                        )
                    is_activation_rollback_cancel = (
                        selection_role == "activation_rollback_cancel"
                    )
                    if not candidates and not is_activation_rollback_cancel:
                        raise ValueError(
                            "fixed real-core scenario stopped before a legal checkpoint"
                        )
                    if is_activation_rollback_cancel:
                        action_kind = ActionKind.DECLINE
                    else:
                        action_kinds = {
                            _action_kind(request, candidate)
                            for candidate in candidates
                        }
                        if len(action_kinds) != 1:
                            raise ValueError(
                                "one core response cannot mix candidate Action kinds"
                            )
                        action_kind = next(iter(action_kinds))
                    candidate_card_refs = tuple(
                        _candidate_card_ref(
                            candidate,
                            require_instance=card_instance_tracker is not None,
                        )
                        for candidate in candidates
                    )
                    action = Action(
                        kind=action_kind,
                        player=request.player,
                        selections=tuple(
                            Selection(
                                candidate_id=candidate.candidate_id,
                                card_ref=card_ref,
                                payload_ref="candidate.payload",
                            )
                            for candidate, card_ref in zip(
                                candidates, candidate_card_refs, strict=True
                            )
                        ),
                        request_signature=request.request_signature,
                        source=(
                            candidate_card_refs[0]
                            if selection_role is not None
                            and (
                                selection_role.startswith(
                                    "interruption_activation:"
                                )
                                or selection_role
                                in {
                                "aggregation_activation",
                                "recovery_primary_activation",
                                "recovery_card_activation",
                                "matrix_primary_activation",
                                "matrix_secondary_activation",
                                }
                            )
                            else None
                        ),
                    )
                    if prefix_mode and action.action_id != expected_action.get(
                        "action_id"
                    ):
                        raise ValueError(
                            "Action prefix identity changed during fresh Replay"
                        )
                    encoded = duel.respond_action(request, action)
                    next_batch = _decode_batch(
                        decoder,
                        duel.process(),
                        len(events) + 1,
                        scenario_id=scenario_id,
                        card_instance_tracker=card_instance_tracker,
                        card_instance_duel=duel,
                    )
                    next_request = next_batch.request
                    assert next_request is not None
                    next_snapshot = duel.capture_snapshot(
                        pending_request=next_request,
                        environment=environment,
                        information_mode=information_policy.information_mode,
                        sampling_reference=information_policy.sampling_reference,
                    )
                    if card_instance_tracker is not None:
                        next_snapshot = card_instance_tracker.enrich_snapshot(
                            next_snapshot
                        )
                    trace = encoded.to_trace_dict()
                    core_output = build_core_output_trace(
                        next_batch,
                        snapshot=next_snapshot.to_dict(),
                    )
                    action_turn = current_turn
                    action_turn_index = turn_action_index
                    next_turn, next_phase = _apply_progress_events(
                        core_output, current_turn, current_phase
                    )
                    step = len(events)
                    events.append(
                        ReplayEventV03a(
                            step=step,
                            request_signature=request.request_signature,
                            action=action,
                            node_id=f"real_core_node_{step}",
                            request=request.to_dict(),
                            core_input_ref=stable_digest(trace, prefix="input_"),
                            core_response=trace,
                            core_output=core_output,
                            state_hash_before=current_snapshot.state_hash,
                            state_hash_after=next_snapshot.state_hash,
                            turn=action_turn,
                            turn_action_index=action_turn_index,
                            chain_index=int(current_snapshot.field_state["chain_count"]),
                        )
                    )
                    checkpoint_snapshots.append(
                        (next_snapshot, next_turn, next_phase)
                    )
                    request_signatures.append(request.request_signature)
                    if is_activation_rollback_cancel:
                        diagnostics = [
                            {
                                "category": item.category,
                                "context": item.context,
                                "message": item.message,
                                "severity": item.severity,
                            }
                            for item in duel.diagnostics
                            if not item.message.startswith(
                                CARD_INSTANCE_TRACE_V2_LOG_PREFIX
                            )
                        ]
                        if any(
                            item["severity"] == "error" for item in diagnostics
                        ):
                            raise ValueError(
                                f"ocgcore emitted error diagnostics: {diagnostics}"
                            )
                        activation_event = next(
                            (
                                event
                                for event in reversed(events[:-1])
                                if event.action.kind == ActionKind.ACTIVATE_EFFECT
                            ),
                            None,
                        )
                        if activation_event is None:
                            raise ValueError(
                                "activation rollback probe has no activation event"
                            )
                        return build_activation_rollback_probe(
                            activation_event=activation_event.to_dict(),
                            cancellation_action=action.to_dict(),
                            cancellation_request=request.to_dict(),
                            cancellation_response=trace,
                            followup_core_output=core_output,
                            manifest=replay_manifest.to_dict(),
                            next_request=next_request.to_dict(),
                            state_after={
                                "chain_count": int(
                                    next_snapshot.field_state["chain_count"]
                                ),
                                "state_hash": next_snapshot.state_hash,
                            },
                            state_before={
                                "chain_count": int(
                                    current_snapshot.field_state["chain_count"]
                                ),
                                "state_hash": current_snapshot.state_hash,
                            },
                        )
                    if action_kind == ActionKind.NORMAL_SUMMON:
                        summoned = True
                    if action_kind == ActionKind.END_TURN:
                        end_turn_submitted = True
                    if selection_role is not None and selection_role.startswith(
                        "interruption_activation:"
                    ):
                        _, raw_definition_index = selection_role.split(":", 1)
                        execution = interruption_by_definition[
                            int(raw_definition_index)
                        ]
                        if execution.activated:
                            raise ValueError(
                                "interruption activation was selected more than once"
                            )
                        execution.activated = True
                        execution.activation_step = step
                    elif selection_role is not None and selection_role.startswith(
                        "interruption_response:"
                    ):
                        (
                            _,
                            raw_definition_index,
                            raw_index,
                            response_role,
                        ) = selection_role.split(":", 3)
                        execution = interruption_by_definition[
                            int(raw_definition_index)
                        ]
                        response_index = int(raw_index)
                        if response_index != execution.response_index:
                            raise ValueError(
                                "interruption response index is not contiguous"
                            )
                        execution.response_steps.append(
                            {
                                "action_step": step,
                                "candidate_ids": [
                                    candidate.candidate_id for candidate in candidates
                                ],
                                "response_index": response_index,
                                "role": response_role,
                            }
                        )
                        execution.response_index += 1
                        if response_role == "target":
                            execution.target_selection_step = step
                    elif selection_role == "aggregation_activation":
                        aggregation_effect_activated = True
                    elif selection_role == "aggregation_cost":
                        aggregation_cost_count += 1
                    elif selection_role == "aggregation_target":
                        aggregation_target_selected = True
                    elif selection_role == "aggregation_resolution_card":
                        aggregation_resolution_card_selected = True
                    elif selection_role == "aggregation_option":
                        aggregation_option_selected = True
                    elif selection_role == "recovery_primary_activation":
                        recovery_primary_activated = True
                    elif selection_role == "recovery_card_activation":
                        recovery_card_activated = True
                    elif selection_role == "matrix_primary_activation":
                        matrix_primary_activated = True
                    elif selection_role == "matrix_secondary_activation":
                        matrix_secondary_activated = True
                    turn_action_index = (
                        0 if next_turn != action_turn else action_turn_index + 1
                    )
                    request = next_request
                    current_snapshot = next_snapshot
                    current_turn = next_turn
                    current_phase = next_phase
                diagnostics = [
                    {
                        "category": item.category,
                        "context": item.context,
                        "message": item.message,
                        "severity": item.severity,
                    }
                    for item in duel.diagnostics
                    if not item.message.startswith(CARD_INSTANCE_TRACE_V2_LOG_PREFIX)
                ]
                if any(item["severity"] == "error" for item in diagnostics):
                    raise ValueError(f"ocgcore emitted error diagnostics: {diagnostics}")

    if not events:
        raise ValueError("fixed real-core scenario produced no replay events")
    if any(
        not execution.activated
        or execution.response_index
        != len(execution.plan.candidate_policy.responses)
        for execution in interruption_executions
    ):
        raise _interruption_error(
            "$.interruption.definitions",
            "configured interruption did not complete its candidate policy",
        )
    if (
        fixture_script_id in {
            ACTION_AGGREGATION_FIXTURE_ID,
            ACTION_AGGREGATION_SELECTION_FIXTURE_ID,
        }
        and not aggregation_option_selected
    ):
        raise ValueError(
            "action aggregation fixture did not complete cost, target, and option selection"
        )
    if (
        fixture_script_id == RECOVERY_ATTRIBUTION_FIXTURE_ID
        and not recovery_primary_activated
    ):
        raise ValueError("recovery attribution fixture did not activate its primary effect")
    if (
        fixture_script_id in GENERIC_INTERRUPTION_FIXTURE_IDS
        and not matrix_primary_activated
    ):
        raise ValueError("interruption matrix fixture did not activate its primary effect")
    if (
        fixture_script_id == INTERRUPTION_SEQUENCE_FIXTURE_ID
        and not matrix_secondary_activated
    ):
        raise ValueError(
            "interruption sequence fixture did not activate its secondary effect"
        )
    if (
        fixture_script_id == RECOVERY_ATTRIBUTION_FIXTURE_ID
        and recovery_card_present
        and interruption_plans
        and not recovery_card_activated
    ):
        raise ValueError("recovery card was present but did not activate after interruption")
    if (
        fixture_script_id == RECOVERY_ATTRIBUTION_FIXTURE_ID
        and (not recovery_card_present or not interruption_plans)
        and recovery_card_activated
    ):
        raise ValueError("recovery card activated outside its treatment route")
    checkpoints: list[dict[str, Any]] = []
    legal_steps: list[int] = []
    for step, (snapshot, turn, phase) in enumerate(checkpoint_snapshots):
        board = build_board_summary(snapshot, viewer=0).to_dict()
        stop = evaluate_legal_stop(snapshot)
        evaluation_result, success = _evaluation(
            board,
            experiment=experiment,
            state_hash=snapshot.state_hash,
            turn=turn,
            phase=phase,
        )
        if stop.can_stop:
            legal_steps.append(step)
        checkpoints.append(
            {
                "step": step,
                "state_hash": snapshot.state_hash,
                "turn": turn,
                "phase": phase,
                "board_summary": board,
                "evaluation": dict(evaluation_result.vector),
                "evaluation_result": evaluation_result.to_dict(),
                "score": evaluation_result.total_score,
                "success": success,
                "legal_stop": stop.to_dict(),
            }
        )
    if not legal_steps:
        raise ValueError("fixed real-core scenario produced no core-derived legal stop")
    if temporary_checkpoint_step is None:
        raise ValueError("fixed real-core scenario missed the temporary board checkpoint")
    peak_step = max(
        legal_steps,
        key=lambda step: (
            checkpoints[step]["success"],
            checkpoints[step]["score"],
            -step,
        ),
    )
    terminal_step = len(checkpoints) - 1
    durability = (
        None
        if prefix_mode
        else build_durability_report(
            checkpoints[temporary_checkpoint_step], checkpoints[terminal_step]
        )
    )
    terminal_checkpoint = checkpoints[terminal_step]
    temporary_modifier_observation = _build_real_core_temporary_observation(
        fixture_script_id=fixture_script_id,
        fixture_script_metadata=fixture_script_metadata,
        interruption_plan=(
            interruption_plans[0] if len(interruption_plans) == 1 else None
        ),
        initial_snapshot=initial_snapshot_object,
        checkpoint_snapshots=checkpoint_snapshots,
        temporary_checkpoint_step=temporary_checkpoint_step,
        terminal_step=terminal_step,
        card_script_bytes=card_script_bytes,
        card_scripts_commit=asset_lock.repositories["card_scripts"]["commit"],
    )
    terminal_evaluation = terminal_checkpoint["evaluation"]
    persistent_metrics = (
        ("field_count",)
        if "field_count" in terminal_evaluation
        else tuple(sorted(terminal_evaluation))
    )
    value_components = [
        EvaluationValueComponent(
            component_id=f"{metric}:observed_after_turn_boundary",
            metric=metric,
            value=terminal_evaluation[metric],
            permanence=ValuePermanence.PERSISTENT,
            source_ref={
                "checkpoint_step": terminal_step,
                "evidence": "core_state_observed_at_evaluation_boundary",
                "state_hash": terminal_checkpoint["state_hash"],
            },
        )
        for metric in persistent_metrics
    ]
    if temporary_modifier_observation is not None:
        value_components.append(
            EvaluationValueComponent(
                component_id=temporary_modifier_observation["component_id"],
                metric=temporary_modifier_observation["metric"],
                value=abs(
                    temporary_modifier_observation["transition"]["active_delta"]
                ),
                permanence=ValuePermanence.TEMPORARY,
                boundary_evidence=BoundaryEvidence.OBSERVED_EXPIRED,
                expires_at=ConstraintExpiration(
                    boundary=ExpirationBoundary.END_OF_TURN,
                    turn=1,
                ),
                source_ref={
                    "observation_id": temporary_modifier_observation[
                        "observation_id"
                    ],
                    "state_hash": temporary_modifier_observation["points"][
                        "expired"
                    ]["state_hash"],
                },
            )
        )
    temporary_effect_report = build_temporary_effect_report(
        tuple(value_components),
        evaluation_boundary=StateCoordinate(
            turn=terminal_checkpoint["turn"],
            phase=terminal_checkpoint["phase"],
        ),
    )
    replay = ReplayHistoryV03a(
        initial_snapshot=initial_snapshot,
        version_metadata=version_metadata,
        seeds={f"duel_seed_{index}": value for index, value in enumerate(DUEL_SEED)},
        events=tuple(events),
        strict_versions=True,
        manifest=replay_manifest,
        initial_core_output=initial_core_output,
    ).to_dict()
    replay["information_policy_id"] = information_policy_id
    assert_complete_io_trace(replay)
    information_audit.assert_no_leaks()
    information_audit_document = information_audit.to_dict()
    action_aggregation, action_aggregation_evidence = (
        derive_ocgcore_action_aggregation(replay)
    )
    presentation = {
        "action_aggregation": action_aggregation.to_dict(),
        "action_aggregation_evidence": action_aggregation_evidence,
        "validation": {
            "method": OCGCORE_ACTION_AGGREGATION_METHOD,
            "status": "validated",
        },
    }
    if card_instance_tracker is not None:
        presentation["card_instance_provenance"] = (
            card_instance_tracker.provenance_document()
        )
    if fixture_script_id in GENERIC_INTERRUPTION_FIXTURE_IDS:
        presentation["interruption_validation_evidence"] = (
            derive_ocgcore_interruption_validation(replay)
        )
    if experiment.get("interruption", {}).get("mode") == "specified":
        presentation["specified_interruption_trace"] = (
            _specified_interruption_trace(experiment, replay)
        )
    interruption_records = []
    lineage = {"parent_route_id": None, "fork_step": None}
    for execution in interruption_executions:
        plan = execution.plan
        assert execution.activation_step is not None
        interruption_record = {
            "activation_step": execution.activation_step,
            "at_step": plan.target.step,
            "definition_id": plan.definition["id"],
            "interruption_id": plan.definition["id"],
            "mode": plan.mode,
            "sampling": plan.sampling_evidence,
            "source_card_code": plan.definition["source_card_code"],
            "source_player": plan.definition["source_player"],
            "status": "applied_by_core",
            "target": plan.target.to_dict(),
        }
        if execution.target_selection_step is not None:
            interruption_record["target_selection_step"] = (
                execution.target_selection_step
            )
        if plan.explicit_candidate_policy:
            interruption_record["candidate_policy_id"] = (
                plan.candidate_policy.policy_id
            )
            interruption_record["response_steps"] = execution.response_steps
        interruption_records.append(interruption_record)
    if interruption_plans:
        final_plan = interruption_plans[-1]
        lineage = {
            "parent_route_id": final_plan.base_route_id,
            "fork_step": final_plan.target.step,
        }
    lua_script_resolution = duel.script_resolution_manifest
    persist_script_resolution = experiment.get("schema_version") == "0.4"
    route_identity = {
        "experiment": experiment,
        "replay": replay,
        "information_audit": information_audit_document,
        **(
            {"lua_script_resolution": lua_script_resolution}
            if persist_script_resolution
            else {}
        ),
        "peak_state_hash": checkpoints[peak_step]["state_hash"],
        "terminal_state_hash": checkpoints[terminal_step]["state_hash"],
        "final_request_signature": final_request_signature,
    }
    document = {
        "dsl": "ygo-route",
        "schema_version": "0.1",
        "route_id": stable_digest(route_identity, prefix="route_"),
        "status": "complete",
        "experiment": experiment,
        "replay": replay,
        "information_audit": information_audit_document,
        "presentation": presentation,
        "checkpoints": checkpoints,
        "result": {
            "success": bool(checkpoints[peak_step]["success"]),
            "final_request_signature": final_request_signature,
            "request_signatures": [*request_signatures, final_request_signature],
            **(
                {"lua_script_resolution": lua_script_resolution}
                if persist_script_resolution
                else {}
            ),
            "evaluation_explanation": {
                "temporary_effects": temporary_effect_report
            },
            "peak_board": _board_result(checkpoints[peak_step], peak_step),
            "terminal_board": _board_result(
                checkpoints[terminal_step], terminal_step
            ),
            "diagnostics": diagnostics,
        },
        "interruptions": interruption_records,
        "lineage": lineage,
    }
    if durability is not None:
        document["result"]["durability"] = durability
    if temporary_modifier_observation is not None:
        document["result"]["temporary_modifier_observation"] = (
            temporary_modifier_observation
        )
    if card_instance_v2_enabled:
        assert_public_card_instance_document(document)
    assert_valid_route_document(document)
    if player_view_mode:
        assert source_route is not None
        if canonical_json(document) != canonical_json(source_route):
            raise ValueError(
                "source Route differs from the complete Route regenerated by fresh Replay"
            )
        player_view = build_player_view_replay(
            PlayerViewProjectionInput(
                source_route=document,
                initial_snapshot=initial_snapshot_object,
                initial_turn=initial_turn,
                initial_phase=initial_phase,
                checkpoint_snapshots=checkpoint_snapshots,
                events=events,
                viewer=viewer,
            )
        )
        assert_valid_player_view_replay(player_view)
        private_canary_registry = build_player_view_canary_registry(
            source_route=document,
            snapshots=(
                initial_snapshot_object,
                *(snapshot for snapshot, _, _ in checkpoint_snapshots),
            ),
            viewer=viewer,
        )
        information_audit = audit_information_artifact(
            player_view,
            artifact_kind="player_view_replay",
            registry=private_canary_registry,
        )
        verification_identity = {
            "event_count": len(events),
            "information_access_audit_id": information_audit["audit_id"],
            "player_view_id": player_view["player_view_id"],
            "schema_version": PLAYER_VIEW_VERIFICATION_SCHEMA_VERSION,
            "status": "verified",
            "viewer": viewer,
        }
        verification = {
            "verification_id": stable_digest(
                verification_identity, prefix="playerviewverification_"
            ),
            **verification_identity,
        }
        lineage_identity = {
            "player_view_id": player_view["player_view_id"],
            "projector_id": PLAYER_VIEW_PROJECTOR_ID,
            "schema_version": PLAYER_VIEW_LINEAGE_SCHEMA_VERSION,
            "source_replay_digest": stable_digest(
                document["replay"], prefix="replay_"
            ),
            "source_route_id": document["route_id"],
            "verification_id": verification["verification_id"],
            "viewer": viewer,
            "information_access_audit_id": information_audit["audit_id"],
        }
        private_lineage = {
            "lineage_id": stable_digest(
                lineage_identity, prefix="playerviewlineage_"
            ),
            **lineage_identity,
        }
        return {
            "information_audit": information_audit,
            "player_view": player_view,
            "private_canary_registry": private_canary_registry.to_private_dict(),
            "private_lineage": private_lineage,
            "schema_version": REAL_CORE_PLAYER_VIEW_RESULT_SCHEMA_VERSION,
            "verification": verification,
        }
    if frontier_mode:
        if frontier_legal_stop is None:
            raise ValueError("search frontier stopped without a legal-stop decision")
        return _frontier_document(
            request=request,
            actions=frontier_actions_at_stop,
            snapshot=current_snapshot,
            checkpoint_snapshots=checkpoint_snapshots,
            experiment=experiment,
            turn=current_turn,
            phase=current_phase,
            legal_stop=frontier_legal_stop,
            route_document=document,
            action_prefix=action_prefix,
        )
    return document


def _board_result(checkpoint: Mapping[str, Any], step: int) -> dict[str, Any]:
    return {
        "checkpoint_step": step,
        "state_hash": checkpoint["state_hash"],
        "score": checkpoint["score"],
        "evaluation": checkpoint["evaluation"],
        "evaluation_result": checkpoint["evaluation_result"],
        "phase": checkpoint["phase"],
        "success": checkpoint["success"],
        "stop_reason": checkpoint["legal_stop"]["reason"],
        "turn": checkpoint["turn"],
    }


def invoke_real_core_worker_process(
    *,
    external_root: str | Path | None = None,
    experiment: Mapping[str, Any] | None = None,
    stress_failure: str | None = None,
    document_kind: str = "route",
    timeout_seconds: float = WORKER_TIMEOUT_SECONDS,
) -> RealCoreWorkerProcessResult:
    if document_kind not in REAL_CORE_DOCUMENT_KINDS - {"player_view"}:
        raise ValueError(f"unsupported real-core document kind {document_kind!r}")
    if stress_failure not in {None, "worker_crash", "worker_timeout", "callback_error"}:
        raise ValueError(f"unsupported real-core stress failure {stress_failure!r}")
    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be positive")
    command = [
        sys.executable,
        "-m",
        "ygo_effect_dsl.prototype._real_core_worker",
    ]
    if external_root is not None:
        command.extend(["--external-root", str(external_root)])
    if document_kind != "route":
        command.extend(["--document-kind", document_kind])
    worker_input = None
    if experiment is not None:
        command.append("--experiment-stdin")
        worker_input = canonical_json(experiment)
    if stress_failure is not None:
        command.extend(["--stress-failure", stress_failure])
    process = subprocess.Popen(
        command,
        stdin=subprocess.PIPE if worker_input is not None else subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=current_checkout_environment(),
    )
    timed_out = False
    try:
        stdout, stderr = process.communicate(
            input=worker_input,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired:
        timed_out = True
        process.kill()
        stdout, stderr = process.communicate()
    returncode = int(process.returncode if process.returncode is not None else -1)
    diagnostic = stderr.strip() or (stdout.strip() if returncode != 0 else "")
    shared = {
        "process_id": process.pid,
        "returncode": returncode,
        "terminated": process.poll() is not None,
        "stdout_digest": stable_digest(stdout, prefix="workerstdout_"),
        "stderr_digest": stable_digest(stderr, prefix="workerstderr_"),
        "diagnostic": diagnostic,
    }
    if timed_out:
        failure_record = classify_failure(
            OcgcoreWorkerTimeoutError(timeout_seconds)
        )
        return RealCoreWorkerProcessResult(
            document=None,
            timed_out=True,
            failure_category=failure_record.category,
            failure_record=failure_record,
            **shared,
        )
    if returncode != 0:
        failure_record: FailureRecord | None = None
        malformed_failure: str | None = None
        try:
            failure_envelope = json.loads(stdout)
        except json.JSONDecodeError:
            failure_envelope = None
        if isinstance(failure_envelope, Mapping) and (
            "failure" in failure_envelope
            or failure_envelope.get("schema_version")
            == WORKER_FAILURE_ENVELOPE_SCHEMA_VERSION
        ):
            try:
                if set(failure_envelope) != {
                    "failure",
                    "schema_version",
                    "status",
                }:
                    raise ValueError("worker failure envelope has unexpected fields")
                if (
                    failure_envelope["schema_version"]
                    != WORKER_FAILURE_ENVELOPE_SCHEMA_VERSION
                    or failure_envelope["status"] != "failure"
                    or not isinstance(failure_envelope["failure"], Mapping)
                ):
                    raise ValueError("worker failure envelope is malformed")
                failure_record = FailureRecord.from_dict(
                    failure_envelope["failure"]
                )
                if stress_failure == "callback_error":
                    failure_record = FailureRecord(
                        category="callback_error",
                        disposition=failure_record.disposition,
                        recovery=failure_record.recovery,
                        retryable=True,
                        message=failure_record.message,
                        exception_type=failure_record.exception_type,
                        context=failure_record.context,
                    )
            except (KeyError, TypeError, ValueError) as exc:
                malformed_failure = str(exc)
        if malformed_failure is not None:
            protocol_failure = classify_failure(
                OcgcoreWorkerProtocolError(malformed_failure)
            )
            return RealCoreWorkerProcessResult(
                document=None,
                timed_out=False,
                failure_category=protocol_failure.category,
                failure_record=protocol_failure,
                diagnostic=malformed_failure,
                **{
                    key: value
                    for key, value in shared.items()
                    if key != "diagnostic"
                },
            )
        if failure_record is not None:
            return RealCoreWorkerProcessResult(
                document=None,
                timed_out=False,
                failure_category=failure_record.category,
                failure_record=failure_record,
                diagnostic=failure_record.message,
                **{
                    key: value
                    for key, value in shared.items()
                    if key != "diagnostic"
                },
            )
        return RealCoreWorkerProcessResult(
            document=None,
            timed_out=False,
            failure_category=(
                failure_record.category
                if failure_record is not None
                else "worker_crash"
            ),
            failure_record=(
                failure_record
                if failure_record is not None
                else classify_failure(
                    OcgcoreWorkerCrashError(returncode, diagnostic)
                )
            ),
            **shared,
        )
    try:
        document = json.loads(stdout)
        if document_kind == "route":
            assert_valid_route_document(document)
        else:
            assert_valid_activation_rollback_probe(document)
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        failure_record = classify_failure(
            OcgcoreWorkerProtocolError(str(exc))
        )
        return RealCoreWorkerProcessResult(
            document=None,
            timed_out=False,
            failure_category=failure_record.category,
            failure_record=failure_record,
            diagnostic=str(exc),
            **{key: value for key, value in shared.items() if key != "diagnostic"},
        )
    return RealCoreWorkerProcessResult(
        document=document,
        timed_out=False,
        failure_category=None,
        **shared,
    )


def probe_activation_rollback_support(
    *,
    external_root: str | Path | None = None,
    experiment: Mapping[str, Any],
) -> dict[str, Any]:
    result = invoke_real_core_worker_process(
        external_root=external_root,
        experiment=experiment,
        document_kind="activation_rollback_probe",
    )
    if result.failure_category == "worker_timeout":
        raise OcgcoreWorkerTimeoutError(WORKER_TIMEOUT_SECONDS)
    if result.failure_category == "worker_protocol":
        raise OcgcoreWorkerProtocolError(
            "real-core worker returned invalid activation rollback probe: "
            f"{result.diagnostic}"
        )
    if result.failure_record is not None:
        raise FailureRecordError(result.failure_record)
    if not result.succeeded or result.document is None:
        raise OcgcoreWorkerCrashError(result.returncode, result.diagnostic)
    return result.document


def build_real_core_route(
    *,
    external_root: str | Path | None = None,
    experiment: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    result = invoke_real_core_worker_process(
        external_root=external_root,
        experiment=experiment,
    )
    if result.failure_category == "worker_timeout":
        raise OcgcoreWorkerTimeoutError(WORKER_TIMEOUT_SECONDS)
    if result.failure_category == "worker_protocol":
        raise OcgcoreWorkerProtocolError(
            f"real-core worker returned invalid Route JSON: {result.diagnostic}"
        )
    if result.failure_record is not None:
        raise FailureRecordError(result.failure_record)
    if not result.succeeded or result.document is None:
        raise OcgcoreWorkerCrashError(result.returncode, result.diagnostic)
    return result.document


def verify_real_core_route(
    route_document: Mapping[str, Any],
    *,
    external_root: str | Path | None = None,
) -> RealCoreVerificationResult:
    assert_valid_route_document(route_document)
    raw_manifest = route_document.get("replay", {}).get("manifest")
    if not isinstance(raw_manifest, Mapping):
        raise ReplayManifestIncompleteError(
            "real-core replay is missing its reproducibility manifest"
        )
    recorded_manifest = ReplayManifestV03a.from_dict(raw_manifest)
    recorded_manifest.assert_reproducible()
    core_lock = load_ocgcore_lock()
    asset_lock = load_ocgcore_asset_lock()
    core_verification = verify_ocgcore(external_root=external_root)
    build = core_verification["build"]
    if build is None:
        raise ReplayManifestIncompleteError(
            "current environment has no built ocgcore runtime"
        )
    route_experiment = route_document.get("experiment")
    if not isinstance(route_experiment, Mapping):
        raise ReplayManifestIncompleteError("Route is missing its Experiment")
    interruption_plans = _resolve_interruption_plans(route_experiment)
    fixture_script_id = _fixture_script_id(route_experiment)
    fixture_bytes = _fixture_script_bytes(fixture_script_id)
    fixture_script_metadata = _fixture_script_metadata(
        fixture_script_id,
        fixture_bytes,
    )
    assets = resolve_ocgcore_assets(external_root=external_root)
    with SQLiteCardDataProvider(assets.database_path) as card_data:
        fixture_script_metadata = _fixture_metadata_with_card_rows(
            fixture_script_id,
            fixture_script_metadata,
            card_data,
        )
    recovery_card_present = _recovery_card_present(route_experiment)
    default_hands = _fixed_hands(
        fixture_script_id,
        recovery_card_present=recovery_card_present,
    )
    information_policy = InformationAccessPolicy.from_experiment(route_experiment)
    opening_hand_plan = _resolve_opening_hand_plan(
        information_policy,
        default_hands,
    )
    fixed_hands = opening_hand_plan.hands
    initial_field = _fixture_initial_field(fixture_script_id)
    player0_hand_count = len(fixed_hands["0"])
    current_manifest = _real_replay_manifest(
        core_lock=core_lock,
        asset_lock=asset_lock,
        build=build,
        information_policy_id=str(
            recorded_manifest.initial_conditions["information_policy_id"]
        ),
        interruption_sampling=(
            next(
                (
                    plan.sampling_evidence
                    for plan in interruption_plans
                    if plan.sampling_evidence is not None
                ),
                None,
            )
        ),
        initial_snapshot_hash=str(
            recorded_manifest.initial_conditions["snapshot_hash"]
        ),
        opening_hand_sampling=opening_hand_plan.sampling_evidence,
        snapshot_kind=opening_hand_plan.snapshot_kind,
        deck_order_in_snapshot=(
            information_policy.deck_order == DeckOrderKnowledge.KNOWN
        ),
        player0_hand_count=player0_hand_count,
        fixed_hands=(
            fixed_hands
            if opening_hand_plan.sampling_evidence is not None
            or fixture_script_id
            in {
                RECOVERY_ATTRIBUTION_FIXTURE_ID,
                *GENERIC_INTERRUPTION_FIXTURE_IDS,
            }
            else None
        ),
        initial_field=(
            initial_field
            if fixture_script_id in GENERIC_INTERRUPTION_FIXTURE_IDS
            else None
        ),
        fixture_script=fixture_script_metadata,
        direct_random_trace=direct_random_trace_metadata(enabled=True),
    )
    assert_manifest_matches(recorded_manifest, current_manifest)
    expected = build_real_core_route(
        external_root=external_root,
        experiment=route_document.get("experiment"),
    )
    assert_replay_request_signatures(
        route_document["replay"], expected["replay"]
    )
    if canonical_json(route_document) != canonical_json(expected):
        raise ValueError(
            "Route DSL does not match a fresh worker-process replay of the real-core scenario"
        )
    events = expected["replay"]["events"]
    return RealCoreVerificationResult(
        route_id=str(expected["route_id"]),
        event_count=len(events),
        final_state_hash=str(events[-1]["state_hash_after"]),
    )
