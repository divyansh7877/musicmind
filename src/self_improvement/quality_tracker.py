"""Quality tracker for monitoring and learning from data source performance."""

import logging
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from config.settings import settings
from src.cache.redis_client import RedisClient
from src.tracing.overmind_client import OvermindClient

logger = logging.getLogger(__name__)


class QualityMetrics:
    """Quality metrics for a data source."""

    def __init__(
        self,
        source_name: str,
        completeness_avg: float = 0.0,
        accuracy_score: float = 0.0,
        freshness_score: float = 1.0,
        response_time_avg: int = 0,
        success_rate: float = 0.0,
        total_requests: int = 0,
        failed_requests: int = 0,
        last_updated: Optional[datetime] = None,
    ):
        """Initialize quality metrics.

        Args:
            source_name: Name of the data source
            completeness_avg: Average completeness score (0.0-1.0)
            accuracy_score: Overall accuracy score (0.0-1.0)
            freshness_score: Freshness score (0.0-1.0)
            response_time_avg: Average response time in milliseconds
            success_rate: Success rate (0.0-1.0)
            total_requests: Total number of requests
            failed_requests: Number of failed requests
            last_updated: Last update timestamp
        """
        self.source_name = source_name
        self.completeness_avg = max(0.0, min(1.0, completeness_avg))
        self.accuracy_score = max(0.0, min(1.0, accuracy_score))
        self.freshness_score = max(0.0, min(1.0, freshness_score))
        self.response_time_avg = max(0, response_time_avg)
        self.success_rate = max(0.0, min(1.0, success_rate))
        self.total_requests = max(0, total_requests)
        self.failed_requests = max(0, min(total_requests, failed_requests))
        self.last_updated = last_updated or datetime.utcnow()

    def to_dict(self) -> Dict[str, Any]:
        """Convert metrics to dictionary.

        Returns:
            Dictionary representation of metrics
        """
        return {
            "source_name": self.source_name,
            "completeness_avg": self.completeness_avg,
            "accuracy_score": self.accuracy_score,
            "freshness_score": self.freshness_score,
            "response_time_avg": self.response_time_avg,
            "success_rate": self.success_rate,
            "total_requests": self.total_requests,
            "failed_requests": self.failed_requests,
            "last_updated": self.last_updated.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "QualityMetrics":
        """Create metrics from dictionary.

        Args:
            data: Dictionary representation

        Returns:
            QualityMetrics instance
        """
        last_updated = None
        if data.get("last_updated"):
            try:
                last_updated = datetime.fromisoformat(data["last_updated"])
            except (ValueError, TypeError):
                last_updated = datetime.utcnow()

        return cls(
            source_name=data.get("source_name", "unknown"),
            completeness_avg=data.get("completeness_avg", 0.0),
            accuracy_score=data.get("accuracy_score", 0.0),
            freshness_score=data.get("freshness_score", 1.0),
            response_time_avg=data.get("response_time_avg", 0),
            success_rate=data.get("success_rate", 0.0),
            total_requests=data.get("total_requests", 0),
            failed_requests=data.get("failed_requests", 0),
            last_updated=last_updated,
        )


class SourceQualityReport:
    """Report of quality rankings for all data sources."""

    def __init__(self, metrics: Dict[str, QualityMetrics]):
        """Initialize quality report.

        Args:
            metrics: Dictionary mapping source names to quality metrics
        """
        self.metrics = metrics
        self.rankings = self._calculate_rankings()

    def _calculate_rankings(self) -> List[tuple[str, float]]:
        """Calculate source rankings by accuracy score.

        Returns:
            List of (source_name, accuracy_score) tuples sorted by score descending
        """
        rankings = [
            (source_name, metrics.accuracy_score)
            for source_name, metrics in self.metrics.items()
        ]
        return sorted(rankings, key=lambda x: x[1], reverse=True)

    def get_quality(self, source_name: str) -> float:
        """Get quality score for a source.

        Args:
            source_name: Name of the data source

        Returns:
            Accuracy score between 0.0 and 1.0
        """
        if source_name in self.metrics:
            return self.metrics[source_name].accuracy_score
        return 0.5  # Default for unknown sources

    def get_rank(self, source_name: str) -> int:
        """Get rank of a source (1-indexed).

        Args:
            source_name: Name of the data source

        Returns:
            Rank (1 = best, higher = worse)
        """
        for i, (name, _) in enumerate(self.rankings, start=1):
            if name == source_name:
                return i
        return len(self.rankings) + 1  # Unknown sources ranked last


class QualityTracker:
    """Tracks and analyzes data quality from multiple sources."""

    def __init__(
        self,
        cache_client: Optional[RedisClient] = None,
        overmind_client: Optional[OvermindClient] = None,
        alpha: float = 0.2,
    ):
        """Initialize quality tracker.

        Args:
            cache_client: Redis client for persistence
            overmind_client: Overmind Lab client for logging
            alpha: Exponential moving average smoothing factor (0.0-1.0)
        """
        self.cache_client = cache_client or RedisClient()
        self.overmind_client = overmind_client
        self.alpha = max(0.0, min(1.0, alpha))  # Clamp to valid range

    def analyze_data_quality(self, results: List[Any]) -> Dict[str, QualityMetrics]:
        """Analyze data quality from agent results.

        Args:
            results: List of AgentResult objects

        Returns:
            Dictionary mapping source names to updated quality metrics
        """
        quality_metrics = {}

        for result in results:
            agent_name = result.agent_name

            # Load historical metrics
            metrics = self._load_metrics(agent_name)

            # Update metrics based on result
            metrics = self._update_metrics(metrics, result)

            # Store updated metrics
            quality_metrics[agent_name] = metrics

        return quality_metrics

    def _load_metrics(self, source_name: str) -> QualityMetrics:
        """Load historical metrics for a source.

        Args:
            source_name: Name of the data source

        Returns:
            QualityMetrics instance (new or loaded from cache)
        """
        cache_key = f"quality_metrics:{source_name}:v1"

        try:
            cached_data = self.cache_client.get(cache_key)
            if cached_data:
                logger.debug(f"Loaded metrics for {source_name} from cache")
                return QualityMetrics.from_dict(cached_data)
        except Exception as e:
            logger.warning(f"Failed to load metrics for {source_name}: {e}")

        # Return new metrics if not found
        logger.debug(f"Creating new metrics for {source_name}")
        return QualityMetrics(source_name=source_name)

    def _update_metrics(self, metrics: QualityMetrics, result: Any) -> QualityMetrics:
        """Update metrics with new result using exponential moving average.

        Args:
            metrics: Current quality metrics
            result: AgentResult with new data

        Returns:
            Updated QualityMetrics instance
        """
        # Update request counts
        metrics.total_requests += 1

        if result.status == "failed":
            metrics.failed_requests += 1

        # Calculate success rate
        if metrics.total_requests > 0:
            metrics.success_rate = (
                metrics.total_requests - metrics.failed_requests
            ) / metrics.total_requests
        else:
            metrics.success_rate = 0.0

        # Update completeness average (only for successful/partial results)
        if result.status in ["success", "partial"]:
            if metrics.total_requests == 1:
                # First request, use actual value
                metrics.completeness_avg = result.completeness_score
            else:
                # Exponential moving average
                metrics.completeness_avg = self._update_moving_average(
                    metrics.completeness_avg,
                    result.completeness_score,
                    self.alpha,
                )

        # Update response time average
        if metrics.total_requests == 1:
            metrics.response_time_avg = result.response_time_ms
        else:
            metrics.response_time_avg = int(
                self._update_moving_average(
                    float(metrics.response_time_avg),
                    float(result.response_time_ms),
                    self.alpha,
                )
            )

        # Calculate freshness score (decay over time since last success)
        if result.status in ["success", "partial"]:
            metrics.freshness_score = 1.0  # Fresh data
        else:
            # Decay freshness based on time since last update
            time_since_update = datetime.utcnow() - metrics.last_updated
            metrics.freshness_score = self._calculate_freshness_decay(time_since_update)

        # Calculate overall accuracy score (weighted combination)
        metrics.accuracy_score = self._calculate_accuracy_score(metrics)

        # Update timestamp
        metrics.last_updated = datetime.utcnow()

        # Ensure all scores are in valid range
        metrics.completeness_avg = max(0.0, min(1.0, metrics.completeness_avg))
        metrics.accuracy_score = max(0.0, min(1.0, metrics.accuracy_score))
        metrics.freshness_score = max(0.0, min(1.0, metrics.freshness_score))
        metrics.success_rate = max(0.0, min(1.0, metrics.success_rate))

        return metrics

    def _update_moving_average(
        self, current_avg: float, new_value: float, alpha: float
    ) -> float:
        """Update exponential moving average.

        Args:
            current_avg: Current average value
            new_value: New value to incorporate
            alpha: Smoothing factor (0.0-1.0)

        Returns:
            Updated average
        """
        # EMA formula: new_avg = alpha * new_value + (1 - alpha) * current_avg
        return alpha * new_value + (1.0 - alpha) * current_avg

    def _calculate_freshness_decay(self, time_delta: timedelta) -> float:
        """Calculate freshness score with exponential decay.

        Args:
            time_delta: Time since last successful update

        Returns:
            Freshness score between 0.0 and 1.0
        """
        # Decay with half-life of 1 hour
        hours = time_delta.total_seconds() / 3600.0
        half_life = 1.0
        decay_factor = 0.5 ** (hours / half_life)
        return max(0.0, min(1.0, decay_factor))

    def _calculate_accuracy_score(self, metrics: QualityMetrics) -> float:
        """Calculate overall accuracy score from component metrics.

        Args:
            metrics: Quality metrics

        Returns:
            Accuracy score between 0.0 and 1.0
        """
        # Weighted combination of metrics
        # Completeness: 40%, Success rate: 30%, Freshness: 20%, Response time: 10%
        normalized_response_time = self._normalize_response_time(metrics.response_time_avg)

        accuracy = (
            metrics.completeness_avg * 0.4
            + metrics.success_rate * 0.3
            + metrics.freshness_score * 0.2
            + (1.0 - normalized_response_time) * 0.1
        )

        return max(0.0, min(1.0, accuracy))

    def _normalize_response_time(self, response_time_ms: int) -> float:
        """Normalize response time to 0.0-1.0 range.

        Args:
            response_time_ms: Response time in milliseconds

        Returns:
            Normalized score (0.0 = fast, 1.0 = slow)
        """
        # Consider 5000ms as maximum acceptable response time
        max_acceptable_ms = 5000.0
        normalized = min(response_time_ms / max_acceptable_ms, 1.0)
        return normalized

    def persist_metrics(self, metrics: QualityMetrics) -> bool:
        """Persist quality metrics to cache.

        Args:
            metrics: Quality metrics to persist

        Returns:
            True if successful, False otherwise
        """
        cache_key = f"quality_metrics:{metrics.source_name}:v1"

        try:
            # Store with long TTL (30 days)
            ttl = 30 * 24 * 60 * 60
            success = self.cache_client.set(cache_key, metrics.to_dict(), ttl=ttl)

            if success:
                logger.debug(f"Persisted metrics for {metrics.source_name}")
            else:
                logger.warning(f"Failed to persist metrics for {metrics.source_name}")

            return success

        except Exception as e:
            logger.error(f"Error persisting metrics for {metrics.source_name}: {e}")
            return False

    def log_metrics_to_overmind(self, metrics: QualityMetrics) -> None:
        """Log quality metrics to Overmind Lab.

        Args:
            metrics: Quality metrics to log
        """
        if not self.overmind_client:
            return

        source_name = metrics.source_name

        # Log individual metrics
        self.overmind_client.log_metric(
            f"{source_name}.completeness",
            metrics.completeness_avg,
            tags={"source": source_name},
        )

        self.overmind_client.log_metric(
            f"{source_name}.success_rate",
            metrics.success_rate,
            tags={"source": source_name},
        )

        self.overmind_client.log_metric(
            f"{source_name}.response_time",
            float(metrics.response_time_avg),
            tags={"source": source_name},
        )

        self.overmind_client.log_metric(
            f"{source_name}.accuracy_score",
            metrics.accuracy_score,
            tags={"source": source_name},
        )

        self.overmind_client.log_metric(
            f"{source_name}.freshness_score",
            metrics.freshness_score,
            tags={"source": source_name},
        )

        logger.debug(f"Logged metrics for {source_name} to Overmind Lab")

    def get_source_quality_report(self) -> SourceQualityReport:
        """Get quality report with rankings for all sources.

        Returns:
            SourceQualityReport with current metrics and rankings
        """
        # Load metrics for all known sources
        known_sources = ["spotify", "musicbrainz", "lastfm", "scraper"]
        metrics_dict = {}

        for source_name in known_sources:
            metrics = self._load_metrics(source_name)
            metrics_dict[source_name] = metrics

        report = SourceQualityReport(metrics_dict)

        logger.info(
            f"Quality rankings: "
            + ", ".join(f"{name}={score:.2f}" for name, score in report.rankings)
        )

        return report

    def update_source_rankings(self, quality_metrics: Dict[str, QualityMetrics]) -> None:
        """Update source rankings after analyzing results.

        Args:
            quality_metrics: Dictionary of updated quality metrics
        """
        # Persist all updated metrics
        for source_name, metrics in quality_metrics.items():
            self.persist_metrics(metrics)

            # Log to Overmind Lab
            self.log_metrics_to_overmind(metrics)

        # Log ranking update event
        if self.overmind_client:
            rankings = sorted(
                [(name, m.accuracy_score) for name, m in quality_metrics.items()],
                key=lambda x: x[1],
                reverse=True,
            )

            self.overmind_client.log_event(
                "source_rankings_updated",
                {
                    "rankings": [
                        {"source": name, "score": score} for name, score in rankings
                    ],
                    "timestamp": datetime.utcnow().isoformat(),
                },
            )

        logger.info("Source rankings updated")
