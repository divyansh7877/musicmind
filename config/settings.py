"""Centralized configuration settings for MusicMind Agent Platform."""

from typing import Optional
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # External API Credentials
    spotify_client_id: str = Field(..., description="Spotify API client ID")
    spotify_client_secret: str = Field(..., description="Spotify API client secret")
    lastfm_api_key: str = Field(..., description="Last.fm API key")
    musicbrainz_user_agent: str = Field(
        default="MusicMindAgent/0.1.0 (contact@example.com)",
        description="MusicBrainz user agent with contact email",
    )

    # Database Configuration
    aerospike_host: str = Field(default="localhost", description="Aerospike host")
    aerospike_port: int = Field(default=3000, description="Aerospike port")
    aerospike_namespace: str = Field(default="musicmind", description="Aerospike namespace")

    # Redis Configuration
    redis_host: str = Field(default="localhost", description="Redis host")
    redis_port: int = Field(default=6379, description="Redis port")
    redis_password: Optional[str] = Field(default=None, description="Redis password")
    redis_db: int = Field(default=0, description="Redis database number")
    redis_max_memory: str = Field(default="2gb", description="Redis max memory")

    # Application Configuration
    app_env: str = Field(default="development", description="Application environment")
    app_host: str = Field(default="0.0.0.0", description="Application host")
    app_port: int = Field(default=8000, description="Application port")
    secret_key: str = Field(..., description="Secret key for JWT signing")
    jwt_algorithm: str = Field(default="HS256", description="JWT algorithm")
    jwt_access_token_expire_minutes: int = Field(
        default=60, description="JWT access token expiration in minutes"
    )
    jwt_refresh_token_expire_days: int = Field(
        default=7, description="JWT refresh token expiration in days"
    )

    # Overmind Lab Configuration
    overmind_api_key: Optional[str] = Field(
        default=None, description="Overmind Lab API key"
    )
    overmind_endpoint: str = Field(
        default="https://api.overmind.com", description="Overmind Lab endpoint"
    )

    # Rate Limiting
    rate_limit_requests_per_minute: int = Field(
        default=10, description="Rate limit requests per minute per user"
    )

    # Cache Configuration
    cache_ttl_seconds: int = Field(
        default=3600, description="Cache time-to-live in seconds"
    )

    # Agent Timeouts
    agent_timeout_ms: int = Field(
        default=30000, description="Agent timeout in milliseconds"
    )

    # Self-Improvement Configuration
    completeness_threshold: float = Field(
        default=0.7, description="Completeness score threshold for enrichment"
    )
    enrichment_stale_days: int = Field(
        default=30, description="Days before node is considered stale"
    )

    @field_validator("completeness_threshold")
    @classmethod
    def validate_completeness_threshold(cls, v: float) -> float:
        """Validate completeness threshold is between 0.0 and 1.0."""
        if not 0.0 <= v <= 1.0:
            raise ValueError("completeness_threshold must be between 0.0 and 1.0")
        return v

    @field_validator("jwt_access_token_expire_minutes")
    @classmethod
    def validate_jwt_access_token_expire(cls, v: int) -> int:
        """Validate JWT access token expiration is positive."""
        if v <= 0:
            raise ValueError("jwt_access_token_expire_minutes must be positive")
        return v

    @field_validator("agent_timeout_ms")
    @classmethod
    def validate_agent_timeout(cls, v: int) -> int:
        """Validate agent timeout is positive."""
        if v <= 0:
            raise ValueError("agent_timeout_ms must be positive")
        return v

    @property
    def redis_url(self) -> str:
        """Construct Redis connection URL."""
        if self.redis_password:
            return f"redis://:{self.redis_password}@{self.redis_host}:{self.redis_port}/{self.redis_db}"
        return f"redis://{self.redis_host}:{self.redis_port}/{self.redis_db}"

    @property
    def is_production(self) -> bool:
        """Check if running in production environment."""
        return self.app_env.lower() == "production"

    @property
    def is_development(self) -> bool:
        """Check if running in development environment."""
        return self.app_env.lower() == "development"


# Global settings instance
settings = Settings()
