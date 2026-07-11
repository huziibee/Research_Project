"""Model client errors."""

from __future__ import annotations


class ModelClientError(Exception):
    """Base error for model client operations."""


class ModelBackendUnavailableError(ModelClientError):
    """Raised when an optional backend dependency is unavailable."""
