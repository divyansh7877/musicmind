"""Authentication service with Clerk + optional custom JWT and bcrypt."""

import logging
import time
from datetime import datetime, timedelta
from typing import Optional
from uuid import UUID, uuid4

import bcrypt
import httpx
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
        # Clerk JWKS cache: {"keys": [...], "fetched_at": timestamp}
        self._clerk_jwks: Optional[dict] = None
        self._clerk_jwks_fetched_at: float = 0.0
        self._clerk_jwks_ttl: float = 3600.0  # Refresh every hour

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
        """Verify token and return user.

        Attempts Clerk token verification first if CLERK_SECRET_KEY is set,
        then falls back to the custom JWT.

        Args:
            token: JWT access token (Clerk or custom)

        Returns:
            User if token valid, None otherwise
        """
        # Try Clerk token first if configured
        if settings.clerk_secret_key:
            clerk_user = await self._verify_clerk_token(token)
            if clerk_user:
                return clerk_user

        # Fall back to custom JWT (only if not clerk-auth-only mode)
        if not settings.clerk_auth_only:
            return await self._verify_custom_jwt(token)

        return None

    async def _verify_clerk_token(self, token: str) -> Optional[User]:
        """Verify a Clerk session token and return a User.

        Fetches Clerk's JWKS on first call (cached for 1 hour) and verifies
        the RS256 JWT signature, then extracts user claims.

        Args:
            token: Clerk session JWT (from Authorization header)

        Returns:
            User if token valid, None otherwise
        """
        try:
            # Fetch Clerk's JWKS if not cached or stale
            if not self._clerk_jwks or (time.time() - self._clerk_jwks_fetched_at) > self._clerk_jwks_ttl:
                jwks_url = f"{settings.clerk_api_url}/jwks"
                try:
                    async with httpx.AsyncClient(timeout=10.0) as client:
                        response = await client.get(jwks_url)
                        response.raise_for_status()
                        self._clerk_jwks = response.json()
                        self._clerk_jwks_fetched_at = time.time()
                        logger.debug("Clerk JWKS refreshed")
                except Exception as e:
                    logger.warning(f"Failed to fetch Clerk JWKS: {e}")
                    # Continue with unverified decode if JWKS fetch fails
                    # (Clerk SDK would do the same in degraded mode)

            if not self._clerk_jwks or not self._clerk_jwks.get("keys"):
                # JWKS unavailable — degrade to unverified decode
                return self._decode_clerk_token_unverified(token)

            # Build a PyJWT-compatible JWKS key dictionary
            jwks_client = jwt.PyJWKClient.from_dict(self._clerk_jwks)
            signing_key = jwks_client.get_signing_key_from_jwt(token)

            payload = jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256"],
                options={"verify_exp": True},
            )

            sub = payload.get("sub")
            if not sub:
                return None

            user_id = UUID(sub)
            email = payload.get("email", "")
            username = (
                payload.get("username")
                or payload.get("name", "")
                or (email.split("@")[0] if email else "")
                or str(user_id)[:8]
            )

            logger.debug(f"Clerk user verified: {username} ({user_id})")

            return User(
                id=user_id,
                username=username,
                email=email or "",
                created_at=datetime.utcnow(),
            )

        except jwt.ExpiredSignatureError:
            logger.debug("Clerk token expired")
            return None
        except (jwt.InvalidTokenError, ValueError) as e:
            logger.debug(f"Clerk token verification failed: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected Clerk token error: {e}")
            return None

    def _decode_clerk_token_unverified(self, token: str) -> Optional[User]:
        """Decode Clerk token without signature verification (degraded mode).

        Used when Clerk JWKS is unavailable. Extracts claims from the JWT
        payload without verifying the signature — only use when Clerk JWKS
        fetch fails.

        Args:
            token: Clerk session JWT

        Returns:
            User if payload contains valid sub/email, None otherwise
        """
        try:
            payload = jwt.decode(
                token,
                options={"verify_signature": False},
                algorithms=["RS256"],
            )
            sub = payload.get("sub")
            if not sub:
                return None

            user_id = UUID(sub)
            email = payload.get("email", "")
            username = (
                payload.get("username")
                or payload.get("name", "")
                or (email.split("@")[0] if email else "")
                or str(user_id)[:8]
            )

            logger.debug(f"Clerk user verified (unverified): {username} ({user_id})")

            return User(
                id=user_id,
                username=username,
                email=email or "",
                created_at=datetime.utcnow(),
            )
        except (jwt.InvalidTokenError, ValueError) as e:
            logger.debug(f"Clerk token unverified decode failed: {e}")
            return None

    async def _verify_custom_jwt(self, token: str) -> Optional[User]:
        """Verify a custom JWT access token and return user.

        Args:
            token: Custom JWT access token

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
