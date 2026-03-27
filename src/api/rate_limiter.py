"""Rate limiter for API endpoints."""

import logging
from datetime import datetime, timedelta

from src.cache.redis_client import RedisClient

logger = logging.getLogger(__name__)


class RateLimiter:
    """Rate limiter using sliding window algorithm."""

    def __init__(self, cache_client: RedisClient, max_requests: int = 10):
        """Initialize rate limiter.

        Args:
            cache_client: Redis client for storing request counts
            max_requests: Maximum requests per minute per user
        """
        self.cache_client = cache_client
        self.max_requests = max_requests
        self.window_seconds = 60

    async def check_rate_limit(self, user_id: str, endpoint: str) -> bool:
        """Check if user is within rate limit.

        Args:
            user_id: User identifier
            endpoint: API endpoint name

        Returns:
            True if request allowed, False if rate limit exceeded
        """
        key = f"rate_limit:{user_id}:{endpoint}"

        try:
            # Get current request count
            data = self.cache_client.get(key)

            if not data:
                # First request in window
                self.cache_client.set(
                    key,
                    {
                        "count": 1,
                        "window_start": datetime.utcnow().isoformat(),
                    },
                    ttl=self.window_seconds,
                )
                return True

            count = data.get("count", 0)
            window_start = datetime.fromisoformat(data["window_start"])

            # Check if window expired
            if datetime.utcnow() - window_start > timedelta(seconds=self.window_seconds):
                # Reset window
                self.cache_client.set(
                    key,
                    {
                        "count": 1,
                        "window_start": datetime.utcnow().isoformat(),
                    },
                    ttl=self.window_seconds,
                )
                return True

            # Check if limit exceeded
            if count >= self.max_requests:
                logger.warning(f"Rate limit exceeded for user {user_id} on {endpoint}")
                return False

            # Increment count
            self.cache_client.set(
                key,
                {
                    "count": count + 1,
                    "window_start": window_start.isoformat(),
                },
                ttl=self.window_seconds,
            )

            return True
        except Exception as e:
            logger.error(f"Rate limit check failed: {e}")
            # Allow request on error to avoid blocking users
            return True
