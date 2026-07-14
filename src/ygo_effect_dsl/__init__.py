"""Reproducible Yu-Gi-Oh! route search and Route Information DSL package.

ocgcore and EDOPro Lua own card behavior, legality, and state transitions.
Python records, searches, evaluates, and compares the resulting routes.
"""

from ygo_effect_dsl.project_identity import PROJECT_IDENTITY
from ygo_effect_dsl.version import __version__

__all__ = ["PROJECT_IDENTITY", "__version__"]
