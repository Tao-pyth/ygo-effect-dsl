"""Replay-specific errors."""


class ReplayFormatError(ValueError):
    """Raised when replay JSON is syntactically valid but violates the schema."""
