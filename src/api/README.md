# MusicMind API Documentation

FastAPI backend for MusicMind web frontend with REST endpoints for song enrichment, graph traversal, user feedback, and authentication.

## Features

- **Song Search & Enrichment**: Search songs and enrich with multi-agent data
- **Graph Traversal**: BFS traversal with configurable depth (1-5 levels)
- **User Feedback**: Submit feedback to improve data quality
- **Authentication**: JWT-based auth with bcrypt password hashing
- **Rate Limiting**: 10 requests per minute per user
- **Input Validation**: Whitelist patterns and XSS prevention
- **CORS Support**: Configurable for development/production

## Endpoints

### Health Check

```
GET /health
```

Returns service health status.

### Authentication

#### Register User
```
POST /api/auth/register
Params: username, password, email
Response: { access_token, refresh_token, token_type, expires_in }
```

- Password must be at least 8 characters
- Username must be 3-32 alphanumeric characters
- Access token expires in 1 hour
- Refresh token expires in 7 days

#### Login
```
POST /api/auth/login
Params: username, password
Response: { access_token, refresh_token, token_type, expires_in }
```

#### Refresh Token
```
POST /api/auth/refresh
Params: refresh_token
Response: { access_token, refresh_token, token_type, expires_in }
```

### Song Search

```
POST /api/search
Headers: Authorization: Bearer <token>
Body: { "song_name": "Song Name" }
Response: {
  "status": "success",
  "request_id": "uuid",
  "graph_node_ids": ["uuid1", "uuid2"],
  "merged_data": {...},
  "completeness_score": 0.85,
  "error_message": null
}
```

- Requires authentication
- Rate limited to 10 requests per minute
- Song name limited to 200 characters
- Input validated against whitelist pattern

### Graph Traversal

```
POST /api/graph/{node_id}
Headers: Authorization: Bearer <token>
Body: { "max_depth": 2 }
Response: {
  "nodes": [...],
  "edges": [...],
  "total_nodes": 50,
  "total_edges": 75,
  "depth_reached": 2,
  "truncated": false
}
```

- Breadth-first traversal from starting node
- Max depth: 1-5 levels
- Node limit: 1000 nodes
- Ensures no duplicate nodes
- All edges reference nodes in result
- Performance targets:
  - Depth 2: ~500ms
  - Depth 3: ~1s

### User Feedback

```
POST /api/feedback
Headers: Authorization: Bearer <token>
Body: {
  "node_id": "uuid",
  "feedback_type": "like|dislike|correction|report",
  "feedback_value": 1|-1|0,
  "comment": "Optional comment"
}
Response: { "status": "success", "message": "Feedback processed" }
```

- Feedback types:
  - `like`: Positive feedback (increases source quality)
  - `dislike`: Negative feedback (decreases quality, schedules re-enrichment)
  - `correction`: User correction (updates node, penalizes incorrect sources)
  - `report`: Report issue (creates issue report, reduces visibility)
- Comments required for `correction` and `report` types
- Comments sanitized to prevent XSS

### Activity Feed

```
GET /api/activity?limit=50&offset=0
Headers: Authorization: Bearer <token>
Response: {
  "activities": [...],
  "total": 100
}
```

Returns recent enrichment and feedback activities.

## Security Features

### Input Validation

- Song names: Alphanumeric + common punctuation, max 200 chars
- Usernames: 3-32 alphanumeric characters, underscores, hyphens
- Email: Standard email format validation
- Comments: HTML sanitized, max 1000 chars

### XSS Prevention

- All user-generated content HTML-escaped
- Script tags removed
- Event handlers stripped
- String lengths limited

### CSRF Protection

- CSRF token generation and validation
- Token expiration: 1 hour
- Required for state-changing operations

### Rate Limiting

- Sliding window algorithm
- 10 requests per minute per user
- Separate limits per endpoint
- Redis-backed for distributed systems

### Authentication

- JWT tokens with HS256 algorithm
- Bcrypt password hashing with salt
- Access token: 1 hour expiration
- Refresh token: 7 days expiration
- Tokens stored in Redis

## Running the API

### Development

```bash
# Install dependencies
pip install -e .

# Set environment variables
cp .env.example .env
# Edit .env with your credentials

# Run server
python src/api/main.py

# Or with uvicorn
uvicorn src.api.main:app --reload --host 0.0.0.0 --port 8000
```

### Production

```bash
# Run with production settings
APP_ENV=production uvicorn src.api.main:app --host 0.0.0.0 --port 8000 --workers 4
```

## Configuration

Environment variables in `.env`:

```
# API
APP_ENV=development
APP_HOST=0.0.0.0
APP_PORT=8000
SECRET_KEY=your-secret-key-here

# JWT
JWT_ALGORITHM=HS256
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=60
JWT_REFRESH_TOKEN_EXPIRE_DAYS=7

# Rate Limiting
RATE_LIMIT_REQUESTS_PER_MINUTE=10

# External APIs
SPOTIFY_CLIENT_ID=your-spotify-client-id
SPOTIFY_CLIENT_SECRET=your-spotify-client-secret
LASTFM_API_KEY=your-lastfm-api-key

# Database
AEROSPIKE_HOST=localhost
AEROSPIKE_PORT=3000
AEROSPIKE_NAMESPACE=musicmind

# Redis
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_PASSWORD=
REDIS_DB=0

# Overmind Lab (optional)
OVERMIND_API_KEY=your-overmind-api-key
```

## Testing

```bash
# Run tests
pytest tests/test_api.py -v

# With coverage
pytest tests/test_api.py --cov=src/api --cov-report=html
```

## Architecture

```
src/api/
├── main.py              # FastAPI application
├── auth.py              # Authentication service
├── graph.py             # Graph traversal service
├── rate_limiter.py      # Rate limiting
├── security.py          # Input validation & sanitization
└── README.md            # This file
```

## Dependencies

- FastAPI: Web framework
- Uvicorn: ASGI server
- PyJWT: JWT token handling
- bcrypt: Password hashing
- Pydantic: Data validation
- Redis: Caching and rate limiting
- Aerospike: Graph database

## Performance Targets

- Search endpoint: < 2s for cache miss
- Graph traversal (depth 2): ~500ms
- Graph traversal (depth 3): ~1s
- Authentication: < 100ms
- Rate limit check: < 10ms

## Error Handling

All endpoints return standard HTTP status codes:

- 200: Success
- 201: Created
- 400: Bad Request (validation error)
- 401: Unauthorized (invalid/expired token)
- 403: Forbidden (no auth header)
- 429: Too Many Requests (rate limit exceeded)
- 500: Internal Server Error
- 503: Service Unavailable

Error response format:
```json
{
  "detail": "Error message"
}
```
