# MusicMind Agent Platform

An autonomous multi-agent platform that enriches music data by fetching from multiple sources in parallel and merging results into an Aerospike graph database.

## What It Does

Given a song and artist, the platform fans out requests to multiple data sources simultaneously -- Spotify, Last.fm, MusicBrainz, and web scraping -- then merges, deduplicates, and persists the enriched data as a knowledge graph of music entities and relationships.

## Key Features

- **Multi-agent orchestration** -- parallel data fetching with conflict resolution and completeness scoring
- **Graph data model** -- songs, artists, albums, labels, instruments, venues, and concerts stored as nodes and edges in Aerospike
- **Self-improvement engine** -- tracks data quality per source, processes user feedback, and schedules re-enrichment of stale data
- **React frontend** -- graph visualization and social features
- **API** -- FastAPI with JWT auth, rate limiting, CSRF protection, and input validation
- **Caching** -- Redis with configurable TTL and LRU eviction
- **Observability** -- distributed tracing via Overmind

## Tech Stack

| Layer | Technology |
|---|---|
| Language | Python 3.11+ |
| API | FastAPI, Uvicorn |
| Database | Aerospike (graph storage) |
| Cache | Redis |
| Frontend | React |
| Auth | JWT (access + refresh tokens) |
| HTTP Client | HTTPX |
| Testing | pytest, Hypothesis |

## Quick Start

```bash
# Start infrastructure
docker-compose up -d

# Install dependencies
pip install -e ".[dev]"

# Run the API server
uvicorn src.api.main:app --reload
```

## Configuration

Copy `.env.example` to `.env` and set the required variables:

- `SPOTIFY_CLIENT_ID` / `SPOTIFY_CLIENT_SECRET`
- `LASTFM_API_KEY`
- `SECRET_KEY`
