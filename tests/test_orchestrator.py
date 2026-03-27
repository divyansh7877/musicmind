"""Unit tests for orchestrator agent."""

import asyncio
from datetime import datetime
from uuid import uuid4

import pytest

from src.agents.orchestrator import AgentResult, EnrichmentResult, OrchestratorAgent
from src.cache.redis_client import RedisClient
from src.tracing.overmind_client import OvermindClient


class MockRedisClient:
    """Mock Redis client for testing."""

    def __init__(self):
        self.cache = {}

    def get(self, key: str):
        return self.cache.get(key)

    def set(self, key: str, value: dict, ttl: int = 3600):
        self.cache[key] = value
        return True

    def delete(self, key: str):
        if key in self.cache:
            del self.cache[key]
            return True
        return False

    def exists(self, key: str):
        return key in self.cache


class MockOvermindClient:
    """Mock Overmind client for testing."""

    def __init__(self):
        self.traces = []
        self.spans = []
        self.metrics = []
        self.events = []

    def start_trace(self, request_id, operation_name):
        from src.tracing.overmind_client import TraceContext

        trace = TraceContext(request_id, operation_name)
        self.traces.append(trace)
        return trace

    def log_agent_dispatch(self, trace, agent_name, song_name):
        span = trace.create_span(f"agent_dispatch_{agent_name}")
        span.set_attribute("agent_name", agent_name)
        span.set_attribute("song_name", song_name)
        self.spans.append(span)
        return span

    def log_agent_response(self, span, response_time_ms, status, completeness):
        span.set_attribute("response_time_ms", response_time_ms)
        span.set_attribute("status", status)
        span.set_attribute("completeness", completeness)
        span.end_span(status)

    def log_metric(self, metric_name, value, tags=None):
        self.metrics.append({"name": metric_name, "value": value, "tags": tags})

    def log_event(self, event_name, properties):
        self.events.append({"name": event_name, "properties": properties})


@pytest.fixture
def mock_cache():
    """Fixture for mock Redis client."""
    return MockRedisClient()


@pytest.fixture
def mock_overmind():
    """Fixture for mock Overmind client."""
    return MockOvermindClient()


@pytest.fixture
def orchestrator(mock_cache, mock_overmind):
    """Fixture for orchestrator agent."""
    return OrchestratorAgent(
        cache_client=mock_cache,
        overmind_client=mock_overmind,
        agent_timeout_ms=30000,
    )


@pytest.mark.asyncio
async def test_enrich_song_basic(orchestrator):
    """Test basic song enrichment flow."""
    result = await orchestrator.enrich_song("Bohemian Rhapsody")

    assert result.status in ["success", "partial"]
    assert len(result.graph_node_ids) > 0
    assert result.completeness_score >= 0.0
    assert result.completeness_score <= 1.0
    assert result.request_id is not None


@pytest.mark.asyncio
async def test_enrich_song_cache_hit(orchestrator, mock_cache):
    """Test cache hit scenario."""
    # First enrichment
    result1 = await orchestrator.enrich_song("Test Song")

    # Second enrichment should hit cache
    result2 = await orchestrator.enrich_song("Test Song")

    assert result2.status == "success"
    assert len(result2.graph_node_ids) > 0


@pytest.mark.asyncio
async def test_dispatch_agents_parallel(orchestrator):
    """Test parallel agent dispatch."""
    results = await orchestrator.dispatch_agents("Test Song")

    # Should have results from all 4 agents
    assert len(results) == 4

    # Check agent names
    agent_names = {r.agent_name for r in results}
    assert agent_names == {"spotify", "musicbrainz", "lastfm", "scraper"}

    # All results should have response times
    for result in results:
        assert result.response_time_ms >= 0


@pytest.mark.asyncio
async def test_dispatch_agents_with_timeout(orchestrator):
    """Test agent timeout handling."""
    # Set very short timeout
    orchestrator.agent_timeout_seconds = 0.001

    results = await orchestrator.dispatch_agents("Test Song")

    # Should still get results (may be timeouts)
    assert len(results) == 4

    # Check that results have proper status
    for result in results:
        assert result.status in ["success", "partial", "failed"]


def test_merge_results_basic(orchestrator):
    """Test basic result merging."""
    results = [
        AgentResult(
            agent_name="spotify",
            status="success",
            data={"song": {"title": "Test Song", "duration_ms": 180000}},
            completeness_score=0.8,
        ),
        AgentResult(
            agent_name="musicbrainz",
            status="success",
            data={"song": {"title": "Test Song", "isrc": "USRC12345678"}},
            completeness_score=0.7,
        ),
    ]

    merged = orchestrator.merge_results(results)

    assert "song" in merged
    assert merged["song"]["title"] == "Test Song"
    assert "duration_ms" in merged["song"]
    assert "isrc" in merged["song"]
    assert "data_sources" in merged
    assert len(merged["data_sources"]) == 2


def test_merge_results_with_failures(orchestrator):
    """Test merging with some failed agents."""
    results = [
        AgentResult(
            agent_name="spotify",
            status="success",
            data={"song": {"title": "Test Song"}},
            completeness_score=0.8,
        ),
        AgentResult(
            agent_name="musicbrainz",
            status="failed",
            data={},
            error_message="Connection timeout",
        ),
        AgentResult(
            agent_name="lastfm",
            status="success",
            data={"song": {"tags": ["rock", "classic"]}},
            completeness_score=0.6,
        ),
    ]

    merged = orchestrator.merge_results(results)

    # Should only include successful results
    assert len(merged["data_sources"]) == 2
    assert "spotify" in merged["data_sources"]
    assert "lastfm" in merged["data_sources"]
    assert "musicbrainz" not in merged["data_sources"]


def test_merge_song_data_conflict_resolution(orchestrator):
    """Test conflict resolution for song data."""
    results = [
        AgentResult(
            agent_name="spotify",
            status="success",
            data={"song": {"title": "Test Song", "duration_ms": 180000}},
            completeness_score=0.8,
            timestamp=datetime(2024, 1, 1, 12, 0, 0),
        ),
        AgentResult(
            agent_name="musicbrainz",
            status="success",
            data={"song": {"title": "Test Song", "duration_ms": 181000}},
            completeness_score=0.9,
            timestamp=datetime(2024, 1, 1, 12, 0, 0),
        ),
    ]

    merged = orchestrator.merge_song_data(results)

    # MusicBrainz has higher quality, should win for duration_ms
    assert merged["duration_ms"] == 181000


def test_merge_song_data_multi_value_fields(orchestrator):
    """Test merging of multi-value fields like tags."""
    results = [
        AgentResult(
            agent_name="spotify",
            status="success",
            data={"song": {"tags": ["rock", "classic"]}},
            completeness_score=0.8,
        ),
        AgentResult(
            agent_name="lastfm",
            status="success",
            data={"song": {"tags": ["classic", "70s", "progressive"]}},
            completeness_score=0.7,
        ),
    ]

    merged = orchestrator.merge_song_data(results)

    # Should merge and deduplicate tags
    assert "tags" in merged
    assert len(merged["tags"]) == 4  # rock, classic, 70s, progressive
    assert "rock" in merged["tags"]
    assert "classic" in merged["tags"]
    assert "70s" in merged["tags"]
    assert "progressive" in merged["tags"]


def test_merge_song_data_time_sensitive_fields(orchestrator):
    """Test merging of time-sensitive fields like play_count."""
    results = [
        AgentResult(
            agent_name="spotify",
            status="success",
            data={"song": {"play_count": 1000000}},
            completeness_score=0.8,
            timestamp=datetime(2024, 1, 1, 12, 0, 0),
        ),
        AgentResult(
            agent_name="lastfm",
            status="success",
            data={"song": {"play_count": 1500000}},
            completeness_score=0.7,
            timestamp=datetime(2024, 1, 2, 12, 0, 0),  # More recent
        ),
    ]

    merged = orchestrator.merge_song_data(results)

    # Should use most recent value
    assert merged["play_count"] == 1500000


def test_calculate_overall_completeness(orchestrator):
    """Test overall completeness calculation."""
    merged_data = {
        "song": {
            "title": "Test Song",
            "duration_ms": 180000,
            "release_date": None,
            "isrc": "USRC12345678",
        },
        "artists": [{"name": "Test Artist"}],
        "album": {},
        "relationships": [],
        "data_sources": ["spotify", "musicbrainz"],
    }

    score = orchestrator._calculate_overall_completeness(merged_data)

    assert 0.0 <= score <= 1.0
    assert score > 0.0  # Should have some populated fields


@pytest.mark.asyncio
async def test_overmind_tracing(orchestrator, mock_overmind):
    """Test Overmind Lab tracing integration."""
    result = await orchestrator.enrich_song("Test Song")

    # Should have created a trace
    assert len(mock_overmind.traces) > 0

    # Should have created spans for agents
    assert len(mock_overmind.spans) == 4  # One per agent


def test_cache_key_generation():
    """Test cache key generation."""
    key1 = RedisClient.make_song_cache_key("Bohemian Rhapsody")
    key2 = RedisClient.make_song_cache_key("bohemian rhapsody")
    key3 = RedisClient.make_song_cache_key("  Bohemian Rhapsody  ")

    # Should normalize to same key
    assert key1 == key2
    assert key1 == key3
    assert key1.startswith("song:")
    assert key1.endswith(":v1")


def test_agent_result_creation():
    """Test AgentResult creation."""
    result = AgentResult(
        agent_name="spotify",
        status="success",
        data={"song": {"title": "Test"}},
        completeness_score=0.8,
        response_time_ms=150,
    )

    assert result.agent_name == "spotify"
    assert result.status == "success"
    assert result.completeness_score == 0.8
    assert result.response_time_ms == 150
    assert result.timestamp is not None


def test_enrichment_result_creation():
    """Test EnrichmentResult creation."""
    node_ids = [uuid4(), uuid4()]
    result = EnrichmentResult(
        status="success",
        graph_node_ids=node_ids,
        merged_data={"song": {"title": "Test"}},
        completeness_score=0.85,
        request_id=uuid4(),
    )

    assert result.status == "success"
    assert len(result.graph_node_ids) == 2
    assert result.completeness_score == 0.85
    assert result.request_id is not None
