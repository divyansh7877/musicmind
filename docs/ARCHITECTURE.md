# AGENTS.md

## Commands

### Backend (Python/FastAPI)

```bash
# Install (editable with dev deps)
pip install -e ".[dev]"

# Run app (development with auto-reload)
uvicorn src.api.main:app --reload

# Run app (production)
uvicorn src.api.main:app --host 0.0.0.0 --port 8000 --workers 2

# Infrastructure (Aerospike + Redis)
docker-compose up -d

# Infrastructure (production)
docker-compose -f docker-compose.prod.yml up -d

# Tests
pytest                          # all tests
pytest tests/test_spotify_agent.py              # single file
pytest tests/test_spotify_agent.py::TestSpotifyAgent::test_search  # single test
pytest --cov=src tests/         # with coverage

# Linting & formatting
black src/ tests/
ruff check src/ tests/
ruff check --fix src/ tests/

# Type checking
mypy src/
```

### Frontend (React/TypeScript/Vite)

```bash
cd frontend

# Install dependencies
npm install

# Development server
npm run dev

# Production build
npm run build

# Lint
npm run lint

# Preview production build
npm run preview
```

## Architecture

Multi-agent platform that enriches music data by fetching from multiple sources in parallel and merging results into an Aerospike graph database.

### Core Flow

1. **API layer** (`src/api/main.py`) receives an enrichment request (song + artist)
2. **OrchestratorAgent** (`src/agents/orchestrator.py`) fans out to sub-agents in parallel using `asyncio.gather`
3. Sub-agents fetch data independently, each returning a typed result with a completeness score
4. Orchestrator merges results, resolves conflicts, computes overall completeness, and persists to Aerospike as graph nodes/edges

### Sub-Agents (`src/agents/`)

| Agent | Source | Result Type |
|---|---|---|
| `SpotifyAgent` | Spotify Web API (OAuth client credentials) | `SpotifyResult` |
| `LastFMAgent` | Last.fm API | `LastFMResult` |
| `MusicBrainzAgent` | MusicBrainz API (rate-limited, no auth) | `MusicBrainzResult` |
| `WebScraperAgent` | General web scraping | `ScraperResult` |
| `LLMQueryAgent` | LLM (OpenAI-compatible API) | Natural language graph queries |

All agents follow the same pattern: search -> fetch details -> build result with completeness score.

### Data Model (`src/models/`)

Graph nodes (`nodes.py`): Song, Artist, Album, RecordLabel, Instrument, Venue, Concert, AudioFeatures.
Graph edges (`edges.py`): PerformedIn, PlayedInstrument, SignedWith, PartOfAlbum, PerformedAt, SimilarTo.

### Self-Improvement Engine (`src/self_improvement/`)

- **QualityTracker**: tracks per-source data quality metrics (accuracy, completeness, freshness)
- **FeedbackProcessor**: ingests user feedback and issue reports, adjusts source trust scores
- **EnrichmentScheduler**: prioritizes re-enrichment of stale/low-quality nodes

### Infrastructure

- **Aerospike** (`src/database/aerospike_client.py`): graph storage for music entities and relationships
- **Redis** (`src/cache/redis_client.py`): caching layer with configurable TTL, LRU eviction
- **Overmind** (`src/tracing/overmind_client.py`): distributed tracing and observability

### API Layer (`src/api/`)

- `main.py`: FastAPI app with lifespan-managed clients, enrichment/search/graph/feedback/query endpoints
- `auth.py`: JWT-based authentication (access + refresh tokens)
- `graph.py`: Graph traversal service for exploring entity relationships
- `rate_limiter.py`: Per-user rate limiting
- `security.py`: Input validation and CSRF protection

### Configuration

All config via environment variables loaded through `pydantic-settings` in `config/settings.py`. Copy `.env.example` to `.env`.

**Required environment variables** (no defaults, will fail if missing):
- `SPOTIFY_CLIENT_ID`
- `SPOTIFY_CLIENT_SECRET`
- `LASTFM_API_KEY`
- `SECRET_KEY`

**Optional but important**:
- `DEMO_MODE=true` - bypasses authentication for demos
- `LLM_API_KEY` - enables natural language query endpoint (`/api/query`)
- `MUSICBRAINZ_USER_AGENT` - defaults to `MusicMindAgent/0.1.0 (contact@example.com)`, should be customized

### Testing Conventions

- pytest with `asyncio_mode = "auto"` -- async test functions run automatically without markers
- Tests live in `tests/` mirroring the source structure
- `scripts/` contains manual verification/integration scripts (not run by pytest)
- Use `@pytest.fixture` for test setup, `@pytest.mark.asyncio` for async tests when needed
- Mock external HTTP calls with `unittest.mock.patch`

## Project Structure

```
/Users/divagarwal/Projects/spotifier/
├── src/
│   ├── agents/              # Multi-agent data enrichment
│   │   ├── orchestrator.py   # Central coordinator
│   │   ├── spotify_agent.py # Spotify Web API
│   │   ├── lastfm_agent.py  # Last.fm API
│   │   ├── musicbrainz_agent.py
│   │   ├── scraper_agent.py
│   │   └── llm_query_agent.py
│   ├── api/                 # FastAPI endpoints
│   ├── cache/               # Redis client
│   ├── database/            # Aerospike client
│   ├── models/              # Pydantic nodes/edges
│   ├── self_improvement/    # Quality tracking & feedback
│   ├── tracing/             # Overmind client
│   ├── utils/               # Helpers (audio features estimator, metrics)
│   ├── validation/          # Data validation
│   └── errors/             # Exception classes and handlers
├── frontend/                # React + TypeScript + Vite + Tailwind CSS
├── config/                  # Settings and Aerospike config
├── tests/                   # pytest test suite
├── scripts/                 # Manual verification scripts
└── docs/                    # API credentials guide
```

## Code Patterns

### Async/Await
- Backend is fully async using `httpx` for HTTP requests
- Use `asyncio.gather()` for parallel operations
- Agents implement `close()` method for cleanup (use `finally` block in orchestrator)

### Pydantic Models
- Use `pydantic.BaseModel` for all data transfer objects
- Use `Field()` for validation with `min_length`, `max_length`, `ge`, `le`
- Custom validators use `@field_validator` decorator
- Agent result types (e.g., `SpotifyResult`) use `.model_dump()` for serialization

### Error Handling
- Domain errors use `MusicMindError` hierarchy in `src/errors/exceptions.py`
- HTTP errors mapped via `status_map` in `src/api/main.py`
- All errors logged to Overmind via `log_error_to_overmind()`

### Graph IDs
- Use deterministic UUIDs: `hashlib.sha256(f"{namespace}:{name.lower().strip()}".encode()).hexdigest()[:32]`
- This ensures the same entity always gets the same ID across enrichments

## Gotchas and Non-Obvious Patterns

1. **Spotify audio features deprecated (Feb 2026)**: `SpotifyAgent.get_audio_features()` returns `None`. Audio features are now estimated from Last.fm/MusicBrainz tags via `src/utils/audio_features_estimator.py` in the orchestrator.

2. **Settings validation**: `config/settings.py` uses pydantic-settings with required fields (no defaults). App will fail to start if `SPOTIFY_CLIENT_ID`, `SPOTIFY_CLIENT_SECRET`, `LASTFM_API_KEY`, or `SECRET_KEY` are missing.

3. **Aerospike optional**: If Aerospike is unavailable, the app still works with in-memory graph accumulation. Graph persistence silently fails with a warning.

4. **Demo mode**: Set `DEMO_MODE=true` to bypass authentication. Returns a demo user (`id=00000000-0000-0000-0000-000000000000`) for all requests.

5. **Rate limiting**: Applied per-user after authentication. Demo mode skips rate limiting.

6. **MusicBrainz rate limiting**: Uses 1 request/second with exponential backoff. User agent must be properly configured.

7. **Redis LRU**: Configured with `allkeys-lru` eviction policy. Cache TTL defaults to 3600 seconds.

8. **Overmind optional**: If `OVERMIND_API_KEY` is not set, tracing is silently skipped.

9. **CORS**: Defaults to `*` (allow all) in development. Configure via `CORS_ORIGINS` env var.

10. **Frontend proxy**: Vite proxies `/api` requests to backend during development via `vite.config.ts`.

11. **LLM Query**: Requires `LLM_API_KEY` set. Falls back to HTTP 503 if not configured.

12. **GraphAccumulator**: In-memory graph accumulation in `src/api/main.py` allows cumulative graph visualization without Aerospike.

## Frontend Stack

- **Framework**: React 19 + TypeScript
- **Build tool**: Vite
- **Styling**: Tailwind CSS v4
- **Routing**: React Router v7
- **State**: TanStack Query (React Query)
- **HTTP**: Axios
- **Visualization**: D3.js (graph visualization)

Key pages: Search (`/search`), Graph (`/graph`), Activity (`/activity`), Query (`/query`), Login (`/login`), Register (`/register`).

## Deployment

- **Backend**: Docker container with uvicorn workers. Healthcheck hits `/health`.
- **Frontend**: Multi-stage Docker build. Nginx serves static assets.
- **Infra**: Docker Compose with Aerospike + Redis for development; TrueFoundry YAML for production deploy.
