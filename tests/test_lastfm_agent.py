"""Unit tests for Last.fm agent."""

import time
from unittest.mock import MagicMock, patch

import pytest

from src.agents.lastfm_agent import LastFMAgent, LastFMRateLimiter, LastFMResult
from src.models.nodes import Artist, Song


@pytest.fixture
def lastfm_agent():
    """Create Last.fm agent for testing."""
    agent = LastFMAgent(
        api_key="test_api_key",
    )
    return agent


@pytest.fixture
def mock_search_response():
    """Mock Last.fm track search response."""
    return {
        "results": {
            "trackmatches": {
                "track": [
                    {
                        "name": "Test Song",
                        "artist": "Test Artist",
                        "url": "https://www.last.fm/music/Test+Artist/_/Test+Song",
                        "listeners": "100000",
                        "mbid": "test-mbid-123",
                    }
                ]
            }
        }
    }


@pytest.fixture
def mock_track_info():
    """Mock Last.fm track info response."""
    return {
        "track": {
            "name": "Test Song",
            "artist": {
                "name": "Test Artist",
                "url": "https://www.last.fm/music/Test+Artist",
            },
            "url": "https://www.last.fm/music/Test+Artist/_/Test+Song",
            "duration": "180000",  # milliseconds
            "playcount": "5000000",
            "listeners": "100000",
            "toptags": {
                "tag": [
                    {"name": "rock"},
                    {"name": "alternative"},
                ]
            },
        }
    }


@pytest.fixture
def mock_similar_tracks():
    """Mock Last.fm similar tracks response."""
    return {
        "similartracks": {
            "track": [
                {
                    "name": "Similar Song 1",
                    "artist": {"name": "Test Artist"},
                    "match": "0.95",
                },
                {
                    "name": "Similar Song 2",
                    "artist": {"name": "Another Artist"},
                    "match": "0.85",
                },
            ]
        }
    }


@pytest.fixture
def mock_top_tags():
    """Mock Last.fm top tags response."""
    return {
        "toptags": {
            "tag": [
                {"name": "rock", "count": 100},
                {"name": "alternative", "count": 80},
                {"name": "indie", "count": 60},
            ]
        }
    }


class TestLastFMRateLimiter:
    """Tests for LastFMRateLimiter class."""

    @pytest.mark.asyncio
    async def test_rate_limiter_allows_requests_within_limit(self):
        """Test that rate limiter allows requests within limit."""
        limiter = LastFMRateLimiter()

        # Should allow 5 requests per second
        for _ in range(5):
            await limiter.acquire()

    @pytest.mark.asyncio
    async def test_rate_limiter_blocks_when_limit_exceeded(self):
        """Test that rate limiter blocks when limit is exceeded."""
        limiter = LastFMRateLimiter()

        # Consume all available time by setting last request to now
        limiter.last_request_time = time.time()

        # Next request should wait
        start_time = time.time()
        await limiter.acquire()
        end_time = time.time()

        # Should have waited at least min_interval (0.2 seconds)
        # Allow small margin for timing precision
        assert end_time - start_time >= limiter.min_interval * 0.8

    @pytest.mark.asyncio
    async def test_rate_limiter_enforces_5_requests_per_second(self):
        """Test that rate limiter enforces 5 req/sec limit."""
        limiter = LastFMRateLimiter()

        assert limiter.max_requests_per_second == 5
        assert limiter.min_interval == 0.2  # 1/5 = 0.2 seconds


class TestLastFMAgent:
    """Tests for LastFMAgent class."""

    @pytest.mark.asyncio
    async def test_make_request_success(self, lastfm_agent):
        """Test successful API request."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"track": {"name": "Test Song"}}

        with patch.object(lastfm_agent.http_client, "get", return_value=mock_response):
            result = await lastfm_agent._make_request("track.search", {"track": "Test Song"})

        assert result == {"track": {"name": "Test Song"}}

    @pytest.mark.asyncio
    async def test_make_request_handles_rate_limit(self, lastfm_agent):
        """Test that rate limit errors are handled with retry."""
        # First response: rate limited
        rate_limit_response = MagicMock()
        rate_limit_response.status_code = 429
        rate_limit_response.headers = {"Retry-After": "1"}

        # Second response: success
        success_response = MagicMock()
        success_response.status_code = 200
        success_response.json.return_value = {"track": {"name": "Test Song"}}

        with patch.object(
            lastfm_agent.http_client, "get", side_effect=[rate_limit_response, success_response]
        ):
            result = await lastfm_agent._make_request("track.search", {"track": "Test Song"})

        assert result == {"track": {"name": "Test Song"}}

    @pytest.mark.asyncio
    async def test_make_request_handles_api_error(self, lastfm_agent):
        """Test that API errors in response are handled."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"error": 6, "message": "Invalid parameters"}

        with patch.object(lastfm_agent.http_client, "get", return_value=mock_response):
            with pytest.raises(Exception, match="Last.fm error 6"):
                await lastfm_agent._make_request("track.search", {"track": ""})

    @pytest.mark.asyncio
    async def test_make_request_retries_on_server_error(self, lastfm_agent):
        """Test that server errors trigger retries."""
        # First response: server error
        error_response = MagicMock()
        error_response.status_code = 500
        error_response.text = "Internal Server Error"

        # Second response: success
        success_response = MagicMock()
        success_response.status_code = 200
        success_response.json.return_value = {"track": {"name": "Test Song"}}

        with patch.object(
            lastfm_agent.http_client, "get", side_effect=[error_response, success_response]
        ):
            result = await lastfm_agent._make_request("track.search", {"track": "Test Song"})

        assert result == {"track": {"name": "Test Song"}}

    @pytest.mark.asyncio
    async def test_make_request_fails_on_client_error(self, lastfm_agent):
        """Test that client errors don't trigger retries."""
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.text = "Not Found"

        with patch.object(lastfm_agent.http_client, "get", return_value=mock_response):
            with pytest.raises(Exception, match="Last.fm API error"):
                await lastfm_agent._make_request("track.search", {"track": "Test Song"})

    @pytest.mark.asyncio
    async def test_search_track_success(self, lastfm_agent, mock_search_response):
        """Test successful track search."""
        with patch.object(lastfm_agent, "_make_request", return_value=mock_search_response):
            result = await lastfm_agent.search_track("Test Song")

        assert result is not None
        assert result["name"] == "Test Song"
        assert result["artist"] == "Test Artist"

    @pytest.mark.asyncio
    async def test_search_track_not_found(self, lastfm_agent):
        """Test track search with no results."""
        mock_response = {"results": {"trackmatches": {"track": []}}}

        with patch.object(lastfm_agent, "_make_request", return_value=mock_response):
            result = await lastfm_agent.search_track("Nonexistent Song")

        assert result is None

    @pytest.mark.asyncio
    async def test_search_track_handles_single_result(self, lastfm_agent):
        """Test track search with single result (not in list)."""
        mock_response = {
            "results": {
                "trackmatches": {
                    "track": {
                        "name": "Test Song",
                        "artist": "Test Artist",
                    }
                }
            }
        }

        with patch.object(lastfm_agent, "_make_request", return_value=mock_response):
            result = await lastfm_agent.search_track("Test Song")

        assert result is not None
        assert result["name"] == "Test Song"

    @pytest.mark.asyncio
    async def test_get_track_info_success(self, lastfm_agent, mock_track_info):
        """Test successful track info fetch."""
        with patch.object(lastfm_agent, "_make_request", return_value=mock_track_info):
            result = await lastfm_agent.get_track_info("Test Artist", "Test Song")

        assert result is not None
        assert result["name"] == "Test Song"
        assert result["playcount"] == "5000000"

    @pytest.mark.asyncio
    async def test_get_similar_tracks_success(self, lastfm_agent, mock_similar_tracks):
        """Test successful similar tracks fetch."""
        with patch.object(lastfm_agent, "_make_request", return_value=mock_similar_tracks):
            result = await lastfm_agent.get_similar_tracks("Test Artist", "Test Song")

        assert result is not None
        assert len(result) == 2
        assert result[0]["name"] == "Similar Song 1"

    @pytest.mark.asyncio
    async def test_get_similar_tracks_handles_single_result(self, lastfm_agent):
        """Test similar tracks with single result (not in list)."""
        mock_response = {
            "similartracks": {
                "track": {
                    "name": "Similar Song",
                    "artist": {"name": "Test Artist"},
                }
            }
        }

        with patch.object(lastfm_agent, "_make_request", return_value=mock_response):
            result = await lastfm_agent.get_similar_tracks("Test Artist", "Test Song")

        assert result is not None
        assert len(result) == 1
        assert result[0]["name"] == "Similar Song"

    @pytest.mark.asyncio
    async def test_get_similar_tracks_empty(self, lastfm_agent):
        """Test similar tracks with no results."""
        mock_response = {"similartracks": {"track": []}}

        with patch.object(lastfm_agent, "_make_request", return_value=mock_response):
            result = await lastfm_agent.get_similar_tracks("Test Artist", "Test Song")

        assert result == []

    @pytest.mark.asyncio
    async def test_get_top_tags_success(self, lastfm_agent, mock_top_tags):
        """Test successful top tags fetch."""
        with patch.object(lastfm_agent, "_make_request", return_value=mock_top_tags):
            result = await lastfm_agent.get_top_tags("Test Artist", "Test Song")

        assert result is not None
        assert len(result) == 3
        assert "rock" in result
        assert "alternative" in result

    @pytest.mark.asyncio
    async def test_get_top_tags_handles_single_result(self, lastfm_agent):
        """Test top tags with single result (not in list)."""
        mock_response = {
            "toptags": {
                "tag": {
                    "name": "rock",
                    "count": 100,
                }
            }
        }

        with patch.object(lastfm_agent, "_make_request", return_value=mock_response):
            result = await lastfm_agent.get_top_tags("Test Artist", "Test Song")

        assert result is not None
        assert len(result) == 1
        assert result[0] == "rock"

    @pytest.mark.asyncio
    async def test_get_top_tags_empty(self, lastfm_agent):
        """Test top tags with no results."""
        mock_response = {"toptags": {"tag": []}}

        with patch.object(lastfm_agent, "_make_request", return_value=mock_response):
            result = await lastfm_agent.get_top_tags("Test Artist", "Test Song")

        assert result == []

    @pytest.mark.asyncio
    async def test_fetch_lastfm_data_complete(
        self,
        lastfm_agent,
        mock_search_response,
        mock_track_info,
        mock_similar_tracks,
        mock_top_tags,
    ):
        """Test complete Last.fm data fetch with all components."""
        # Mock all API calls
        with (
            patch.object(
                lastfm_agent,
                "search_track",
                return_value=mock_search_response["results"]["trackmatches"]["track"][0],
            ),
            patch.object(lastfm_agent, "get_track_info", return_value=mock_track_info["track"]),
            patch.object(
                lastfm_agent,
                "get_similar_tracks",
                return_value=mock_similar_tracks["similartracks"]["track"],
            ),
            patch.object(
                lastfm_agent, "get_top_tags", return_value=["rock", "alternative", "indie"]
            ),
        ):

            result = await lastfm_agent.fetch_lastfm_data("Test Song")

        # Verify result structure
        assert isinstance(result, LastFMResult)
        assert result.song is not None
        assert result.song.title == "Test Song"
        assert result.song.lastfm_url == "https://www.last.fm/music/Test+Artist/_/Test+Song"
        assert result.song.play_count == 5000000
        assert result.song.listener_count == 100000

        # Verify tags
        assert len(result.tags) == 3
        assert "rock" in result.tags

        # Verify artists
        assert len(result.artists) == 1
        assert result.artists[0].name == "Test Artist"

        # Verify similar tracks
        assert len(result.similar_tracks) == 2
        assert result.similar_tracks[0]["name"] == "Similar Song 1"

        # Verify completeness score
        assert result.completeness_score > 0.0
        assert result.completeness_score <= 1.0

    @pytest.mark.asyncio
    async def test_fetch_lastfm_data_track_not_found(self, lastfm_agent):
        """Test Last.fm data fetch when track is not found."""
        with patch.object(lastfm_agent, "search_track", return_value=None):
            result = await lastfm_agent.fetch_lastfm_data("Nonexistent Song")

        assert isinstance(result, LastFMResult)
        assert result.song is None
        assert result.completeness_score == 0.0

    @pytest.mark.asyncio
    async def test_fetch_lastfm_data_partial_failure(
        self,
        lastfm_agent,
        mock_search_response,
        mock_track_info,
    ):
        """Test Last.fm data fetch with partial failures."""
        # Mock track search and info success, but similar tracks and tags fail
        with (
            patch.object(
                lastfm_agent,
                "search_track",
                return_value=mock_search_response["results"]["trackmatches"]["track"][0],
            ),
            patch.object(lastfm_agent, "get_track_info", return_value=mock_track_info["track"]),
            patch.object(lastfm_agent, "get_similar_tracks", return_value=None),
            patch.object(lastfm_agent, "get_top_tags", return_value=None),
        ):

            result = await lastfm_agent.fetch_lastfm_data("Test Song")

        # Should still return song and artist data
        assert result.song is not None
        assert len(result.artists) == 1
        assert result.similar_tracks == []
        assert result.tags == []

        # Completeness should be lower but not zero
        assert 0.0 < result.completeness_score < 1.0

    @pytest.mark.asyncio
    async def test_fetch_lastfm_data_handles_exception(self, lastfm_agent):
        """Test that exceptions during fetch are handled gracefully."""
        with patch.object(lastfm_agent, "search_track", side_effect=Exception("API Error")):
            result = await lastfm_agent.fetch_lastfm_data("Test Song")

        assert isinstance(result, LastFMResult)
        assert result.completeness_score == 0.0

    @pytest.mark.asyncio
    async def test_fetch_lastfm_data_handles_string_artist(self, lastfm_agent):
        """Test handling of artist data as string instead of dict."""
        mock_search = {
            "name": "Test Song",
            "artist": "Test Artist",
        }

        mock_info = {
            "name": "Test Song",
            "artist": "Test Artist",  # String instead of dict
            "url": "https://www.last.fm/music/Test+Artist/_/Test+Song",
            "duration": "180000",
            "playcount": "5000000",
            "listeners": "100000",
        }

        with (
            patch.object(lastfm_agent, "search_track", return_value=mock_search),
            patch.object(lastfm_agent, "get_track_info", return_value=mock_info),
            patch.object(lastfm_agent, "get_similar_tracks", return_value=[]),
            patch.object(lastfm_agent, "get_top_tags", return_value=[]),
        ):

            result = await lastfm_agent.fetch_lastfm_data("Test Song")

        assert result.song is not None
        assert len(result.artists) == 1
        assert result.artists[0].name == "Test Artist"

    @pytest.mark.asyncio
    async def test_close_cleanup(self, lastfm_agent):
        """Test that close method cleans up resources."""
        with patch.object(lastfm_agent.http_client, "aclose") as mock_close:
            await lastfm_agent.close()
            mock_close.assert_called_once()


class TestLastFMResult:
    """Tests for LastFMResult class."""

    def test_lastfm_result_initialization(self):
        """Test LastFMResult initialization."""
        song = Song(title="Test Song", spotify_id="track123")
        artist = Artist(name="Test Artist", spotify_id="artist123")
        similar_tracks = [{"name": "Similar Song"}]
        tags = ["rock", "alternative"]

        result = LastFMResult(
            song=song,
            artists=[artist],
            similar_tracks=similar_tracks,
            tags=tags,
            completeness_score=0.85,
        )

        assert result.song == song
        assert len(result.artists) == 1
        assert result.artists[0] == artist
        assert len(result.similar_tracks) == 1
        assert len(result.tags) == 2
        assert result.completeness_score == 0.85

    def test_lastfm_result_defaults(self):
        """Test LastFMResult with default values."""
        result = LastFMResult()

        assert result.song is None
        assert result.artists == []
        assert result.similar_tracks == []
        assert result.tags == []
        assert result.completeness_score == 0.0
