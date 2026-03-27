"""Unit tests for MusicBrainz agent."""

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.agents.musicbrainz_agent import (
    MusicBrainzAgent,
    MusicBrainzRateLimiter,
    MusicBrainzResult,
)


@pytest.fixture
def mock_overmind_client():
    """Create mock Overmind client."""
    client = MagicMock()
    client.log_event = MagicMock()
    return client


@pytest.fixture
def musicbrainz_agent(mock_overmind_client):
    """Create MusicBrainz agent with mock dependencies."""
    agent = MusicBrainzAgent(
        user_agent="TestAgent/1.0 (test@example.com)",
        overmind_client=mock_overmind_client,
    )
    return agent


class TestMusicBrainzRateLimiter:
    """Test MusicBrainz rate limiter."""

    @pytest.mark.asyncio
    async def test_rate_limiter_enforces_one_second_delay(self):
        """Test that rate limiter enforces 1 second between requests."""
        limiter = MusicBrainzRateLimiter()

        time.time()
        await limiter.acquire()
        first_request_time = time.time()

        await limiter.acquire()
        second_request_time = time.time()

        # Second request should be at least 1 second after first
        time_between_requests = second_request_time - first_request_time
        assert time_between_requests >= 1.0
        assert time_between_requests < 1.1  # Allow small overhead

    @pytest.mark.asyncio
    async def test_rate_limiter_allows_immediate_first_request(self):
        """Test that first request is not delayed."""
        limiter = MusicBrainzRateLimiter()

        start_time = time.time()
        await limiter.acquire()
        elapsed = time.time() - start_time

        # First request should be immediate
        assert elapsed < 0.1


class TestMusicBrainzAgent:
    """Test MusicBrainz agent."""

    @pytest.mark.asyncio
    async def test_search_recording_success(self, musicbrainz_agent):
        """Test successful recording search."""
        mock_response = {
            "recordings": [
                {
                    "id": "abc123",
                    "title": "Bohemian Rhapsody",
                    "length": 354000,
                }
            ]
        }

        with patch.object(
            musicbrainz_agent, "_make_request", new_callable=AsyncMock
        ) as mock_request:
            mock_request.return_value = mock_response

            result = await musicbrainz_agent.search_recording("Bohemian Rhapsody")

            assert result is not None
            assert result["id"] == "abc123"
            assert result["title"] == "Bohemian Rhapsody"
            mock_request.assert_called_once()

    @pytest.mark.asyncio
    async def test_search_recording_not_found(self, musicbrainz_agent):
        """Test recording search with no results."""
        mock_response = {"recordings": []}

        with patch.object(
            musicbrainz_agent, "_make_request", new_callable=AsyncMock
        ) as mock_request:
            mock_request.return_value = mock_response

            result = await musicbrainz_agent.search_recording("NonexistentSong")

            assert result is None

    @pytest.mark.asyncio
    async def test_get_recording_details_success(self, musicbrainz_agent):
        """Test getting recording details."""
        mock_response = {
            "id": "abc123",
            "title": "Bohemian Rhapsody",
            "length": 354000,
            "artist-credit": [{"artist": {"id": "artist123", "name": "Queen"}}],
        }

        with patch.object(
            musicbrainz_agent, "_make_request", new_callable=AsyncMock
        ) as mock_request:
            mock_request.return_value = mock_response

            result = await musicbrainz_agent.get_recording_details("abc123")

            assert result is not None
            assert result["id"] == "abc123"
            assert result["title"] == "Bohemian Rhapsody"

    @pytest.mark.asyncio
    async def test_get_artist_relationships_success(self, musicbrainz_agent):
        """Test getting artist relationships."""
        mock_response = {
            "id": "artist123",
            "name": "Freddie Mercury",
            "relations": [
                {
                    "type": "member of band",
                    "artist": {"id": "band123", "name": "Queen"},
                }
            ],
        }

        with patch.object(
            musicbrainz_agent, "_make_request", new_callable=AsyncMock
        ) as mock_request:
            mock_request.return_value = mock_response

            result = await musicbrainz_agent.get_artist_relationships("artist123")

            assert result is not None
            assert result["id"] == "artist123"
            assert len(result["relations"]) == 1

    @pytest.mark.asyncio
    async def test_get_label_info_success(self, musicbrainz_agent):
        """Test getting label information."""
        mock_response = {
            "id": "label123",
            "name": "EMI Records",
            "country": "GB",
            "type": "Original Production",
        }

        with patch.object(
            musicbrainz_agent, "_make_request", new_callable=AsyncMock
        ) as mock_request:
            mock_request.return_value = mock_response

            result = await musicbrainz_agent.get_label_info("label123")

            assert result is not None
            assert result["name"] == "EMI Records"
            assert result["country"] == "GB"

    @pytest.mark.asyncio
    async def test_fetch_musicbrainz_data_complete(self, musicbrainz_agent):
        """Test complete data fetch with all components."""
        # Use valid UUIDs for MusicBrainz IDs
        rec_uuid = "5b11f4ce-a62d-471e-81fc-a69a8278c7da"
        artist_uuid = "0383dadf-2a4e-4d10-a46a-e9e041da8eb3"
        label_uuid = "1c9f1b9e-7a1f-4f0f-8b1f-1f1f1f1f1f1f"

        # Mock search_recording
        search_result = {"id": rec_uuid, "title": "Test Song"}

        # Mock get_recording_details
        recording_details = {
            "id": rec_uuid,
            "title": "Test Song",
            "length": 240000,
            "artist-credit": [{"artist": {"id": artist_uuid, "name": "Test Artist"}}],
            "releases": [{"label-info": [{"label": {"id": label_uuid, "name": "Test Label"}}]}],
        }

        # Mock get_artist_relationships
        artist_details = {
            "id": artist_uuid,
            "name": "Test Artist",
            "country": "US",
            "relations": [
                {
                    "type": "collaboration",
                    "artist": {
                        "id": "2c9f1b9e-7a1f-4f0f-8b1f-1f1f1f1f1f1f",
                        "name": "Collaborator",
                    },
                }
            ],
        }

        # Mock get_label_info
        label_details = {
            "id": label_uuid,
            "name": "Test Label",
            "country": "US",
            "type": "Original Production",
        }

        with (
            patch.object(
                musicbrainz_agent, "search_recording", new_callable=AsyncMock
            ) as mock_search,
            patch.object(
                musicbrainz_agent, "get_recording_details", new_callable=AsyncMock
            ) as mock_recording,
            patch.object(
                musicbrainz_agent, "get_artist_relationships", new_callable=AsyncMock
            ) as mock_artist,
            patch.object(musicbrainz_agent, "get_label_info", new_callable=AsyncMock) as mock_label,
        ):

            mock_search.return_value = search_result
            mock_recording.return_value = recording_details
            mock_artist.return_value = artist_details
            mock_label.return_value = label_details

            result = await musicbrainz_agent.fetch_musicbrainz_data("Test Song")

            assert isinstance(result, MusicBrainzResult)
            assert result.song is not None
            assert result.song.title == "Test Song"
            assert result.song.duration_ms == 240000
            assert len(result.artists) == 1
            assert result.artists[0].name == "Test Artist"
            assert len(result.relationships) == 1
            assert result.label_info is not None
            assert result.label_info["name"] == "Test Label"
            assert result.completeness_score > 0.0

    @pytest.mark.asyncio
    async def test_fetch_musicbrainz_data_not_found(self, musicbrainz_agent):
        """Test data fetch when recording not found."""
        with patch.object(
            musicbrainz_agent, "search_recording", new_callable=AsyncMock
        ) as mock_search:
            mock_search.return_value = None

            result = await musicbrainz_agent.fetch_musicbrainz_data("NonexistentSong")

            assert isinstance(result, MusicBrainzResult)
            assert result.song is None
            assert result.completeness_score == 0.0

    @pytest.mark.asyncio
    async def test_make_request_includes_user_agent(self, musicbrainz_agent):
        """Test that requests include user agent header."""
        assert "User-Agent" in musicbrainz_agent.http_client.headers
        assert (
            musicbrainz_agent.http_client.headers["User-Agent"]
            == "TestAgent/1.0 (test@example.com)"
        )

    @pytest.mark.asyncio
    async def test_make_request_adds_json_format(self, musicbrainz_agent):
        """Test that requests add fmt=json parameter."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"test": "data"}

        with patch.object(musicbrainz_agent.http_client, "get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_response

            await musicbrainz_agent._make_request("recording", params={"query": "test"})

            # Check that fmt=json was added to params
            call_args = mock_get.call_args
            assert call_args[1]["params"]["fmt"] == "json"

    @pytest.mark.asyncio
    async def test_make_request_handles_rate_limit_error(self, musicbrainz_agent):
        """Test handling of 503 rate limit errors."""
        mock_response_503 = MagicMock()
        mock_response_503.status_code = 503
        mock_response_503.headers = {"Retry-After": "2"}

        mock_response_200 = MagicMock()
        mock_response_200.status_code = 200
        mock_response_200.json.return_value = {"test": "data"}

        with patch.object(musicbrainz_agent.http_client, "get", new_callable=AsyncMock) as mock_get:
            mock_get.side_effect = [mock_response_503, mock_response_200]

            result = await musicbrainz_agent._make_request("recording")

            assert result == {"test": "data"}
            assert mock_get.call_count == 2

    @pytest.mark.asyncio
    async def test_make_request_retries_on_server_error(self, musicbrainz_agent):
        """Test retry logic for server errors."""
        mock_response_500 = MagicMock()
        mock_response_500.status_code = 500
        mock_response_500.text = "Internal Server Error"

        mock_response_200 = MagicMock()
        mock_response_200.status_code = 200
        mock_response_200.json.return_value = {"test": "data"}

        with patch.object(musicbrainz_agent.http_client, "get", new_callable=AsyncMock) as mock_get:
            mock_get.side_effect = [mock_response_500, mock_response_200]

            result = await musicbrainz_agent._make_request("recording")

            assert result == {"test": "data"}
            assert mock_get.call_count == 2

    @pytest.mark.asyncio
    async def test_make_request_fails_on_client_error(self, musicbrainz_agent):
        """Test that client errors are not retried."""
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.text = "Not Found"

        with patch.object(musicbrainz_agent.http_client, "get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_response

            with pytest.raises(Exception, match="MusicBrainz API error"):
                await musicbrainz_agent._make_request("recording")

            # Should only try once for client errors
            assert mock_get.call_count == 1

    @pytest.mark.asyncio
    async def test_close_closes_http_client(self, musicbrainz_agent):
        """Test that close method closes HTTP client."""
        with patch.object(
            musicbrainz_agent.http_client, "aclose", new_callable=AsyncMock
        ) as mock_close:
            await musicbrainz_agent.close()
            mock_close.assert_called_once()

    @pytest.mark.asyncio
    async def test_overmind_logging(self, musicbrainz_agent, mock_overmind_client):
        """Test that API calls are logged to Overmind."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"test": "data"}

        with patch.object(musicbrainz_agent.http_client, "get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_response

            await musicbrainz_agent._make_request("recording")

            # Verify Overmind logging was called
            mock_overmind_client.log_event.assert_called()
            call_args = mock_overmind_client.log_event.call_args[0]
            assert call_args[0] == "musicbrainz_api_call"
