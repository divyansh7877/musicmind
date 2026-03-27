"""Integration tests for Spotify agent with orchestrator."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.agents.orchestrator import OrchestratorAgent
from src.agents.spotify_agent import SpotifyAgent
from src.cache.redis_client import RedisClient


@pytest.fixture
def mock_spotify_search_response():
    """Mock Spotify search response."""
    return {
        "tracks": {
            "items": [
                {
                    "id": "3n3Ppam7vgaVa1iaRUc9Lp",
                    "name": "Mr. Brightside",
                    "duration_ms": 222973,
                    "popularity": 89,
                    "artists": [
                        {"id": "0C0XlULifJtAgn6ZNCW2eu", "name": "The Killers"}
                    ],
                    "album": {
                        "id": "4piJq7R3gjUOxnYs6lDCTg",
                        "name": "Hot Fuss",
                        "album_type": "album",
                        "release_date": "2004-06-07",
                    }
                }
            ]
        }
    }


@pytest.fixture
def mock_spotify_artist_response():
    """Mock Spotify artist response."""
    return {
        "id": "0C0XlULifJtAgn6ZNCW2eu",
        "name": "The Killers",
        "genres": ["alternative rock", "indie rock", "modern rock", "rock"],
        "popularity": 82,
        "followers": {"total": 8500000},
        "images": [
            {"url": "https://i.scdn.co/image/ab6761610000e5eb12345"}
        ],
    }


@pytest.fixture
def mock_spotify_album_response():
    """Mock Spotify album response."""
    return {
        "id": "4piJq7R3gjUOxnYs6lDCTg",
        "name": "Hot Fuss",
        "album_type": "album",
        "release_date": "2004-06-07",
        "total_tracks": 11,
        "label": "Island Records",
        "images": [
            {"url": "https://i.scdn.co/image/ab67616d0000b27312345"}
        ],
    }


@pytest.fixture
def mock_spotify_audio_features_response():
    """Mock Spotify audio features response."""
    return {
        "tempo": 148.0,
        "key": 1,
        "mode": 1,
        "time_signature": 4,
        "energy": 0.918,
        "danceability": 0.349,
        "valence": 0.232,
        "acousticness": 0.00146,
    }


@pytest.mark.asyncio
async def test_spotify_agent_integration_with_orchestrator(
    mock_spotify_search_response,
    mock_spotify_artist_response,
    mock_spotify_album_response,
    mock_spotify_audio_features_response,
):
    """Test Spotify agent integration with orchestrator."""
    # Create mock cache client
    mock_cache = MagicMock(spec=RedisClient)
    mock_cache.get.return_value = None  # Cache miss

    # Create orchestrator
    orchestrator = OrchestratorAgent(cache_client=mock_cache, overmind_client=None)

    # Mock Spotify API responses
    with patch("src.agents.spotify_agent.SpotifyAgent._make_request") as mock_request:
        # Setup mock responses for different endpoints
        async def mock_make_request(method, endpoint, params=None, max_retries=3):
            if endpoint == "search":
                return mock_spotify_search_response
            elif endpoint.startswith("artists/"):
                return mock_spotify_artist_response
            elif endpoint.startswith("albums/"):
                return mock_spotify_album_response
            elif endpoint.startswith("audio-features/"):
                return mock_spotify_audio_features_response
            return {}

        mock_request.side_effect = mock_make_request

        # Mock authentication
        with patch("src.agents.spotify_agent.SpotifyAgent._ensure_authenticated"):
            # Enrich a song
            result = await orchestrator.enrich_song("Mr. Brightside")

    # Verify result
    assert result.status == "success"
    assert result.completeness_score > 0.0
    assert len(result.graph_node_ids) > 0

    # Verify merged data contains Spotify data
    assert "song" in result.merged_data
    assert result.merged_data["song"]["title"] == "Mr. Brightside"
    assert result.merged_data["song"]["spotify_id"] == "3n3Ppam7vgaVa1iaRUc9Lp"
    assert result.merged_data["song"]["duration_ms"] == 222973

    # Verify artist data
    assert "artists" in result.merged_data
    assert len(result.merged_data["artists"]) > 0
    assert result.merged_data["artists"][0]["name"] == "The Killers"
    assert "alternative rock" in result.merged_data["artists"][0]["genres"]

    # Verify album data
    assert "album" in result.merged_data
    assert result.merged_data["album"]["title"] == "Hot Fuss"
    assert result.merged_data["album"]["album_type"] == "album"

    # Verify audio features
    assert "audio_features" in result.merged_data["song"]
    assert result.merged_data["song"]["audio_features"]["tempo"] == 148.0
    assert result.merged_data["song"]["audio_features"]["energy"] == 0.918


@pytest.mark.asyncio
async def test_spotify_agent_handles_not_found():
    """Test Spotify agent handles song not found gracefully."""
    # Create mock cache client
    mock_cache = MagicMock(spec=RedisClient)
    mock_cache.get.return_value = None

    # Create orchestrator
    orchestrator = OrchestratorAgent(cache_client=mock_cache, overmind_client=None)

    # Mock Spotify API to return no results
    with patch("src.agents.spotify_agent.SpotifyAgent._make_request") as mock_request:
        async def mock_make_request(method, endpoint, params=None, max_retries=3):
            if endpoint == "search":
                return {"tracks": {"items": []}}
            return {}

        mock_request.side_effect = mock_make_request

        with patch("src.agents.spotify_agent.SpotifyAgent._ensure_authenticated"):
            result = await orchestrator.enrich_song("Nonexistent Song XYZ123")

    # Should still return a result, but with partial status
    assert result.status in ["success", "partial"]
    # Spotify agent should have failed, but other mock agents succeeded
    assert result.completeness_score >= 0.0


@pytest.mark.asyncio
async def test_spotify_agent_rate_limiting():
    """Test that Spotify agent respects rate limits."""
    agent = SpotifyAgent(client_id="test_id", client_secret="test_secret")

    # Mock authentication
    agent.access_token = "test_token"
    from datetime import datetime, timedelta
    agent.token_expires_at = datetime.utcnow() + timedelta(hours=1)

    # Mock HTTP client
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"data": "test"}

    with patch.object(agent.http_client, "request", return_value=mock_response):
        # Make multiple requests rapidly
        start_time = asyncio.get_event_loop().time()

        tasks = [agent._make_request("GET", "test") for _ in range(5)]
        await asyncio.gather(*tasks)

        end_time = asyncio.get_event_loop().time()

        # Should complete quickly since we're within burst allowance
        assert end_time - start_time < 1.0

    await agent.close()


@pytest.mark.asyncio
async def test_spotify_agent_token_refresh():
    """Test that Spotify agent refreshes expired tokens."""
    agent = SpotifyAgent(client_id="test_id", client_secret="test_secret")

    # Set expired token
    from datetime import datetime, timedelta
    agent.access_token = "old_token"
    agent.token_expires_at = datetime.utcnow() - timedelta(seconds=1)

    # Mock authentication response
    auth_response = MagicMock()
    auth_response.status_code = 200
    auth_response.json.return_value = {
        "access_token": "new_token",
        "expires_in": 3600,
    }

    # Mock API response
    api_response = MagicMock()
    api_response.status_code = 200
    api_response.json.return_value = {"data": "test"}

    with patch.object(agent.http_client, "post", return_value=auth_response), \
         patch.object(agent.http_client, "request", return_value=api_response):

        result = await agent._make_request("GET", "test")

        # Token should have been refreshed
        assert agent.access_token == "new_token"
        assert result == {"data": "test"}

    await agent.close()


@pytest.mark.asyncio
async def test_spotify_agent_parallel_execution():
    """Test that orchestrator executes Spotify agent in parallel with others."""
    mock_cache = MagicMock(spec=RedisClient)
    mock_cache.get.return_value = None

    orchestrator = OrchestratorAgent(cache_client=mock_cache, overmind_client=None)

    # Track which agents were called
    called_agents = []

    async def track_agent_call(agent_name, song_name, trace_id):
        called_agents.append(agent_name)
        # Simulate some work
        await asyncio.sleep(0.1)
        from src.agents.orchestrator import AgentResult
        return AgentResult(
            agent_name=agent_name,
            status="success",
            data={"song": {"title": song_name}},
            completeness_score=0.5,
        )

    with patch.object(orchestrator, "_execute_agent", side_effect=track_agent_call):
        # Mock the trace context
        from src.tracing.overmind_client import TraceContext
        from uuid import uuid4
        trace = TraceContext(uuid4(), "test")

        await orchestrator.dispatch_agents("Test Song", trace)

    # All agents should have been called
    assert "spotify" in called_agents
    assert "musicbrainz" in called_agents
    assert "lastfm" in called_agents
    assert "scraper" in called_agents
    assert len(called_agents) == 4
