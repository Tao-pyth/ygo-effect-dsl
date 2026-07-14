from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal

from ygo_effect_dsl.engine.bridge import DecisionRequest
from ygo_effect_dsl.engine.canonical import to_canonical_data


INTERRUPTION_SUPPORT_TAXONOMY_SCHEMA_VERSION = "interruption-support-taxonomy-v1"

InterruptionOutcomeStatus = Literal[
    "supported",
    "configuration_failure",
    "path_failure",
    "unsupported_category",
]
InterruptionSourceZone = Literal["hand", "field"]
InterruptionTargetShape = Literal[
    "not_applicable",
    "targetless",
    "single",
    "multi",
]

_KNOWN_VALIDATION_CATEGORIES = frozenset(
    {
        "standard",
        "damage_step",
        "simultaneous_trigger",
        "mandatory_trigger",
        "segoc",
    }
)
_FAIL_CLOSE_VALIDATION_CATEGORIES = frozenset(
    {"damage_step", "simultaneous_trigger", "mandatory_trigger", "segoc"}
)
_KNOWN_RESPONSE_ROLES = frozenset({"cost", "target", "option"})
_KNOWN_ROLES = _KNOWN_RESPONSE_ROLES | {"activation"}
_NON_CARD_CANDIDATE_KINDS = frozenset(
    {
        "attribute",
        "control",
        "number",
        "option",
        "pass",
        "position",
        "race",
        "yes_no",
        "zone",
    }
)


@dataclass(frozen=True)
class InterruptionValidationPolicy:
    """Fixture-backed validation categories accepted by this run."""

    verified_fixture_categories: frozenset[str] = frozenset({"standard"})
    schema_version: str = INTERRUPTION_SUPPORT_TAXONOMY_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != INTERRUPTION_SUPPORT_TAXONOMY_SCHEMA_VERSION:
            raise ValueError(
                "schema_version must be "
                f"{INTERRUPTION_SUPPORT_TAXONOMY_SCHEMA_VERSION!r}"
            )
        if not isinstance(self.verified_fixture_categories, frozenset):
            raise TypeError("verified_fixture_categories must be a frozenset")
        unknown = sorted(
            self.verified_fixture_categories - _KNOWN_VALIDATION_CATEGORIES
        )
        if unknown:
            raise ValueError(f"unknown validation categories: {unknown}")

    def register_verified(
        self, *categories: str
    ) -> "InterruptionValidationPolicy":
        """Return a new policy; the original policy remains immutable."""

        requested = frozenset(categories)
        unknown = sorted(requested - _KNOWN_VALIDATION_CATEGORIES)
        if unknown:
            raise ValueError(f"unknown validation categories: {unknown}")
        return InterruptionValidationPolicy(
            verified_fixture_categories=(
                self.verified_fixture_categories | requested
            )
        )

    def to_dict(self) -> dict[str, Any]:
        return to_canonical_data(
            {
                "fail_close_categories": sorted(
                    _FAIL_CLOSE_VALIDATION_CATEGORIES
                ),
                "schema_version": self.schema_version,
                "verified_fixture_categories": sorted(
                    self.verified_fixture_categories
                ),
            }
        )


@dataclass(frozen=True)
class InterruptionCandidateSupport:
    candidate_id: str
    source_card_code: int
    source_zone: InterruptionSourceZone
    activation: bool
    cost: bool
    target: InterruptionTargetShape
    option: bool
    validation_categories: tuple[str, ...]
    schema_version: str = INTERRUPTION_SUPPORT_TAXONOMY_SCHEMA_VERSION

    def __post_init__(self) -> None:
        active_roles = sum(
            (
                self.activation,
                self.cost,
                self.option,
                self.target in {"single", "multi"},
            )
        )
        if active_roles != 1:
            raise ValueError("candidate support must describe exactly one request role")
        if self.target == "targetless" and not self.activation:
            raise ValueError("targetless is valid only for an activation candidate")
        if self.activation and self.target not in {"not_applicable", "targetless"}:
            raise ValueError(
                "activation target must be not_applicable or targetless"
            )
        unknown = sorted(
            set(self.validation_categories) - _KNOWN_VALIDATION_CATEGORIES
        )
        if unknown:
            raise ValueError(f"unknown validation categories: {unknown}")

    def to_dict(self) -> dict[str, Any]:
        return to_canonical_data(
            {
                "activation": self.activation,
                "candidate_id": self.candidate_id,
                "cost": self.cost,
                "option": self.option,
                "schema_version": self.schema_version,
                "source_card_code": self.source_card_code,
                "source_zone": self.source_zone,
                "target": self.target,
                "validation_categories": list(self.validation_categories),
            }
        )


@dataclass(frozen=True)
class InterruptionTaxonomyDiagnostic:
    code: str
    message: str
    path: str
    candidate_ids: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return to_canonical_data(
            {
                "candidate_ids": list(self.candidate_ids),
                "code": self.code,
                "message": self.message,
                "path": self.path,
            }
        )


@dataclass(frozen=True)
class InterruptionTaxonomyOutcome:
    status: InterruptionOutcomeStatus
    request_id: str | None
    source_card_code: int | None
    candidates: tuple[InterruptionCandidateSupport, ...] = ()
    diagnostics: tuple[InterruptionTaxonomyDiagnostic, ...] = ()
    schema_version: str = INTERRUPTION_SUPPORT_TAXONOMY_SCHEMA_VERSION

    @property
    def supported(self) -> bool:
        return self.status == "supported"

    def to_dict(self) -> dict[str, Any]:
        return to_canonical_data(
            {
                "candidates": [candidate.to_dict() for candidate in self.candidates],
                "diagnostics": [
                    diagnostic.to_dict() for diagnostic in self.diagnostics
                ],
                "request_id": self.request_id,
                "schema_version": self.schema_version,
                "source_card_code": self.source_card_code,
                "status": self.status,
                "supported": self.supported,
            }
        )


class _TaxonomyInputError(ValueError):
    def __init__(
        self,
        *,
        status: InterruptionOutcomeStatus,
        code: str,
        message: str,
        path: str,
        candidate_ids: Sequence[str] = (),
    ) -> None:
        self.status = status
        self.diagnostic = InterruptionTaxonomyDiagnostic(
            code=code,
            message=message,
            path=path,
            candidate_ids=tuple(candidate_ids),
        )
        super().__init__(message)


@dataclass(frozen=True)
class _RequestView:
    request_id: str
    request_type: str
    candidates: tuple[Mapping[str, Any], ...]
    min_selections: int
    max_selections: int
    phase: str
    extra: Mapping[str, Any]


def _configuration_failure(
    code: str, message: str, path: str, *, candidate_ids: Sequence[str] = ()
) -> _TaxonomyInputError:
    return _TaxonomyInputError(
        status="configuration_failure",
        code=code,
        message=message,
        path=path,
        candidate_ids=candidate_ids,
    )


def _unsupported_category(
    code: str, message: str, path: str, *, candidate_ids: Sequence[str] = ()
) -> _TaxonomyInputError:
    return _TaxonomyInputError(
        status="unsupported_category",
        code=code,
        message=message,
        path=path,
        candidate_ids=candidate_ids,
    )


def _as_mapping(value: Any, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise _configuration_failure(
            "unknown_candidate_shape", "must be a mapping", path
        )
    return value


def _non_empty_string(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value:
        raise _configuration_failure(
            "unknown_candidate_shape", "must be a non-empty string", path
        )
    return value


def _selection_bound(value: Any, path: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise _configuration_failure(
            "unknown_request_shape", "must be a non-negative integer", path
        )
    return value


def _request_view(request: DecisionRequest | Mapping[str, Any]) -> _RequestView:
    document = request.to_dict() if isinstance(request, DecisionRequest) else request
    data = _as_mapping(document, "$.request")
    request_id = _non_empty_string(data.get("request_id"), "$.request.request_id")
    request_type = _non_empty_string(
        data.get("request_type"), "$.request.request_type"
    )
    raw_candidates = data.get("candidates")
    if not isinstance(raw_candidates, Sequence) or isinstance(
        raw_candidates, (str, bytes)
    ):
        raise _configuration_failure(
            "unknown_request_shape",
            "must be a sequence",
            "$.request.candidates",
        )
    candidates = tuple(
        _as_mapping(candidate, f"$.request.candidates[{index}]")
        for index, candidate in enumerate(raw_candidates)
    )
    constraints = _as_mapping(
        data.get("constraints"), "$.request.constraints"
    )
    min_selections = _selection_bound(
        constraints.get("min_selections"),
        "$.request.constraints.min_selections",
    )
    max_selections = _selection_bound(
        constraints.get("max_selections"),
        "$.request.constraints.max_selections",
    )
    if min_selections > max_selections:
        raise _configuration_failure(
            "unknown_request_shape",
            "min_selections must not exceed max_selections",
            "$.request.constraints",
        )
    context = _as_mapping(data.get("context"), "$.request.context")
    phase = context.get("phase", "")
    if not isinstance(phase, str):
        raise _configuration_failure(
            "unknown_request_shape", "must be a string", "$.request.context.phase"
        )
    extra = _as_mapping(context.get("extra", {}), "$.request.context.extra")
    return _RequestView(
        request_id=request_id,
        request_type=request_type,
        candidates=candidates,
        min_selections=min_selections,
        max_selections=max_selections,
        phase=phase,
        extra=extra,
    )


def _candidate_identity(
    candidate: Mapping[str, Any], index: int
) -> tuple[str, str]:
    path = f"$.request.candidates[{index}]"
    for field in ("card_ref", "effect_ref"):
        value = candidate.get(field)
        if value is not None and not isinstance(value, Mapping):
            raise _configuration_failure(
                "unknown_candidate_shape",
                "must be a mapping or null",
                f"{path}.{field}",
            )
    payload = candidate.get("payload", {})
    if not isinstance(payload, Mapping):
        raise _configuration_failure(
            "unknown_candidate_shape", "must be a mapping", f"{path}.payload"
        )
    return (
        _non_empty_string(candidate.get("candidate_id"), f"{path}.candidate_id"),
        _non_empty_string(candidate.get("kind"), f"{path}.kind"),
    )


def _card_code(card_ref: Mapping[str, Any], path: str) -> int | None:
    values: list[int] = []
    for key in ("public_card_id", "card_code", "code"):
        if key not in card_ref:
            continue
        value = card_ref[key]
        if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
            raise _configuration_failure(
                "unknown_candidate_shape",
                "card code must be a positive integer",
                f"{path}.{key}",
            )
        values.append(value)
    if len(set(values)) > 1:
        raise _configuration_failure(
            "ambiguous_candidate_source",
            "candidate exposes conflicting card codes",
            path,
        )
    return values[0] if values else None


def _source_zone(value: Any, path: str) -> InterruptionSourceZone:
    if value in {0x02, "hand"}:
        return "hand"
    if value in {0x04, 0x08, "field", "monster_zone", "spell_trap_zone"}:
        return "field"
    raise _unsupported_category(
        "unsupported_source_zone",
        "source location is outside the hand/field MVP taxonomy",
        path,
    )


def _explicit_source_binding(
    view: _RequestView,
    source_card_code: int,
    source_player: int | None,
    source_zone: InterruptionSourceZone | None,
) -> InterruptionSourceZone:
    source = _as_mapping(
        view.extra.get("interruption_source"),
        "$.request.context.extra.interruption_source",
    )
    configured_code = source.get("card_code")
    if configured_code != source_card_code:
        raise _configuration_failure(
            "ambiguous_source_binding",
            "interruption_source.card_code does not match source_card_code",
            "$.request.context.extra.interruption_source.card_code",
        )
    configured_player = source.get("player")
    if source_player is not None and configured_player != source_player:
        raise _configuration_failure(
            "ambiguous_source_binding",
            "interruption_source.player does not match source_player",
            "$.request.context.extra.interruption_source.player",
        )
    configured_zone = _source_zone(
        source.get("zone"), "$.request.context.extra.interruption_source.zone"
    )
    if source_zone is not None and configured_zone != source_zone:
        raise _configuration_failure(
            "ambiguous_source_binding",
            "interruption_source.zone does not match source_zone",
            "$.request.context.extra.interruption_source.zone",
        )
    return configured_zone


def _response_role(view: _RequestView) -> str:
    explicit_role = view.extra.get("interruption_role")
    implied_role = {
        "select_chain": "activation",
        "select_option": "option",
    }.get(view.request_type)
    if explicit_role is not None and (
        not isinstance(explicit_role, str) or explicit_role not in _KNOWN_ROLES
    ):
        raise _configuration_failure(
            "unknown_candidate_shape",
            f"interruption_role must be one of {sorted(_KNOWN_ROLES)}",
            "$.request.context.extra.interruption_role",
        )
    if implied_role is not None and explicit_role not in {None, implied_role}:
        raise _configuration_failure(
            "ambiguous_candidate_role",
            "request_type and interruption_role disagree",
            "$.request.context.extra.interruption_role",
        )
    role = implied_role or explicit_role
    if role is None:
        raise _configuration_failure(
            "unknown_candidate_shape",
            "request role is not explicit; cost and target are not inferred",
            "$.request.context.extra.interruption_role",
        )
    return role


def _target_shape(view: _RequestView, role: str) -> InterruptionTargetShape:
    if role == "target":
        if view.max_selections == 0:
            raise _configuration_failure(
                "unknown_candidate_shape",
                "a target request must select at least one candidate",
                "$.request.constraints.max_selections",
            )
        return "single" if view.max_selections == 1 else "multi"
    if role == "activation":
        explicit = view.extra.get("interruption_target")
        if explicit is None:
            return "not_applicable"
        if explicit != "targetless":
            raise _configuration_failure(
                "ambiguous_target_shape",
                "activation requests may declare only explicit targetless support",
                "$.request.context.extra.interruption_target",
            )
        return "targetless"
    return "not_applicable"


def _validation_categories(
    view: _RequestView, explicit: Iterable[str] | None
) -> tuple[str, ...]:
    if explicit is None:
        raw = view.extra.get("interruption_validation_categories")
        if raw is None:
            categories: set[str] = set()
        elif isinstance(raw, Sequence) and not isinstance(raw, (str, bytes)):
            categories = set()
            for index, value in enumerate(raw):
                if not isinstance(value, str) or not value:
                    raise _configuration_failure(
                        "unknown_validation_category",
                        "must be a non-empty string",
                        "$.request.context.extra."
                        f"interruption_validation_categories[{index}]",
                    )
                categories.add(value)
        else:
            raise _configuration_failure(
                "unknown_validation_category",
                "must be a sequence of strings",
                "$.request.context.extra.interruption_validation_categories",
            )
    else:
        if isinstance(explicit, (str, bytes)):
            raise _configuration_failure(
                "unknown_validation_category",
                "must be an iterable of category strings, not one string",
                "$.validation_categories",
            )
        try:
            categories = set(explicit)
        except TypeError as exc:
            raise _configuration_failure(
                "unknown_validation_category",
                "must be an iterable of strings",
                "$.validation_categories",
            ) from exc
        if any(not isinstance(value, str) or not value for value in categories):
            raise _configuration_failure(
                "unknown_validation_category",
                "must contain non-empty strings",
                "$.validation_categories",
            )

    phase = view.phase.strip().lower().replace("-", "_").replace(" ", "_")
    if phase in {"damage", "damage_step"}:
        categories.add("damage_step")
    for category in ("simultaneous_trigger", "mandatory_trigger", "segoc"):
        marker = view.extra.get(category, False)
        if not isinstance(marker, bool):
            raise _configuration_failure(
                "unknown_validation_category",
                "must be a boolean",
                f"$.request.context.extra.{category}",
            )
        if marker:
            categories.add(category)
    if not categories:
        categories.add("standard")
    unknown = sorted(categories - _KNOWN_VALIDATION_CATEGORIES)
    if unknown:
        raise _unsupported_category(
            "unsupported_validation_category",
            f"unknown validation categories: {unknown}",
            "$.validation_categories",
        )
    return tuple(sorted(categories))


def _candidate_support(
    *,
    candidate_id: str,
    source_card_code: int,
    source_zone: InterruptionSourceZone,
    role: str,
    target: InterruptionTargetShape,
    categories: tuple[str, ...],
) -> InterruptionCandidateSupport:
    return InterruptionCandidateSupport(
        candidate_id=candidate_id,
        source_card_code=source_card_code,
        source_zone=source_zone,
        activation=role == "activation",
        cost=role == "cost",
        target=target,
        option=role == "option",
        validation_categories=categories,
    )


def classify_interruption_candidates(
    request: DecisionRequest | Mapping[str, Any],
    *,
    source_card_code: int,
    source_player: int | None = None,
    source_zone: InterruptionSourceZone | None = None,
    policy: InterruptionValidationPolicy | None = None,
    expected_candidate_ids: Iterable[str] = (),
    validation_categories: Iterable[str] | None = None,
) -> InterruptionTaxonomyOutcome:
    """Classify only candidates exposed by core, with fail-closed outcomes.

    ``select_card`` cannot distinguish cost from target by protocol shape, so the
    request must carry ``context.extra.interruption_role``. Non-activation
    requests must also carry ``context.extra.interruption_source`` to bind the
    response to the configured source card without effect inference.
    """

    request_id: str | None = None
    normalized_code: int | None = None
    try:
        if (
            not isinstance(source_card_code, int)
            or isinstance(source_card_code, bool)
            or source_card_code <= 0
        ):
            raise _configuration_failure(
                "invalid_source_card_code",
                "source_card_code must be a positive integer",
                "$.source_card_code",
            )
        normalized_code = source_card_code
        if source_player is not None and source_player not in (0, 1):
            raise _configuration_failure(
                "invalid_source_player",
                "source_player must be 0, 1, or null",
                "$.source_player",
            )
        if source_zone is not None and source_zone not in {"hand", "field"}:
            raise _configuration_failure(
                "unsupported_source_zone",
                "source_zone must be hand, field, or null",
                "$.source_zone",
            )
        active_policy = policy or InterruptionValidationPolicy()
        if not isinstance(active_policy, InterruptionValidationPolicy):
            raise _configuration_failure(
                "invalid_validation_policy",
                "policy must be InterruptionValidationPolicy",
                "$.policy",
            )
        view = _request_view(request)
        request_id = view.request_id
        role = _response_role(view)
        categories = _validation_categories(view, validation_categories)
        unverified = sorted(
            set(categories) - active_policy.verified_fixture_categories
        )
        if unverified:
            raise _unsupported_category(
                "unverified_fixture_category",
                f"fixture validation is not registered for {unverified}",
                "$.validation_categories",
            )

        identities = tuple(
            _candidate_identity(candidate, index)
            for index, candidate in enumerate(view.candidates)
        )
        ids = [candidate_id for candidate_id, _kind in identities]
        duplicate_ids = sorted(
            candidate_id for candidate_id in set(ids) if ids.count(candidate_id) > 1
        )
        if duplicate_ids:
            raise _configuration_failure(
                "ambiguous_candidate_identity",
                "candidate IDs must be unique",
                "$.request.candidates",
                candidate_ids=duplicate_ids,
            )

        selected: list[tuple[str, InterruptionSourceZone]] = []
        if role == "activation":
            for index, (candidate, identity) in enumerate(
                zip(view.candidates, identities, strict=True)
            ):
                candidate_id, kind = identity
                raw_card_ref = candidate.get("card_ref")
                if raw_card_ref is None:
                    if kind in _NON_CARD_CANDIDATE_KINDS:
                        continue
                    raise _configuration_failure(
                        "unknown_candidate_shape",
                        "card/effect candidate requires card_ref",
                        f"$.request.candidates[{index}].card_ref",
                        candidate_ids=(candidate_id,),
                    )
                card_ref = _as_mapping(
                    raw_card_ref, f"$.request.candidates[{index}].card_ref"
                )
                candidate_code = _card_code(
                    card_ref, f"$.request.candidates[{index}].card_ref"
                )
                if candidate_code is None:
                    raise _configuration_failure(
                        "unknown_candidate_shape",
                        "card_ref requires an explicit card code",
                        f"$.request.candidates[{index}].card_ref",
                        candidate_ids=(candidate_id,),
                    )
                controller = card_ref.get("controller")
                if (
                    not isinstance(controller, int)
                    or isinstance(controller, bool)
                    or controller not in (0, 1)
                ):
                    raise _configuration_failure(
                        "unknown_candidate_shape",
                        "card_ref.controller must be player 0 or 1",
                        f"$.request.candidates[{index}].card_ref.controller",
                    )
                candidate_zone = _source_zone(
                    card_ref.get("location"),
                    f"$.request.candidates[{index}].card_ref.location",
                )
                if (
                    candidate_code == source_card_code
                    and source_player in {None, controller}
                    and source_zone in {None, candidate_zone}
                ):
                    selected.append(
                        (
                            candidate_id,
                            candidate_zone,
                        )
                    )
        else:
            bound_zone = _explicit_source_binding(
                view, source_card_code, source_player, source_zone
            )
            selected.extend((candidate_id, bound_zone) for candidate_id, _ in identities)

        if isinstance(expected_candidate_ids, (str, bytes)):
            raise _configuration_failure(
                "invalid_expected_candidate_id",
                "expected_candidate_ids must be an iterable of IDs, not one string",
                "$.expected_candidate_ids",
            )
        try:
            expected = tuple(expected_candidate_ids)
        except TypeError as exc:
            raise _configuration_failure(
                "invalid_expected_candidate_id",
                "expected_candidate_ids must be iterable",
                "$.expected_candidate_ids",
            ) from exc
        if any(not isinstance(value, str) or not value for value in expected):
            raise _configuration_failure(
                "invalid_expected_candidate_id",
                "expected_candidate_ids must contain non-empty strings",
                "$.expected_candidate_ids",
            )
        if len(expected) != len(set(expected)):
            raise _configuration_failure(
                "ambiguous_expected_candidate_id",
                "expected_candidate_ids must be unique",
                "$.expected_candidate_ids",
            )
        selected_ids = {candidate_id for candidate_id, _zone in selected}
        missing = tuple(sorted(set(expected) - selected_ids))
        if missing:
            raise _TaxonomyInputError(
                status="path_failure",
                code="candidate_disappeared",
                message="expected core candidate is absent from this request",
                path="$.request.candidates",
                candidate_ids=missing,
            )
        if not selected:
            raise _TaxonomyInputError(
                status="path_failure",
                code="candidate_disappeared",
                message="no core candidate matches the configured source card",
                path="$.request.candidates",
            )

        target = _target_shape(view, role)
        supports = tuple(
            _candidate_support(
                candidate_id=candidate_id,
                source_card_code=source_card_code,
                source_zone=zone,
                role=role,
                target=target,
                categories=categories,
            )
            for candidate_id, zone in sorted(selected)
        )
        return InterruptionTaxonomyOutcome(
            status="supported",
            request_id=request_id,
            source_card_code=source_card_code,
            candidates=supports,
        )
    except _TaxonomyInputError as exc:
        return InterruptionTaxonomyOutcome(
            status=exc.status,
            request_id=request_id,
            source_card_code=normalized_code,
            diagnostics=(exc.diagnostic,),
        )


__all__ = [
    "INTERRUPTION_SUPPORT_TAXONOMY_SCHEMA_VERSION",
    "InterruptionCandidateSupport",
    "InterruptionOutcomeStatus",
    "InterruptionSourceZone",
    "InterruptionTargetShape",
    "InterruptionTaxonomyDiagnostic",
    "InterruptionTaxonomyOutcome",
    "InterruptionValidationPolicy",
    "classify_interruption_candidates",
]
