"""Orchestrator agent for coordinating multi-agent music data enrichment."""

import asyncio
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from config.settings import settings
from src.cache.redis_client import RedisClient
from src.errors.handlers import log_error_to_overmind
from src.tracing.overmind_client import OvermindClient, TraceContext
from src.validation.data_validator import DataValidator

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
        db_client: Optional[Any] = None,
        agent_timeout_ms: int = settings.agent_timeout_ms,
    ):
        """Initialize orchestrator agent.

        Args:
            cache_client: Redis cache client
            overmind_client: Overmind Lab tracing client
            db_client: Aerospike database client for graph operations
            agent_timeout_ms: Timeout for agent execution in milliseconds
        """
        self.cache_client = cache_client or RedisClient()
        self.overmind_client = overmind_client
        self.db_client = db_client
        self.agent_timeout_ms = agent_timeout_ms
        self.agent_timeout_seconds = agent_timeout_ms / 1000.0

        # Initialize quality tracker with same cache and overmind clients
        from src.self_improvement.quality_tracker import QualityTracker

        self.quality_tracker = QualityTracker(
            cache_client=self.cache_client,
            overmind_client=self.overmind_client,
        )

        # Initialize enrichment scheduler if database client is available
        self.enrichment_scheduler = None
        if self.db_client:
            from src.self_improvement.enrichment_scheduler import EnrichmentScheduler

            self.enrichment_scheduler = EnrichmentScheduler(
                db_client=self.db_client,
                overmind_client=self.overmind_client,
            )

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

            # Step 4: Analyze data quality and update rankings
            quality_metrics = self.quality_tracker.analyze_data_quality(results)
            self.quality_tracker.update_source_rankings(quality_metrics)

            # Step 5: Merge results with conflict resolution (using updated rankings)
            merged_data = self.merge_results(results)

            # Step 5.5: Validate merged data before persistence
            merged_data, invalid_fields = DataValidator.validate_merged_data(merged_data)
            if invalid_fields:
                logger.info(
                    f"Validation stripped {len(invalid_fields)} invalid fields from merged data"
                )
                if self.overmind_client:
                    self.overmind_client.log_event(
                        "data_validation",
                        {
                            "request_id": str(request_id),
                            "song_name": song_name,
                            "invalid_fields": invalid_fields,
                        },
                    )

            # Step 6: Calculate overall completeness
            completeness_score = self._calculate_overall_completeness(merged_data)

            # Step 7: Persist to graph database
            graph_node_ids = self._persist_to_graph(merged_data, completeness_score)

            enrichment_result = EnrichmentResult(
                status="success" if any(r.status == "success" for r in results) else "partial",
                graph_node_ids=graph_node_ids,
                merged_data=merged_data,
                completeness_score=completeness_score,
                request_id=request_id,
            )

            # Step 8: Identify incomplete nodes and schedule proactive enrichment
            if self.enrichment_scheduler:
                try:
                    enrichment_tasks = self.enrichment_scheduler.identify_incomplete_nodes(
                        graph_node_ids
                    )
                    if enrichment_tasks:
                        await self.enrichment_scheduler.schedule_proactive_enrichment(
                            enrichment_tasks
                        )
                        logger.info(f"Scheduled {len(enrichment_tasks)} proactive enrichment tasks")

                        # Log self-improvement activity to Overmind Lab
                        if self.overmind_client:
                            self.overmind_client.log_event(
                                "self_improvement_cycle_complete",
                                {
                                    "request_id": str(request_id),
                                    "song_name": song_name,
                                    "enrichment_tasks_scheduled": len(enrichment_tasks),
                                    "completeness_score": completeness_score,
                                    "quality_metrics_updated": True,
                                    "timestamp": datetime.utcnow().isoformat(),
                                },
                            )
                except Exception as e:
                    logger.warning(f"Failed to schedule proactive enrichment: {e}")

            # Step 9: Cache result
            cache_data = {
                "graph_node_ids": [str(nid) for nid in graph_node_ids],
                "merged_data": merged_data,
                "completeness_score": completeness_score,
            }
            self.cache_client.set(cache_key, cache_data, ttl=settings.cache_ttl_seconds)

            # Step 10: End trace
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
            log_error_to_overmind(
                self.overmind_client,
                operation=f"agent_{agent_name}",
                error=asyncio.TimeoutError(f"Agent {agent_name} timed out"),
                extra={"agent_name": agent_name, "timeout_ms": self.agent_timeout_ms, "song_name": song_name},
            )
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
            log_error_to_overmind(
                self.overmind_client,
                operation=f"agent_{agent_name}",
                error=e,
                extra={"agent_name": agent_name, "song_name": song_name},
            )
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
            from src.agents.spotify_agent import SpotifyAgent

            agent = SpotifyAgent(overmind_client=self.overmind_client)
            try:
                spotify_result = await agent.fetch_spotify_data(song_name)

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

        elif agent_name == "lastfm":
            from src.agents.lastfm_agent import LastFMAgent

            lastfm_agent = LastFMAgent(overmind_client=self.overmind_client)
            try:
                lastfm_result = await lastfm_agent.fetch_lastfm_data(song_name)

                data = {}
                if lastfm_result.song:
                    data["song"] = lastfm_result.song.model_dump()
                if lastfm_result.artists:
                    data["artists"] = [artist.model_dump() for artist in lastfm_result.artists]
                if lastfm_result.similar_tracks:
                    data["similar_tracks"] = lastfm_result.similar_tracks
                if lastfm_result.tags:
                    data["tags"] = lastfm_result.tags

                status = "success" if lastfm_result.completeness_score > 0.0 else "failed"

                return AgentResult(
                    agent_name=agent_name,
                    status=status,
                    data=data,
                    completeness_score=lastfm_result.completeness_score,
                )
            finally:
                await lastfm_agent.close()

        elif agent_name == "musicbrainz":
            from src.agents.musicbrainz_agent import MusicBrainzAgent

            mb_agent = MusicBrainzAgent(overmind_client=self.overmind_client)
            try:
                mb_result = await mb_agent.fetch_musicbrainz_data(song_name)

                data = {}
                if mb_result.song:
                    data["song"] = mb_result.song.model_dump()
                if mb_result.artists:
                    data["artists"] = [artist.model_dump() for artist in mb_result.artists]
                if mb_result.relationships:
                    data["relationships"] = mb_result.relationships
                if mb_result.label_info:
                    data["label_info"] = mb_result.label_info

                status = "success" if mb_result.completeness_score > 0.0 else "failed"

                return AgentResult(
                    agent_name=agent_name,
                    status=status,
                    data=data,
                    completeness_score=mb_result.completeness_score,
                )
            finally:
                await mb_agent.close()

        elif agent_name == "scraper":
            from src.agents.scraper_agent import WebScraperAgent

            scraper_agent = WebScraperAgent(overmind_client=self.overmind_client)
            try:
                scraper_result = await scraper_agent.scrape_web_data(song_name)

                data = {}
                if scraper_result.venues:
                    data["venues"] = [v.model_dump() for v in scraper_result.venues]
                if scraper_result.concerts:
                    data["concerts"] = [
                        c.model_dump() for c in scraper_result.concerts
                    ]
                if scraper_result.setlists:
                    data["setlists"] = scraper_result.setlists

                status = "success" if scraper_result.status == "success" else scraper_result.status

                return AgentResult(
                    agent_name=agent_name,
                    status=status,
                    data=data,
                    completeness_score=scraper_result.completeness_score,
                )
            finally:
                await scraper_agent.close()

        else:
            # Unknown agent
            return AgentResult(
                agent_name=agent_name,
                status="failed",
                data={},
                completeness_score=0.0,
                error_message=f"Unknown agent: {agent_name}",
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
            "venues": [],
            "concerts": [],
            "setlists": [],
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

        # Merge venues
        venue_data_list = [r for r in valid_results if r.data.get("venues")]
        if venue_data_list:
            merged_data["venues"] = self._merge_venues(venue_data_list)

        # Merge concerts
        concert_data_list = [r for r in valid_results if r.data.get("concerts")]
        if concert_data_list:
            merged_data["concerts"] = self._merge_concerts(concert_data_list)

        # Merge setlists
        setlist_data_list = [r for r in valid_results if r.data.get("setlists")]
        if setlist_data_list:
            merged_data["setlists"] = self._merge_setlists(setlist_data_list)

        # Estimate audio features from tags if not already present
        song_data = merged_data.get("song", {})
        has_audio_features = song_data.get("audio_features") is not None
        if not has_audio_features:
            all_tags: list = []
            # Collect tags from song data
            song_tags = song_data.get("tags", [])
            if isinstance(song_tags, list):
                all_tags.extend(song_tags)
            # Collect tags from Last.fm/MusicBrainz agent results
            for r in valid_results:
                agent_tags = r.data.get("tags", [])
                if isinstance(agent_tags, list):
                    all_tags.extend(agent_tags)

            if all_tags:
                from src.utils.audio_features_estimator import estimate_audio_features

                estimated = estimate_audio_features(all_tags)
                if estimated:
                    merged_data["song"]["audio_features"] = estimated.model_dump()

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

    def _resolve_field_conflict(self, field_name: str, candidates: List[Dict[str, Any]]) -> Any:
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

    def _merge_venues(self, venue_data_list: List[AgentResult]) -> List[Dict[str, Any]]:
        """Merge venue data from multiple sources.

        Args:
            venue_data_list: List of agent results containing venue data

        Returns:
            List of merged venue dictionaries (deduplicated by name)
        """
        seen = set()
        merged_venues = []
        for result in venue_data_list:
            venues = result.data.get("venues", [])
            if isinstance(venues, list):
                for venue in venues:
                    name = venue.get("name", "") if isinstance(venue, dict) else ""
                    if name and name not in seen:
                        seen.add(name)
                        merged_venues.append(venue)
        return merged_venues

    def _merge_concerts(self, concert_data_list: List[AgentResult]) -> List[Dict[str, Any]]:
        """Merge concert data from multiple sources.

        Args:
            concert_data_list: List of agent results containing concert data

        Returns:
            List of merged concert dictionaries
        """
        all_concerts = []
        for result in concert_data_list:
            concerts = result.data.get("concerts", [])
            if isinstance(concerts, list):
                all_concerts.extend(concerts)
        return all_concerts

    def _merge_setlists(self, setlist_data_list: List[AgentResult]) -> List[Dict[str, Any]]:
        """Merge setlist data from multiple sources.

        Args:
            setlist_data_list: List of agent results containing setlist data

        Returns:
            List of merged setlist dictionaries
        """
        all_setlists = []
        for result in setlist_data_list:
            setlists = result.data.get("setlists", [])
            if isinstance(setlists, list):
                all_setlists.extend(setlists)
        return all_setlists

    def _get_source_quality(self, source_name: str) -> float:
        """Get quality score for a data source.

        Args:
            source_name: Name of the data source

        Returns:
            Quality score between 0.0 and 1.0
        """
        # Get quality from self-improvement engine
        quality_report = self.quality_tracker.get_source_quality_report()
        return quality_report.get_quality(source_name)

    def _persist_to_graph(
        self, merged_data: Dict[str, Any], completeness_score: float
    ) -> List[UUID]:
        """Persist enrichment data to the graph database.

        Creates/updates Song, Artist, and Album nodes and connects them
        with edges. Uses deterministic IDs based on entity names so that
        repeated enrichments merge into the same nodes.

        Args:
            merged_data: Merged data from all agents
            completeness_score: Overall completeness score

        Returns:
            List of persisted graph node UUIDs
        """
        import hashlib

        def _deterministic_uuid(namespace: str, name: str) -> UUID:
            h = hashlib.sha256(f"{namespace}:{name.lower().strip()}".encode()).hexdigest()
            return UUID(h[:32])

        graph_node_ids: List[UUID] = []
        song_data = merged_data.get("song", {})
        artists_data = merged_data.get("artists", [])
        album_data = merged_data.get("album", {})
        data_sources = merged_data.get("data_sources", [])

        # Compute deterministic IDs first (independent of DB availability)
        song_title = song_data.get("title") or song_data.get("name", "")
        if song_title:
            song_id = _deterministic_uuid("song", song_title)
            graph_node_ids.append(song_id)
        else:
            song_id = uuid4()
            graph_node_ids.append(song_id)

        if not self.db_client:
            return graph_node_ids

        try:
            # --- Song node ---
            if song_title:
                song_props = {
                    "id": str(song_id),
                    "title": song_title,
                    "node_type": "Song",
                    "completeness_score": completeness_score,
                    "last_enriched": datetime.utcnow().isoformat(),
                    "data_sources": data_sources,
                }
                for k, v in song_data.items():
                    if k not in song_props and v is not None:
                        song_props[k] = v
                self.db_client.upsert_node("Song", song_props)

                # --- Artist nodes + PERFORMED_IN edges ---
                if isinstance(artists_data, list):
                    for artist in artists_data:
                        artist_name = artist.get("name", "") if isinstance(artist, dict) else ""
                        if not artist_name:
                            continue
                        artist_id = _deterministic_uuid("artist", artist_name)
                        artist_props = {
                            "id": str(artist_id),
                            "name": artist_name,
                            "node_type": "Artist",
                            "last_enriched": datetime.utcnow().isoformat(),
                        }
                        if isinstance(artist, dict):
                            for k, v in artist.items():
                                if k not in artist_props and v is not None:
                                    artist_props[k] = v
                        self.db_client.upsert_node("Artist", artist_props)

                        # Edge: Artist --PERFORMED_IN--> Song
                        edge_id = _deterministic_uuid("performed_in", f"{artist_name}:{song_title}")
                        try:
                            self.db_client.upsert_edge(
                                from_node_id=artist_id,
                                to_node_id=song_id,
                                edge_type="PERFORMED_IN",
                                properties={
                                    "id": str(edge_id),
                                    "from_node_id": str(artist_id),
                                    "to_node_id": str(song_id),
                                },
                            )
                        except ValueError:
                            logger.debug(f"Skipped edge for {artist_name} -> {song_title}")

                # --- Album node + PART_OF_ALBUM edge ---
                if album_data and isinstance(album_data, dict):
                    album_name = album_data.get("name") or album_data.get("title", "")
                    if album_name:
                        album_id = _deterministic_uuid("album", album_name)
                        album_props = {
                            "id": str(album_id),
                            "name": album_name,
                            "node_type": "Album",
                            "last_enriched": datetime.utcnow().isoformat(),
                        }
                        for k, v in album_data.items():
                            if k not in album_props and v is not None:
                                album_props[k] = v
                        self.db_client.upsert_node("Album", album_props)

                        # Edge: Song --PART_OF_ALBUM--> Album
                        edge_id = _deterministic_uuid("part_of_album", f"{song_title}:{album_name}")
                        try:
                            self.db_client.upsert_edge(
                                from_node_id=song_id,
                                to_node_id=album_id,
                                edge_type="PART_OF_ALBUM",
                                properties={
                                    "id": str(edge_id),
                                    "from_node_id": str(song_id),
                                    "to_node_id": str(album_id),
                                },
                            )
                        except ValueError:
                            logger.debug(f"Skipped edge for {song_title} -> {album_name}")

        except Exception as e:
            logger.warning(f"Graph persistence failed (non-fatal): {e}")

        return graph_node_ids

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
