"""Orchestrator agent for coordinating multi-agent music data enrichment."""

import asyncio
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from config.settings import settings
from src.cache.redis_client import RedisClient
from src.tracing.overmind_client import OvermindClient, TraceContext
from src.utils.metrics import calculate_completeness

logger = logging.getLogger(__name__)


class AgentResult:
    """Result from a sub-agent execution."""

    def __init__(
        self,
        agent_name: str,
        status: str,
        data: Dict[str, Any],
        completeness_score: float = 0.0,
        response_time_ms: int = 0,
        error_message: Optional[str] = None,
        timestamp: Optional[datetime] = None,
        trace_id: Optional[UUID] = None,
    ):
        """Initialize agent result.

        Args:
            agent_name: Name of the agent
            status: Status (success, partial, failed)
            data: Data returned by agent
            completeness_score: Completeness score
            response_time_ms: Response time in milliseconds
            error_message: Error message if failed
            timestamp: Result timestamp
            trace_id: Trace ID for correlation
        """
        self.agent_name = agent_name
        self.status = status
        self.data = data
        self.completeness_score = completeness_score
        self.response_time_ms = response_time_ms
        self.error_message = error_message
        self.timestamp = timestamp or datetime.utcnow()
        self.trace_id = trace_id


class EnrichmentResult:
    """Result of song enrichment operation."""

    def __init__(
        self,
        status: str,
        graph_node_ids: List[UUID],
        merged_data: Dict[str, Any],
        completeness_score: float,
        request_id: UUID,
        error_message: Optional[str] = None,
    ):
        """Initialize enrichment result.

        Args:
            status: Overall status (success, partial, failed)
            graph_node_ids: List of created/updated graph node IDs
            merged_data: Merged data from all agents
            completeness_score: Overall completeness score
            request_id: Request ID for tracing
            error_message: Error message if failed
        """
        self.status = status
        self.graph_node_ids = graph_node_ids
        self.merged_data = merged_data
        self.completeness_score = completeness_score
        self.request_id = request_id
        self.error_message = error_message


class OrchestratorAgent:
    """Central orchestrator that coordinates all sub-agents."""

    def __init__(
        self,
        cache_client: Optional[RedisClient] = None,
        overmind_client: Optional[OvermindClient] = None,
        agent_timeout_ms: int = settings.agent_timeout_ms,
    ):
        """Initialize orchestrator agent.

        Args:
            cache_client: Redis cache client
            overmind_client: Overmind Lab tracing client
            agent_timeout_ms: Timeout for agent execution in milliseconds
        """
        self.cache_client = cache_client or RedisClient()
        self.overmind_client = overmind_client
        self.agent_timeout_ms = agent_timeout_ms
        self.agent_timeout_seconds = agent_timeout_ms / 1000.0

    async def enrich_song(self, song_name: str) -> EnrichmentResult:
        """Main entry point for song enrichment.

        Args:
            song_name: Name of the song to enrich

        Returns:
            EnrichmentResult with merged data and graph node IDs
        """
        # Step 1: Initialize request tracking
        request_id = uuid4()
        trace = None
        if self.overmind_client:
            trace = self.overmind_client.start_trace(request_id, "song_enrichment")

        logger.info(f"Starting enrichment for song: '{song_name}' [{request_id}]")

        try:
            # Step 2: Check cache for recent enrichment
            cache_key = RedisClient.make_song_cache_key(song_name)
            cached_result = self.cache_client.get(cache_key)

            if cached_result:
                logger.info(f"Cache hit for song: '{song_name}'")
                if trace:
                    trace.end_trace("cache_hit")
                return EnrichmentResult(
                    status="success",
                    graph_node_ids=[UUID(nid) for nid in cached_result.get("graph_node_ids", [])],
                    merged_data=cached_result.get("merged_data", {}),
                    completeness_score=cached_result.get("completeness_score", 0.0),
                    request_id=request_id,
                )

            # Step 3: Dispatch agents in parallel
            logger.info(f"Cache miss for song: '{song_name}', dispatching agents")
            results = await self.dispatch_agents(song_name, trace)

            # Step 4: Merge results with conflict resolution
            merged_data = self.merge_results(results)

            # Step 5: Calculate overall completeness
            completeness_score = self._calculate_overall_completeness(merged_data)

            # Step 6: Create enrichment result
            # Note: Graph persistence would happen here in full implementation
            # For now, we'll create placeholder node IDs
            graph_node_ids = [uuid4()]  # Placeholder for song node

            enrichment_result = EnrichmentResult(
                status="success" if any(r.status == "success" for r in results) else "partial",
                graph_node_ids=graph_node_ids,
                merged_data=merged_data,
                completeness_score=completeness_score,
                request_id=request_id,
            )

            # Step 7: Cache result
            cache_data = {
                "graph_node_ids": [str(nid) for nid in graph_node_ids],
                "merged_data": merged_data,
                "completeness_score": completeness_score,
            }
            self.cache_client.set(cache_key, cache_data, ttl=settings.cache_ttl_seconds)

            # Step 8: End trace
            if trace:
                trace.end_trace("success")

            logger.info(
                f"Enrichment complete for '{song_name}': "
                f"completeness={completeness_score:.2f}, "
                f"nodes={len(graph_node_ids)}"
            )

            return enrichment_result

        except Exception as e:
            logger.error(f"Enrichment failed for '{song_name}': {e}", exc_info=True)
            if trace:
                trace.end_trace("failure")
            return EnrichmentResult(
                status="failed",
                graph_node_ids=[],
                merged_data={},
                completeness_score=0.0,
                request_id=request_id,
                error_message=str(e),
            )

    async def dispatch_agents(
        self, song_name: str, trace: Optional[TraceContext] = None
    ) -> List[AgentResult]:
        """Dispatch all sub-agents in parallel with timeout.

        Args:
            song_name: Song name to enrich
            trace: Optional trace context for logging

        Returns:
            List of agent results (includes both successful and failed)
        """
        # Define agent tasks
        agent_names = ["spotify", "musicbrainz", "lastfm", "scraper"]

        # Create tasks for parallel execution
        tasks = []
        spans = {}

        for agent_name in agent_names:
            # Create span for this agent
            span = None
            if trace and self.overmind_client:
                span = self.overmind_client.log_agent_dispatch(trace, agent_name, song_name)
                spans[agent_name] = span

            # Create async task for agent
            task = self._execute_agent(agent_name, song_name, trace.request_id if trace else None)
            tasks.append(task)

        # Execute all agents in parallel with timeout
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Process results and log to Overmind
        agent_results = []
        for i, result in enumerate(results):
            agent_name = agent_names[i]
            span = spans.get(agent_name)

            if isinstance(result, Exception):
                # Agent raised exception
                logger.warning(f"Agent {agent_name} failed with exception: {result}")
                agent_result = AgentResult(
                    agent_name=agent_name,
                    status="failed",
                    data={},
                    error_message=str(result),
                    trace_id=trace.request_id if trace else None,
                )
            else:
                agent_result = result

            # Log agent response to Overmind
            if span and self.overmind_client:
                self.overmind_client.log_agent_response(
                    span,
                    agent_result.response_time_ms,
                    agent_result.status,
                    agent_result.completeness_score,
                )

            agent_results.append(agent_result)

        return agent_results

    async def _execute_agent(
        self, agent_name: str, song_name: str, trace_id: Optional[UUID]
    ) -> AgentResult:
        """Execute a single agent with timeout.

        Args:
            agent_name: Name of the agent to execute
            song_name: Song name to enrich
            trace_id: Trace ID for correlation

        Returns:
            AgentResult with data or error
        """
        start_time = asyncio.get_event_loop().time()

        try:
            # Wrap agent execution with timeout
            result = await asyncio.wait_for(
                self._call_agent(agent_name, song_name),
                timeout=self.agent_timeout_seconds,
            )

            end_time = asyncio.get_event_loop().time()
            response_time_ms = int((end_time - start_time) * 1000)

            result.response_time_ms = response_time_ms
            result.trace_id = trace_id

            return result

        except asyncio.TimeoutError:
            end_time = asyncio.get_event_loop().time()
            response_time_ms = int((end_time - start_time) * 1000)

            logger.warning(f"Agent {agent_name} timed out after {response_time_ms}ms")
            return AgentResult(
                agent_name=agent_name,
                status="failed",
                data={},
                response_time_ms=response_time_ms,
                error_message=f"Timeout after {self.agent_timeout_ms}ms",
                trace_id=trace_id,
            )

        except Exception as e:
            end_time = asyncio.get_event_loop().time()
            response_time_ms = int((end_time - start_time) * 1000)

            logger.error(f"Agent {agent_name} failed: {e}", exc_info=True)
            return AgentResult(
                agent_name=agent_name,
                status="failed",
                data={},
                response_time_ms=response_time_ms,
                error_message=str(e),
                trace_id=trace_id,
            )

    async def _call_agent(self, agent_name: str, song_name: str) -> AgentResult:
        """Call a specific agent.

        Args:
            agent_name: Name of the agent
            song_name: Song name to enrich

        Returns:
            AgentResult with data from the agent
        """
        if agent_name == "spotify":
            # Import here to avoid circular dependencies
            from src.agents.spotify_agent import SpotifyAgent

            agent = SpotifyAgent(overmind_client=self.overmind_client)
            try:
                spotify_result = await agent.fetch_spotify_data(song_name)

                # Convert to AgentResult format
                data = {}
                if spotify_result.song:
                    data["song"] = spotify_result.song.model_dump()
                if spotify_result.artists:
                    data["artists"] = [artist.model_dump() for artist in spotify_result.artists]
                if spotify_result.album:
                    data["album"] = spotify_result.album.model_dump()

                status = "success" if spotify_result.completeness_score > 0.0 else "failed"

                return AgentResult(
                    agent_name=agent_name,
                    status=status,
                    data=data,
                    completeness_score=spotify_result.completeness_score,
                )
            finally:
                await agent.close()
        else:
            # Placeholder for other agents (musicbrainz, lastfm, scraper)
            await asyncio.sleep(0.1)
            return AgentResult(
                agent_name=agent_name,
                status="success",
                data={
                    "song": {
                        "title": song_name,
                        "source": agent_name,
                    }
                },
                completeness_score=0.5,
            )

    def merge_results(self, results: List[AgentResult]) -> Dict[str, Any]:
        """Merge results from multiple agents with conflict resolution.

        Args:
            results: List of agent results

        Returns:
            Merged data dictionary
        """
        merged_data = {
            "song": {},
            "artists": [],
            "album": {},
            "relationships": [],
            "data_sources": [],
        }

        # Filter successful and partial results
        valid_results = [r for r in results if r.status in ["success", "partial"]]

        if not valid_results:
            logger.warning("No valid results to merge")
            return merged_data

        # Collect data sources
        merged_data["data_sources"] = [r.agent_name for r in valid_results]

        # Merge song data
        song_data_list = [r for r in valid_results if r.data.get("song")]
        if song_data_list:
            merged_data["song"] = self.merge_song_data(song_data_list)

        # Merge artist data
        artist_data_list = [r for r in valid_results if r.data.get("artists")]
        if artist_data_list:
            merged_data["artists"] = self._merge_artist_data(artist_data_list)

        # Merge album data
        album_data_list = [r for r in valid_results if r.data.get("album")]
        if album_data_list:
            merged_data["album"] = self._merge_album_data(album_data_list)

        # Merge relationships
        relationship_data_list = [r for r in valid_results if r.data.get("relationships")]
        if relationship_data_list:
            merged_data["relationships"] = self._merge_relationships(relationship_data_list)

        return merged_data

    def merge_song_data(self, song_data_list: List[AgentResult]) -> Dict[str, Any]:
        """Merge song data with quality-based conflict resolution.

        Args:
            song_data_list: List of agent results containing song data

        Returns:
            Merged song data dictionary
        """
        merged_song = {}
        field_sources: Dict[str, List[Dict[str, Any]]] = {}

        # Step 1: Collect all field values from all sources
        for result in song_data_list:
            song_data = result.data.get("song", {})
            source_name = result.agent_name
            source_quality = self._get_source_quality(source_name)

            for field_name, field_value in song_data.items():
                if field_value is not None:
                    if field_name not in field_sources:
                        field_sources[field_name] = []

                    field_sources[field_name].append(
                        {
                            "value": field_value,
                            "source": source_name,
                            "quality": source_quality,
                            "timestamp": result.timestamp,
                        }
                    )

        # Step 2: Resolve conflicts for each field
        for field_name, candidates in field_sources.items():
            if len(candidates) == 1:
                # No conflict, use single value
                merged_song[field_name] = candidates[0]["value"]
            else:
                # Apply field-specific conflict resolution strategy
                merged_song[field_name] = self._resolve_field_conflict(field_name, candidates)

        return merged_song

    def _resolve_field_conflict(
        self, field_name: str, candidates: List[Dict[str, Any]]
    ) -> Any:
        """Resolve conflict for a specific field using appropriate strategy.

        Args:
            field_name: Name of the field
            candidates: List of candidate values with metadata

        Returns:
            Resolved field value
        """
        # Single-value fields: use highest quality source
        if field_name in ["title", "duration_ms", "release_date", "isrc"]:
            best = max(candidates, key=lambda c: c["quality"])
            return best["value"]

        # Multi-value fields: merge and deduplicate
        elif field_name in ["tags", "genres", "data_sources"]:
            all_values = []
            for candidate in candidates:
                value = candidate["value"]
                if isinstance(value, list):
                    all_values.extend(value)
                else:
                    all_values.append(value)
            # Deduplicate while preserving order
            seen = set()
            unique_values = []
            for v in all_values:
                if v not in seen:
                    seen.add(v)
                    unique_values.append(v)
            return unique_values

        # Time-sensitive fields: use most recent
        elif field_name in ["play_count", "listener_count"]:
            most_recent = max(candidates, key=lambda c: c["timestamp"])
            return most_recent["value"]

        # Default: use highest quality source
        else:
            best = max(candidates, key=lambda c: c["quality"])
            return best["value"]

    def _merge_artist_data(self, artist_data_list: List[AgentResult]) -> List[Dict[str, Any]]:
        """Merge artist data from multiple sources.

        Args:
            artist_data_list: List of agent results containing artist data

        Returns:
            List of merged artist dictionaries
        """
        # Simplified merge - in full implementation would deduplicate by artist ID
        all_artists = []
        for result in artist_data_list:
            artists = result.data.get("artists", [])
            if isinstance(artists, list):
                all_artists.extend(artists)
        return all_artists

    def _merge_album_data(self, album_data_list: List[AgentResult]) -> Dict[str, Any]:
        """Merge album data from multiple sources.

        Args:
            album_data_list: List of agent results containing album data

        Returns:
            Merged album dictionary
        """
        # Simplified merge - similar to song data merge
        merged_album = {}
        for result in album_data_list:
            album = result.data.get("album", {})
            merged_album.update(album)
        return merged_album

    def _merge_relationships(
        self, relationship_data_list: List[AgentResult]
    ) -> List[Dict[str, Any]]:
        """Merge relationship data from multiple sources.

        Args:
            relationship_data_list: List of agent results containing relationships

        Returns:
            List of merged relationships
        """
        all_relationships = []
        for result in relationship_data_list:
            relationships = result.data.get("relationships", [])
            if isinstance(relationships, list):
                all_relationships.extend(relationships)
        return all_relationships

    def _get_source_quality(self, source_name: str) -> float:
        """Get quality score for a data source.

        Args:
            source_name: Name of the data source

        Returns:
            Quality score between 0.0 and 1.0
        """
        # Placeholder quality rankings (would come from self-improvement engine)
        quality_rankings = {
            "spotify": 0.9,
            "musicbrainz": 0.95,
            "lastfm": 0.8,
            "scraper": 0.7,
        }
        return quality_rankings.get(source_name, 0.5)

    def _calculate_overall_completeness(self, merged_data: Dict[str, Any]) -> float:
        """Calculate overall completeness score for merged data.

        Args:
            merged_data: Merged data from all agents

        Returns:
            Completeness score between 0.0 and 1.0
        """
        # Count populated fields across all entities
        total_fields = 0
        populated_fields = 0

        for entity_type, entity_data in merged_data.items():
            if entity_type == "data_sources":
                continue

            if isinstance(entity_data, dict):
                for field_name, field_value in entity_data.items():
                    total_fields += 1
                    if field_value is not None and field_value != "" and field_value != []:
                        populated_fields += 1
            elif isinstance(entity_data, list):
                # Count list items as populated if list is non-empty
                total_fields += 1
                if len(entity_data) > 0:
                    populated_fields += 1

        if total_fields == 0:
            return 0.0

        return populated_fields / total_fields
