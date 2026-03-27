"""FastAPI application for MusicMind web frontend."""

import logging
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import FastAPI, HTTPException, Depends, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field, field_validator
from pydantic import ValidationError as PydanticValidationError

from config.settings import settings
from src.agents.orchestrator import OrchestratorAgent
from src.cache.redis_client import RedisClient
from src.database.aerospike_client import AerospikeClient
from src.errors.exceptions import (
    MusicMindError,
    RateLimitError as MusicMindRateLimitError,
    ServiceUnavailableError,
)
from src.errors.handlers import build_error_response, log_error_to_overmind
from src.self_improvement.feedback_processor import FeedbackProcessor, UserFeedback
from src.self_improvement.quality_tracker import QualityTracker
from src.self_improvement.enrichment_scheduler import EnrichmentScheduler
from src.tracing.overmind_client import OvermindClient
from src.api.auth import AuthService, User, TokenResponse
from src.api.graph import GraphService, GraphTraversalRequest, GraphTraversalResponse
from src.api.rate_limiter import RateLimiter
from src.api.security import InputValidator

logger = logging.getLogger(__name__)

# Initialize clients
redis_client = RedisClient()
db_client = None
overmind_client = None
orchestrator = None
feedback_processor = None
auth_service = None
graph_service = None
rate_limiter = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle manager for FastAPI application."""
    global db_client, overmind_client, orchestrator, feedback_processor, auth_service, graph_service, rate_limiter

    # Initialize clients
    try:
        db_client = AerospikeClient()
        logger.info("Aerospike client initialized")
    except Exception as e:
        logger.warning(f"Failed to initialize Aerospike: {e}")

    if settings.overmind_api_key:
        overmind_client = OvermindClient()
        logger.info("Overmind client initialized")

    # Initialize orchestrator
    orchestrator = OrchestratorAgent(
        cache_client=redis_client,
        overmind_client=overmind_client,
        db_client=db_client,
    )
    logger.info("Orchestrator initialized")

    # Initialize feedback processor
    if db_client:
        quality_tracker = QualityTracker(
            cache_client=redis_client,
            overmind_client=overmind_client,
        )
        enrichment_scheduler = EnrichmentScheduler(
            db_client=db_client,
            overmind_client=overmind_client,
        )
        feedback_processor = FeedbackProcessor(
            db_client=db_client,
            quality_tracker=quality_tracker,
            enrichment_scheduler=enrichment_scheduler,
            cache_client=redis_client,
            overmind_client=overmind_client,
        )
        logger.info("Feedback processor initialized")

    # Initialize auth service
    auth_service = AuthService(cache_client=redis_client)
    logger.info("Auth service initialized")

    # Initialize graph service
    if db_client:
        graph_service = GraphService(db_client=db_client)
        logger.info("Graph service initialized")

    # Initialize rate limiter
    rate_limiter = RateLimiter(
        cache_client=redis_client,
        max_requests=settings.rate_limit_requests_per_minute,
    )
    logger.info("Rate limiter initialized")

    yield

    # Cleanup
    logger.info("Shutting down application")


app = FastAPI(
    title="MusicMind API",
    description="REST API for MusicMind music knowledge graph",
    version="1.0.0",
    lifespan=lifespan,
)

# Configure CORS
_cors_origins = (
    ["*"]
    if settings.cors_origins == "*"
    else [o.strip() for o in settings.cors_origins.split(",")]
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Global Exception Handlers ---


@app.exception_handler(MusicMindError)
async def musicmind_error_handler(request: Request, exc: MusicMindError):
    """Handle all MusicMind domain errors with structured responses."""
    log_error_to_overmind(overmind_client, operation=request.url.path, error=exc)

    status_map = {
        "AGENT_TIMEOUT": 504,
        "RATE_LIMIT_EXCEEDED": 429,
        "DATABASE_CONNECTION_ERROR": 503,
        "SERVICE_UNAVAILABLE": 503,
        "CONCURRENT_WRITE_CONFLICT": 409,
        "VALIDATION_ERROR": 422,
        "DATA_VALIDATION_ERROR": 422,
    }
    status_code = status_map.get(exc.error_code, 500)

    headers = {}
    if isinstance(exc, MusicMindRateLimitError) and exc.retry_after:
        headers["Retry-After"] = str(exc.retry_after)

    return JSONResponse(
        status_code=status_code,
        content=build_error_response(
            error_code=exc.error_code,
            message=exc.message,
            details=exc.details,
            retryable=exc.retryable,
        ),
        headers=headers,
    )


@app.exception_handler(PydanticValidationError)
async def pydantic_validation_handler(request: Request, exc: PydanticValidationError):
    """Handle Pydantic validation errors with structured responses."""
    return JSONResponse(
        status_code=422,
        content=build_error_response(
            error_code="VALIDATION_ERROR",
            message="Request validation failed",
            details={"errors": exc.errors()},
            retryable=False,
        ),
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """Catch-all handler for unexpected errors."""
    log_error_to_overmind(
        overmind_client,
        operation=request.url.path,
        error=exc,
        extra={"method": request.method},
    )
    return JSONResponse(
        status_code=500,
        content=build_error_response(
            error_code="INTERNAL_ERROR",
            message="An unexpected error occurred",
            retryable=False,
        ),
    )


# Security
security = HTTPBearer()


# Request/Response Models
class SearchRequest(BaseModel):
    """Request model for song search."""

    song_name: str = Field(..., min_length=1, max_length=200, description="Song name to search")

    @field_validator("song_name")
    @classmethod
    def validate_song_name(cls, v: str) -> str:
        """Validate and sanitize song name."""
        if not InputValidator.validate_song_name(v):
            raise ValueError("Invalid song name format")
        return InputValidator.sanitize_html(v)


class SearchResponse(BaseModel):
    """Response model for song search."""

    status: str
    request_id: str
    graph_node_ids: List[str]
    merged_data: Dict[str, Any]
    completeness_score: float
    error_message: Optional[str] = None


class FeedbackRequest(BaseModel):
    """Request model for user feedback."""

    node_id: UUID
    feedback_type: str
    feedback_value: int = Field(ge=-1, le=1)
    comment: Optional[str] = None

    @field_validator("comment")
    @classmethod
    def validate_comment(cls, v: Optional[str]) -> Optional[str]:
        """Validate and sanitize comment."""
        if v:
            return InputValidator.validate_and_sanitize_comment(v)
        return v


class ActivityItem(BaseModel):
    """Activity feed item."""

    id: str
    type: str
    timestamp: str
    description: str
    metadata: Dict[str, Any]


class ActivityResponse(BaseModel):
    """Response model for activity feed."""

    activities: List[ActivityItem]
    total: int


# Dependency: Get current user
async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> User:
    """Get current authenticated user from JWT token."""
    if not auth_service:
        raise HTTPException(status_code=503, detail="Auth service not available")

    token = credentials.credentials
    user = await auth_service.verify_token(token)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )

    return user


# Dependency: Rate limiting
async def check_rate_limit(user: User = Depends(get_current_user)):
    """Check rate limit for current user."""
    if not rate_limiter:
        return

    allowed = await rate_limiter.check_rate_limit(str(user.id), "search")
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded. Please try again later.",
        )


# Health check endpoint
@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "services": {
            "redis": redis_client is not None,
            "aerospike": db_client is not None,
            "overmind": overmind_client is not None,
        },
    }


# Search endpoint
@app.post("/api/search", response_model=SearchResponse)
async def search_song(
    request: SearchRequest,
    user: User = Depends(get_current_user),
    _rate_limit: None = Depends(check_rate_limit),
):
    """Search and enrich song data."""
    if not orchestrator:
        raise ServiceUnavailableError("orchestrator")

    try:
        result = await orchestrator.enrich_song(request.song_name)

        return SearchResponse(
            status=result.status,
            request_id=str(result.request_id),
            graph_node_ids=[str(nid) for nid in result.graph_node_ids],
            merged_data=result.merged_data,
            completeness_score=result.completeness_score,
            error_message=result.error_message,
        )
    except MusicMindError:
        raise
    except Exception as e:
        logger.error(f"Search failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# Graph traversal endpoint
@app.post("/api/graph/{node_id}", response_model=GraphTraversalResponse)
async def traverse_graph(
    node_id: UUID,
    request: GraphTraversalRequest,
    user: User = Depends(get_current_user),
):
    """Traverse graph from a node with depth limit."""
    if not graph_service:
        raise ServiceUnavailableError("graph_service")

    try:
        result = await graph_service.traverse_graph(node_id, request.max_depth)
        return result
    except (MusicMindError, HTTPException):
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Graph traversal failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# Feedback endpoint
@app.post("/api/feedback", status_code=status.HTTP_201_CREATED)
async def submit_feedback(
    request: FeedbackRequest,
    user: User = Depends(get_current_user),
):
    """Submit user feedback on data quality."""
    if not feedback_processor:
        raise ServiceUnavailableError("feedback_processor")

    try:
        feedback = UserFeedback(
            user_id=user.id,
            node_id=request.node_id,
            feedback_type=request.feedback_type,
            feedback_value=request.feedback_value,
            comment=request.comment,
        )

        feedback_processor.process_user_feedback(feedback)

        return {"status": "success", "message": "Feedback processed"}
    except (MusicMindError, HTTPException):
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Feedback processing failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# Activity feed endpoint
@app.get("/api/activity", response_model=ActivityResponse)
async def get_activity_feed(
    limit: int = 50,
    offset: int = 0,
    user: User = Depends(get_current_user),
):
    """Get activity feed for user."""
    try:
        # Fetch recent activities from cache
        activities = []

        # Get recent enrichment activities
        # In production, implement proper activity feed storage

        # Mock response for now
        activities = [
            ActivityItem(
                id="1",
                type="enrichment",
                timestamp=datetime.utcnow().isoformat(),
                description="Song enriched successfully",
                metadata={"song": "Example Song", "completeness": 0.85},
            )
        ]

        return ActivityResponse(
            activities=activities[offset : offset + limit],
            total=len(activities),
        )
    except Exception as e:
        logger.error(f"Activity feed failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# Authentication endpoints
@app.post("/api/auth/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(username: str, password: str, email: str):
    """Register a new user."""
    if not auth_service:
        raise ServiceUnavailableError("auth_service")

    try:
        tokens = await auth_service.register_user(username, password, email)
        return tokens
    except (MusicMindError, HTTPException):
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Registration failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/auth/login", response_model=TokenResponse)
async def login(username: str, password: str):
    """Login and get JWT tokens."""
    if not auth_service:
        raise HTTPException(status_code=503, detail="Auth service not available")

    try:
        tokens = await auth_service.login_user(username, password)
        if not tokens:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid credentials",
            )
        return tokens
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Login failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/auth/refresh", response_model=TokenResponse)
async def refresh_token(refresh_token: str):
    """Refresh access token using refresh token."""
    if not auth_service:
        raise HTTPException(status_code=503, detail="Auth service not available")

    try:
        tokens = await auth_service.refresh_access_token(refresh_token)
        if not tokens:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid refresh token",
            )
        return tokens
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Token refresh failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=settings.app_host, port=settings.app_port)
