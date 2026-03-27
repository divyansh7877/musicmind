"""Unit tests for Redis cache client."""

import pytest

from src.cache.redis_client import RedisClient


class MockRedis:
    """Mock Redis connection for testing."""

    def __init__(self):
        self.data = {}
        self.ttls = {}

    def ping(self):
        return True

    def get(self, key):
        return self.data.get(key)

    def setex(self, key, ttl, value):
        self.data[key] = value
        self.ttls[key] = ttl

    def delete(self, key):
        if key in self.data:
            del self.data[key]
            if key in self.ttls:
                del self.ttls[key]
            return 1
        return 0

    def exists(self, key):
        return 1 if key in self.data else 0

    def close(self):
        pass


@pytest.fixture
def mock_redis(monkeypatch):
    """Fixture for mock Redis connection."""
    mock = MockRedis()

    def mock_redis_init(*args, **kwargs):
        return mock

    monkeypatch.setattr("redis.Redis", mock_redis_init)
    return mock


def test_redis_client_connect(mock_redis):
    """Test Redis client connection."""
    client = RedisClient()
    client.connect()
    assert client._client is not None


def test_redis_client_set_and_get(mock_redis):
    """Test setting and getting cache values."""
    client = RedisClient()
    client.connect()

    test_data = {"title": "Test Song", "duration_ms": 180000}
    result = client.set("test_key", test_data, ttl=3600)

    assert result is True

    retrieved = client.get("test_key")
    assert retrieved is not None
    assert retrieved["title"] == "Test Song"
    assert retrieved["duration_ms"] == 180000


def test_redis_client_get_nonexistent(mock_redis):
    """Test getting non-existent key."""
    client = RedisClient()
    client.connect()

    result = client.get("nonexistent_key")
    assert result is None


def test_redis_client_delete(mock_redis):
    """Test deleting cache key."""
    client = RedisClient()
    client.connect()

    client.set("test_key", {"data": "value"})
    assert client.exists("test_key") is True

    result = client.delete("test_key")
    assert result is True
    assert client.exists("test_key") is False


def test_redis_client_exists(mock_redis):
    """Test checking key existence."""
    client = RedisClient()
    client.connect()

    assert client.exists("test_key") is False

    client.set("test_key", {"data": "value"})
    assert client.exists("test_key") is True


def test_make_song_cache_key():
    """Test song cache key generation."""
    key1 = RedisClient.make_song_cache_key("Bohemian Rhapsody")
    assert key1 == "song:bohemian rhapsody:v1"

    key2 = RedisClient.make_song_cache_key("  Test Song  ")
    assert key2 == "song:test song:v1"

    key3 = RedisClient.make_song_cache_key("UPPERCASE")
    assert key3 == "song:uppercase:v1"


def test_redis_client_context_manager(mock_redis):
    """Test Redis client as context manager."""
    with RedisClient() as client:
        assert client._client is not None
        client.set("test_key", {"data": "value"})
        assert client.get("test_key") is not None

    # Client should be disconnected after context
    assert client._client is None


def test_redis_client_auto_reconnect(mock_redis):
    """Test automatic reconnection."""
    client = RedisClient()

    # First operation should auto-connect
    client.set("test_key", {"data": "value"})
    assert client._client is not None

    # Disconnect
    client.disconnect()
    assert client._client is None

    # Next operation should auto-reconnect
    result = client.get("test_key")
    assert client._client is not None
