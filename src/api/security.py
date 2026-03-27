"""Security utilities for input validation and sanitization."""

import html
import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)


class InputValidator:
    """Input validator with whitelist patterns."""

    # Whitelist patterns
    SONG_NAME_PATTERN = re.compile(r"^[a-zA-Z0-9\s\-\'\"\(\)\[\]&.,!?]+$")
    USERNAME_PATTERN = re.compile(r"^[a-zA-Z0-9_-]{3,32}$")
    EMAIL_PATTERN = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")

    @staticmethod
    def validate_song_name(song_name: str) -> bool:
        """Validate song name input.

        Args:
            song_name: Song name to validate

        Returns:
            True if valid, False otherwise
        """
        if not song_name or len(song_name) > 200:
            return False

        return bool(InputValidator.SONG_NAME_PATTERN.match(song_name))

    @staticmethod
    def validate_username(username: str) -> bool:
        """Validate username input.

        Args:
            username: Username to validate

        Returns:
            True if valid, False otherwise
        """
        return bool(InputValidator.USERNAME_PATTERN.match(username))

    @staticmethod
    def validate_email(email: str) -> bool:
        """Validate email input.

        Args:
            email: Email to validate

        Returns:
            True if valid, False otherwise
        """
        return bool(InputValidator.EMAIL_PATTERN.match(email))

    @staticmethod
    def sanitize_html(text: str) -> str:
        """Sanitize user-generated content to prevent XSS.

        Args:
            text: Text to sanitize

        Returns:
            Sanitized text with HTML entities escaped
        """
        if not text:
            return ""

        # Escape HTML entities
        sanitized = html.escape(text)

        # Remove any remaining script tags
        sanitized = re.sub(
            r"<script[^>]*>.*?</script>", "", sanitized, flags=re.IGNORECASE | re.DOTALL
        )

        # Remove event handlers
        sanitized = re.sub(r"on\w+\s*=", "", sanitized, flags=re.IGNORECASE)

        return sanitized

    @staticmethod
    def validate_and_sanitize_comment(comment: str, max_length: int = 1000) -> Optional[str]:
        """Validate and sanitize user comment.

        Args:
            comment: User comment
            max_length: Maximum allowed length

        Returns:
            Sanitized comment or None if invalid
        """
        if not comment:
            return None

        # Trim whitespace
        comment = comment.strip()

        # Check length
        if len(comment) > max_length:
            comment = comment[:max_length]

        # Sanitize HTML
        return InputValidator.sanitize_html(comment)


class CSRFProtection:
    """CSRF token generation and validation."""

    @staticmethod
    def generate_token(user_id: str, secret: str) -> str:
        """Generate CSRF token for user.

        Args:
            user_id: User identifier
            secret: Secret key

        Returns:
            CSRF token
        """
        import hashlib
        import time

        timestamp = str(int(time.time()))
        data = f"{user_id}:{timestamp}:{secret}"
        token = hashlib.sha256(data.encode()).hexdigest()

        return f"{timestamp}:{token}"

    @staticmethod
    def validate_token(token: str, user_id: str, secret: str, max_age: int = 3600) -> bool:
        """Validate CSRF token.

        Args:
            token: CSRF token to validate
            user_id: User identifier
            secret: Secret key
            max_age: Maximum token age in seconds

        Returns:
            True if valid, False otherwise
        """
        import hashlib
        import time

        try:
            timestamp_str, token_hash = token.split(":", 1)
            timestamp = int(timestamp_str)

            # Check age
            if time.time() - timestamp > max_age:
                logger.warning(f"CSRF token expired for user {user_id}")
                return False

            # Verify hash
            data = f"{user_id}:{timestamp_str}:{secret}"
            expected_hash = hashlib.sha256(data.encode()).hexdigest()

            if token_hash != expected_hash:
                logger.warning(f"CSRF token validation failed for user {user_id}")
                return False

            return True
        except Exception as e:
            logger.error(f"CSRF token validation error: {e}")
            return False
