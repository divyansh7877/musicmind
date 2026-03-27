"""Tests for FastAPI backend API endpoints."""

import pytest
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from fastapi.testclient import TestClient

from src.api.auth import AuthService
from src.api.rate_limiter import RateLimiter
from src.api.security import InputValidator, CSRFProtection


class MockRedisClient:
    """Mock Redis client for testing."""

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
def mock_redis():
    return MockRedisClient()


@pytest.fixture
def auth_service(mock_redis):
    return AuthService(cache_client=mock_redis)


@pytest.fixture
def client():
    """Create test client with mocked globals."""
    import src.api.main as api_main

    mock_redis = MockRedisClient()
    mock_overmind = MagicMock()
    mock_overmind.start_trace.return_value = MagicMock(request_id=uuid4())
    mock_overmind.log_agent_dispatch.return_value = MagicMock()
    mock_overmind.log_agent_response.return_value = None
    mock_overmind.log_metric.return_value = None
    mock_overmind.log_event.return_value = None

    auth_svc = AuthService(cache_client=mock_redis)
    rate_lim = RateLimiter(cache_client=mock_redis)

    # Patch module-level globals
    api_main.auth_service = auth_svc
    api_main.rate_limiter = rate_lim
    api_main.redis_client = mock_redis
    api_main.orchestrator = MagicMock()
    api_main.feedback_processor = MagicMock()

    yield TestClient(api_main.app, raise_server_exceptions=False)

    # Cleanup
    api_main.auth_service = None
    api_main.rate_limiter = None
    api_main.orchestrator = None
    api_main.feedback_processor = None


def _register_user(client, username=None, password="testpass123", email="test@example.com"):
    """Helper to register a user and return tokens."""
    username = username or f"testuser_{uuid4().hex[:8]}"
    response = client.post(
        "/api/auth/register",
        params={"username": username, "password": password, "email": email},
    )
    return response


def _get_auth_header(client, username=None):
    """Helper to register user and return auth header."""
    response = _register_user(client, username)
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


# --- Health Check ---


def test_health_check(client):
    """Test health check endpoint."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "timestamp" in data
    assert "services" in data


# --- Authentication ---


def test_register_user(client):
    """Test user registration."""
    response = _register_user(client)
    assert response.status_code == 201
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"
    assert data["expires_in"] > 0


def test_register_user_short_username(client):
    """Test registration with short username fails."""
    response = _register_user(client, username="ab", password="testpass123")
    assert response.status_code == 400


def test_register_user_short_password(client):
    """Test registration with short password fails."""
    response = _register_user(client, password="short")
    assert response.status_code == 400


def test_register_duplicate_username(client):
    """Test registration with duplicate username fails."""
    username = f"testuser_{uuid4().hex[:8]}"
    _register_user(client, username=username)
    response = _register_user(client, username=username)
    assert response.status_code == 400


def test_login_user(client):
    """Test user login."""
    username = f"testuser_{uuid4().hex[:8]}"
    password = "testpass123"

    _register_user(client, username=username, password=password)

    response = client.post(
        "/api/auth/login",
        params={"username": username, "password": password},
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data


def test_login_invalid_credentials(client):
    """Test login with wrong password."""
    username = f"testuser_{uuid4().hex[:8]}"
    _register_user(client, username=username, password="testpass123")

    response = client.post(
        "/api/auth/login",
        params={"username": username, "password": "wrongpassword"},
    )
    assert response.status_code == 401


def test_login_nonexistent_user(client):
    """Test login with non-existent user."""
    response = client.post(
        "/api/auth/login",
        params={"username": "nonexistent", "password": "testpass123"},
    )
    assert response.status_code == 401


def test_refresh_token(client):
    """Test token refresh."""
    reg_response = _register_user(client)
    refresh_token = reg_response.json()["refresh_token"]

    response = client.post(
        "/api/auth/refresh",
        params={"refresh_token": refresh_token},
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data


def test_refresh_invalid_token(client):
    """Test refresh with invalid token."""
    response = client.post(
        "/api/auth/refresh",
        params={"refresh_token": "invalid.token.here"},
    )
    assert response.status_code == 401


# --- Search ---


def test_search_requires_auth(client):
    """Test search endpoint requires authentication."""
    response = client.post("/api/search", json={"song_name": "Test Song"})
    assert response.status_code == 403


def test_search_with_auth(client):
    """Test search endpoint with valid auth token."""
    import src.api.main as api_main

    # Mock the orchestrator's enrich_song
    from src.agents.orchestrator import EnrichmentResult

    mock_result = EnrichmentResult(
        status="success",
        graph_node_ids=[uuid4()],
        merged_data={"song": {"title": "Test Song"}, "data_sources": ["spotify"]},
        completeness_score=0.85,
        request_id=uuid4(),
    )
    api_main.orchestrator.enrich_song = AsyncMock(return_value=mock_result)

    headers = _get_auth_header(client)
    response = client.post(
        "/api/search",
        json={"song_name": "Test Song"},
        headers=headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["completeness_score"] == 0.85


# --- Input Validation ---


def test_input_validation_long_song_name(client):
    """Test input validation rejects too-long song names."""
    headers = _get_auth_header(client)
    response = client.post(
        "/api/search",
        json={"song_name": "a" * 201},
        headers=headers,
    )
    assert response.status_code == 422


def test_input_validation_empty_song_name(client):
    """Test input validation rejects empty song names."""
    headers = _get_auth_header(client)
    response = client.post(
        "/api/search",
        json={"song_name": ""},
        headers=headers,
    )
    assert response.status_code == 422


# --- Feedback ---


def test_feedback_requires_auth(client):
    """Test feedback endpoint requires authentication."""
    response = client.post(
        "/api/feedback",
        json={
            "node_id": str(uuid4()),
            "feedback_type": "like",
            "feedback_value": 1,
        },
    )
    assert response.status_code == 403


def test_feedback_with_auth(client):
    """Test feedback endpoint with valid auth."""
    import src.api.main as api_main

    api_main.feedback_processor.process_user_feedback = MagicMock()

    headers = _get_auth_header(client)
    response = client.post(
        "/api/feedback",
        json={
            "node_id": str(uuid4()),
            "feedback_type": "like",
            "feedback_value": 1,
        },
        headers=headers,
    )
    assert response.status_code == 201
    assert response.json()["status"] == "success"


# --- Activity Feed ---


def test_activity_feed_requires_auth(client):
    """Test activity endpoint requires authentication."""
    response = client.get("/api/activity")
    assert response.status_code == 403


def test_activity_feed_with_auth(client):
    """Test activity endpoint returns data."""
    headers = _get_auth_header(client)
    response = client.get("/api/activity", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert "activities" in data
    assert "total" in data


# --- Security ---


class TestInputValidator:
    """Test input validation utilities."""

    def test_valid_song_names(self):
        assert InputValidator.validate_song_name("Bohemian Rhapsody")
        assert InputValidator.validate_song_name("Don't Stop Me Now")
        assert InputValidator.validate_song_name("Under Pressure (Live)")

    def test_invalid_song_names(self):
        assert not InputValidator.validate_song_name("")
        assert not InputValidator.validate_song_name("a" * 201)
        assert not InputValidator.validate_song_name("<script>alert(1)</script>")

    def test_sanitize_html(self):
        sanitized = InputValidator.sanitize_html("<script>alert('xss')</script>")
        assert "<script>" not in sanitized
        assert "alert" not in sanitized or "&" in sanitized

    def test_validate_username(self):
        assert InputValidator.validate_username("testuser")
        assert InputValidator.validate_username("user_123")
        assert not InputValidator.validate_username("ab")
        assert not InputValidator.validate_username("a" * 33)

    def test_validate_email(self):
        assert InputValidator.validate_email("test@example.com")
        assert not InputValidator.validate_email("invalid")
        assert not InputValidator.validate_email("@example.com")


class TestCSRFProtection:
    """Test CSRF token generation and validation."""

    def test_generate_and_validate_token(self):
        token = CSRFProtection.generate_token("user123", "secret")
        assert CSRFProtection.validate_token(token, "user123", "secret")

    def test_invalid_token(self):
        assert not CSRFProtection.validate_token("invalid:token", "user123", "secret")

    def test_wrong_user_token(self):
        token = CSRFProtection.generate_token("user123", "secret")
        assert not CSRFProtection.validate_token(token, "user456", "secret")


class TestRateLimiter:
    """Test rate limiting functionality."""

    @pytest.mark.asyncio
    async def test_rate_limit_allows_within_limit(self):
        mock_redis = MockRedisClient()
        limiter = RateLimiter(cache_client=mock_redis, max_requests=5)

        for i in range(5):
            assert await limiter.check_rate_limit("user1", "search")

    @pytest.mark.asyncio
    async def test_rate_limit_blocks_over_limit(self):
        mock_redis = MockRedisClient()
        limiter = RateLimiter(cache_client=mock_redis, max_requests=3)

        for i in range(3):
            await limiter.check_rate_limit("user1", "search")

        # 4th request should be blocked
        assert not await limiter.check_rate_limit("user1", "search")

    @pytest.mark.asyncio
    async def test_rate_limit_separate_users(self):
        mock_redis = MockRedisClient()
        limiter = RateLimiter(cache_client=mock_redis, max_requests=2)

        await limiter.check_rate_limit("user1", "search")
        await limiter.check_rate_limit("user1", "search")

        # user2 should still be allowed
        assert await limiter.check_rate_limit("user2", "search")


# --- Auth Service ---


class TestAuthService:
    """Test auth service JWT token management."""

    @pytest.mark.asyncio
    async def test_access_token_verified(self, auth_service):
        tokens = await auth_service.register_user("testuser", "testpass123", "test@example.com")
        user = await auth_service.verify_token(tokens.access_token)
        assert user is not None
        assert user.username == "testuser"

    @pytest.mark.asyncio
    async def test_expired_token_rejected(self, auth_service):
        user = await auth_service.verify_token("expired.invalid.token")
        assert user is None

    @pytest.mark.asyncio
    async def test_refresh_token_not_valid_as_access(self, auth_service):
        tokens = await auth_service.register_user("testuser2", "testpass123", "test@example.com")
        user = await auth_service.verify_token(tokens.refresh_token)
        assert user is None  # Refresh token type != "access"


# --- Graph Traversal ---


class TestGraphTraversal:
    """Test graph traversal service."""

    def test_traversal_request_validation(self):
        from src.api.graph import GraphTraversalRequest

        req = GraphTraversalRequest(max_depth=3)
        assert req.max_depth == 3

        with pytest.raises(Exception):
            GraphTraversalRequest(max_depth=0)

        with pytest.raises(Exception):
            GraphTraversalRequest(max_depth=6)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
