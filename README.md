# MusicMind Agent Platform

An autonomous AI agent platform for music data enrichment using multi-source integration and self-improvement capabilities.

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

1. Clone the repository:
```bash
git clone <repository-url>
cd musicmind-agent-platform
```

2. Create and activate virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -e ".[dev]"
```

4. Configure environment variables:
```bash
cp .env.example .env
# Edit .env with your API credentials
# See docs/API_CREDENTIALS.md for detailed instructions on obtaining API keys
```

5. Start infrastructure services:
```bash
docker-compose up -d
```

6. Run the application:
```bash
uvicorn src.main:app --reload
```

## Project Structure

```
musicmind-agent-platform/
├── src/                    # Application source code
├── tests/                  # Test files
├── config/                 # Configuration files
│   ├── settings.py        # Centralized settings
│   └── aerospike.conf     # Aerospike database configuration
├── scripts/                # Utility scripts
├── docs/                   # Documentation
│   └── API_CREDENTIALS.md # Guide for obtaining API credentials
├── docker-compose.yml      # Docker services configuration
├── pyproject.toml          # Project dependencies
└── README.md              # This file
```

## API Credentials

Before running the application, you need to obtain API credentials from:
- **Spotify**: Client ID and Client Secret
- **Last.fm**: API Key
- **MusicBrainz**: User agent with contact email (no registration required)

See [docs/API_CREDENTIALS.md](docs/API_CREDENTIALS.md) for detailed step-by-step instructions.

## Development

Run tests:
```bash
pytest
```

Run with coverage:
```bash
pytest --cov=src tests/
```

Format code:
```bash
black src/ tests/
ruff check src/ tests/
```

Type checking:
```bash
mypy src/
```

## License

MIT
