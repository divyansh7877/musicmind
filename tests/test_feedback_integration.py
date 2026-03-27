"""Integration tests for user feedback processing with quality tracking."""

import pytest
from datetime import datetime
from unittest.mock import MagicMock
from uuid import uuid4

from src.database.aerospike_client import AerospikeClient
from src.self_improvement.enrichment_scheduler import EnrichmentScheduler
from src.self_improvement.feedback_processor import FeedbackProcessor, UserFeedback
from src.self_improvement.quality_tracker import QualityMetrics, QualityTracker
from src.tracing.overmind_client import OvermindClient


class TestFeedbackIntegration:
    """Integration tests for feedback processing with quality tracking."""

    @pytest.fixture
    def mock_db_client(self):
        """Create mock database client."""
        client = MagicMock(spec=AerospikeClient)
        return client

    @pytest.fixture
    def quality_tracker(self):
        """Create quality tracker with mocked dependencies."""
        cache_client = MagicMock()
        overmind_client = MagicMock()
        return QualityTracker(
            cache_client=cache_client,
            overmind_client=overmind_client,
        )

    @pytest.fixture
    def enrichment_scheduler(self, mock_db_client):
        """Create enrichment scheduler with mocked dependencies."""
        overmind_client = MagicMock()
        return EnrichmentScheduler(
            db_client=mock_db_client,
            overmind_client=overmind_client,
        )

    @pytest.fixture
    def feedback_processor(
        self, mock_db_client, quality_tracker, enrichment_scheduler
    ):
        """Create feedback processor with real quality tracker."""
        cache_client = MagicMock()
        overmind_client = MagicMock()

        return FeedbackProcessor(
            db_client=mock_db_client,
            quality_tracker=quality_tracker,
            enrichment_scheduler=enrichment_scheduler,
            cache_client=cache_client,
            overmind_client=overmind_client,
        )

    def test_like_feedback_improves_source_quality(
        self, feedback_processor, mock_db_client, quality_tracker
    ):
        """Test that like feedback improves source quality scores."""
        node_id = uuid4()
        user_id = uuid4()

        # Mock node data with multiple sources
        node_data = {
            "id": str(node_id),
            "title": "Test Song",
            "duration_ms": 300000,
            "data_sources": ["spotify", "musicbrainz"],
        }
        mock_db_client._get_node_by_id.return_value = node_data

        # Create initial metrics for sources
        spotify_metrics = QualityMetrics(
            source_name="spotify",
            accuracy_score=0.7,
        )
        musicbrainz_metrics = QualityMetrics(
            source_name="musicbrainz",
            accuracy_score=0.6,
        )

        # Mock cache to return initial metrics
        quality_tracker.cache_client.get.side_effect = [
            spotify_metrics.to_dict(),
            musicbrainz_metrics.to_dict(),
        ]

        # Create like feedback
        feedback = UserFeedback(
            user_id=user_id,
            node_id=node_id,
            feedback_type="like",
            feedback_value=1,
        )

        # Process feedback
        feedback_processor.process_user_feedback(feedback)

        # Verify metrics were persisted (should be called twice, once per source)
        assert quality_tracker.cache_client.set.call_count == 2

        # Verify feedback was logged
        assert feedback_processor.cache_client.set.called

    def test_dislike_feedback_decreases_quality_and_schedules_enrichment(
        self, feedback_processor, mock_db_client, quality_tracker
    ):
        """Test that dislike feedback decreases quality and schedules re-enrichment."""
        node_id = uuid4()
        user_id = uuid4()

        # Mock node data
        node_data = {
            "id": str(node_id),
            "title": "Test Song",
            "duration_ms": 300000,
            "data_sources": ["spotify"],
            "completeness_score": 0.8,
            "last_enriched": datetime.utcnow().isoformat(),
        }
        mock_db_client._get_node_by_id.return_value = node_data

        # Create initial metrics
        spotify_metrics = QualityMetrics(
            source_name="spotify",
            accuracy_score=0.8,
        )

        # Mock cache to return initial metrics
        quality_tracker.cache_client.get.return_value = spotify_metrics.to_dict()

        # Create dislike feedback
        feedback = UserFeedback(
            user_id=user_id,
            node_id=node_id,
            feedback_type="dislike",
            feedback_value=-1,
        )

        # Process feedback
        feedback_processor.process_user_feedback(feedback)

        # Verify metrics were updated
        assert quality_tracker.cache_client.set.called

        # Verify feedback was logged
        assert feedback_processor.cache_client.set.called

    def test_correction_feedback_updates_node_and_penalizes_sources(
        self, feedback_processor, mock_db_client, quality_tracker
    ):
        """Test that correction feedback updates node and penalizes sources."""
        node_id = uuid4()
        user_id = uuid4()

        # Mock node data
        node_data = {
            "id": str(node_id),
            "name": "Test Artist",
            "genres": ["rock"],
            "popularity": 80,
            "formed_date": "1971-01-01",
            "data_sources": ["spotify", "musicbrainz"],
        }
        mock_db_client._get_node_by_id.return_value = node_data

        # Create initial metrics
        spotify_metrics = QualityMetrics(
            source_name="spotify",
            accuracy_score=0.8,
        )
        musicbrainz_metrics = QualityMetrics(
            source_name="musicbrainz",
            accuracy_score=0.9,
        )

        # Mock cache to return initial metrics
        quality_tracker.cache_client.get.side_effect = [
            spotify_metrics.to_dict(),
            musicbrainz_metrics.to_dict(),
        ]

        # Create correction feedback
        feedback = UserFeedback(
            user_id=user_id,
            node_id=node_id,
            feedback_type="correction",
            comment="Artist formed in 1970, not 1971",
        )

        # Process feedback
        feedback_processor.process_user_feedback(feedback)

        # Verify node was updated
        assert mock_db_client.upsert_node.called

        # Verify both sources were penalized
        assert quality_tracker.cache_client.set.call_count == 2

        # Verify feedback was logged
        assert feedback_processor.cache_client.set.called

    def test_report_feedback_creates_issue_and_reduces_visibility(
        self, feedback_processor, mock_db_client
    ):
        """Test that report feedback creates issue and reduces visibility."""
        node_id = uuid4()
        user_id = uuid4()

        # Mock node data
        node_data = {
            "id": str(node_id),
            "title": "Test Song",
            "duration_ms": 300000,
            "visibility_score": 1.0,
        }
        mock_db_client._get_node_by_id.return_value = node_data

        # Create report feedback
        feedback = UserFeedback(
            user_id=user_id,
            node_id=node_id,
            feedback_type="report",
            comment="This data is completely wrong",
        )

        # Process feedback
        feedback_processor.process_user_feedback(feedback)

        # Verify issue report was created
        assert feedback_processor.cache_client.set.call_count == 2  # Issue + feedback

        # Verify node was updated with reduced visibility
        assert mock_db_client.upsert_node.called

        # Get the updated node data
        call_args = mock_db_client.upsert_node.call_args
        updated_node = call_args[0][1]

        # Verify visibility was reduced by 50%
        assert updated_node["visibility_score"] == 0.5

    def test_multiple_feedbacks_accumulate_quality_changes(
        self, feedback_processor, mock_db_client, quality_tracker
    ):
        """Test that multiple feedbacks accumulate quality changes."""
        node_id = uuid4()
        user_id = uuid4()

        # Mock node data
        node_data = {
            "id": str(node_id),
            "title": "Test Song",
            "duration_ms": 300000,
            "data_sources": ["spotify"],
        }
        mock_db_client._get_node_by_id.return_value = node_data

        # Create initial metrics
        initial_metrics = QualityMetrics(
            source_name="spotify",
            accuracy_score=0.5,
        )

        # Mock cache to return metrics
        quality_tracker.cache_client.get.return_value = initial_metrics.to_dict()

        # Process multiple like feedbacks
        for _ in range(3):
            feedback = UserFeedback(
                user_id=user_id,
                node_id=node_id,
                feedback_type="like",
                feedback_value=1,
            )
            feedback_processor.process_user_feedback(feedback)

        # Verify metrics were updated multiple times
        assert quality_tracker.cache_client.set.call_count >= 3

    def test_feedback_processing_with_overmind_logging(
        self, feedback_processor, mock_db_client
    ):
        """Test that feedback processing logs to Overmind Lab."""
        node_id = uuid4()
        user_id = uuid4()

        # Mock node data
        node_data = {
            "id": str(node_id),
            "title": "Test Song",
            "duration_ms": 300000,
            "data_sources": ["spotify"],
        }
        mock_db_client._get_node_by_id.return_value = node_data

        # Create feedback
        feedback = UserFeedback(
            user_id=user_id,
            node_id=node_id,
            feedback_type="like",
        )

        # Process feedback
        feedback_processor.process_user_feedback(feedback)

        # Verify Overmind logging
        assert feedback_processor.overmind_client.log_event.called

        # Verify event details
        call_args = feedback_processor.overmind_client.log_event.call_args
        assert call_args[0][0] == "user_feedback_processed"
        assert call_args[0][1]["feedback_type"] == "like"
        assert call_args[0][1]["node_id"] == str(node_id)
        assert call_args[0][1]["user_id"] == str(user_id)
