"""Unit tests for user feedback processor."""

import pytest
from datetime import datetime
from unittest.mock import MagicMock
from uuid import uuid4

from src.self_improvement.feedback_processor import (
    FeedbackProcessor,
    IssueReport,
    UserFeedback,
)
from src.self_improvement.quality_tracker import QualityMetrics


class TestUserFeedback:
    """Tests for UserFeedback model."""

    def test_valid_like_feedback(self):
        """Test creating valid like feedback."""
        feedback = UserFeedback(
            user_id=uuid4(),
            node_id=uuid4(),
            feedback_type="like",
            feedback_value=1,
        )

        assert feedback.feedback_type == "like"
        assert feedback.feedback_value == 1

    def test_valid_dislike_feedback(self):
        """Test creating valid dislike feedback."""
        feedback = UserFeedback(
            user_id=uuid4(),
            node_id=uuid4(),
            feedback_type="dislike",
            feedback_value=-1,
        )

        assert feedback.feedback_type == "dislike"
        assert feedback.feedback_value == -1

    def test_valid_correction_feedback(self):
        """Test creating valid correction feedback with comment."""
        feedback = UserFeedback(
            user_id=uuid4(),
            node_id=uuid4(),
            feedback_type="correction",
            comment="Artist formed in 1970, not 1971",
        )

        assert feedback.feedback_type == "correction"
        assert feedback.comment is not None

    def test_valid_report_feedback(self):
        """Test creating valid report feedback with comment."""
        feedback = UserFeedback(
            user_id=uuid4(),
            node_id=uuid4(),
            feedback_type="report",
            comment="This data is completely wrong",
        )

        assert feedback.feedback_type == "report"
        assert feedback.comment is not None

    def test_invalid_feedback_type(self):
        """Test that invalid feedback type raises error."""
        with pytest.raises(ValueError, match="feedback_type must be one of"):
            UserFeedback(
                user_id=uuid4(),
                node_id=uuid4(),
                feedback_type="invalid",
            )

    def test_correction_requires_comment(self):
        """Test that correction feedback requires comment."""
        with pytest.raises(ValueError, match="comment is required"):
            UserFeedback(
                user_id=uuid4(),
                node_id=uuid4(),
                feedback_type="correction",
            )

    def test_report_requires_comment(self):
        """Test that report feedback requires comment."""
        with pytest.raises(ValueError, match="comment is required"):
            UserFeedback(
                user_id=uuid4(),
                node_id=uuid4(),
                feedback_type="report",
            )

    def test_feedback_to_dict(self):
        """Test converting feedback to dictionary."""
        user_id = uuid4()
        node_id = uuid4()
        timestamp = datetime.utcnow()

        feedback = UserFeedback(
            user_id=user_id,
            node_id=node_id,
            feedback_type="like",
            feedback_value=1,
            timestamp=timestamp,
        )

        data = feedback.to_dict()

        assert data["user_id"] == str(user_id)
        assert data["node_id"] == str(node_id)
        assert data["feedback_type"] == "like"
        assert data["feedback_value"] == 1
        assert data["timestamp"] == timestamp.isoformat()


class TestIssueReport:
    """Tests for IssueReport model."""

    def test_create_issue_report(self):
        """Test creating issue report."""
        report = IssueReport(
            node_id=uuid4(),
            user_id=uuid4(),
            description="Data is incorrect",
        )

        assert report.status == "pending"
        assert report.description == "Data is incorrect"

    def test_issue_report_to_dict(self):
        """Test converting issue report to dictionary."""
        node_id = uuid4()
        user_id = uuid4()

        report = IssueReport(
            node_id=node_id,
            user_id=user_id,
            description="Data is incorrect",
        )

        data = report.to_dict()

        assert data["node_id"] == str(node_id)
        assert data["user_id"] == str(user_id)
        assert data["description"] == "Data is incorrect"
        assert data["status"] == "pending"


class TestFeedbackProcessor:
    """Tests for FeedbackProcessor."""

    @pytest.fixture
    def mock_db_client(self):
        """Create mock database client."""
        client = MagicMock()
        return client

    @pytest.fixture
    def mock_quality_tracker(self):
        """Create mock quality tracker."""
        tracker = MagicMock()
        return tracker

    @pytest.fixture
    def mock_enrichment_scheduler(self):
        """Create mock enrichment scheduler."""
        scheduler = MagicMock()
        scheduler.AGENT_CAPABILITIES = {
            "spotify": {"Song": ["spotify_id"], "Artist": ["spotify_id"]},
            "musicbrainz": {"Song": ["musicbrainz_id"], "Artist": ["musicbrainz_id"]},
        }
        return scheduler

    @pytest.fixture
    def mock_cache_client(self):
        """Create mock cache client."""
        client = MagicMock()
        return client

    @pytest.fixture
    def mock_overmind_client(self):
        """Create mock Overmind client."""
        client = MagicMock()
        return client

    @pytest.fixture
    def processor(
        self,
        mock_db_client,
        mock_quality_tracker,
        mock_enrichment_scheduler,
        mock_cache_client,
        mock_overmind_client,
    ):
        """Create feedback processor with mocked dependencies."""
        return FeedbackProcessor(
            db_client=mock_db_client,
            quality_tracker=mock_quality_tracker,
            enrichment_scheduler=mock_enrichment_scheduler,
            cache_client=mock_cache_client,
            overmind_client=mock_overmind_client,
        )

    def test_process_like_feedback(self, processor, mock_db_client, mock_quality_tracker):
        """Test processing like feedback increases source quality scores."""
        node_id = uuid4()
        user_id = uuid4()

        # Mock node data
        node_data = {
            "id": str(node_id),
            "title": "Test Song",
            "duration_ms": 300000,
            "data_sources": ["spotify", "musicbrainz"],
        }
        mock_db_client._get_node_by_id.return_value = node_data

        # Mock quality metrics
        spotify_metrics = QualityMetrics(source_name="spotify")
        musicbrainz_metrics = QualityMetrics(source_name="musicbrainz")

        mock_quality_tracker._load_metrics.side_effect = [
            spotify_metrics,
            musicbrainz_metrics,
        ]

        # Create like feedback
        feedback = UserFeedback(
            user_id=user_id,
            node_id=node_id,
            feedback_type="like",
            feedback_value=1,
        )

        # Process feedback
        processor.process_user_feedback(feedback)

        # Verify metrics were loaded for both sources
        assert mock_quality_tracker._load_metrics.call_count == 2

        # Verify metrics were persisted
        assert mock_quality_tracker.persist_metrics.call_count == 2

    def test_process_dislike_feedback(
        self, processor, mock_db_client, mock_quality_tracker, mock_enrichment_scheduler
    ):
        """Test processing dislike feedback decreases scores and schedules re-enrichment."""
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

        # Mock quality metrics
        spotify_metrics = QualityMetrics(source_name="spotify")
        mock_quality_tracker._load_metrics.return_value = spotify_metrics

        # Create dislike feedback
        feedback = UserFeedback(
            user_id=user_id,
            node_id=node_id,
            feedback_type="dislike",
            feedback_value=-1,
        )

        # Process feedback
        processor.process_user_feedback(feedback)

        # Verify metrics were updated
        assert mock_quality_tracker._load_metrics.called
        assert mock_quality_tracker.persist_metrics.called

    def test_process_correction_feedback(self, processor, mock_db_client, mock_quality_tracker):
        """Test processing correction feedback updates node and penalizes sources."""
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

        # Mock quality metrics
        spotify_metrics = QualityMetrics(source_name="spotify")
        musicbrainz_metrics = QualityMetrics(source_name="musicbrainz")

        mock_quality_tracker._load_metrics.side_effect = [
            spotify_metrics,
            musicbrainz_metrics,
        ]

        # Create correction feedback
        feedback = UserFeedback(
            user_id=user_id,
            node_id=node_id,
            feedback_type="correction",
            comment="Artist formed in 1970, not 1971",
        )

        # Process feedback
        processor.process_user_feedback(feedback)

        # Verify node was updated
        assert mock_db_client.upsert_node.called

        # Verify sources were penalized
        assert mock_quality_tracker._load_metrics.call_count == 2
        assert mock_quality_tracker.persist_metrics.call_count == 2

    def test_process_report_feedback(self, processor, mock_db_client, mock_cache_client):
        """Test processing report feedback creates issue and reduces visibility."""
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
        processor.process_user_feedback(feedback)

        # Verify issue report was created
        assert mock_cache_client.set.called

        # Verify node visibility was reduced
        assert mock_db_client.upsert_node.called

    def test_process_feedback_nonexistent_node(self, processor, mock_db_client):
        """Test processing feedback for nonexistent node raises error."""
        node_id = uuid4()
        user_id = uuid4()

        # Mock node not found
        mock_db_client._get_node_by_id.return_value = None

        # Create feedback
        feedback = UserFeedback(
            user_id=user_id,
            node_id=node_id,
            feedback_type="like",
        )

        # Process feedback should raise error
        with pytest.raises(ValueError, match="does not exist"):
            processor.process_user_feedback(feedback)

    def test_parse_correction_formed_date(self, processor):
        """Test parsing correction for formed date."""
        comment = "Artist formed in 1970, not 1971"
        corrected = processor._parse_correction(comment, "Artist")

        assert corrected is not None
        assert "formed_date" in corrected
        assert "1970" in corrected["formed_date"]

    def test_parse_correction_duration(self, processor):
        """Test parsing correction for duration."""
        comment = "Duration is 354000ms"
        corrected = processor._parse_correction(comment, "Song")

        assert corrected is not None
        assert "duration_ms" in corrected
        assert corrected["duration_ms"] == 354000

    def test_parse_correction_title(self, processor):
        """Test parsing correction for title."""
        comment = "Title should be 'Bohemian Rhapsody'"
        corrected = processor._parse_correction(comment, "Song")

        assert corrected is not None
        assert "title" in corrected
        assert corrected["title"] == "Bohemian Rhapsody"

    def test_parse_correction_unparseable(self, processor):
        """Test parsing unparseable correction returns None."""
        comment = "This is wrong but I don't know how to fix it"
        corrected = processor._parse_correction(comment, "Song")

        assert corrected is None or corrected == {}

    def test_determine_node_type_song(self, processor):
        """Test determining node type for Song."""
        node_data = {"duration_ms": 300000, "title": "Test Song"}
        node_type = processor._determine_node_type(node_data)

        assert node_type == "Song"

    def test_determine_node_type_artist(self, processor):
        """Test determining node type for Artist."""
        node_data = {"genres": ["rock"], "popularity": 80, "name": "Test Artist"}
        node_type = processor._determine_node_type(node_data)

        assert node_type == "Artist"

    def test_determine_node_type_album(self, processor):
        """Test determining node type for Album."""
        node_data = {"album_type": "album", "title": "Test Album"}
        node_type = processor._determine_node_type(node_data)

        assert node_type == "Album"

    def test_determine_node_type_venue(self, processor):
        """Test determining node type for Venue."""
        node_data = {"capacity": 5000, "name": "Test Venue"}
        node_type = processor._determine_node_type(node_data)

        assert node_type == "Venue"

    def test_get_all_agents_for_type(self, processor):
        """Test getting all agents for a node type."""
        agents = processor._get_all_agents_for_type("Song")

        assert "spotify" in agents
        assert "musicbrainz" in agents
        assert len(agents) == 2

    def test_persist_feedback(self, processor, mock_cache_client):
        """Test persisting feedback to cache."""
        feedback = UserFeedback(
            user_id=uuid4(),
            node_id=uuid4(),
            feedback_type="like",
        )

        processor._persist_feedback(feedback)

        # Verify cache was called
        assert mock_cache_client.set.called

        # Verify TTL is 90 days
        call_args = mock_cache_client.set.call_args
        assert call_args[1]["ttl"] == 90 * 24 * 60 * 60

    def test_create_issue_report(self, processor, mock_cache_client):
        """Test creating issue report."""
        node_id = uuid4()
        user_id = uuid4()
        description = "Data is incorrect"

        processor._create_issue_report(node_id, user_id, description)

        # Verify cache was called
        assert mock_cache_client.set.called

        # Verify TTL is 30 days
        call_args = mock_cache_client.set.call_args
        assert call_args[1]["ttl"] == 30 * 24 * 60 * 60

    def test_feedback_logged_to_overmind(self, processor, mock_db_client, mock_overmind_client):
        """Test that feedback is logged to Overmind Lab."""
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

        # Mock quality metrics
        mock_quality_tracker = processor.quality_tracker
        mock_quality_tracker._load_metrics.return_value = QualityMetrics(source_name="spotify")

        # Create feedback
        feedback = UserFeedback(
            user_id=user_id,
            node_id=node_id,
            feedback_type="like",
        )

        # Process feedback
        processor.process_user_feedback(feedback)

        # Verify Overmind logging
        assert mock_overmind_client.log_event.called

        # Verify event details
        call_args = mock_overmind_client.log_event.call_args
        assert call_args[0][0] == "user_feedback_processed"
        assert call_args[0][1]["feedback_type"] == "like"
        assert call_args[0][1]["node_id"] == str(node_id)
