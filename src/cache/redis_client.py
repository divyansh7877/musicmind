"""Redis client wrapper for caching enrichment results."""

import json
import logging
from typing import Any, Dict, Optional

import redis
from config.settings import settings

logger = logging.getLogger(__name__)


class RedisClient:
    """Wrapper for Redis caching operations."""

    def __init__(
        self,
        host: str = settings.redis_host,
        port: int = settings.redis_port,
        password: Optional[str] = settings.redis_password,
        db: int = settings.redis_db,
    ):
        """Initialize Redis client.

        Args:
            host: Redis server host
            port: Redis server port
            password: Redis password (optional)
            db: Redis database number
        """
        self.host = host
        self.port = port
        self.password = password
        self.db = db
        self._client: Optional[redis.Redis] = None

    def connect(self) -> None:
        """Establish connection to Redis."""
        try:
            self._client = redis.Redis(
                host=self.host,
                port=self.port,
                password=self.password,
                db=self.db,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5,
            )
            # Test connection
            self._client.ping()
            logger.info(f"Connected to Redis at {self.host}:{self.port}")
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}")
            raise ConnectionError(f"Could not connect to Redis at {self.host}:{self.port}") from e

    def disconnect(self) -> None:
        """Close connection to Redis."""
        if self._client:
            self._client.close()
            self._client = None
            logger.info("Disconnected from Redis")

    def _ensure_connected(self) -> None:
        """Ensure client is connected, reconnect if necessary."""
        if not self._client:
            self.connect()

    def get(self, key: str) -> Optional[Dict[str, Any]]:
        """Get value from cache.

        Args:
            key: Cache key

        Returns:
            Cached value as dictionary or None if not found
        """
        self._ensure_connected()
        try:
            value = self._client.get(key)
            if value:
                logger.debug(f"Cache hit for key: {key}")
                return json.loads(value)
            logger.debug(f"Cache miss for key: {key}")
            return None
        except Exception as e:
            logger.warning(f"Failed to get cache key {key}: {e}")
            return None

    def set(self, key: str, value: Dict[str, Any], ttl: int = settings.cache_ttl_seconds) -> bool:
        """Set value in cache with TTL.

        Args:
            key: Cache key
            value: Value to cache (must be JSON serializable)
            ttl: Time-to-live in seconds (default from settings)

        Returns:
            True if successful, False otherwise
        """
        self._ensure_connected()
        try:
            serialized = json.dumps(value, default=str)
            self._client.setex(key, ttl, serialized)
            logger.debug(f"Cached key: {key} with TTL: {ttl}s")
            return True
        except Exception as e:
            logger.warning(f"Failed to set cache key {key}: {e}")
            return False

    def delete(self, key: str) -> bool:
        """Delete key from cache.

        Args:
            key: Cache key to delete

        Returns:
            True if key was deleted, False otherwise
        """
        self._ensure_connected()
        try:
            result = self._client.delete(key)
            logger.debug(f"Deleted cache key: {key}")
            return result > 0
        except Exception as e:
            logger.warning(f"Failed to delete cache key {key}: {e}")
            return False

    def exists(self, key: str) -> bool:
        """Check if key exists in cache.

        Args:
            key: Cache key to check

        Returns:
            True if key exists, False otherwise
        """
        self._ensure_connected()
        try:
            return self._client.exists(key) > 0
        except Exception as e:
            logger.warning(f"Failed to check cache key {key}: {e}")
            return False

    @staticmethod
    def make_song_cache_key(song_name: str) -> str:
        """Generate cache key for song enrichment.

        Args:
            song_name: Song name

        Returns:
            Cache key in format: song:{song_name}:v1
        """
        # Normalize song name for consistent caching
        normalized = song_name.lower().strip()
        return f"song:{normalized}:v1"

    def __enter__(self):
        """Context manager entry."""
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.disconnect()
