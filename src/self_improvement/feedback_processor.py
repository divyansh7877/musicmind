"""User feedback processor for self-improvement and data quality learning."""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from src.cache.redis_client import RedisClient
from src.database.aerospike_client import AerospikeClient
from src.self_improvement.enrichment_scheduler import (
    EnrichmentPriority,
    EnrichmentScheduler,
    EnrichmentTask,
)
from src.self_improvement.quality_tracker import QualityTracker
from src.tracing.overmind_client import OvermindClient

logger = logging.getLogger(__name__)


class UserFeedback(BaseModel):
    """User feedback on data quality."""

    user_id: UUID = Field(..., description="User identifier")
    node_id: UUID = Field(..., description="Graph node identifier")
    feedback_type: str = Field(..., description="Type of feedback")
    feedback_value: int = Field(default=0, ge=-1, le=1, description="Feedback value (-1, 0, or 1)")
    comment: Optional[str] = Field(None, description="Optional comment or correction")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Feedback timestamp")

    @field_validator("feedback_type")
    @classmethod
    def validate_feedback_type(cls, v: str) -> str:
        """Ensure feedback_type is one of the valid values."""
        valid_types = {"like", "dislike", "correction", "report"}
        if v.lower() not in valid_types:
            raise ValueError(f"feedback_type must be one of: {', '.join(valid_types)}")
        return v.lower()

    def model_post_init(self, __context) -> None:
        """Validate comment is present for correction and report types."""
        if self.feedback_type in ["correction", "report"]:
            if not self.comment or not self.comment.strip():
                raise ValueError(f"comment is required for {self.feedback_type} feedback")

    def to_dict(self) -> Dict[str, Any]:
        """Convert feedback to dictionary.

        Returns:
            Dictionary representation
        """
        return {
            "user_id": str(self.user_id),
            "node_id": str(self.node_id),
            "feedback_type": self.feedback_type,
            "feedback_value": self.feedback_value,
            "comment": self.comment,
            "timestamp": self.timestamp.isoformat(),
        }


class IssueReport(BaseModel):
    """Issue report for manual review."""

    node_id: UUID = Field(..., description="Graph node identifier")
    user_id: UUID = Field(..., description="User who reported the issue")
    description: str = Field(..., description="Issue description")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Report timestamp")
    status: str = Field(default="pending", description="Report status")

    def to_dict(self) -> Dict[str, Any]:
        """Convert report to dictionary.

        Returns:
            Dictionary representation
        """
        return {
            "node_id": str(self.node_id),
            "user_id": str(self.user_id),
            "description": self.description,
            "timestamp": self.timestamp.isoformat(),
            "status": self.status,
        }


class FeedbackProcessor:
    """Processes user feedback for self-improvement and data quality learning."""

    def __init__(
        self,
        db_client: AerospikeClient,
        quality_tracker: QualityTracker,
        enrichment_scheduler: EnrichmentScheduler,
        cache_client: Optional[RedisClient] = None,
        overmind_client: Optional[OvermindClient] = None,
    ):
        """Initialize feedback processor.

        Args:
            db_client: Aerospike database client
            quality_tracker: Quality tracker for updating source metrics
            enrichment_scheduler: Enrichment scheduler for re-enrichment tasks
            cache_client: Redis client for persistence
            overmind_client: Overmind Lab client for logging
        """
        self.db_client = db_client
        self.quality_tracker = quality_tracker
        self.enrichment_scheduler = enrichment_scheduler
        self.cache_client = cache_client or RedisClient()
        self.overmind_client = overmind_client

    def process_user_feedback(self, feedback: UserFeedback) -> None:
        """Process user feedback and update system accordingly.

        Args:
            feedback: User feedback object

        Raises:
            ValueError: If node doesn't exist or feedback is invalid
        """
        # Retrieve the graph node
        node_data = self.db_client._get_node_by_id(feedback.node_id)

        if not node_data:
            raise ValueError(f"Node {feedback.node_id} does not exist")

        # Determine node type
        node_type = self._determine_node_type(node_data)
        if not node_type:
            raise ValueError(f"Could not determine type for node {feedback.node_id}")

        logger.info(
            f"Processing {feedback.feedback_type} feedback for {node_type} {feedback.node_id}"
        )

        # Process based on feedback type
        if feedback.feedback_type == "like":
            self._process_like_feedback(feedback, node_data, node_type)
        elif feedback.feedback_type == "dislike":
            self._process_dislike_feedback(feedback, node_data, node_type)
        elif feedback.feedback_type == "correction":
            self._process_correction_feedback(feedback, node_data, node_type)
        elif feedback.feedback_type == "report":
            self._process_report_feedback(feedback, node_data, node_type)

        # Log feedback event to Overmind Lab
        if self.overmind_client:
            self.overmind_client.log_event(
                "user_feedback_processed",
                {
                    "feedback_type": feedback.feedback_type,
                    "node_id": str(feedback.node_id),
                    "node_type": node_type,
                    "user_id": str(feedback.user_id),
                    "timestamp": feedback.timestamp.isoformat(),
                },
            )

        # Persist feedback for historical analysis
        self._persist_feedback(feedback)

        logger.info(f"Successfully processed {feedback.feedback_type} feedback")

    def _process_like_feedback(
        self, feedback: UserFeedback, node_data: Dict[str, Any], node_type: str
    ) -> None:
        """Process like feedback by increasing source quality scores.

        Args:
            feedback: User feedback object
            node_data: Node data dictionary
            node_type: Type of node
        """
        # Get data sources that contributed to this node
        data_sources = node_data.get("data_sources", [])

        if not data_sources:
            logger.warning(f"Node {feedback.node_id} has no data sources")
            return

        # Increase user_satisfaction_score for all contributing sources
        for source_name in data_sources:
            if source_name == "user_correction":
                continue  # Skip user corrections

            metrics = self.quality_tracker._load_metrics(source_name)

            # Update user satisfaction score (positive signal = 1.0)
            if not hasattr(metrics, "user_satisfaction_score"):
                metrics.user_satisfaction_score = 0.5  # Initialize if not present

            if not hasattr(metrics, "feedback_count"):
                metrics.feedback_count = 0

            # Use exponential moving average
            alpha = 0.2
            metrics.user_satisfaction_score = (
                alpha * 1.0 + (1.0 - alpha) * metrics.user_satisfaction_score
            )
            metrics.feedback_count += 1

            # Recalculate accuracy score
            metrics.accuracy_score = self.quality_tracker._calculate_accuracy_score(metrics)

            # Persist updated metrics
            self.quality_tracker.persist_metrics(metrics)

            # Log to Overmind Lab
            if self.overmind_client:
                self.overmind_client.log_metric(
                    f"{source_name}.user_satisfaction",
                    metrics.user_satisfaction_score,
                    tags={"source": source_name, "feedback": "like"},
                )

            logger.debug(
                f"Increased satisfaction score for {source_name} to "
                f"{metrics.user_satisfaction_score:.2f}"
            )

    def _process_dislike_feedback(
        self, feedback: UserFeedback, node_data: Dict[str, Any], node_type: str
    ) -> None:
        """Process dislike feedback by decreasing source quality scores and scheduling re-enrichment.

        Args:
            feedback: User feedback object
            node_data: Node data dictionary
            node_type: Type of node
        """
        # Get data sources that contributed to this node
        data_sources = node_data.get("data_sources", [])

        if not data_sources:
            logger.warning(f"Node {feedback.node_id} has no data sources")
            return

        # Decrease user_satisfaction_score for all contributing sources
        for source_name in data_sources:
            if source_name == "user_correction":
                continue  # Skip user corrections

            metrics = self.quality_tracker._load_metrics(source_name)

            # Update user satisfaction score (negative signal = 0.0)
            if not hasattr(metrics, "user_satisfaction_score"):
                metrics.user_satisfaction_score = 0.5  # Initialize if not present

            if not hasattr(metrics, "feedback_count"):
                metrics.feedback_count = 0

            # Use exponential moving average
            alpha = 0.2
            metrics.user_satisfaction_score = (
                alpha * 0.0 + (1.0 - alpha) * metrics.user_satisfaction_score
            )
            metrics.feedback_count += 1

            # Recalculate accuracy score
            metrics.accuracy_score = self.quality_tracker._calculate_accuracy_score(metrics)

            # Persist updated metrics
            self.quality_tracker.persist_metrics(metrics)

            # Log to Overmind Lab
            if self.overmind_client:
                self.overmind_client.log_metric(
                    f"{source_name}.user_satisfaction",
                    metrics.user_satisfaction_score,
                    tags={"source": source_name, "feedback": "dislike"},
                )

            logger.debug(
                f"Decreased satisfaction score for {source_name} to "
                f"{metrics.user_satisfaction_score:.2f}"
            )

        # Schedule re-enrichment for this node
        completeness_score = node_data.get("completeness_score", 0.0)
        last_enriched_str = node_data.get("last_enriched")

        try:
            last_enriched = datetime.fromisoformat(last_enriched_str)
        except (ValueError, TypeError):
            last_enriched = datetime.utcnow()

        # Determine target agents for re-enrichment
        target_agents = self._get_all_agents_for_type(node_type)

        # Create medium-priority enrichment task
        task = EnrichmentTask(
            node_id=feedback.node_id,
            node_type=node_type,
            priority=EnrichmentPriority.MEDIUM,
            missing_fields=[],  # Re-enrich all fields
            target_agents=target_agents,
            completeness_score=completeness_score,
            last_enriched=last_enriched,
        )

        # Schedule the task (in production, use a task queue like Celery)
        # For now, just log the intent
        logger.info(f"Would schedule enrichment task: {task.to_dict()}")

        logger.info(f"Scheduled re-enrichment for node {feedback.node_id} due to dislike")

    def _process_correction_feedback(
        self, feedback: UserFeedback, node_data: Dict[str, Any], node_type: str
    ) -> None:
        """Process correction feedback by updating node and penalizing incorrect sources.

        Args:
            feedback: User feedback object
            node_data: Node data dictionary
            node_type: Type of node
        """
        if not feedback.comment:
            logger.warning("Correction feedback missing comment")
            return

        # Parse correction from comment
        corrected_data = self._parse_correction(feedback.comment, node_type)

        if not corrected_data:
            logger.warning(f"Could not parse correction: {feedback.comment}")
            # Flag for manual review
            self._create_issue_report(
                feedback.node_id,
                feedback.user_id,
                f"Correction needs clarification: {feedback.comment}",
            )
            return

        # Apply correction to node
        for field_name, field_value in corrected_data.items():
            node_data[field_name] = field_value
            logger.debug(f"Updated {field_name} to {field_value}")

        # Add user_correction as data source
        data_sources = node_data.get("data_sources", [])
        if "user_correction" not in data_sources:
            data_sources.append("user_correction")
            node_data["data_sources"] = data_sources

        # Update last_enriched timestamp
        node_data["last_enriched"] = datetime.utcnow().isoformat()

        # Update node in database
        try:
            self.db_client.upsert_node(node_type, node_data)
            logger.info(f"Applied user correction to node {feedback.node_id}")
        except Exception as e:
            logger.error(f"Failed to update node with correction: {e}")
            raise

        # Penalize sources that provided incorrect data
        original_sources = [s for s in data_sources if s != "user_correction"]

        for source_name in original_sources:
            metrics = self.quality_tracker._load_metrics(source_name)

            # Increment correction count
            if not hasattr(metrics, "correction_count"):
                metrics.correction_count = 0

            metrics.correction_count += 1

            # Decrease accuracy score
            metrics.accuracy_score = max(
                0.0, metrics.accuracy_score - 0.1
            )  # Penalty for incorrect data

            # Persist updated metrics
            self.quality_tracker.persist_metrics(metrics)

            # Log to Overmind Lab
            if self.overmind_client:
                self.overmind_client.log_metric(
                    f"{source_name}.correction_count",
                    float(metrics.correction_count),
                    tags={"source": source_name},
                )

            logger.debug(
                f"Penalized {source_name} for incorrect data "
                f"(corrections: {metrics.correction_count})"
            )

    def _process_report_feedback(
        self, feedback: UserFeedback, node_data: Dict[str, Any], node_type: str
    ) -> None:
        """Process report feedback by creating issue report and reducing visibility.

        Args:
            feedback: User feedback object
            node_data: Node data dictionary
            node_type: Type of node
        """
        if not feedback.comment:
            logger.warning("Report feedback missing comment")
            return

        # Create issue report for manual review
        self._create_issue_report(feedback.node_id, feedback.user_id, feedback.comment)

        # Reduce node visibility by 50%
        visibility_score = node_data.get("visibility_score", 1.0)
        node_data["visibility_score"] = visibility_score * 0.5

        # Update node in database
        try:
            self.db_client.upsert_node(node_type, node_data)
            logger.info(
                f"Reduced visibility for node {feedback.node_id} to "
                f"{node_data['visibility_score']:.2f}"
            )
        except Exception as e:
            logger.error(f"Failed to update node visibility: {e}")
            raise

    def _parse_correction(self, comment: str, node_type: str) -> Optional[Dict[str, Any]]:
        """Parse correction from user comment.

        Args:
            comment: User correction comment
            node_type: Type of node being corrected

        Returns:
            Dictionary of corrected fields or None if cannot parse
        """
        # Simple parsing logic - in production, use NLP or structured forms
        corrected_data = {}

        # Look for common patterns
        comment_lower = comment.lower()

        # Example: "Artist formed in 1970, not 1971"
        if "formed" in comment_lower and node_type == "Artist":
            # Extract year
            import re

            years = re.findall(r"\b(19\d{2}|20\d{2})\b", comment)
            if years:
                # Use first year found as correction
                corrected_data["formed_date"] = f"{years[0]}-01-01"

        # Example: "Duration is 354000ms"
        if "duration" in comment_lower and node_type == "Song":
            import re

            durations = re.findall(r"(\d+)\s*ms", comment)
            if durations:
                corrected_data["duration_ms"] = int(durations[0])

        # Example: "Title should be 'Bohemian Rhapsody'"
        if "title" in comment_lower:
            import re

            titles = re.findall(r"['\"]([^'\"]+)['\"]", comment)
            if titles:
                corrected_data["title"] = titles[0]

        return corrected_data if corrected_data else None

    def _create_issue_report(self, node_id: UUID, user_id: UUID, description: str) -> None:
        """Create an issue report for manual review.

        Args:
            node_id: Graph node identifier
            user_id: User who reported the issue
            description: Issue description
        """
        report = IssueReport(
            node_id=node_id,
            user_id=user_id,
            description=description,
        )

        # Store report in cache
        cache_key = f"issue_report:{node_id}:{report.timestamp.isoformat()}"

        try:
            # Store with 30-day TTL
            ttl = 30 * 24 * 60 * 60
            self.cache_client.set(cache_key, report.to_dict(), ttl=ttl)

            logger.info(f"Created issue report for node {node_id}")

            # Log to Overmind Lab
            if self.overmind_client:
                self.overmind_client.log_event(
                    "issue_report_created",
                    {
                        "node_id": str(node_id),
                        "user_id": str(user_id),
                        "description": description,
                        "timestamp": report.timestamp.isoformat(),
                    },
                )

        except Exception as e:
            logger.error(f"Failed to create issue report: {e}")

    def _persist_feedback(self, feedback: UserFeedback) -> None:
        """Persist feedback for historical analysis.

        Args:
            feedback: User feedback object
        """
        cache_key = f"feedback:{feedback.node_id}:{feedback.timestamp.isoformat()}"

        try:
            # Store with 90-day TTL
            ttl = 90 * 24 * 60 * 60
            self.cache_client.set(cache_key, feedback.to_dict(), ttl=ttl)

            logger.debug(f"Persisted feedback for node {feedback.node_id}")

        except Exception as e:
            logger.error(f"Failed to persist feedback: {e}")

    def _determine_node_type(self, node_data: Dict[str, Any]) -> Optional[str]:
        """Determine node type from node data.

        Args:
            node_data: Node data dictionary

        Returns:
            Node type string or None if cannot determine
        """
        # Check for type-specific fields
        if "duration_ms" in node_data or "isrc" in node_data:
            return "Song"
        elif "genres" in node_data and "popularity" in node_data:
            return "Artist"
        elif "album_type" in node_data:
            return "Album"
        elif "parent_label_id" in node_data or (
            "founded_date" in node_data and "name" in node_data
        ):
            return "RecordLabel"
        elif "category" in node_data and "name" in node_data:
            return "Instrument"
        elif "capacity" in node_data or "latitude" in node_data:
            return "Venue"
        elif "concert_date" in node_data or "setlist" in node_data:
            return "Concert"

        return None

    def _get_all_agents_for_type(self, node_type: str) -> List[str]:
        """Get all agents that can provide data for a node type.

        Args:
            node_type: Type of node

        Returns:
            List of agent names
        """
        agents = set()

        for agent_name, capabilities in self.enrichment_scheduler.AGENT_CAPABILITIES.items():
            if node_type in capabilities:
                agents.add(agent_name)

        return sorted(list(agents))
