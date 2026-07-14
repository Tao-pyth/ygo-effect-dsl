"""Replay-specific errors."""


class ReplayFormatError(ValueError):
    """Raised when replay JSON is syntactically valid but violates the schema."""


class ReplaySignatureMismatchError(ValueError):
    """Raised when replay playback reaches a different DecisionRequest."""

    def __init__(
        self,
        message: str,
        *,
        step: int | None = None,
        path: str | None = None,
        recorded: object = None,
        current: object = None,
    ) -> None:
        self.step = step
        self.path = path
        self.recorded = recorded
        self.current = current
        super().__init__(message)


class ReplayManifestIncompleteError(ReplayFormatError):
    """Raised when a replay cannot prove that its environment is reproducible."""


class ReplayEnvironmentMismatchError(ValueError):
    """Raised before playback when the recorded and current environments differ."""

    def __init__(self, path: str, recorded: object, current: object) -> None:
        self.path = path
        self.recorded = recorded
        self.current = current
        super().__init__(
            f"replay environment mismatch at {path}: "
            f"recorded={recorded!r}, current={current!r}"
        )
