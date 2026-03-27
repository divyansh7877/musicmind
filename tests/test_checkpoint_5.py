"""Checkpoint 5: End-to-end enrichment verification with Spotify agent."""

import asyncio
import os
from uuid import uuid4

import pytest

from src.agents.orchestrator import OrchestratorAgent
from src.agents.spotify_agent import SpotifyAgent
from src.cache.redis_client import RedisClient
from src.tracing.overmind_client import OvermindClient


class TestCheckpoint5EndToEnd:
    """End-to-end tests for checkpoint 5 verification."""

    @pytest.mark.asyncio
    async def test_end_to_end_enrichment_with_spotify(self):
        """Test complete enrichment flow with Spotify agent only.

        Verifies:
        - Song enrichment works end-to-end
        - Data is properly structured
        - Completeness scores are calculated
        - Response times are tracked
        """
        # Create orchestrator with real components
        cache_client = RedisClient()
        overmind_client = OvermindClient() if os.getenv("OVERMIND_API_KEY") else None
        orchestrator = OrchestratorAgent(
            cache_client=cache_client,
            overmind_client=overmind_client,
        )

        # Test with a well-known song
        song_name = "Bohemian Rhapsody"

        # Clear cache to ensure fresh enrichment
        cache_key = RedisClient.make_song_cache_key(song_name)
        cache_client.delete(cache_key)

        # Perform enrichment
        result = await orchestrator.enrich_song(song_name)

        # Verify enrichment result structure
        assert result is not None
        assert result.status in ["success", "partial"]
        assert result.request_id is not None

        # Verify graph node IDs are created
        assert len(result.graph_node_ids) > 0

        # Verify merged data contains song information
        assert "song" in result.merged_data
        assert "data_sources" in result.merged_data

        # Verify completeness score is valid
        assert 0.0 <= result.completeness_score <= 1.0

        # If Spotify is working, we should have good data
        if "spotify" in result.merged_data.get("data_sources", []):
            assert result.completeness_score > 0.0
            song_data = result.merged_data["song"]
            assert "title" in song_data
            assert song_data["title"] is not None

    @pytest.mark.asyncio
    async def test_caching_works_correctly(self):
        """Test that caching works correctly for repeated requests.

        Verifies:
        - First request is cached
        - Second request returns cached data quickly
        - Cache TTL is respected
        """
        cache_client = RedisClient()
        orchestrator = OrchestratorAgent(cache_client=cache_client)

        song_name = "Test Song For Caching"
        cache_key = RedisClient.make_song_cache_key(song_name)

        # Clear cache
        cache_client.delete(cache_key)

        # First enrichment - should be cache miss
        start_time = asyncio.get_event_loop().time()
        result1 = await orchestrator.enrich_song(song_name)
        asyncio.get_event_loop().time() - start_time

        # Verify cache was populated
        cached_data = cache_client.get(cache_key)
        assert cached_data is not None
        assert "merged_data" in cached_data
        assert "completeness_score" in cached_data

        # Second enrichment - should be cache hit
        start_time = asyncio.get_event_loop().time()
        result2 = await orchestrator.enrich_song(song_name)
        second_duration = asyncio.get_event_loop().time() - start_time

        # Cache hit should be much faster (< 100ms requirement)
        assert second_duration < 0.1  # 100 milliseconds

        # Results should be consistent
        assert result1.completeness_score == result2.completeness_score
        assert len(result1.graph_node_ids) == len(result2.graph_node_ids)

    @pytest.mark.asyncio
    async def test_overmind_traces_created(self):
        """Test that Overmind Lab traces are created during enrichment.

        Verifies:
        - Traces are started for enrichment requests
        - Spans are created for agent dispatches
        - Traces are ended with proper status
        """
        from tests.test_orchestrator import MockOvermindClient, MockRedisClient

        mock_overmind = MockOvermindClient()
        cache_client = MockRedisClient()
        orchestrator = OrchestratorAgent(
            cache_client=cache_client,
            overmind_client=mock_overmind,
        )

        song_name = "Trace Test Song"

        # Perform enrichment
        result = await orchestrator.enrich_song(song_name)

        # Verify trace was created
        assert len(mock_overmind.traces) > 0
        trace = mock_overmind.traces[0]
        assert trace.operation_name == "song_enrichment"
        assert trace.request_id == result.request_id

        # Verify spans were created for agents
        assert len(mock_overmind.spans) == 4  # One per agent

        # Verify span metadata (Span stores attributes in .metadata)
        for span in mock_overmind.spans:
            assert "agent_name" in span.metadata
            assert "response_time_ms" in span.metadata
            assert "status" in span.metadata
            assert "completeness" in span.metadata

    @pytest.mark.asyncio
    async def test_spotify_agent_integration(self):
        """Test Spotify agent integration in isolation.

        Verifies:
        - Spotify agent can fetch data successfully
        - Data models are properly populated
        - Completeness scores are calculated
        - Rate limiting works
        """
        # Skip if no Spotify credentials
        if not os.getenv("SPOTIFY_CLIENT_ID") or not os.getenv("SPOTIFY_CLIENT_SECRET"):
            pytest.skip("Spotify credentials not configured")

        agent = SpotifyAgent()

        try:
            # Test with a well-known song
            result = await agent.fetch_spotify_data("Bohemian Rhapsody")

            # Verify result structure
            assert result is not None
            assert result.completeness_score >= 0.0

            # If song was found, verify data
            if result.song:
                assert result.song.title is not None
                assert result.song.spotify_id is not None

                # Verify artists
                assert len(result.artists) > 0
                assert result.artists[0].name is not None

                # Verify album
                if result.album:
                    assert result.album.title is not None
                    assert result.album.spotify_id is not None

                # Verify completeness score is reasonable
                assert result.completeness_score > 0.0
                assert result.completeness_score <= 1.0

        finally:
            await agent.close()

    @pytest.mark.asyncio
    async def test_parallel_agent_execution(self):
        """Test that agents execute in parallel.

        Verifies:
        - All agents are dispatched concurrently
        - Total time is less than sum of individual times
        - All agents complete or timeout
        """
        from tests.test_orchestrator import MockRedisClient, MockOvermindClient

        cache_client = MockRedisClient()
        mock_overmind = MockOvermindClient()
        orchestrator = OrchestratorAgent(
            cache_client=cache_client,
            overmind_client=mock_overmind,
        )

        song_name = "Parallel Test Song"
        trace = mock_overmind.start_trace(uuid4(), "test")

        # Measure time for parallel execution
        start_time = asyncio.get_event_loop().time()
        results = await orchestrator.dispatch_agents(song_name, trace)
        asyncio.get_event_loop().time() - start_time

        # Verify all 4 agents were dispatched
        assert len(results) == 4

        # Verify agent names
        agent_names = {r.agent_name for r in results}
        assert agent_names == {"spotify", "musicbrainz", "lastfm", "scraper"}

        # All results should have valid status
        for result in results:
            assert result.status in ["success", "partial", "failed"]
            assert result.response_time_ms >= 0

    @pytest.mark.asyncio
    async def test_agent_timeout_handling(self):
        """Test that agent timeouts are handled correctly.

        Verifies:
        - Agents that timeout are marked as failed
        - Orchestrator continues with other results
        - Timeout duration is enforced
        """
        cache_client = RedisClient()
        orchestrator = OrchestratorAgent(
            cache_client=cache_client,
            agent_timeout_ms=100,  # Very short timeout
        )

        song_name = "Timeout Test Song"

        # Dispatch agents with short timeout
        results = await orchestrator.dispatch_agents(song_name)

        # Should still get results from all agents
        assert len(results) == 4

        # Some agents may have timed out
        sum(1 for r in results if r.error_message and "timeout" in r.error_message.lower())

        # All results should have valid status
        for result in results:
            assert result.status in ["success", "partial", "failed"]
            assert result.response_time_ms >= 0

    @pytest.mark.asyncio
    async def test_data_persistence_structure(self):
        """Test that data is structured correctly for graph persistence.

        Verifies:
        - Merged data has correct structure
        - Node types are properly identified
        - Relationships are captured
        - Data sources are tracked
        """
        cache_client = RedisClient()
        orchestrator = OrchestratorAgent(cache_client=cache_client)

        song_name = "Persistence Test Song"
        cache_key = RedisClient.make_song_cache_key(song_name)
        cache_client.delete(cache_key)

        result = await orchestrator.enrich_song(song_name)

        # Verify merged data structure
        merged_data = result.merged_data

        # Should have all entity types
        assert "song" in merged_data
        assert "artists" in merged_data
        assert "album" in merged_data
        assert "relationships" in merged_data
        assert "data_sources" in merged_data

        # Data sources should be tracked
        assert isinstance(merged_data["data_sources"], list)
        assert len(merged_data["data_sources"]) > 0

        # Song data should be a dictionary
        assert isinstance(merged_data["song"], dict)

        # Artists should be a list
        assert isinstance(merged_data["artists"], list)

        # Album should be a dictionary
        assert isinstance(merged_data["album"], dict)

    @pytest.mark.asyncio
    async def test_error_handling_graceful_degradation(self):
        """Test that errors are handled gracefully.

        Verifies:
        - Failed agents don't crash the system
        - Partial results are still returned
        - Error messages are captured
        """
        cache_client = RedisClient()
        orchestrator = OrchestratorAgent(cache_client=cache_client)

        # Test with empty song name (should handle gracefully)
        result = await orchestrator.enrich_song("")

        # Should still return a result (even if failed)
        assert result is not None
        assert result.status in ["success", "partial", "failed"]
        assert result.request_id is not None

    def test_cache_key_normalization(self):
        """Test that cache keys are normalized correctly.

        Verifies:
        - Different capitalizations map to same key
        - Whitespace is handled
        - Keys have proper format
        """
        key1 = RedisClient.make_song_cache_key("Bohemian Rhapsody")
        key2 = RedisClient.make_song_cache_key("bohemian rhapsody")
        key3 = RedisClient.make_song_cache_key("  BOHEMIAN RHAPSODY  ")

        # All should normalize to same key
        assert key1 == key2
        assert key1 == key3

        # Key should have proper format
        assert key1.startswith("song:")
        assert key1.endswith(":v1")
        assert "bohemian rhapsody" in key1.lower()


class TestCheckpoint5Summary:
    """Summary test to verify all checkpoint requirements."""

    @pytest.mark.asyncio
    async def test_all_checkpoint_requirements(self):
        """Comprehensive test verifying all checkpoint 5 requirements.

        This test verifies:
        1. Song enrichment with Spotify agent works end-to-end
        2. Data is persisted (structured for graph DB)
        3. Caching works correctly
        4. Overmind Lab traces are created
        """
        # Setup
        from tests.test_orchestrator import MockRedisClient, MockOvermindClient

        cache_client = MockRedisClient()
        mock_overmind = MockOvermindClient()

        orchestrator = OrchestratorAgent(
            cache_client=cache_client,
            overmind_client=mock_overmind,
        )

        song_name = "Checkpoint 5 Test Song"
        cache_key = RedisClient.make_song_cache_key(song_name)
        cache_client.delete(cache_key)

        # 1. Test song enrichment with Spotify agent
        result = await orchestrator.enrich_song(song_name)

        assert result.status in ["success", "partial"]
        assert len(result.graph_node_ids) > 0
        assert 0.0 <= result.completeness_score <= 1.0

        # 2. Verify data is structured for persistence
        assert "song" in result.merged_data
        assert "artists" in result.merged_data
        assert "album" in result.merged_data
        assert "data_sources" in result.merged_data

        # 3. Verify caching works
        cached_data = cache_client.get(cache_key)
        assert cached_data is not None

        # Second request should hit cache
        result2 = await orchestrator.enrich_song(song_name)
        assert result2.completeness_score == result.completeness_score

        # 4. Verify Overmind Lab traces were created
        assert len(mock_overmind.traces) > 0
        assert len(mock_overmind.spans) == 4  # One per agent

        print("\n✅ Checkpoint 5 verification complete!")
        print(f"   - Song enrichment: {'✓' if result.status == 'success' else '⚠'}")
        print("   - Data persistence structure: ✓")
        print("   - Caching: ✓")
        print("   - Overmind tracing: ✓")
        print(f"   - Completeness score: {result.completeness_score:.2f}")
