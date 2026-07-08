"""Domain errors — used across adapters, services, and API layers."""

from __future__ import annotations


class IStockError(Exception):
    """Base class for all istock domain errors."""


class NotFoundError(IStockError):
    """Requested domain entity does not exist."""

    def __init__(self, message: str, code: str = "NOT_FOUND_TRADING_DAY") -> None:
        super().__init__(message)
        self.code = code


class ValidationError(IStockError):
    """Client-supplied parameter fails validation (maps to VALIDATION_*)."""

    def __init__(self, code: str, message: str, detail: dict | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.detail = detail or {}


class AdapterError(IStockError):
    """Base class for external-source adapter errors."""


class AdapterConnectionError(AdapterError):
    """Network / socket-level failure reaching an external data source."""


class AdapterAuthError(AdapterError):
    """Authentication / login failure at an external data source."""


class AdapterDataError(AdapterError):
    """External source returned an error response or malformed data."""


class AdapterQuotaExceededError(AdapterError):
    """External source signaled the daily / rate-limit quota is exhausted.

    baostock returns `error_code=10001007` when the account exceeds the 50k
    calls/day cap; the quota does not reset until the next calendar day, so
    callers must abort the batch instead of retrying.
    """
