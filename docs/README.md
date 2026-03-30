# MusicMind Agent Platform

An autonomous multi-agent platform that enriches music data by fetching from multiple sources in parallel and merging results into an Aerospike graph database.

## Features

- **Multi-Agent Orchestration**: Parallel data fetching from Spotify, MusicBrainz, Last.fm, and web sources
- **Graph Database**: Rich entity relationships stored in Aerospike Graph
- **Self-Improvement**: Autonomous learning from data quality metrics and user feedback
- **Interactive Visualization**: Explore music connections through graph visualization
- **Social Features**: Share discoveries and provide feedback

## Quick Start

### Prerequisites

- Python 3.11+
- Docker and Docker Compose
- External API credentials (Spotify, Last.fm)

### Installation

```bash
# Clone the repository
git clone <repository-url>
cd musicmind-agent-platform

# Create and activate virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -e ".[dev]"

# Configure environment variables
cp .env.example .env
# Edit .env with your API credentials
# See docs/API_CREDENTIALS.md for detailed instructions on obtaining API keys

# Start infrastructure services
docker-compose up -d

# Run the application
uvicorn src.api.main:app --reload
```

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

## Configuration

Copy `.env.example` to `.env` and set required variables:

- `SPOTIFY_CLIENT_ID` / `SPOTIFY_CLIENT_SECRET`
- `LASTFM_API_KEY`
- `SECRET_KEY`

See [docs/API_CREDENTIALS.md](docs/API_CREDENTIALS.md) for detailed instructions.

## Project Structure

```
├── src/
│   ├── agents/              # Multi-agent data enrichment
│   ├── api/                 # FastAPI endpoints
│   ├── cache/               # Redis client
│   ├── database/            # Aerospike client
│   ├── models/              # Pydantic nodes/edges
│   ├── self_improvement/    # Quality tracking & feedback
│   ├── tracing/             # Overmind client
│   └── utils/               # Helpers
├── frontend/                # React + TypeScript + Vite + Tailwind CSS
├── config/                  # Settings and Aerospike config
├── tests/                   # pytest test suite
├── scripts/                 # Manual verification scripts
└── docs/                    # Documentation
```

## Development

```bash
# Backend tests
pytest

# With coverage
pytest --cov=src tests/

# Linting & formatting
black src/ tests/
ruff check src/ tests/

# Type checking
mypy src/

# Frontend
cd frontend
npm install
npm run dev
```

## Documentation

- [Architecture & Agents](docs/ARCHITECTURE.md) - System design, agents, data models, and code patterns
- [API Reference](docs/API.md) - REST endpoints, authentication, and security features
- [Spotify Agent](docs/SPOTIFY_AGENT.md) - Spotify data source details
- [API Credentials](docs/API_CREDENTIALS.md) - How to obtain API keys
