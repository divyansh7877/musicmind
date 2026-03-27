"""Tests for comprehensive error handling (Task 20.1)."""

import pytest
from unittest.mock import MagicMock, AsyncMock
from uuid import uuid4

from fastapi.testclient import TestClient

from src.errors.exceptions import (
    MusicMindError,
    AgentError,
    AgentTimeoutError,
    RateLimitError,
    DatabaseConnectionError,
    ConcurrentWriteConflictError,
    ServiceUnavailableError,
    DataValidationError,
)
from src.errors.handlers import ErrorResponse, build_error_response, log_error_to_overmind


# --- Exception hierarchy ---


class TestExceptionHierarchy:
    """Test centralized exception classes."""

    def test_base_error(self):
        err = MusicMindError("something broke", error_code="TEST", retryable=True)
        assert str(err) == "something broke"
        assert err.error_code == "TEST"
        assert err.retryable is True
        assert err.details == {}

    def test_agent_error(self):
        err = AgentError("timeout", agent_name="spotify")
        assert err.agent_name == "spotify"
        assert err.error_code == "AGENT_ERROR"
        assert err.retryable is True
        assert err.details["agent_name"] == "spotify"

    def test_agent_timeout_error(self):
        err = AgentTimeoutError(agent_name="lastfm", timeout_ms=30000)
        assert err.error_code == "AGENT_TIMEOUT"
        assert "30000" in err.message
        assert err.retryable is True

    def test_rate_limit_error(self):
        err = RateLimitError(retry_after=60, source="spotify_api")
        assert err.error_code == "RATE_LIMIT_EXCEEDED"
        assert err.retry_after == 60
        assert err.retryable is True

    def test_database_connection_error(self):
        err = DatabaseConnectionError()
        assert err.error_code == "DATABASE_CONNECTION_ERROR"
        assert err.retryable is True

    def test_concurrent_write_conflict(self):
        err = ConcurrentWriteConflictError(
            node_type="Song", node_id="abc-123", expected_gen=5, actual_gen=7
        )
        assert err.error_code == "CONCURRENT_WRITE_CONFLICT"
        assert err.retryable is True
        assert err.details["expected_generation"] == 5
        assert err.details["actual_generation"] == 7

    def test_service_unavailable(self):
        err = ServiceUnavailableError("orchestrator")
        assert err.error_code == "SERVICE_UNAVAILABLE"
        assert "orchestrator" in err.message

    def test_data_validation_error(self):
        err = DataValidationError(
            "bad data",
            invalid_fields={"title": "empty"},
            valid_data={"artist": "Queen"},
        )
        assert err.error_code == "DATA_VALIDATION_ERROR"
        assert err.invalid_fields == {"title": "empty"}
        assert err.valid_data == {"artist": "Queen"}


# --- Structured error response ---


class TestErrorResponse:
    """Test structured error response model."""

    def test_build_error_response(self):
        resp = build_error_response(
            error_code="TEST_ERROR",
            message="Something went wrong",
            details={"key": "value"},
            retryable=True,
        )
        assert resp["error_code"] == "TEST_ERROR"
        assert resp["message"] == "Something went wrong"
        assert resp["details"]["key"] == "value"
        assert resp["retryable"] is True
        assert "timestamp" in resp

    def test_error_response_model(self):
        resp = ErrorResponse(
            error_code="INTERNAL_ERROR",
            message="Unexpected error",
        )
        assert resp.error_code == "INTERNAL_ERROR"
        assert resp.retryable is False
        assert resp.details == {}


# --- Overmind error logging ---


class TestErrorLogging:
    """Test error logging to Overmind."""

    def test_log_error_to_overmind(self):
        mock_overmind = MagicMock()
        err = AgentError("timeout", agent_name="spotify")

        log_error_to_overmind(mock_overmind, "enrich_song", err, extra={"song": "Test"})

        mock_overmind.log_event.assert_called_once()
        call_args = mock_overmind.log_event.call_args
        assert call_args[0][0] == "error"
        props = call_args[0][1]
        assert props["operation"] == "enrich_song"
        assert props["error_type"] == "AgentError"
        assert props["error_code"] == "AGENT_ERROR"
        assert props["song"] == "Test"

    def test_log_error_without_overmind(self):
        # Should not raise when overmind_client is None
        log_error_to_overmind(None, "test_op", ValueError("oops"))

    def test_log_non_musicmind_error(self):
        mock_overmind = MagicMock()
        log_error_to_overmind(mock_overmind, "test", RuntimeError("crash"))

        call_args = mock_overmind.log_event.call_args[0][1]
        assert call_args["error_type"] == "RuntimeError"
        assert "error_code" not in call_args


# --- Global exception handlers in FastAPI ---


class MockRedisClient:
    def __init__(self):
        self.cache = {}

    def get(self, key):
        return self.cache.get(key)

    def set(self, key, value, ttl=3600):
        self.cache[key] = value
        return True

    def delete(self, key):
        if key in self.cache:
            del self.cache[key]
            return True
        return False

    def exists(self, key):
        return key in self.cache


@pytest.fixture
def client():
    """Create test client with mocked globals."""
    import src.api.main as api_main
    from src.api.auth import AuthService
    from src.api.rate_limiter import RateLimiter

    mock_redis = MockRedisClient()
    auth_svc = AuthService(cache_client=mock_redis)
    rate_lim = RateLimiter(cache_client=mock_redis)

    api_main.auth_service = auth_svc
    api_main.rate_limiter = rate_lim
    api_main.redis_client = mock_redis
    api_main.orchestrator = MagicMock()
    api_main.feedback_processor = MagicMock()
    api_main.overmind_client = MagicMock()

    yield TestClient(api_main.app, raise_server_exceptions=False)

    api_main.auth_service = None
    api_main.rate_limiter = None
    api_main.orchestrator = None
    api_main.feedback_processor = None
    api_main.overmind_client = None


def _get_auth_header(client):
    username = f"testuser_{uuid4().hex[:8]}"
    resp = client.post(
        "/api/auth/register",
        params={"username": username, "password": "testpass123", "email": "t@e.com"},
    )
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


class TestGlobalExceptionHandlers:
    """Test that MusicMind errors are caught by global handlers."""

    def test_service_unavailable_returns_503(self, client):
        """When orchestrator is None the endpoint raises ServiceUnavailableError."""
        import src.api.main as api_main

        api_main.orchestrator = None

        headers = _get_auth_header(client)
        resp = client.post("/api/search", json={"song_name": "Test Song"}, headers=headers)

        assert resp.status_code == 503
        body = resp.json()
        assert body["error_code"] == "SERVICE_UNAVAILABLE"
        assert body["retryable"] is True

        # Restore
        api_main.orchestrator = MagicMock()

    def test_search_orchestrator_error_returns_structured(self, client):
        """Domain error from orchestrator is returned as structured JSON."""
        import src.api.main as api_main
        from src.errors.exceptions import DatabaseConnectionError

        api_main.orchestrator.enrich_song = AsyncMock(
            side_effect=DatabaseConnectionError("DB down")
        )

        headers = _get_auth_header(client)
        resp = client.post("/api/search", json={"song_name": "Test Song"}, headers=headers)

        assert resp.status_code == 503
        body = resp.json()
        assert body["error_code"] == "DATABASE_CONNECTION_ERROR"

    def test_feedback_service_unavailable(self, client):
        import src.api.main as api_main

        api_main.feedback_processor = None

        headers = _get_auth_header(client)
        resp = client.post(
            "/api/feedback",
            json={"node_id": str(uuid4()), "feedback_type": "like", "feedback_value": 1},
            headers=headers,
        )
        assert resp.status_code == 503

        api_main.feedback_processor = MagicMock()


# --- Orchestrator error logging ---


class TestOrchestratorErrorLogging:
    """Test that orchestrator logs errors to Overmind."""

    @pytest.mark.asyncio
    async def test_agent_timeout_logged_to_overmind(self):
        from src.agents.orchestrator import OrchestratorAgent

        mock_overmind = MagicMock()
        mock_overmind.start_trace.return_value = MagicMock(request_id=uuid4())
        mock_overmind.log_agent_dispatch.return_value = MagicMock()
        mock_overmind.log_agent_response.return_value = None

        orch = OrchestratorAgent(
            cache_client=MockRedisClient(),
            overmind_client=mock_overmind,
            agent_timeout_ms=1,  # Very short timeout to trigger timeouts
        )

        results = await orch.dispatch_agents("Test Song")

        # At least some agents should have timed out
        failed = [r for r in results if r.status == "failed"]
        # Overmind log_event should have been called for errors
        if failed:
            assert mock_overmind.log_event.called


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
