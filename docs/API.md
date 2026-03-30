# MusicMind API Documentation

FastAPI backend for MusicMind web frontend with REST endpoints for song enrichment, graph traversal, user feedback, and authentication.

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

### Natural Language Query

```
POST /api/query
Headers: Authorization: Bearer <token>
Body: { "question": "What artists performed at venues in New York?" }
Response: { "answer": "...", "nodes": [...], "edges": [...] }
```

Requires `LLM_API_KEY` to be configured.

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

### CSRF Protection

- CSRF token generation and validation
- Token expiration: 1 hour

### Rate Limiting

- Sliding window algorithm
- 10 requests per minute per user
- Redis-backed for distributed systems

### Authentication

- JWT tokens with HS256 algorithm
- Bcrypt password hashing
- Access token: 1 hour expiration
- Refresh token: 7 days expiration

## Performance Targets

- Search endpoint: < 2s for cache miss
- Graph traversal (depth 2): ~500ms
- Graph traversal (depth 3): ~1s
- Rate limit check: < 10ms

## Error Handling

- 200: Success
- 201: Created
- 400: Bad Request (validation error)
- 401: Unauthorized
- 403: Forbidden
- 429: Too Many Requests
- 500: Internal Server Error
- 503: Service Unavailable

## Running

```bash
# Development
uvicorn src.api.main:app --reload --host 0.0.0.0 --port 8000

# Production
APP_ENV=production uvicorn src.api.main:app --host 0.0.0.0 --port 8000 --workers 4
```
