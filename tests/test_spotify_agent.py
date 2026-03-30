"""Unit tests for Spotify agent."""

import asyncio
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from src.agents.spotify_agent import RateLimiter, SpotifyAgent, SpotifyResult
from src.models.nodes import Album, Artist, Song


@pytest.fixture
def spotify_agent():
    """Create Spotify agent for testing."""
    agent = SpotifyAgent(
        client_id="test_client_id",
        client_secret="test_client_secret",
    )
    return agent


@pytest.fixture
def mock_track_data():
    """Mock Spotify track data."""
    return {
        "id": "track123",
        "name": "Test Song",
        "duration_ms": 180000,
        "popularity": 75,
        "artists": [{"id": "artist123", "name": "Test Artist"}],
        "album": {
            "id": "album123",
            "name": "Test Album",
            "album_type": "album",
            "release_date": "2020-01-15",
        },
    }


@pytest.fixture
def mock_artist_data():
    """Mock Spotify artist data."""
    return {
        "id": "artist123",
        "name": "Test Artist",
        "genres": ["rock", "alternative"],
        "popularity": 80,
        "followers": {"total": 1000000},
        "images": [{"url": "https://example.com/artist.jpg"}],
    }


@pytest.fixture
def mock_album_data():
    """Mock Spotify album data."""
    return {
        "id": "album123",
        "name": "Test Album",
        "album_type": "album",
        "release_date": "2020-01-15",
        "total_tracks": 12,
        "label": "Test Records",
        "images": [{"url": "https://example.com/album.jpg"}],
    }


@pytest.fixture
def mock_audio_features():
    """Mock Spotify audio features."""
    return {
        "tempo": 120.0,
        "key": 5,
        "mode": 1,
        "time_signature": 4,
        "energy": 0.8,
        "danceability": 0.7,
        "valence": 0.6,
        "acousticness": 0.2,
    }


class TestRateLimiter:
    """Tests for RateLimiter class."""

    @pytest.mark.asyncio
    async def test_rate_limiter_allows_requests_within_limit(self):
        """Test that rate limiter allows requests within limit."""
        limiter = RateLimiter(requests_per_minute=60, burst_allowance=10)

        # Should allow immediate requests up to burst capacity
        for _ in range(10):
            await limiter.acquire()

    @pytest.mark.asyncio
    async def test_rate_limiter_blocks_when_limit_exceeded(self):
        """Test that rate limiter blocks when limit is exceeded."""
        limiter = RateLimiter(requests_per_minute=60, burst_allowance=5)

        # Consume all tokens
        limiter.tokens = 0.5

        # Next request should wait
        start_time = asyncio.get_event_loop().time()
        await limiter.acquire()
        end_time = asyncio.get_event_loop().time()

        # Should have waited some time
        assert end_time - start_time > 0.01

    @pytest.mark.asyncio
    async def test_rate_limiter_refills_tokens_over_time(self):
        """Test that rate limiter refills tokens over time."""
        limiter = RateLimiter(requests_per_minute=60, burst_allowance=5)

        # Consume all tokens
        limiter.tokens = 0.0
        limiter.last_update = asyncio.get_event_loop().time() - 1.0

        # Acquire should refill tokens based on elapsed time
        await limiter.acquire()

        # Tokens should have been refilled
        assert limiter.tokens >= 0.0


class TestSpotifyAgent:
    """Tests for SpotifyAgent class."""

    @pytest.mark.asyncio
    async def test_authenticate_success(self, spotify_agent):
        """Test successful authentication."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "test_token",
            "expires_in": 3600,
        }

        with patch.object(spotify_agent.http_client, "post", return_value=mock_response):
            await spotify_agent._authenticate()

        assert spotify_agent.access_token == "test_token"
        assert spotify_agent.token_expires_at is not None
        assert spotify_agent.token_expires_at > datetime.utcnow()

    @pytest.mark.asyncio
    async def test_authenticate_failure(self, spotify_agent):
        """Test authentication failure."""
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.text = "Invalid credentials"

        with patch.object(spotify_agent.http_client, "post", return_value=mock_response):
            with pytest.raises(Exception, match="Authentication failed"):
                await spotify_agent._authenticate()

    @pytest.mark.asyncio
    async def test_ensure_authenticated_refreshes_expired_token(self, spotify_agent):
        """Test that expired token is refreshed."""
        # Set expired token
        spotify_agent.access_token = "old_token"
        spotify_agent.token_expires_at = datetime.utcnow() - timedelta(seconds=1)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "new_token",
            "expires_in": 3600,
        }

        with patch.object(spotify_agent.http_client, "post", return_value=mock_response):
            await spotify_agent._ensure_authenticated()

        assert spotify_agent.access_token == "new_token"

    @pytest.mark.asyncio
    async def test_make_request_success(self, spotify_agent):
        """Test successful API request."""
        spotify_agent.access_token = "test_token"
        spotify_agent.token_expires_at = datetime.utcnow() + timedelta(hours=1)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": "test"}

        with patch.object(spotify_agent.http_client, "request", return_value=mock_response):
            result = await spotify_agent._make_request("GET", "test/endpoint")

        assert result == {"data": "test"}

    @pytest.mark.asyncio
    async def test_make_request_handles_rate_limit(self, spotify_agent):
        """Test that rate limit errors are handled with retry."""
        spotify_agent.access_token = "test_token"
        spotify_agent.token_expires_at = datetime.utcnow() + timedelta(hours=1)

        # First response: rate limited
        rate_limit_response = MagicMock()
        rate_limit_response.status_code = 429
        rate_limit_response.headers = {"Retry-After": "1"}

        # Second response: success
        success_response = MagicMock()
        success_response.status_code = 200
        success_response.json.return_value = {"data": "test"}

        with patch.object(
            spotify_agent.http_client,
            "request",
            side_effect=[rate_limit_response, success_response],
        ):
            result = await spotify_agent._make_request("GET", "test/endpoint")

        assert result == {"data": "test"}

    @pytest.mark.asyncio
    async def test_make_request_retries_on_server_error(self, spotify_agent):
        """Test that server errors trigger retries."""
        spotify_agent.access_token = "test_token"
        spotify_agent.token_expires_at = datetime.utcnow() + timedelta(hours=1)

        # First response: server error
        error_response = MagicMock()
        error_response.status_code = 500
        error_response.text = "Internal Server Error"

        # Second response: success
        success_response = MagicMock()
        success_response.status_code = 200
        success_response.json.return_value = {"data": "test"}

        with patch.object(
            spotify_agent.http_client, "request", side_effect=[error_response, success_response]
        ):
            result = await spotify_agent._make_request("GET", "test/endpoint")

        assert result == {"data": "test"}

    @pytest.mark.asyncio
    async def test_make_request_fails_on_client_error(self, spotify_agent):
        """Test that client errors don't trigger retries."""
        spotify_agent.access_token = "test_token"
        spotify_agent.token_expires_at = datetime.utcnow() + timedelta(hours=1)

        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.text = "Not Found"

        with patch.object(spotify_agent.http_client, "request", return_value=mock_response):
            with pytest.raises(Exception, match="Spotify API error"):
                await spotify_agent._make_request("GET", "test/endpoint")

    @pytest.mark.asyncio
    async def test_search_track_success(self, spotify_agent, mock_track_data):
        """Test successful track search."""
        mock_response = {"tracks": {"items": [mock_track_data]}}

        with patch.object(spotify_agent, "_make_request", return_value=mock_response):
            result = await spotify_agent.search_track("Test Song")

        assert result is not None
        assert result["id"] == "track123"
        assert result["name"] == "Test Song"

    @pytest.mark.asyncio
    async def test_search_track_not_found(self, spotify_agent):
        """Test track search with no results."""
        mock_response = {"tracks": {"items": []}}

        with patch.object(spotify_agent, "_make_request", return_value=mock_response):
            result = await spotify_agent.search_track("Nonexistent Song")

        assert result is None

    @pytest.mark.asyncio
    async def test_get_artist_details_success(self, spotify_agent, mock_artist_data):
        """Test successful artist details fetch."""
        with patch.object(spotify_agent, "_make_request", return_value=mock_artist_data):
            result = await spotify_agent.get_artist_details("artist123")

        assert result is not None
        assert result["id"] == "artist123"
        assert result["name"] == "Test Artist"

    @pytest.mark.asyncio
    async def test_get_album_details_success(self, spotify_agent, mock_album_data):
        """Test successful album details fetch."""
        with patch.object(spotify_agent, "_make_request", return_value=mock_album_data):
            result = await spotify_agent.get_album_details("album123")

        assert result is not None
        assert result["id"] == "album123"
        assert result["name"] == "Test Album"

    @pytest.mark.asyncio
    async def test_get_audio_features_deprecated(self, spotify_agent, mock_audio_features):
        """Test audio features returns None (endpoint deprecated Feb 2026)."""
        result = await spotify_agent.get_audio_features("track123")
        assert result is None

    @pytest.mark.asyncio
    async def test_fetch_spotify_data_complete(
        self,
        spotify_agent,
        mock_track_data,
        mock_artist_data,
        mock_album_data,
        mock_audio_features,
    ):
        """Test complete Spotify data fetch with all components."""
        # Mock all API calls (audio features endpoint is deprecated, returns None)
        with (
            patch.object(spotify_agent, "search_track", return_value=mock_track_data),
            patch.object(spotify_agent, "get_artist_details", return_value=mock_artist_data),
            patch.object(spotify_agent, "get_album_details", return_value=mock_album_data),
        ):

            result = await spotify_agent.fetch_spotify_data("Test Song")

        # Verify result structure
        assert isinstance(result, SpotifyResult)
        assert result.song is not None
        assert result.song.title == "Test Song"
        assert result.song.spotify_id == "track123"
        assert result.song.duration_ms == 180000

        # Audio features are no longer available from Spotify (deprecated Feb 2026);
        # they are estimated from Last.fm/MusicBrainz tags in the orchestrator instead
        assert result.song.audio_features is None

        # Verify artists
        assert len(result.artists) == 1
        assert result.artists[0].name == "Test Artist"
        assert result.artists[0].spotify_id == "artist123"
        assert "rock" in result.artists[0].genres

        # Verify album
        assert result.album is not None
        assert result.album.title == "Test Album"
        assert result.album.spotify_id == "album123"
        assert result.album.album_type == "album"

        # Verify completeness score
        assert result.completeness_score > 0.0
        assert result.completeness_score <= 1.0

    @pytest.mark.asyncio
    async def test_fetch_spotify_data_track_not_found(self, spotify_agent):
        """Test Spotify data fetch when track is not found."""
        with patch.object(spotify_agent, "search_track", return_value=None):
            result = await spotify_agent.fetch_spotify_data("Nonexistent Song")

        assert isinstance(result, SpotifyResult)
        assert result.song is None
        assert result.completeness_score == 0.0

    @pytest.mark.asyncio
    async def test_fetch_spotify_data_partial_failure(
        self,
        spotify_agent,
        mock_track_data,
        mock_artist_data,
    ):
        """Test Spotify data fetch with partial failures."""
        # Mock track search success, but album and audio features fail
        with (
            patch.object(spotify_agent, "search_track", return_value=mock_track_data),
            patch.object(spotify_agent, "get_audio_features", return_value=None),
            patch.object(spotify_agent, "get_artist_details", return_value=mock_artist_data),
            patch.object(spotify_agent, "get_album_details", return_value=None),
        ):

            result = await spotify_agent.fetch_spotify_data("Test Song")

        # Should still return song and artist data
        assert result.song is not None
        assert len(result.artists) == 1
        assert result.album is None
        assert result.song.audio_features is None

        # Completeness should be lower but not zero
        assert 0.0 < result.completeness_score < 1.0

    @pytest.mark.asyncio
    async def test_fetch_spotify_data_handles_exception(self, spotify_agent):
        """Test that exceptions during fetch are handled gracefully."""
        with patch.object(spotify_agent, "search_track", side_effect=Exception("API Error")):
            result = await spotify_agent.fetch_spotify_data("Test Song")

        assert isinstance(result, SpotifyResult)
        assert result.completeness_score == 0.0

    @pytest.mark.asyncio
    async def test_close_cleanup(self, spotify_agent):
        """Test that close method cleans up resources."""
        with patch.object(spotify_agent.http_client, "aclose") as mock_close:
            await spotify_agent.close()
            mock_close.assert_called_once()


class TestSpotifyResult:
    """Tests for SpotifyResult class."""

    def test_spotify_result_initialization(self):
        """Test SpotifyResult initialization."""
        song = Song(title="Test Song", spotify_id="track123")
        artist = Artist(name="Test Artist", spotify_id="artist123")
        album = Album(title="Test Album", album_type="album", spotify_id="album123")

        result = SpotifyResult(
            song=song,
            artists=[artist],
            album=album,
            completeness_score=0.85,
        )

        assert result.song == song
        assert len(result.artists) == 1
        assert result.artists[0] == artist
        assert result.album == album
        assert result.completeness_score == 0.85

    def test_spotify_result_defaults(self):
        """Test SpotifyResult with default values."""
        result = SpotifyResult()

        assert result.song is None
        assert result.artists == []
        assert result.album is None
        assert result.completeness_score == 0.0
