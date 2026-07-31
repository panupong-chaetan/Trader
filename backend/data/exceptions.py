from __future__ import annotations


class DataIntegrityError(Exception):
    """Raised when OHLCV data fails validation and cannot be safely persisted."""

    def __init__(
        self,
        message: str,
        *,
        start: str | None = None,
        end: str | None = None,
    ) -> None:
        super().__init__(message)
        self.start = start
        self.end = end
