# AGENTS.md

## Commands

```bash
# Install (editable with dev deps)
pip install -e ".[dev]"

# Run app
uvicorn src.api.main:app --reload

# Infrastructure (Aerospike + Redis)
docker-compose up -d

# Tests
pytest                          # all tests
pytest tests/test_spotify_agent.py  # single file
pytest tests/test_spotify_agent.py::TestSpotifyAgent::test_search  # single test
pytest --cov=src tests/         # with coverage

# Linting & formatting
black src/ tests/
ruff check src/ tests/
ruff check --fix src/ tests/

# Type checking
mypy src/
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

- `main.py`: FastAPI app with lifespan-managed clients, enrichment/search/graph/feedback endpoints
- `auth.py`: JWT-based authentication (access + refresh tokens)
- `graph.py`: Graph traversal service for exploring entity relationships
- `rate_limiter.py`: Per-user rate limiting
- `security.py`: Input validation and CSRF protection

### Configuration

All config via environment variables loaded through `pydantic-settings` in `config/settings.py`. Copy `.env.example` to `.env`. Required vars: `SPOTIFY_CLIENT_ID`, `SPOTIFY_CLIENT_SECRET`, `LASTFM_API_KEY`, `SECRET_KEY`.

### Testing Conventions

- pytest with `asyncio_mode = "auto"` -- async test functions run automatically without markers
- Tests live in `tests/` mirroring the source structure
- `scripts/` contains manual verification/integration scripts (not run by pytest)
