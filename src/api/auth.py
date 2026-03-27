"""Authentication service with JWT and bcrypt."""

import logging
from datetime import datetime, timedelta
from typing import Optional
from uuid import UUID, uuid4

import bcrypt
import jwt
from pydantic import BaseModel

from config.settings import settings
from src.cache.redis_client import RedisClient

logger = logging.getLogger(__name__)


class User(BaseModel):
    """User model."""

    id: UUID
    username: str
    email: str
    created_at: datetime


class TokenResponse(BaseModel):
    """JWT token response."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class AuthService:
    """Authentication service for user management and JWT tokens."""

    def __init__(self, cache_client: RedisClient):
        """Initialize auth service.

        Args:
            cache_client: Redis client for storing user data and tokens
        """
        self.cache_client = cache_client
        self.secret_key = settings.secret_key
        self.algorithm = settings.jwt_algorithm
        self.access_token_expire_minutes = settings.jwt_access_token_expire_minutes
        self.refresh_token_expire_days = settings.jwt_refresh_token_expire_days

    def _hash_password(self, password: str) -> str:
        """Hash password using bcrypt with salt.

        Args:
            password: Plain text password

        Returns:
            Hashed password
        """
        salt = bcrypt.gensalt()
        hashed = bcrypt.hashpw(password.encode("utf-8"), salt)
        return hashed.decode("utf-8")

    def _verify_password(self, password: str, hashed: str) -> bool:
        """Verify password against hash.

        Args:
            password: Plain text password
            hashed: Hashed password

        Returns:
            True if password matches
        """
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))

    def _create_access_token(self, user_id: UUID, username: str) -> str:
        """Create JWT access token.

        Args:
            user_id: User ID
            username: Username

        Returns:
            JWT access token
        """
        expire = datetime.utcnow() + timedelta(minutes=self.access_token_expire_minutes)
        payload = {
            "sub": str(user_id),
            "username": username,
            "exp": expire,
            "type": "access",
        }
        return jwt.encode(payload, self.secret_key, algorithm=self.algorithm)

    def _create_refresh_token(self, user_id: UUID) -> str:
        """Create JWT refresh token.

        Args:
            user_id: User ID

        Returns:
            JWT refresh token
        """
        expire = datetime.utcnow() + timedelta(days=self.refresh_token_expire_days)
        payload = {
            "sub": str(user_id),
            "exp": expire,
            "type": "refresh",
        }
        return jwt.encode(payload, self.secret_key, algorithm=self.algorithm)

    async def register_user(self, username: str, password: str, email: str) -> TokenResponse:
        """Register a new user.

        Args:
            username: Username (must be unique)
            password: Plain text password
            email: Email address

        Returns:
            TokenResponse with access and refresh tokens

        Raises:
            ValueError: If username already exists or validation fails
        """
        # Validate input
        if len(username) < 3:
            raise ValueError("Username must be at least 3 characters")
        if len(password) < 8:
            raise ValueError("Password must be at least 8 characters")

        # Check if username exists
        user_key = f"user:username:{username}"
        existing = self.cache_client.get(user_key)
        if existing:
            raise ValueError("Username already exists")

        # Create user
        user_id = uuid4()
        hashed_password = self._hash_password(password)

        user_data = {
            "id": str(user_id),
            "username": username,
            "email": email,
            "password_hash": hashed_password,
            "created_at": datetime.utcnow().isoformat(),
        }

        # Store user data
        user_id_key = f"user:id:{user_id}"
        self.cache_client.set(user_key, user_data, ttl=0)  # No expiration
        self.cache_client.set(user_id_key, user_data, ttl=0)

        logger.info(f"User registered: {username}")

        # Generate tokens
        access_token = self._create_access_token(user_id, username)
        refresh_token = self._create_refresh_token(user_id)

        # Store refresh token
        refresh_key = f"refresh_token:{user_id}"
        self.cache_client.set(
            refresh_key,
            {"token": refresh_token},
            ttl=self.refresh_token_expire_days * 24 * 60 * 60,
        )

        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=self.access_token_expire_minutes * 60,
        )

    async def login_user(self, username: str, password: str) -> Optional[TokenResponse]:
        """Login user and generate tokens.

        Args:
            username: Username
            password: Plain text password

        Returns:
            TokenResponse if credentials valid, None otherwise
        """
        # Get user data
        user_key = f"user:username:{username}"
        user_data = self.cache_client.get(user_key)

        if not user_data:
            logger.warning(f"Login failed: user not found - {username}")
            return None

        # Verify password
        if not self._verify_password(password, user_data["password_hash"]):
            logger.warning(f"Login failed: invalid password - {username}")
            return None

        user_id = UUID(user_data["id"])

        # Generate tokens
        access_token = self._create_access_token(user_id, username)
        refresh_token = self._create_refresh_token(user_id)

        # Store refresh token
        refresh_key = f"refresh_token:{user_id}"
        self.cache_client.set(
            refresh_key,
            {"token": refresh_token},
            ttl=self.refresh_token_expire_days * 24 * 60 * 60,
        )

        logger.info(f"User logged in: {username}")

        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=self.access_token_expire_minutes * 60,
        )

    async def verify_token(self, token: str) -> Optional[User]:
        """Verify JWT access token and return user.

        Args:
            token: JWT access token

        Returns:
            User if token valid, None otherwise
        """
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=[self.algorithm])

            if payload.get("type") != "access":
                return None

            user_id = UUID(payload["sub"])
            username = payload["username"]

            # Get user data
            user_id_key = f"user:id:{user_id}"
            user_data = self.cache_client.get(user_id_key)

            if not user_data:
                return None

            return User(
                id=user_id,
                username=username,
                email=user_data["email"],
                created_at=datetime.fromisoformat(user_data["created_at"]),
            )
        except jwt.ExpiredSignatureError:
            logger.debug("Token expired")
            return None
        except jwt.InvalidTokenError as e:
            logger.debug(f"Invalid token: {e}")
            return None
        except Exception as e:
            logger.error(f"Token verification failed: {e}")
            return None

    async def refresh_access_token(self, refresh_token: str) -> Optional[TokenResponse]:
        """Refresh access token using refresh token.

        Args:
            refresh_token: JWT refresh token

        Returns:
            TokenResponse with new tokens if valid, None otherwise
        """
        try:
            payload = jwt.decode(refresh_token, self.secret_key, algorithms=[self.algorithm])

            if payload.get("type") != "refresh":
                return None

            user_id = UUID(payload["sub"])

            # Verify refresh token is stored
            refresh_key = f"refresh_token:{user_id}"
            stored_data = self.cache_client.get(refresh_key)

            if not stored_data or stored_data.get("token") != refresh_token:
                logger.warning(f"Refresh token not found or mismatch for user {user_id}")
                return None

            # Get user data
            user_id_key = f"user:id:{user_id}"
            user_data = self.cache_client.get(user_id_key)

            if not user_data:
                return None

            username = user_data["username"]

            # Generate new tokens
            new_access_token = self._create_access_token(user_id, username)
            new_refresh_token = self._create_refresh_token(user_id)

            # Update stored refresh token
            self.cache_client.set(
                refresh_key,
                {"token": new_refresh_token},
                ttl=self.refresh_token_expire_days * 24 * 60 * 60,
            )

            logger.info(f"Token refreshed for user: {username}")

            return TokenResponse(
                access_token=new_access_token,
                refresh_token=new_refresh_token,
                expires_in=self.access_token_expire_minutes * 60,
            )
        except jwt.ExpiredSignatureError:
            logger.debug("Refresh token expired")
            return None
        except jwt.InvalidTokenError as e:
            logger.debug(f"Invalid refresh token: {e}")
            return None
        except Exception as e:
            logger.error(f"Token refresh failed: {e}")
            return None
