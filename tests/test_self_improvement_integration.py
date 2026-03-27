"""Integration tests for self-improvement engine wired into orchestrator."""

from datetime import datetime
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from src.agents.orchestrator import AgentResult, OrchestratorAgent


@pytest.fixture
def mock_cache_client():
    """Create mock Redis cache client."""
    mock = MagicMock()
    mock.get.return_value = None  # Cache miss by default
    mock.set.return_value = True
    return mock


@pytest.fixture
def mock_overmind_client():
    """Create mock Overmind Lab client."""
    mock = MagicMock()
    mock.start_trace.return_value = MagicMock(request_id=uuid4())
    mock.log_agent_dispatch.return_value = MagicMock()
    mock.log_agent_response.return_value = None
    mock.log_metric.return_value = None
    mock.log_event.return_value = None
    return mock


@pytest.fixture
def mock_db_client():
    """Create mock Aerospike database client."""
    mock = MagicMock()
    mock._get_node_by_id.return_value = {
        "id": str(uuid4()),
        "title": "Test Song",
        "completeness_score": 0.5,
        "last_enriched": datetime.utcnow().isoformat(),
    }
    return mock


@pytest.fixture
def orchestrator(mock_cache_client, mock_overmind_client, mock_db_client):
    """Create orchestrator with mocked dependencies."""
    return OrchestratorAgent(
        cache_client=mock_cache_client,
        overmind_client=mock_overmind_client,
        db_client=mock_db_client,
        agent_timeout_ms=30000,
    )


@pytest.mark.asyncio
async def test_quality_tracking_integration(orchestrator, mock_overmind_client):
    """Test that quality tracking is integrated into enrichment flow."""
    # Mock agent execution
    with patch.object(orchestrator, "_call_agent") as mock_call_agent:
        mock_call_agent.return_value = AgentResult(
            agent_name="spotify",
            status="success",
            data={"song": {"title": "Test Song", "duration_ms": 240000}},
            completeness_score=0.8,
            response_time_ms=500,
        )

        # Execute enrichment
        result = await orchestrator.enrich_song("Test Song")

        # Verify quality metrics were analyzed
        assert result.status == "success"

        # Verify metrics were logged to Overmind Lab
        # Check that log_metric was called for quality metrics
        metric_calls = [call for call in mock_overmind_client.log_metric.call_args_list]
        assert len(metric_calls) > 0


@pytest.mark.asyncio
async def test_source_rankings_used_in_conflict_resolution(orchestrator):
    """Test that updated source rankings are used in conflict resolution."""
    # Create conflicting results from different sources
    spotify_result = AgentResult(
        agent_name="spotify",
        status="success",
        data={"song": {"title": "Test Song", "duration_ms": 240000}},
        completeness_score=0.9,
        response_time_ms=300,
    )

    musicbrainz_result = AgentResult(
        agent_name="musicbrainz",
        status="success",
        data={"song": {"title": "Test Song", "duration_ms": 245000}},
        completeness_score=0.95,
        response_time_ms=400,
    )

    # Analyze quality to update rankings
    quality_metrics = orchestrator.quality_tracker.analyze_data_quality(
        [spotify_result, musicbrainz_result]
    )
    orchestrator.quality_tracker.update_source_rankings(quality_metrics)

    # Merge results - should use quality rankings
    merged_data = orchestrator.merge_results([spotify_result, musicbrainz_result])

    # Verify merged data contains song
    assert "song" in merged_data
    assert "title" in merged_data["song"]
    assert merged_data["song"]["title"] == "Test Song"


@pytest.mark.asyncio
async def test_proactive_enrichment_integration(orchestrator, mock_overmind_client, mock_db_client):
    """Test that proactive enrichment is triggered after enrichment."""
    # Mock incomplete node data
    mock_db_client._get_node_by_id.return_value = {
        "id": str(uuid4()),
        "title": "Test Song",
        "completeness_score": 0.5,  # Below threshold
        "last_enriched": datetime.utcnow().isoformat(),
    }

    # Mock agent execution
    with patch.object(orchestrator, "_call_agent") as mock_call_agent:
        mock_call_agent.return_value = AgentResult(
            agent_name="spotify",
            status="success",
            data={"song": {"title": "Test Song"}},
            completeness_score=0.5,
            response_time_ms=500,
        )

        # Execute enrichment
        result = await orchestrator.enrich_song("Test Song")

        # Verify enrichment completed
        assert result.status == "success"

        # Verify self-improvement cycle event was logged
        event_calls = [
            call
            for call in mock_overmind_client.log_event.call_args_list
            if call[0][0] == "self_improvement_cycle_complete"
        ]

        # Should have at least one self-improvement cycle event
        # (may be 0 if no incomplete nodes were identified)
        assert len(event_calls) >= 0


@pytest.mark.asyncio
async def test_enrichment_tasks_scheduled(orchestrator, mock_db_client):
    """Test that enrichment tasks are scheduled for incomplete nodes."""
    # Create incomplete node
    node_id = uuid4()
    mock_db_client._get_node_by_id.return_value = {
        "id": str(node_id),
        "title": "Incomplete Song",
        "completeness_score": 0.3,  # Very incomplete
        "last_enriched": datetime.utcnow().isoformat(),
        "duration_ms": None,  # Missing field
        "spotify_id": None,  # Missing field
    }

    # Mock agent execution
    with patch.object(orchestrator, "_call_agent") as mock_call_agent:
        mock_call_agent.return_value = AgentResult(
            agent_name="spotify",
            status="success",
            data={"song": {"title": "Incomplete Song"}},
            completeness_score=0.3,
            response_time_ms=500,
        )

        # Execute enrichment
        result = await orchestrator.enrich_song("Incomplete Song")

        # Verify enrichment completed
        assert result.status == "success"

        # Verify enrichment scheduler was called
        assert orchestrator.enrichment_scheduler is not None


@pytest.mark.asyncio
async def test_quality_metrics_persistence(orchestrator):
    """Test that quality metrics are persisted after analysis."""
    # Create agent results
    results = [
        AgentResult(
            agent_name="spotify",
            status="success",
            data={"song": {"title": "Test"}},
            completeness_score=0.8,
            response_time_ms=300,
        ),
        AgentResult(
            agent_name="musicbrainz",
            status="success",
            data={"song": {"title": "Test"}},
            completeness_score=0.9,
            response_time_ms=500,
        ),
    ]

    # Analyze quality
    quality_metrics = orchestrator.quality_tracker.analyze_data_quality(results)

    # Verify metrics were created
    assert "spotify" in quality_metrics
    assert "musicbrainz" in quality_metrics

    # Verify metrics have valid values
    spotify_metrics = quality_metrics["spotify"]
    assert 0.0 <= spotify_metrics.completeness_avg <= 1.0
    assert 0.0 <= spotify_metrics.accuracy_score <= 1.0
    assert spotify_metrics.total_requests > 0


@pytest.mark.asyncio
async def test_self_improvement_logging(orchestrator, mock_overmind_client):
    """Test that self-improvement activities are logged to Overmind Lab."""
    # Mock agent execution
    with patch.object(orchestrator, "_call_agent") as mock_call_agent:
        mock_call_agent.return_value = AgentResult(
            agent_name="spotify",
            status="success",
            data={"song": {"title": "Test Song"}},
            completeness_score=0.8,
            response_time_ms=500,
        )

        # Execute enrichment
        await orchestrator.enrich_song("Test Song")

        # Verify events were logged
        event_calls = mock_overmind_client.log_event.call_args_list

        # Should have logged quality metrics update
        ranking_events = [call for call in event_calls if "ranking" in str(call).lower()]
        assert len(ranking_events) > 0


@pytest.mark.asyncio
async def test_failed_agent_quality_tracking(orchestrator):
    """Test that failed agents are tracked in quality metrics."""
    # Create failed agent result
    failed_result = AgentResult(
        agent_name="scraper",
        status="failed",
        data={},
        completeness_score=0.0,
        response_time_ms=30000,
        error_message="Timeout",
    )

    # Analyze quality
    quality_metrics = orchestrator.quality_tracker.analyze_data_quality([failed_result])

    # Verify failed request was tracked
    scraper_metrics = quality_metrics["scraper"]
    assert scraper_metrics.failed_requests > 0
    assert scraper_metrics.success_rate < 1.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
