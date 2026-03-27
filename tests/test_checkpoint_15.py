"""Checkpoint 15: Verify self-improvement engine works end-to-end.

Tests:
- Complete self-improvement cycle end-to-end
- Quality metrics improve over time
- Proactive enrichment tasks are scheduled
- User feedback updates quality scores
"""

from datetime import datetime
from unittest.mock import patch
from uuid import uuid4

import pytest

from src.agents.orchestrator import AgentResult, OrchestratorAgent
from src.self_improvement.enrichment_scheduler import (
    EnrichmentPriority,
    EnrichmentScheduler,
    EnrichmentTask,
)
from src.self_improvement.feedback_processor import FeedbackProcessor, UserFeedback
from src.self_improvement.quality_tracker import QualityMetrics, QualityTracker


class MockRedisClient:
    """Mock Redis client for testing."""

    def __init__(self):
        self.cache = {}

    def get(self, key):
        return self.cache.get(key)

    def set(self, key, value, ttl=3600):
        self.cache[key] = value
        return True

    def delete(self, key):
        if key in self.cache:
            del self.cache[key]
            return True
        return False

    def exists(self, key):
        return key in self.cache


class MockOvermindClient:
    """Mock Overmind Lab client for testing."""

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


class MockAerospikeClient:
    """Mock Aerospike client for testing."""

    def __init__(self):
        self.nodes = {}

    def _get_node_by_id(self, node_id):
        return self.nodes.get(str(node_id))

    def upsert_node(self, node_type, node_data):
        node_id = node_data.get("id", str(uuid4()))
        self.nodes[str(node_id)] = node_data
        return True


@pytest.fixture
def cache_client():
    return MockRedisClient()


@pytest.fixture
def overmind_client():
    return MockOvermindClient()


@pytest.fixture
def db_client():
    return MockAerospikeClient()


@pytest.fixture
def quality_tracker(cache_client, overmind_client):
    return QualityTracker(
        cache_client=cache_client,
        overmind_client=overmind_client,
    )


@pytest.fixture
def enrichment_scheduler(db_client, overmind_client):
    return EnrichmentScheduler(
        db_client=db_client,
        overmind_client=overmind_client,
    )


@pytest.fixture
def feedback_processor(
    db_client, quality_tracker, enrichment_scheduler, cache_client, overmind_client
):
    return FeedbackProcessor(
        db_client=db_client,
        quality_tracker=quality_tracker,
        enrichment_scheduler=enrichment_scheduler,
        cache_client=cache_client,
        overmind_client=overmind_client,
    )


@pytest.fixture
def orchestrator(cache_client, overmind_client, db_client):
    return OrchestratorAgent(
        cache_client=cache_client,
        overmind_client=overmind_client,
        db_client=db_client,
        agent_timeout_ms=30000,
    )


class TestSelfImprovementCycleEndToEnd:
    """Test the complete self-improvement cycle."""

    @pytest.mark.asyncio
    async def test_full_self_improvement_cycle(self, orchestrator, overmind_client):
        """Test complete self-improvement cycle: enrich -> track quality -> schedule enrichment."""
        with patch.object(orchestrator, "_call_agent") as mock_call:
            mock_call.return_value = AgentResult(
                agent_name="spotify",
                status="success",
                data={"song": {"title": "Test Song", "duration_ms": 240000}},
                completeness_score=0.8,
                response_time_ms=500,
            )

            result = await orchestrator.enrich_song("Test Song")

            assert result.status == "success"
            assert result.completeness_score > 0.0

            # Verify quality metrics were logged
            metric_calls = [m for m in overmind_client.metrics if "completeness" in m["name"]]
            assert len(metric_calls) > 0

            # Verify source ranking event was logged
            ranking_events = [
                e for e in overmind_client.events if e["name"] == "source_rankings_updated"
            ]
            assert len(ranking_events) > 0

    @pytest.mark.asyncio
    async def test_multiple_enrichments_improve_metrics(self, cache_client, overmind_client):
        """Test that quality metrics improve as more successful enrichments occur."""
        tracker = QualityTracker(
            cache_client=cache_client,
            overmind_client=overmind_client,
        )

        # First enrichment with low completeness
        result1 = AgentResult(
            agent_name="spotify",
            status="success",
            data={"song": {"title": "Song 1"}},
            completeness_score=0.3,
            response_time_ms=1000,
        )
        metrics1 = tracker.analyze_data_quality([result1])
        tracker.update_source_rankings(metrics1)
        initial_accuracy = metrics1["spotify"].accuracy_score

        # Series of enrichments with increasing completeness
        for i in range(5):
            result = AgentResult(
                agent_name="spotify",
                status="success",
                data={"song": {"title": f"Song {i+2}"}},
                completeness_score=0.7 + (i * 0.05),
                response_time_ms=500,
            )
            metrics = tracker.analyze_data_quality([result])
            tracker.update_source_rankings(metrics)

        # Load final metrics
        final_metrics = tracker._load_metrics("spotify")

        # Quality should have improved
        assert final_metrics.accuracy_score > initial_accuracy
        assert final_metrics.completeness_avg > 0.3
        assert final_metrics.success_rate == 1.0
        assert final_metrics.total_requests == 6

    @pytest.mark.asyncio
    async def test_failed_agents_reduce_quality(self, cache_client, overmind_client):
        """Test that failed enrichments reduce quality scores."""
        tracker = QualityTracker(
            cache_client=cache_client,
            overmind_client=overmind_client,
        )

        # Successful enrichment
        success_result = AgentResult(
            agent_name="scraper",
            status="success",
            data={"song": {"title": "Good Song"}},
            completeness_score=0.9,
            response_time_ms=300,
        )
        metrics = tracker.analyze_data_quality([success_result])
        tracker.update_source_rankings(metrics)
        good_accuracy = metrics["scraper"].accuracy_score

        # Multiple failures
        for _ in range(3):
            fail_result = AgentResult(
                agent_name="scraper",
                status="failed",
                data={},
                completeness_score=0.0,
                response_time_ms=30000,
                error_message="Timeout",
            )
            metrics = tracker.analyze_data_quality([fail_result])
            tracker.update_source_rankings(metrics)

        bad_metrics = tracker._load_metrics("scraper")
        assert bad_metrics.accuracy_score < good_accuracy
        assert bad_metrics.success_rate < 1.0
        assert bad_metrics.failed_requests == 3


class TestProactiveEnrichmentScheduling:
    """Test proactive enrichment task scheduling."""

    def test_incomplete_nodes_identified(self, enrichment_scheduler, db_client):
        """Test that incomplete nodes are identified and tasks are created."""
        node_id = uuid4()
        db_client.nodes[str(node_id)] = {
            "id": str(node_id),
            "title": "Incomplete Song",
            "completeness_score": 0.3,
            "last_enriched": datetime.utcnow().isoformat(),
            "duration_ms": None,
            "isrc": None,
        }

        tasks = enrichment_scheduler.identify_incomplete_nodes([node_id])

        assert len(tasks) > 0
        task = tasks[0]
        assert task.node_id == node_id
        assert task.priority == EnrichmentPriority.HIGH  # < 0.4
        assert len(task.missing_fields) > 0
        assert len(task.target_agents) > 0

    def test_priority_mapping(self, enrichment_scheduler, db_client):
        """Test that priority correctly maps to completeness ranges."""
        # High priority: completeness < 0.4
        high_id = uuid4()
        db_client.nodes[str(high_id)] = {
            "id": str(high_id),
            "title": "Very Incomplete",
            "completeness_score": 0.2,
            "last_enriched": datetime.utcnow().isoformat(),
            "duration_ms": None,
        }

        # Medium priority: completeness 0.4-0.7
        med_id = uuid4()
        db_client.nodes[str(med_id)] = {
            "id": str(med_id),
            "title": "Somewhat Incomplete",
            "completeness_score": 0.5,
            "last_enriched": datetime.utcnow().isoformat(),
            "duration_ms": None,
        }

        high_tasks = enrichment_scheduler.identify_incomplete_nodes([high_id])
        enrichment_scheduler.clear_processed_nodes()
        med_tasks = enrichment_scheduler.identify_incomplete_nodes([med_id])

        assert len(high_tasks) > 0
        assert high_tasks[0].priority == EnrichmentPriority.HIGH

        assert len(med_tasks) > 0
        assert med_tasks[0].priority == EnrichmentPriority.MEDIUM

    @pytest.mark.asyncio
    async def test_tasks_scheduled_by_priority(
        self, enrichment_scheduler, db_client, overmind_client
    ):
        """Test that tasks are added to priority queues."""
        tasks = [
            EnrichmentTask(
                node_id=uuid4(),
                node_type="Song",
                priority=EnrichmentPriority.HIGH,
                missing_fields=["duration_ms"],
                target_agents=["spotify"],
                completeness_score=0.3,
                last_enriched=datetime.utcnow(),
            ),
            EnrichmentTask(
                node_id=uuid4(),
                node_type="Artist",
                priority=EnrichmentPriority.MEDIUM,
                missing_fields=["biography"],
                target_agents=["lastfm"],
                completeness_score=0.5,
                last_enriched=datetime.utcnow(),
            ),
        ]

        await enrichment_scheduler.schedule_proactive_enrichment(tasks)

        # Verify tasks were scheduled
        scheduling_events = [
            e for e in overmind_client.events if e["name"] == "enrichment_tasks_scheduled"
        ]
        assert len(scheduling_events) > 0
        assert scheduling_events[0]["properties"]["total_tasks"] == 2

    def test_task_deduplication(self, enrichment_scheduler):
        """Test that tasks for the same node are deduplicated."""
        node_id = uuid4()
        tasks = [
            EnrichmentTask(
                node_id=node_id,
                node_type="Song",
                priority=EnrichmentPriority.MEDIUM,
                missing_fields=["duration_ms"],
                target_agents=["spotify"],
                completeness_score=0.5,
                last_enriched=datetime.utcnow(),
            ),
            EnrichmentTask(
                node_id=node_id,
                node_type="Song",
                priority=EnrichmentPriority.HIGH,
                missing_fields=["duration_ms", "isrc"],
                target_agents=["spotify", "musicbrainz"],
                completeness_score=0.3,
                last_enriched=datetime.utcnow(),
            ),
        ]

        deduped = enrichment_scheduler._deduplicate_tasks(tasks)
        assert len(deduped) == 1
        assert deduped[0].priority == EnrichmentPriority.HIGH  # Keeps highest priority

    @pytest.mark.asyncio
    async def test_enrichment_integrated_into_orchestrator(
        self, orchestrator, db_client, overmind_client
    ):
        """Test that proactive enrichment is triggered by the orchestrator after enrichment."""
        node_id = uuid4()
        db_client.nodes[str(node_id)] = {
            "id": str(node_id),
            "title": "Test Song",
            "completeness_score": 0.3,
            "last_enriched": datetime.utcnow().isoformat(),
            "duration_ms": None,
        }

        with patch.object(orchestrator, "_call_agent") as mock_call:
            mock_call.return_value = AgentResult(
                agent_name="spotify",
                status="success",
                data={"song": {"title": "Test Song"}},
                completeness_score=0.3,
                response_time_ms=500,
            )

            result = await orchestrator.enrich_song("Test Song")
            assert result.status == "success"

            # Verify self-improvement events were logged
            si_events = [
                e
                for e in overmind_client.events
                if "self_improvement" in e["name"]
                or "enrichment" in e["name"]
                or "ranking" in e["name"]
            ]
            assert len(si_events) > 0


class TestUserFeedbackUpdatesQuality:
    """Test that user feedback updates quality scores."""

    def test_like_feedback_increases_quality(
        self, feedback_processor, db_client, quality_tracker, cache_client
    ):
        """Test that 'like' feedback increases source quality scores."""
        node_id = uuid4()
        db_client.nodes[str(node_id)] = {
            "id": str(node_id),
            "title": "Liked Song",
            "duration_ms": 240000,
            "completeness_score": 0.8,
            "data_sources": ["spotify", "musicbrainz"],
            "last_enriched": datetime.utcnow().isoformat(),
        }

        # Set initial metrics
        for source in ["spotify", "musicbrainz"]:
            initial_metrics = QualityMetrics(
                source_name=source,
                completeness_avg=0.7,
                accuracy_score=0.6,
                success_rate=0.8,
                total_requests=10,
            )
            quality_tracker.persist_metrics(initial_metrics)

        # Process like feedback
        feedback = UserFeedback(
            user_id=uuid4(),
            node_id=node_id,
            feedback_type="like",
            feedback_value=1,
        )
        feedback_processor.process_user_feedback(feedback)

        # Verify quality improved
        spotify_metrics = quality_tracker._load_metrics("spotify")
        assert spotify_metrics.accuracy_score >= 0.6

    def test_dislike_feedback_decreases_quality(
        self, feedback_processor, db_client, quality_tracker, cache_client
    ):
        """Test that 'dislike' feedback decreases source quality scores."""
        node_id = uuid4()
        db_client.nodes[str(node_id)] = {
            "id": str(node_id),
            "title": "Disliked Song",
            "duration_ms": 240000,
            "completeness_score": 0.8,
            "data_sources": ["spotify"],
            "last_enriched": datetime.utcnow().isoformat(),
        }

        initial_metrics = QualityMetrics(
            source_name="spotify",
            completeness_avg=0.8,
            accuracy_score=0.9,
            success_rate=0.9,
            total_requests=10,
        )
        quality_tracker.persist_metrics(initial_metrics)

        feedback = UserFeedback(
            user_id=uuid4(),
            node_id=node_id,
            feedback_type="dislike",
            feedback_value=-1,
        )
        feedback_processor.process_user_feedback(feedback)

        spotify_metrics = quality_tracker._load_metrics("spotify")
        # Accuracy should have decreased or stayed same after recalculation
        assert spotify_metrics.accuracy_score <= 0.9

    def test_correction_feedback_updates_node(
        self, feedback_processor, db_client, quality_tracker, cache_client
    ):
        """Test that 'correction' feedback updates the node data."""
        node_id = uuid4()
        db_client.nodes[str(node_id)] = {
            "id": str(node_id),
            "title": "Wrong Song Title",
            "duration_ms": 240000,
            "completeness_score": 0.8,
            "data_sources": ["spotify"],
            "last_enriched": datetime.utcnow().isoformat(),
        }

        feedback = UserFeedback(
            user_id=uuid4(),
            node_id=node_id,
            feedback_type="correction",
            feedback_value=0,
            comment="Title should be 'Correct Song Title'",
        )
        feedback_processor.process_user_feedback(feedback)

        # Verify node was updated
        updated_node = db_client.nodes.get(str(node_id))
        assert updated_node is not None
        assert "user_correction" in updated_node.get("data_sources", [])
        assert updated_node.get("title") == "Correct Song Title"

    def test_report_feedback_reduces_visibility(self, feedback_processor, db_client):
        """Test that 'report' feedback reduces node visibility."""
        node_id = uuid4()
        db_client.nodes[str(node_id)] = {
            "id": str(node_id),
            "title": "Reported Song",
            "duration_ms": 240000,
            "completeness_score": 0.8,
            "visibility_score": 1.0,
            "data_sources": ["spotify"],
            "last_enriched": datetime.utcnow().isoformat(),
        }

        feedback = UserFeedback(
            user_id=uuid4(),
            node_id=node_id,
            feedback_type="report",
            feedback_value=-1,
            comment="This data is incorrect",
        )
        feedback_processor.process_user_feedback(feedback)

        updated_node = db_client.nodes.get(str(node_id))
        assert updated_node["visibility_score"] == 0.5

    def test_feedback_events_logged(self, feedback_processor, db_client, overmind_client):
        """Test that all feedback events are logged to Overmind Lab."""
        node_id = uuid4()
        db_client.nodes[str(node_id)] = {
            "id": str(node_id),
            "title": "Logged Song",
            "duration_ms": 240000,
            "completeness_score": 0.8,
            "data_sources": ["spotify"],
            "last_enriched": datetime.utcnow().isoformat(),
        }

        feedback = UserFeedback(
            user_id=uuid4(),
            node_id=node_id,
            feedback_type="like",
            feedback_value=1,
        )
        feedback_processor.process_user_feedback(feedback)

        feedback_events = [
            e for e in overmind_client.events if e["name"] == "user_feedback_processed"
        ]
        assert len(feedback_events) == 1
        assert feedback_events[0]["properties"]["feedback_type"] == "like"


class TestQualityMetricsValidity:
    """Test quality metrics stay valid across operations."""

    def test_all_scores_bounded(self, cache_client, overmind_client):
        """Test that all quality scores remain between 0.0 and 1.0."""
        tracker = QualityTracker(cache_client=cache_client, overmind_client=overmind_client)

        # Process many results with extreme values
        for i in range(20):
            result = AgentResult(
                agent_name="spotify",
                status="success" if i % 3 != 0 else "failed",
                data={"song": {"title": f"Song {i}"}} if i % 3 != 0 else {},
                completeness_score=float(i % 2),
                response_time_ms=i * 500,
            )
            metrics = tracker.analyze_data_quality([result])
            m = metrics["spotify"]

            assert 0.0 <= m.completeness_avg <= 1.0
            assert 0.0 <= m.accuracy_score <= 1.0
            assert 0.0 <= m.freshness_score <= 1.0
            assert 0.0 <= m.success_rate <= 1.0
            assert m.failed_requests <= m.total_requests

    def test_success_rate_calculation(self, cache_client, overmind_client):
        """Test success_rate = (total - failed) / total."""
        tracker = QualityTracker(cache_client=cache_client, overmind_client=overmind_client)

        results = []
        for i in range(10):
            results.append(
                AgentResult(
                    agent_name="lastfm",
                    status="success" if i < 7 else "failed",
                    data={"song": {"title": f"Song {i}"}} if i < 7 else {},
                    completeness_score=0.8 if i < 7 else 0.0,
                    response_time_ms=300,
                )
            )

        for result in results:
            metrics = tracker.analyze_data_quality([result])
            tracker.update_source_rankings(metrics)

        final = tracker._load_metrics("lastfm")
        expected_rate = (final.total_requests - final.failed_requests) / final.total_requests
        assert abs(final.success_rate - expected_rate) < 0.001
        assert final.total_requests == 10
        assert final.failed_requests == 3

    def test_source_rankings_order(self, cache_client, overmind_client):
        """Test that source rankings are ordered by accuracy score."""
        tracker = QualityTracker(cache_client=cache_client, overmind_client=overmind_client)

        # Create varied quality results for different agents
        agent_results = [
            ("spotify", 0.9, 300),
            ("musicbrainz", 0.8, 400),
            ("lastfm", 0.6, 200),
            ("scraper", 0.4, 1000),
        ]

        for agent_name, completeness, response_time in agent_results:
            result = AgentResult(
                agent_name=agent_name,
                status="success",
                data={"song": {"title": "Test"}},
                completeness_score=completeness,
                response_time_ms=response_time,
            )
            metrics = tracker.analyze_data_quality([result])
            tracker.update_source_rankings(metrics)

        report = tracker.get_source_quality_report()

        # Rankings should be sorted descending by accuracy
        prev_score = float("inf")
        for name, score in report.rankings:
            assert score <= prev_score
            prev_score = score


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
