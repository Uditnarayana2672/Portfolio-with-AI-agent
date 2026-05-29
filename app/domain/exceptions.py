"""Domain exceptions (innermost layer).

Framework-free errors raised by domain/application code. The API layer catches
these and maps them to HTTP status codes, so use cases never import FastAPI or
deal with HTTP themselves.
"""
from __future__ import annotations


class DomainError(Exception):
    """Base class for all domain/application errors."""


class NotFoundError(DomainError):
    """A requested resource does not exist (→ HTTP 404)."""


class ConflictError(DomainError):
    """The operation conflicts with current state, e.g. duplicate (→ HTTP 409)."""


class ValidationError(DomainError):
    """Input violates a business rule (→ HTTP 422)."""


class PermissionError(DomainError):
    """The caller is not allowed to perform this action (→ HTTP 403)."""
