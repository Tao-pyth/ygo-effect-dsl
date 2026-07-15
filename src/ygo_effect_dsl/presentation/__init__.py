"""Read-only presentation projections that never own game rules."""

from ygo_effect_dsl.presentation.cards import (
    CARD_PRESENTATION_CONTRACT_VERSION,
    CARD_PRESENTATION_PROVIDER_VERSION,
    CardMetadataPresentation,
    CardPresentation,
    CardPresentationQuery,
    CardPresentationSource,
    CardPresentationSourceError,
    CardTextRegion,
    LocalizedCardPresentationProvider,
    PresentationDiagnostic,
    card_presentation_contract_document,
)


__all__ = [
    "CARD_PRESENTATION_CONTRACT_VERSION",
    "CARD_PRESENTATION_PROVIDER_VERSION",
    "CardMetadataPresentation",
    "CardPresentation",
    "CardPresentationQuery",
    "CardPresentationSource",
    "CardPresentationSourceError",
    "CardTextRegion",
    "LocalizedCardPresentationProvider",
    "PresentationDiagnostic",
    "card_presentation_contract_document",
]
