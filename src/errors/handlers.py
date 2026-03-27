"""Global error handlers and structured error response model."""

import logging
import traceback
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field

from src.errors.exceptions import MusicMindError

logger = logging.getLogger(__name__)


class ErrorResponse(BaseModel):
    """Structured error response returned by the API."""

    error_code: str = Field(..., description="Machine-readable error code")
    message: str = Field(..., description="Human-readable error message")
    details: Dict[str, Any] = Field(default_factory=dict, description="Additional context")
    retryable: bool = Field(default=False, description="Whether the client should retry")
    timestamp: str = Field(
        default_factory=lambda: datetime.utcnow().isoformat(),
        description="Error timestamp",
    )


def build_error_response(
    error_code: str,
    message: str,
    details: Optional[Dict[str, Any]] = None,
    retryable: bool = False,
) -> Dict[str, Any]:
    """Build a structured error response dict."""
    return ErrorResponse(
        error_code=error_code,
        message=message,
        details=details or {},
        retryable=retryable,
    ).model_dump()


@contextmanager
def error_context(operation: str, overmind_client=None, **extra):
    """Context manager that logs errors to Overmind with full context.

    Usage:
        with error_context("enrich_song", overmind_client=client, song="Test"):
            ...
    """
    try:
        yield
    except MusicMindError:
        raise
    except Exception as exc:
        log_error_to_overmind(
            overmind_client,
            operation=operation,
            error=exc,
            extra=extra,
        )
        raise


def log_error_to_overmind(
    overmind_client,
    operation: str,
    error: Exception,
    extra: Optional[Dict[str, Any]] = None,
) -> None:
    """Log an error event to Overmind Lab with full context."""
    error_data = {
        "operation": operation,
        "error_type": type(error).__name__,
        "error_message": str(error),
        "traceback": traceback.format_exc(),
        "timestamp": datetime.utcnow().isoformat(),
        **(extra or {}),
    }

    if isinstance(error, MusicMindError):
        error_data["error_code"] = error.error_code
        error_data["retryable"] = error.retryable
        error_data["details"] = error.details

    logger.error(f"[{operation}] {type(error).__name__}: {error}", exc_info=True)

    if overmind_client:
        overmind_client.log_event("error", error_data)
