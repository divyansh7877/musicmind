"""Tests for quality tracker."""

import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, MagicMock

from src.self_improvement.quality_tracker import (
    QualityMetrics,
    QualityTracker,
    SourceQualityReport,
)
from src.agents.orchestrator import AgentResult


class TestQualityMetrics:
    """Tests for QualityMetrics class."""

    def test_initialization_with_defaults(self):
        """Test metrics initialization with default values."""
        metrics = QualityMetrics(source_name="test_source")

        assert metrics.source_name == "test_source"
        assert metrics.completeness_avg == 0.0
        assert metrics.accuracy_score == 0.0
        assert metrics.freshness_score == 1.0
        assert metrics.response_time_avg == 0
        assert metrics.success_rate == 0.0
        assert metrics.total_requests == 0
        assert metrics.failed_requests == 0
        assert isinstance(metrics.last_updated, datetime)

    def test_initialization_clamps_values(self):
        """Test that initialization clamps values to valid ranges."""
        metrics = QualityMetrics(
            source_name="test",
            completeness_avg=1.5,  # Should clamp to 1.0
            accuracy_score=-0.5,  # Should clamp to 0.0
            success_rate=2.0,  # Should clamp to 1.0
            response_time_avg=-100,  # Should clamp to 0
            total_requests=10,
            failed_requests=15,  # Should clamp to total_requests
        )

        assert metrics.completeness_avg == 1.0
        assert metrics.accuracy_score == 0.0
        assert metrics.success_rate == 1.0
        assert metrics.response_time_avg == 0
        assert metrics.failed_requests == 10

    def test_to_dict(self):
        """Test conversion to dictionary."""
        metrics = QualityMetrics(
            source_name="spotify",
            completeness_avg=0.85,
            accuracy_score=0.9,
            total_requests=100,
            failed_requests=5,
        )

        data = metrics.to_dict()

        assert data["source_name"] == "spotify"
        assert data["completeness_avg"] == 0.85
        assert data["accuracy_score"] == 0.9
        assert data["total_requests"] == 100
        assert data["failed_requests"] == 5
        assert "last_updated" in data

    def test_from_dict(self):
        """Test creation from dictionary."""
        data = {
            "source_name": "musicbrainz",
            "completeness_avg": 0.75,
            "accuracy_score": 0.8,
            "freshness_score": 0.95,
            "response_time_avg": 1500,
            "success_rate": 0.92,
            "total_requests": 50,
            "failed_requests": 4,
            "last_updated": "2024-01-15T10:30:00",
        }

        metrics = QualityMetrics.from_dict(data)

        assert metrics.source_name == "musicbrainz"
        assert metrics.completeness_avg == 0.75
        assert metrics.accuracy_score == 0.8
        assert metrics.total_requests == 50
        assert metrics.failed_requests == 4


class TestSourceQualityReport:
    """Tests for SourceQualityReport class."""

    def test_rankings_calculation(self):
        """Test that rankings are calculated correctly."""
        metrics = {
            "spotify": QualityMetrics("spotify", accuracy_score=0.9),
            "musicbrainz": QualityMetrics("musicbrainz", accuracy_score=0.95),
            "lastfm": QualityMetrics("lastfm", accuracy_score=0.8),
            "scraper": QualityMetrics("scraper", accuracy_score=0.7),
        }

        report = SourceQualityReport(metrics)

        # Rankings should be sorted by accuracy score descending
        assert report.rankings[0] == ("musicbrainz", 0.95)
        assert report.rankings[1] == ("spotify", 0.9)
        assert report.rankings[2] == ("lastfm", 0.8)
        assert report.rankings[3] == ("scraper", 0.7)

    def test_get_quality(self):
        """Test getting quality score for a source."""
        metrics = {
            "spotify": QualityMetrics("spotify", accuracy_score=0.9),
            "lastfm": QualityMetrics("lastfm", accuracy_score=0.8),
        }

        report = SourceQualityReport(metrics)

        assert report.get_quality("spotify") == 0.9
        assert report.get_quality("lastfm") == 0.8
        assert report.get_quality("unknown") == 0.5  # Default

    def test_get_rank(self):
        """Test getting rank for a source."""
        metrics = {
            "spotify": QualityMetrics("spotify", accuracy_score=0.9),
            "musicbrainz": QualityMetrics("musicbrainz", accuracy_score=0.95),
            "lastfm": QualityMetrics("lastfm", accuracy_score=0.8),
        }

        report = SourceQualityReport(metrics)

        assert report.get_rank("musicbrainz") == 1  # Best
        assert report.get_rank("spotify") == 2
        assert report.get_rank("lastfm") == 3
        assert report.get_rank("unknown") == 4  # Unknown ranked last


class TestQualityTracker:
    """Tests for QualityTracker class."""

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
        return mock

    @pytest.fixture
    def tracker(self, mock_cache_client, mock_overmind_client):
        """Create quality tracker with mocked dependencies."""
        return QualityTracker(
            cache_client=mock_cache_client,
            overmind_client=mock_overmind_client,
            alpha=0.2,
        )

    def test_analyze_data_quality_first_request(self, tracker):
        """Test analyzing quality for first request."""
        result = AgentResult(
            agent_name="spotify",
            status="success",
            data={"song": {"title": "Test Song"}},
            completeness_score=0.8,
            response_time_ms=500,
        )

        quality_metrics = tracker.analyze_data_quality([result])

        assert "spotify" in quality_metrics
        metrics = quality_metrics["spotify"]
        assert metrics.total_requests == 1
        assert metrics.failed_requests == 0
        assert metrics.success_rate == 1.0
        assert metrics.completeness_avg == 0.8
        assert metrics.response_time_avg == 500

    def test_analyze_data_quality_failed_request(self, tracker):
        """Test analyzing quality for failed request."""
        result = AgentResult(
            agent_name="scraper",
            status="failed",
            data={},
            completeness_score=0.0,
            response_time_ms=30000,
            error_message="Timeout",
        )

        quality_metrics = tracker.analyze_data_quality([result])

        assert "scraper" in quality_metrics
        metrics = quality_metrics["scraper"]
        assert metrics.total_requests == 1
        assert metrics.failed_requests == 1
        assert metrics.success_rate == 0.0

    def test_analyze_data_quality_exponential_moving_average(self, tracker, mock_cache_client):
        """Test that EMA is applied correctly."""
        # Set up existing metrics
        existing_metrics = QualityMetrics(
            source_name="lastfm",
            completeness_avg=0.7,
            response_time_avg=1000,
            total_requests=10,
            failed_requests=1,
        )
        mock_cache_client.get.return_value = existing_metrics.to_dict()

        # New result
        result = AgentResult(
            agent_name="lastfm",
            status="success",
            data={"song": {"title": "Test"}},
            completeness_score=0.9,
            response_time_ms=500,
        )

        quality_metrics = tracker.analyze_data_quality([result])
        metrics = quality_metrics["lastfm"]

        # Check EMA was applied (alpha=0.2)
        # new_avg = 0.2 * 0.9 + 0.8 * 0.7 = 0.18 + 0.56 = 0.74
        assert abs(metrics.completeness_avg - 0.74) < 0.01

        # Check counts updated
        assert metrics.total_requests == 11
        assert metrics.failed_requests == 1

    def test_accuracy_score_calculation(self, tracker):
        """Test overall accuracy score calculation."""
        result = AgentResult(
            agent_name="musicbrainz",
            status="success",
            data={"song": {"title": "Test"}},
            completeness_score=0.8,
            response_time_ms=1000,
        )

        quality_metrics = tracker.analyze_data_quality([result])
        metrics = quality_metrics["musicbrainz"]

        # Accuracy = 0.4*completeness + 0.3*success_rate + 0.2*freshness + 0.1*(1-norm_time)
        # = 0.4*0.8 + 0.3*1.0 + 0.2*1.0 + 0.1*(1-0.2)
        # = 0.32 + 0.3 + 0.2 + 0.08 = 0.9
        assert abs(metrics.accuracy_score - 0.9) < 0.01

    def test_scores_clamped_to_valid_range(self, tracker):
        """Test that all scores remain between 0.0 and 1.0."""
        # Create result that might cause out-of-range values
        result = AgentResult(
            agent_name="test",
            status="success",
            data={},
            completeness_score=1.5,  # Invalid
            response_time_ms=-100,  # Invalid
        )

        quality_metrics = tracker.analyze_data_quality([result])
        metrics = quality_metrics["test"]

        # All scores should be clamped
        assert 0.0 <= metrics.completeness_avg <= 1.0
        assert 0.0 <= metrics.accuracy_score <= 1.0
        assert 0.0 <= metrics.freshness_score <= 1.0
        assert 0.0 <= metrics.success_rate <= 1.0

    def test_success_rate_calculation(self, tracker, mock_cache_client):
        """Test success rate calculation."""
        # Set up existing metrics with some failures
        existing_metrics = QualityMetrics(
            source_name="spotify",
            total_requests=10,
            failed_requests=2,
        )
        mock_cache_client.get.return_value = existing_metrics.to_dict()

        # Add successful request
        result = AgentResult(
            agent_name="spotify",
            status="success",
            data={"song": {"title": "Test"}},
            completeness_score=0.8,
            response_time_ms=500,
        )

        quality_metrics = tracker.analyze_data_quality([result])
        metrics = quality_metrics["spotify"]

        # success_rate = (11 - 2) / 11 = 9/11 ≈ 0.818
        assert abs(metrics.success_rate - (9.0 / 11.0)) < 0.01

    def test_persist_metrics(self, tracker, mock_cache_client):
        """Test persisting metrics to cache."""
        metrics = QualityMetrics(
            source_name="spotify",
            completeness_avg=0.85,
            accuracy_score=0.9,
        )

        success = tracker.persist_metrics(metrics)

        assert success
        mock_cache_client.set.assert_called_once()
        call_args = mock_cache_client.set.call_args
        assert call_args[0][0] == "quality_metrics:spotify:v1"
        assert call_args[1]["ttl"] == 30 * 24 * 60 * 60  # 30 days

    def test_log_metrics_to_overmind(self, tracker, mock_overmind_client):
        """Test logging metrics to Overmind Lab."""
        metrics = QualityMetrics(
            source_name="lastfm",
            completeness_avg=0.75,
            accuracy_score=0.8,
            success_rate=0.9,
            response_time_avg=1200,
        )

        tracker.log_metrics_to_overmind(metrics)

        # Should log multiple metrics
        assert mock_overmind_client.log_metric.call_count >= 4

    def test_get_source_quality_report(self, tracker, mock_cache_client):
        """Test getting quality report."""
        # Mock metrics for different sources
        def mock_get(key):
            if "spotify" in key:
                return QualityMetrics("spotify", accuracy_score=0.9).to_dict()
            elif "musicbrainz" in key:
                return QualityMetrics("musicbrainz", accuracy_score=0.95).to_dict()
            return None

        mock_cache_client.get.side_effect = mock_get

        report = tracker.get_source_quality_report()

        assert isinstance(report, SourceQualityReport)
        assert len(report.rankings) == 4  # All known sources

    def test_update_source_rankings(self, tracker, mock_cache_client, mock_overmind_client):
        """Test updating source rankings."""
        quality_metrics = {
            "spotify": QualityMetrics("spotify", accuracy_score=0.9),
            "lastfm": QualityMetrics("lastfm", accuracy_score=0.8),
        }

        tracker.update_source_rankings(quality_metrics)

        # Should persist all metrics
        assert mock_cache_client.set.call_count == 2

        # Should log to Overmind
        assert mock_overmind_client.log_metric.call_count >= 8  # 4 metrics per source
        mock_overmind_client.log_event.assert_called_once()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
