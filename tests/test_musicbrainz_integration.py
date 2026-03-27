"""Integration tests for MusicBrainz agent (requires API access)."""

import os

import pytest

from src.agents.musicbrainz_agent import MusicBrainzAgent


@pytest.mark.skipif(
    os.getenv("RUN_INTEGRATION_TESTS") != "true",
    reason="Integration tests disabled (set RUN_INTEGRATION_TESTS=true to enable)",
)
class TestMusicBrainzIntegration:
    """Integration tests for MusicBrainz agent."""

    @pytest.mark.asyncio
    async def test_fetch_real_song_data(self):
        """Test fetching real song data from MusicBrainz API."""
        agent = MusicBrainzAgent(user_agent="MusicMindTestAgent/1.0 (test@example.com)")

        try:
            # Search for a well-known song
            result = await agent.fetch_musicbrainz_data("Bohemian Rhapsody")

            # Verify we got some data
            assert result is not None
            assert result.completeness_score > 0.0

            if result.song:
                assert result.song.title is not None
                print(f"Found song: {result.song.title}")
                print(f"Duration: {result.song.duration_ms}ms")
                print(f"MusicBrainz ID: {result.song.musicbrainz_id}")

            if result.artists:
                print(f"Artists: {[a.name for a in result.artists]}")

            if result.relationships:
                print(f"Relationships: {len(result.relationships)}")

            if result.label_info:
                print(f"Label: {result.label_info.get('name')}")

        finally:
            await agent.close()

    @pytest.mark.asyncio
    async def test_rate_limiting_works(self):
        """Test that rate limiting is enforced."""
        agent = MusicBrainzAgent(user_agent="MusicMindTestAgent/1.0 (test@example.com)")

        try:
            import time

            start_time = time.time()

            # Make 3 requests - should take at least 2 seconds due to rate limiting
            await agent.search_recording("Test Song 1")
            await agent.search_recording("Test Song 2")
            await agent.search_recording("Test Song 3")

            elapsed = time.time() - start_time

            # Should take at least 2 seconds (3 requests with 1 sec between each)
            assert elapsed >= 2.0
            print(f"3 requests took {elapsed:.2f}s (rate limiting working)")

        finally:
            await agent.close()
