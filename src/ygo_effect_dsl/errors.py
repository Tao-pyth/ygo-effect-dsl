from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class DslError:
    """Validation diagnostic shared by CORE commands."""

    path: str
    code: str
    message: str
    severity: Literal["error", "warning", "info"] = "error"
