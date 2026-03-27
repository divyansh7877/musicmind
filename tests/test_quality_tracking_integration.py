"""Integration tests for quality tracking with orchestrator."""

import pytest
from unittest.mock import Mock, patch

from src.agents.orchestrator import OrchestratorAgent, AgentResult
from src.self_improvement.quality_tracker import QualityTracker


@pytest.mark.asyncio
class TestQualityTrackingIntegration:
    """Tests for quality tracking integration with orchestrator."""

    @pytest.fixture
    def mock_cache_client(self):
        """Create mock cache client."""
        mock = Mock()
        mock.get.return_value = None
        mock.set.return_value = True
        return mock

    @pytest.fixture
    def mock_overmind_client(self):
        """Create mock Overmind client."""
        mock = Mock()
        mock.start_trace.return_value = Mock(request_id="test-id")
        mock.log_agent_dispatch.return_value = Mock()
        return mock

    @pytest.fixture
    def orchestrator(self, mock_cache_client, mock_overmind_client):
        """Create orchestrator with mocked dependencies."""
        return OrchestratorAgent(
            cache_client=mock_cache_client,
            overmind_client=mock_overmind_client,
        )

    async def test_quality_metrics_updated_after_enrichment(
        self, orchestrator, mock_cache_client
    ):
        """Test that quality metrics are updated after song enrichment."""
        # Track cache calls to verify metrics are persisted
        cache_calls = []

        def track_cache_set(key, value, ttl=None):
            cache_calls.append((key, value))
            return True

        mock_cache_client.set.side_effect = track_cache_set

        # Mock agent responses
        with patch.object(orchestrator, "_call_agent") as mock_call_agent:
            mock_call_agent.return_value = AgentResult(
                agent_name="spotify",
                status="success",
                data={"song": {"title": "Test Song"}},
                completeness_score=0.85,
                response_time_ms=500,
            )

            # Enrich a song
            result = await orchestrator.enrich_song("Test Song")

            assert result.status == "success"

            # Verify quality metrics were persisted
            quality_metric_calls = [
                call for call in cache_calls if "quality_metrics" in call[0]
            ]
            assert len(quality_metric_calls) > 0

            # Verify metrics contain expected data
            for key, value in quality_metric_calls:
                assert "source_name" in value
                assert "accuracy_score" in value
                assert "completeness_avg" in value
                assert "success_rate" in value

    async def test_source_rankings_affect_conflict_resolution(
        self, orchestrator, mock_cache_client
    ):
        """Test that source rankings are used in conflict resolution."""
        # Set up quality metrics for different sources
        spotify_metrics = {
            "source_name": "spotify",
            "accuracy_score": 0.9,
            "completeness_avg": 0.85,
            "success_rate": 0.95,
            "total_requests": 100,
            "failed_requests": 5,
            "response_time_avg": 500,
            "freshness_score": 1.0,
            "last_updated": "2024-01-15T10:00:00",
        }

        musicbrainz_metrics = {
            "source_name": "musicbrainz",
            "accuracy_score": 0.95,
            "completeness_avg": 0.9,
            "success_rate": 0.98,
            "total_requests": 100,
            "failed_requests": 2,
            "response_time_avg": 1500,
            "freshness_score": 1.0,
            "last_updated": "2024-01-15T10:00:00",
        }

        def mock_get(key):
            if "spotify" in key:
                return spotify_metrics
            elif "musicbrainz" in key:
                return musicbrainz_metrics
            return None

        mock_cache_client.get.side_effect = mock_get

        # Create conflicting results
        spotify_result = AgentResult(
            agent_name="spotify",
            status="success",
            data={"song": {"title": "Song Title", "duration_ms": 180000}},
            completeness_score=0.8,
            response_time_ms=500,
        )

        musicbrainz_result = AgentResult(
            agent_name="musicbrainz",
            status="success",
            data={"song": {"title": "Song Title", "duration_ms": 185000}},
            completeness_score=0.85,
            response_time_ms=1500,
        )

        # Merge results
        merged = orchestrator.merge_results([spotify_result, musicbrainz_result])

        # MusicBrainz has higher quality (0.95 vs 0.9), so its duration should win
        assert merged["song"]["duration_ms"] == 185000

    async def test_quality_improves_over_time(self, orchestrator, mock_cache_client):
        """Test that quality metrics improve with successful requests."""
        # Start with poor metrics
        initial_metrics = {
            "source_name": "lastfm",
            "accuracy_score": 0.5,
            "completeness_avg": 0.4,
            "success_rate": 0.6,
            "total_requests": 10,
            "failed_requests": 4,
            "response_time_avg": 3000,
            "freshness_score": 0.8,
            "last_updated": "2024-01-15T09:00:00",
        }

        cache_data = {}

        def mock_get(key):
            return cache_data.get(key)

        def mock_set(key, value, ttl=None):
            cache_data[key] = value
            return True

        mock_cache_client.get.side_effect = mock_get
        mock_cache_client.set.side_effect = mock_set

        # Set initial metrics
        cache_data["quality_metrics:lastfm:v1"] = initial_metrics

        # Mock successful agent response
        with patch.object(orchestrator, "_call_agent") as mock_call_agent:
            mock_call_agent.return_value = AgentResult(
                agent_name="lastfm",
                status="success",
                data={"song": {"title": "Test Song"}},
                completeness_score=0.9,
                response_time_ms=800,
            )

            # Enrich song
            await orchestrator.enrich_song("Test Song")

            # Check updated metrics
            updated_metrics = cache_data.get("quality_metrics:lastfm:v1")
            assert updated_metrics is not None

            # Metrics should improve
            assert updated_metrics["total_requests"] == 11
            assert updated_metrics["completeness_avg"] > 0.4  # Should increase
            assert updated_metrics["accuracy_score"] > 0.5  # Should increase

    async def test_failed_requests_decrease_quality(
        self, orchestrator, mock_cache_client
    ):
        """Test that failed requests decrease quality scores."""
        # Start with good metrics
        initial_metrics = {
            "source_name": "scraper",
            "accuracy_score": 0.8,
            "completeness_avg": 0.75,
            "success_rate": 0.9,
            "total_requests": 10,
            "failed_requests": 1,
            "response_time_avg": 2000,
            "freshness_score": 1.0,
            "last_updated": "2024-01-15T09:00:00",
        }

        cache_data = {}

        def mock_get(key):
            return cache_data.get(key)

        def mock_set(key, value, ttl=None):
            cache_data[key] = value
            return True

        mock_cache_client.get.side_effect = mock_get
        mock_cache_client.set.side_effect = mock_set

        # Set initial metrics
        cache_data["quality_metrics:scraper:v1"] = initial_metrics

        # Mock failed agent response
        with patch.object(orchestrator, "_call_agent") as mock_call_agent:
            mock_call_agent.return_value = AgentResult(
                agent_name="scraper",
                status="failed",
                data={},
                completeness_score=0.0,
                response_time_ms=30000,
                error_message="Timeout",
            )

            # Enrich song
            await orchestrator.enrich_song("Test Song")

            # Check updated metrics
            updated_metrics = cache_data.get("quality_metrics:scraper:v1")
            assert updated_metrics is not None

            # Metrics should degrade
            assert updated_metrics["total_requests"] == 11
            assert updated_metrics["failed_requests"] == 2
            assert updated_metrics["success_rate"] < 0.9  # Should decrease


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
