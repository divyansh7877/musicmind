"""Centralized error handling module."""

from src.errors.exceptions import (
    MusicMindError,
    AgentError,
    AgentTimeoutError,
    RateLimitError,
    DatabaseError,
    DatabaseConnectionError,
    ConcurrentWriteConflictError,
    ValidationError as MusicMindValidationError,
    DataValidationError,
    ServiceUnavailableError,
)
from src.errors.handlers import ErrorResponse, error_context

__all__ = [
    "MusicMindError",
    "AgentError",
    "AgentTimeoutError",
    "RateLimitError",
    "DatabaseError",
    "DatabaseConnectionError",
    "ConcurrentWriteConflictError",
    "MusicMindValidationError",
    "DataValidationError",
    "ServiceUnavailableError",
    "ErrorResponse",
    "error_context",
]
