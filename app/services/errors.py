from __future__ import annotations


class ExternalServiceError(Exception):
    """Base class for simulated downstream failures."""


class TransientError(ExternalServiceError):
    pass


class PermanentError(ExternalServiceError):
    pass


class TimeoutError(ExternalServiceError):
    pass
