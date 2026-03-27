"""Enrichment scheduler for proactive node enrichment and self-improvement."""

import asyncio
import logging
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Set
from uuid import UUID

from pydantic import BaseModel, Field

from src.database.aerospike_client import AerospikeClient
from src.tracing.overmind_client import OvermindClient

logger = logging.getLogger(__name__)


class EnrichmentPriority(str, Enum):
    """Priority levels for enrichment tasks."""

    HIGH = "high"  # Completeness < 0.4
    MEDIUM = "medium"  # Completeness 0.4-0.7
    LOW = "low"  # Stale nodes (>30 days)


class EnrichmentTask(BaseModel):
    """Task for proactive node enrichment."""

    node_id: UUID = Field(..., description="Node UUID to enrich")
    node_type: str = Field(..., description="Type of node (Song, Artist, etc.)")
    priority: EnrichmentPriority = Field(..., description="Task priority")
    missing_fields: List[str] = Field(
        default_factory=list, description="List of missing field names"
    )
    target_agents: List[str] = Field(
        default_factory=list, description="Agents that can provide missing fields"
    )
    completeness_score: float = Field(..., ge=0.0, le=1.0, description="Current completeness")
    last_enriched: datetime = Field(..., description="Last enrichment timestamp")
    created_at: datetime = Field(
        default_factory=datetime.utcnow, description="Task creation timestamp"
    )

    def to_dict(self) -> Dict[str, Any]:
        """Convert task to dictionary.

        Returns:
            Dictionary representation
        """
        return {
            "node_id": str(self.node_id),
            "node_type": self.node_type,
            "priority": self.priority.value,
            "missing_fields": self.missing_fields,
            "target_agents": self.target_agents,
            "completeness_score": self.completeness_score,
            "last_enriched": self.last_enriched.isoformat(),
            "created_at": self.created_at.isoformat(),
        }


class EnrichmentScheduler:
    """Scheduler for proactive node enrichment and self-improvement."""

    # Agent capabilities mapping: which agents can provide which fields
    AGENT_CAPABILITIES = {
        "spotify": {
            "Song": [
                "spotify_id",
                "duration_ms",
                "audio_features",
                "play_count",
                "release_date",
            ],
            "Artist": [
                "spotify_id",
                "genres",
                "popularity",
                "follower_count",
                "image_urls",
            ],
            "Album": [
                "spotify_id",
                "release_date",
                "total_tracks",
                "cover_art_url",
                "album_type",
            ],
        },
        "musicbrainz": {
            "Song": ["musicbrainz_id", "isrc", "duration_ms"],
            "Artist": [
                "musicbrainz_id",
                "country",
                "formed_date",
                "disbanded_date",
                "biography",
            ],
            "Album": [
                "musicbrainz_id",
                "release_date",
                "label",
                "catalog_number",
                "total_tracks",
            ],
            "RecordLabel": [
                "musicbrainz_id",
                "country",
                "founded_date",
                "website_url",
                "parent_label_id",
            ],
            "Instrument": ["musicbrainz_id", "description", "category"],
        },
        "lastfm": {
            "Song": [
                "lastfm_url",
                "tags",
                "play_count",
                "listener_count",
            ],
            "Artist": ["lastfm_url", "biography", "image_urls"],
        },
        "scraper": {
            "Venue": [
                "address",
                "capacity",
                "latitude",
                "longitude",
                "website_url",
            ],
            "Concert": [
                "setlist",
                "attendance",
                "ticket_price_range",
                "tour_name",
            ],
        },
    }

    def __init__(
        self,
        db_client: AerospikeClient,
        overmind_client: Optional[OvermindClient] = None,
        completeness_threshold: float = 0.7,
        stale_days: int = 30,
    ):
        """Initialize enrichment scheduler.

        Args:
            db_client: Aerospike database client
            overmind_client: Overmind Lab client for logging
            completeness_threshold: Threshold below which nodes are considered incomplete
            stale_days: Number of days after which nodes are considered stale
        """
        self.db_client = db_client
        self.overmind_client = overmind_client
        self.completeness_threshold = completeness_threshold
        self.stale_days = stale_days
        self._task_queue: Dict[EnrichmentPriority, List[EnrichmentTask]] = {
            EnrichmentPriority.HIGH: [],
            EnrichmentPriority.MEDIUM: [],
            EnrichmentPriority.LOW: [],
        }
        self._processed_nodes: Set[UUID] = set()

    def identify_incomplete_nodes(self, graph_node_ids: List[UUID]) -> List[EnrichmentTask]:
        """Identify incomplete nodes and create enrichment tasks.

        Args:
            graph_node_ids: List of node UUIDs to analyze

        Returns:
            List of enrichment tasks for incomplete nodes
        """
        enrichment_tasks = []

        for node_id in graph_node_ids:
            # Skip if already processed in this session
            if node_id in self._processed_nodes:
                continue

            # Fetch node data
            node_data = self.db_client._get_node_by_id(node_id)
            if not node_data:
                logger.warning(f"Node {node_id} not found in database")
                continue

            # Determine node type
            node_type = self._determine_node_type(node_data)
            if not node_type:
                logger.warning(f"Could not determine type for node {node_id}")
                continue

            # Get completeness score
            completeness_score = node_data.get("completeness_score", 0.0)

            # Check if node is incomplete
            if completeness_score < self.completeness_threshold:
                task = self._create_enrichment_task(node_id, node_type, node_data)
                if task:
                    enrichment_tasks.append(task)
                    self._processed_nodes.add(node_id)

                    # Log to Overmind Lab
                    if self.overmind_client:
                        self.overmind_client.log_event(
                            "incomplete_node_identified",
                            {
                                "node_id": str(node_id),
                                "node_type": node_type,
                                "completeness": completeness_score,
                                "priority": task.priority.value,
                                "missing_fields": task.missing_fields,
                            },
                        )

        logger.info(
            f"Identified {len(enrichment_tasks)} incomplete nodes for enrichment"
        )

        return enrichment_tasks

    def identify_stale_nodes(
        self, node_types: Optional[List[str]] = None
    ) -> List[EnrichmentTask]:
        """Identify stale nodes that haven't been enriched recently.

        Args:
            node_types: Optional list of node types to check (default: all)

        Returns:
            List of enrichment tasks for stale nodes
        """
        if node_types is None:
            node_types = ["Song", "Artist", "Album", "RecordLabel", "Venue", "Concert"]

        stale_tasks = []
        stale_threshold = datetime.utcnow() - timedelta(days=self.stale_days)

        for node_type in node_types:
            # Scan all nodes of this type
            scan = self.db_client._client.scan(self.db_client.namespace, node_type)

            def callback(input_tuple):
                (key, metadata, record) = input_tuple

                # Parse last_enriched timestamp
                last_enriched_str = record.get("last_enriched")
                if not last_enriched_str:
                    return

                try:
                    last_enriched = datetime.fromisoformat(last_enriched_str)
                except (ValueError, TypeError):
                    return

                # Check if stale
                if last_enriched < stale_threshold:
                    node_id_str = record.get("id")
                    if not node_id_str:
                        return

                    try:
                        node_id = UUID(node_id_str)
                    except (ValueError, TypeError):
                        return

                    # Skip if already processed
                    if node_id in self._processed_nodes:
                        return

                    # Create low-priority task
                    task = self._create_enrichment_task(
                        node_id, node_type, record, is_stale=True
                    )
                    if task:
                        stale_tasks.append(task)
                        self._processed_nodes.add(node_id)

                        # Log to Overmind Lab
                        if self.overmind_client:
                            self.overmind_client.log_event(
                                "stale_node_identified",
                                {
                                    "node_id": str(node_id),
                                    "node_type": node_type,
                                    "last_enriched": last_enriched.isoformat(),
                                    "days_since_enrichment": (
                                        datetime.utcnow() - last_enriched
                                    ).days,
                                },
                            )

            scan.foreach(callback)

        logger.info(f"Identified {len(stale_tasks)} stale nodes for enrichment")

        return stale_tasks

    def _create_enrichment_task(
        self,
        node_id: UUID,
        node_type: str,
        node_data: Dict[str, Any],
        is_stale: bool = False,
    ) -> Optional[EnrichmentTask]:
        """Create an enrichment task for a node.

        Args:
            node_id: Node UUID
            node_type: Type of node
            node_data: Node data dictionary
            is_stale: Whether this is a stale node task

        Returns:
            EnrichmentTask or None if no enrichment needed
        """
        # Get completeness score
        completeness_score = node_data.get("completeness_score", 0.0)

        # Get last enriched timestamp
        last_enriched_str = node_data.get("last_enriched")
        try:
            last_enriched = datetime.fromisoformat(last_enriched_str)
        except (ValueError, TypeError):
            last_enriched = datetime.utcnow()

        # Identify missing fields
        missing_fields = self._identify_missing_fields(node_type, node_data)

        if not missing_fields and not is_stale:
            # No missing fields, no task needed
            return None

        # Determine which agents can provide missing fields
        target_agents = self._determine_target_agents(node_type, missing_fields)

        if not target_agents and not is_stale:
            # No agents can help, no task needed
            return None

        # Determine priority
        if is_stale:
            priority = EnrichmentPriority.LOW
        elif completeness_score < 0.4:
            priority = EnrichmentPriority.HIGH
        else:
            priority = EnrichmentPriority.MEDIUM

        return EnrichmentTask(
            node_id=node_id,
            node_type=node_type,
            priority=priority,
            missing_fields=missing_fields,
            target_agents=target_agents,
            completeness_score=completeness_score,
            last_enriched=last_enriched,
        )

    def _identify_missing_fields(
        self, node_type: str, node_data: Dict[str, Any]
    ) -> List[str]:
        """Identify missing fields for a node.

        Args:
            node_type: Type of node
            node_data: Node data dictionary

        Returns:
            List of missing field names
        """
        # Define expected fields for each node type
        expected_fields = {
            "Song": [
                "duration_ms",
                "release_date",
                "isrc",
                "spotify_id",
                "musicbrainz_id",
                "lastfm_url",
                "audio_features",
                "tags",
                "play_count",
                "listener_count",
            ],
            "Artist": [
                "genres",
                "country",
                "formed_date",
                "spotify_id",
                "musicbrainz_id",
                "lastfm_url",
                "popularity",
                "follower_count",
                "biography",
                "image_urls",
            ],
            "Album": [
                "release_date",
                "total_tracks",
                "spotify_id",
                "musicbrainz_id",
                "label",
                "catalog_number",
                "cover_art_url",
            ],
            "RecordLabel": [
                "country",
                "founded_date",
                "musicbrainz_id",
                "website_url",
            ],
            "Venue": [
                "capacity",
                "latitude",
                "longitude",
                "address",
                "website_url",
            ],
            "Concert": [
                "setlist",
                "attendance",
                "ticket_price_range",
                "tour_name",
            ],
        }

        fields = expected_fields.get(node_type, [])
        missing = []

        for field in fields:
            value = node_data.get(field)
            # Consider field missing if None, empty string, or empty list
            if value is None or value == "" or value == []:
                missing.append(field)

        return missing

    def _determine_target_agents(
        self, node_type: str, missing_fields: List[str]
    ) -> List[str]:
        """Determine which agents can provide missing fields.

        Args:
            node_type: Type of node
            missing_fields: List of missing field names

        Returns:
            List of agent names that can provide at least one missing field
        """
        target_agents = set()

        for agent_name, capabilities in self.AGENT_CAPABILITIES.items():
            if node_type not in capabilities:
                continue

            agent_fields = capabilities[node_type]

            # Check if agent can provide any missing field
            if any(field in agent_fields for field in missing_fields):
                target_agents.add(agent_name)

        return sorted(list(target_agents))

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

    async def schedule_proactive_enrichment(
        self, tasks: List[EnrichmentTask]
    ) -> None:
        """Schedule enrichment tasks for execution.

        Args:
            tasks: List of enrichment tasks to schedule
        """
        if not tasks:
            logger.info("No enrichment tasks to schedule")
            return

        # Deduplicate tasks by node_id
        unique_tasks = self._deduplicate_tasks(tasks)

        # Add tasks to priority queues
        for task in unique_tasks:
            self._task_queue[task.priority].append(task)

        logger.info(
            f"Scheduled {len(unique_tasks)} enrichment tasks: "
            f"{len(self._task_queue[EnrichmentPriority.HIGH])} high, "
            f"{len(self._task_queue[EnrichmentPriority.MEDIUM])} medium, "
            f"{len(self._task_queue[EnrichmentPriority.LOW])} low priority"
        )

        # Log to Overmind Lab
        if self.overmind_client:
            self.overmind_client.log_event(
                "enrichment_tasks_scheduled",
                {
                    "total_tasks": len(unique_tasks),
                    "high_priority": len(self._task_queue[EnrichmentPriority.HIGH]),
                    "medium_priority": len(self._task_queue[EnrichmentPriority.MEDIUM]),
                    "low_priority": len(self._task_queue[EnrichmentPriority.LOW]),
                    "timestamp": datetime.utcnow().isoformat(),
                },
            )

        # Schedule execution based on priority
        await self._execute_scheduled_tasks()

    def _deduplicate_tasks(self, tasks: List[EnrichmentTask]) -> List[EnrichmentTask]:
        """Deduplicate tasks for the same node, keeping highest priority.

        Args:
            tasks: List of enrichment tasks

        Returns:
            Deduplicated list of tasks
        """
        task_map: Dict[UUID, EnrichmentTask] = {}

        for task in tasks:
            if task.node_id not in task_map:
                task_map[task.node_id] = task
            else:
                # Keep task with higher priority
                existing = task_map[task.node_id]
                priority_order = {
                    EnrichmentPriority.HIGH: 3,
                    EnrichmentPriority.MEDIUM: 2,
                    EnrichmentPriority.LOW: 1,
                }

                if priority_order[task.priority] > priority_order[existing.priority]:
                    task_map[task.node_id] = task

        return list(task_map.values())

    async def _execute_scheduled_tasks(self) -> None:
        """Execute scheduled tasks based on priority and timing.

        High priority: Execute immediately
        Medium priority: Execute within 1 hour
        Low priority: Execute within 24 hours
        """
        # Execute high priority tasks immediately
        high_priority_tasks = self._task_queue[EnrichmentPriority.HIGH]
        if high_priority_tasks:
            logger.info(f"Executing {len(high_priority_tasks)} high priority tasks immediately")
            # In a real implementation, this would dispatch to the orchestrator
            # For now, we just log the intent
            for task in high_priority_tasks:
                logger.debug(
                    f"Would enrich {task.node_type} {task.node_id} "
                    f"using agents: {', '.join(task.target_agents)}"
                )

            self._task_queue[EnrichmentPriority.HIGH] = []

        # Schedule medium priority tasks for 1 hour delay
        medium_priority_tasks = self._task_queue[EnrichmentPriority.MEDIUM]
        if medium_priority_tasks:
            logger.info(
                f"Scheduling {len(medium_priority_tasks)} medium priority tasks "
                f"for execution in 1 hour"
            )
            # In production, this would use a task queue like Celery
            # For now, we use asyncio.create_task with delay
            asyncio.create_task(self._execute_delayed_tasks(medium_priority_tasks, delay=3600))
            self._task_queue[EnrichmentPriority.MEDIUM] = []

        # Schedule low priority tasks for 24 hour delay
        low_priority_tasks = self._task_queue[EnrichmentPriority.LOW]
        if low_priority_tasks:
            logger.info(
                f"Scheduling {len(low_priority_tasks)} low priority tasks "
                f"for execution in 24 hours"
            )
            asyncio.create_task(
                self._execute_delayed_tasks(low_priority_tasks, delay=24 * 3600)
            )
            self._task_queue[EnrichmentPriority.LOW] = []

    async def _execute_delayed_tasks(
        self, tasks: List[EnrichmentTask], delay: int
    ) -> None:
        """Execute tasks after a delay.

        Args:
            tasks: List of tasks to execute
            delay: Delay in seconds before execution
        """
        await asyncio.sleep(delay)

        logger.info(f"Executing {len(tasks)} delayed enrichment tasks")

        for task in tasks:
            logger.debug(
                f"Would enrich {task.node_type} {task.node_id} "
                f"using agents: {', '.join(task.target_agents)}"
            )

            # Log to Overmind Lab
            if self.overmind_client:
                self.overmind_client.log_event(
                    "delayed_enrichment_executed",
                    {
                        "node_id": str(task.node_id),
                        "node_type": task.node_type,
                        "priority": task.priority.value,
                        "delay_seconds": delay,
                    },
                )

    def get_task_queue_status(self) -> Dict[str, int]:
        """Get current status of task queues.

        Returns:
            Dictionary with task counts by priority
        """
        return {
            "high_priority": len(self._task_queue[EnrichmentPriority.HIGH]),
            "medium_priority": len(self._task_queue[EnrichmentPriority.MEDIUM]),
            "low_priority": len(self._task_queue[EnrichmentPriority.LOW]),
            "total": sum(len(tasks) for tasks in self._task_queue.values()),
        }

    def clear_processed_nodes(self) -> None:
        """Clear the set of processed nodes."""
        self._processed_nodes.clear()
        logger.debug("Cleared processed nodes set")
