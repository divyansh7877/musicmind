"""Centralized exception hierarchy for MusicMind."""

from typing import Any, Dict, Optional


class MusicMindError(Exception):
    """Base exception for all MusicMind errors."""

    def __init__(
        self,
        message: str,
        error_code: str = "INTERNAL_ERROR",
        details: Optional[Dict[str, Any]] = None,
        retryable: bool = False,
    ):
        super().__init__(message)
        self.message = message
        self.error_code = error_code
        self.details = details or {}
        self.retryable = retryable


class AgentError(MusicMindError):
    """Error raised by a sub-agent."""

    def __init__(
        self,
        message: str,
        agent_name: str,
        details: Optional[Dict[str, Any]] = None,
        retryable: bool = True,
    ):
        super().__init__(
            message,
            error_code="AGENT_ERROR",
            details={"agent_name": agent_name, **(details or {})},
            retryable=retryable,
        )
        self.agent_name = agent_name


class AgentTimeoutError(AgentError):
    """Agent exceeded its execution timeout."""

    def __init__(self, agent_name: str, timeout_ms: int):
        super().__init__(
            message=f"Agent {agent_name} timed out after {timeout_ms}ms",
            agent_name=agent_name,
            details={"timeout_ms": timeout_ms},
            retryable=True,
        )
        self.error_code = "AGENT_TIMEOUT"


class RateLimitError(MusicMindError):
    """Rate limit exceeded for an external API or internal endpoint."""

    def __init__(
        self,
        message: str = "Rate limit exceeded",
        retry_after: Optional[int] = None,
        source: Optional[str] = None,
    ):
        super().__init__(
            message,
            error_code="RATE_LIMIT_EXCEEDED",
            details={"retry_after": retry_after, "source": source},
            retryable=True,
        )
        self.retry_after = retry_after


class DatabaseError(MusicMindError):
    """Error from database operations."""

    def __init__(
        self,
        message: str,
        operation: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        retryable: bool = True,
    ):
        super().__init__(
            message,
            error_code="DATABASE_ERROR",
            details={"operation": operation, **(details or {})},
            retryable=retryable,
        )


class DatabaseConnectionError(DatabaseError):
    """Failed to connect to the database."""

    def __init__(self, message: str = "Database connection failed"):
        super().__init__(message, operation="connect", retryable=True)
        self.error_code = "DATABASE_CONNECTION_ERROR"


class ConcurrentWriteConflictError(DatabaseError):
    """Optimistic locking conflict on a concurrent write."""

    def __init__(self, node_type: str, node_id: str, expected_gen: int, actual_gen: int):
        super().__init__(
            message=(
                f"Concurrent write conflict on {node_type} {node_id}: "
                f"expected generation {expected_gen}, found {actual_gen}"
            ),
            operation="upsert",
            details={
                "node_type": node_type,
                "node_id": node_id,
                "expected_generation": expected_gen,
                "actual_generation": actual_gen,
            },
            retryable=True,
        )
        self.error_code = "CONCURRENT_WRITE_CONFLICT"


class ValidationError(MusicMindError):
    """Input or data validation error."""

    def __init__(
        self,
        message: str,
        field: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(
            message,
            error_code="VALIDATION_ERROR",
            details={"field": field, **(details or {})},
            retryable=False,
        )


class DataValidationError(ValidationError):
    """Validation error when processing enrichment data."""

    def __init__(
        self,
        message: str,
        invalid_fields: Optional[Dict[str, str]] = None,
        valid_data: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(
            message,
            details={
                "invalid_fields": invalid_fields or {},
                "valid_data_keys": list((valid_data or {}).keys()),
            },
        )
        self.error_code = "DATA_VALIDATION_ERROR"
        self.invalid_fields = invalid_fields or {}
        self.valid_data = valid_data or {}


class ServiceUnavailableError(MusicMindError):
    """A required service is not available."""

    def __init__(self, service_name: str):
        super().__init__(
            message=f"Service '{service_name}' is currently unavailable",
            error_code="SERVICE_UNAVAILABLE",
            details={"service_name": service_name},
            retryable=True,
        )
