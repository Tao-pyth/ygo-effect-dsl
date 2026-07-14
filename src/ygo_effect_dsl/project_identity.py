"""Stable public names and responsibility labels for the project."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


PROJECT_IDENTITY_SCHEMA_VERSION = "project-identity-v1"


@dataclass(frozen=True)
class ProjectIdentity:
    """Names that remain stable until a replacement ADR defines migration."""

    technical_project_name: str
    python_package_name: str
    cli_name: str
    product_description: str
    current_dsl_name: str
    legacy_pipeline_name: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": PROJECT_IDENTITY_SCHEMA_VERSION,
            **asdict(self),
        }


PROJECT_IDENTITY = ProjectIdentity(
    technical_project_name="ygo-effect-dsl",
    python_package_name="ygo_effect_dsl",
    cli_name="ygo-effect-dsl",
    product_description=(
        "Reproducible Yu-Gi-Oh! route search and Route Information DSL"
    ),
    current_dsl_name="Route Information DSL",
    legacy_pipeline_name="legacy card-text artifact pipeline",
)

__all__ = [
    "PROJECT_IDENTITY",
    "PROJECT_IDENTITY_SCHEMA_VERSION",
    "ProjectIdentity",
]
