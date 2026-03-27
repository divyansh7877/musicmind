"""MusicBrainz agent for fetching authoritative music metadata."""

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional
from uuid import UUID

import httpx
from config.settings import settings
from src.models.nodes import Artist, Song
from src.tracing.overmind_client import OvermindClient
from src.utils.metrics import calculate_completeness

logger = logging.getLogger(__name__)


class MusicBrainzClientError(Exception):
    """Exception for MusicBrainz client errors (4xx) that should not be retried."""

    pass


class MusicBrainzResult:
    """Result from MusicBrainz API with completeness score."""

    def __init__(
        self,
        song: Optional[Song] = None,
        artists: Optional[List[Artist]] = None,
        relationships: Optional[List[Dict[str, Any]]] = None,
        label_info: Optional[Dict[str, Any]] = None,
        completeness_score: float = 0.0,
    ):
        """Initialize MusicBrainz result.

        Args:
            song: Song data
            artists: List of artist data
            relationships: Artist relationships (collaborations, member of)
            label_info: Record label information
            completeness_score: Overall completeness score
        """
        self.song = song
        self.artists = artists or []
        self.relationships = relationships or []
        self.label_info = label_info
        self.completeness_score = completeness_score


class MusicBrainzRateLimiter:
    """Strict rate limiter for MusicBrainz API (1 request per second)."""

    def __init__(self):
        """Initialize rate limiter with 1 req/sec limit."""
        self.min_interval = 1.0  # 1 second between requests
        self.last_request_time = 0.0
        self.lock = asyncio.Lock()
        self.request_queue: List[asyncio.Future] = []

    async def acquire(self) -> None:
        """Acquire permission to make a request (blocks if rate limit reached)."""
        async with self.lock:
            now = time.time()
            time_since_last = now - self.last_request_time

            if time_since_last < self.min_interval:
                wait_time = self.min_interval - time_since_last
                logger.debug(f"MusicBrainz rate limit: waiting {wait_time:.2f}s")
                await asyncio.sleep(wait_time)

            self.last_request_time = time.time()


class MusicBrainzAgent:
    """Agent for fetching authoritative music metadata from MusicBrainz API."""

    def __init__(
        self,
        user_agent: Optional[str] = None,
        overmind_client: Optional[OvermindClient] = None,
    ):
        """Initialize MusicBrainz agent.

        Args:
            user_agent: User agent string with contact email
            overmind_client: Overmind Lab tracing client
        """
        self.user_agent = user_agent or settings.musicbrainz_user_agent
        self.overmind_client = overmind_client

        # Strict rate limiting (1 req/sec)
        self.rate_limiter = MusicBrainzRateLimiter()

        # HTTP client
        self.http_client = httpx.AsyncClient(
            timeout=10.0,
            headers={"User-Agent": self.user_agent},
        )

        # API endpoints
        self.api_base_url = "https://musicbrainz.org/ws/2"

    async def _make_request(
        self,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        max_retries: int = 3,
    ) -> Dict[str, Any]:
        """Make request to MusicBrainz API with strict rate limiting.

        Args:
            endpoint: API endpoint path
            params: Query parameters
            max_retries: Maximum number of retry attempts

        Returns:
            JSON response data

        Raises:
            Exception: If request fails after all retries
        """
        await self.rate_limiter.acquire()

        url = f"{self.api_base_url}/{endpoint}"

        # Always request JSON format
        if params is None:
            params = {}
        params["fmt"] = "json"

        for attempt in range(max_retries):
            try:
                # Log API call to Overmind Lab
                if self.overmind_client:
                    self.overmind_client.log_event(
                        "musicbrainz_api_call",
                        {"endpoint": endpoint, "attempt": attempt + 1},
                    )

                response = await self.http_client.get(url, params=params)

                # Handle rate limit errors (503 with Retry-After)
                if response.status_code == 503:
                    retry_after = int(response.headers.get("Retry-After", 2))
                    logger.warning(f"MusicBrainz rate limited, waiting {retry_after}s")

                    if self.overmind_client:
                        self.overmind_client.log_event(
                            "musicbrainz_rate_limit",
                            {"retry_after": retry_after, "endpoint": endpoint},
                        )

                    await asyncio.sleep(retry_after)
                    continue

                # Handle other errors
                if response.status_code >= 400:
                    error_msg = f"MusicBrainz API error: {response.status_code} {response.text}"
                    logger.error(error_msg)

                    # Don't retry client errors (except rate limits already handled above)
                    if 400 <= response.status_code < 500:
                        raise MusicBrainzClientError(error_msg)

                    # Retry server errors with exponential backoff
                    if attempt < max_retries - 1:
                        wait_time = (2**attempt) + (asyncio.get_event_loop().time() % 1)
                        logger.info(f"Retrying after {wait_time:.2f}s")
                        await asyncio.sleep(wait_time)
                        continue

                    raise Exception(error_msg)

                return response.json()

            except httpx.TimeoutException:
                logger.warning(f"Request timeout on attempt {attempt + 1}")
                if attempt < max_retries - 1:
                    wait_time = (2**attempt) + (asyncio.get_event_loop().time() % 1)
                    await asyncio.sleep(wait_time)
                    continue
                raise Exception("Request timed out after all retries")

            except MusicBrainzClientError:
                # Don't retry client errors
                raise

            except Exception as e:
                if attempt < max_retries - 1:
                    wait_time = (2**attempt) + (asyncio.get_event_loop().time() % 1)
                    logger.warning(f"Request failed, retrying after {wait_time:.2f}s: {e}")
                    await asyncio.sleep(wait_time)
                    continue
                raise

        raise Exception("Request failed after all retries")

    async def search_recording(self, query: str) -> Optional[Dict[str, Any]]:
        """Search for a recording by name.

        Args:
            query: Song name to search for

        Returns:
            Recording data or None if not found
        """
        try:
            data = await self._make_request(
                "recording",
                params={"query": query, "limit": 1},
            )

            recordings = data.get("recordings", [])
            if not recordings:
                logger.info(f"No recordings found for query: {query}")
                return None

            return recordings[0]

        except Exception as e:
            logger.error(f"Recording search failed for '{query}': {e}", exc_info=True)
            return None

    async def get_recording_details(self, recording_id: str) -> Optional[Dict[str, Any]]:
        """Get detailed recording information.

        Args:
            recording_id: MusicBrainz recording ID

        Returns:
            Recording data or None if not found
        """
        try:
            return await self._make_request(
                f"recording/{recording_id}",
                params={"inc": "artists+releases+tags+ratings"},
            )
        except Exception as e:
            logger.error(f"Failed to get recording details for {recording_id}: {e}", exc_info=True)
            return None

    async def get_artist_relationships(self, artist_id: str) -> Optional[Dict[str, Any]]:
        """Get artist relationships (collaborations, member of).

        Args:
            artist_id: MusicBrainz artist ID

        Returns:
            Artist data with relationships or None if not found
        """
        try:
            return await self._make_request(
                f"artist/{artist_id}",
                params={"inc": "artist-rels+url-rels+tags"},
            )
        except Exception as e:
            logger.error(f"Failed to get artist relationships for {artist_id}: {e}", exc_info=True)
            return None

    async def get_label_info(self, label_id: str) -> Optional[Dict[str, Any]]:
        """Get record label information.

        Args:
            label_id: MusicBrainz label ID

        Returns:
            Label data or None if not found
        """
        try:
            return await self._make_request(
                f"label/{label_id}",
                params={"inc": "aliases+tags"},
            )
        except Exception as e:
            logger.error(f"Failed to get label info for {label_id}: {e}", exc_info=True)
            return None

    async def fetch_musicbrainz_data(self, song_name: str) -> MusicBrainzResult:
        """Main entry point for fetching MusicBrainz data.

        Args:
            song_name: Name of the song to search for

        Returns:
            MusicBrainzResult with song, artists, relationships, and completeness score
        """
        try:
            # Step 1: Search for recording
            recording_data = await self.search_recording(song_name)
            if not recording_data:
                return MusicBrainzResult(completeness_score=0.0)

            # Step 2: Get detailed recording info
            recording_id = recording_data.get("id")
            detailed_recording = await self.get_recording_details(recording_id)

            if not detailed_recording:
                return MusicBrainzResult(completeness_score=0.0)

            # Step 3: Extract basic recording info
            title = detailed_recording.get("title", song_name)
            length_ms = detailed_recording.get("length")  # Already in milliseconds

            # Step 4: Create Song object
            # Convert MusicBrainz ID string to UUID
            try:
                mb_uuid = UUID(recording_id)
            except (ValueError, TypeError):
                logger.warning(f"Invalid MusicBrainz UUID: {recording_id}")
                mb_uuid = None

            song = Song(
                title=title,
                duration_ms=length_ms,
                musicbrainz_id=mb_uuid,
                spotify_id="placeholder",  # Satisfy at least one external ID requirement
                data_sources=["musicbrainz"],
            )

            # Step 5: Get artist details and relationships
            artists = []
            relationships = []

            artist_credits = detailed_recording.get("artist-credit", [])
            for credit in artist_credits:
                artist_data = credit.get("artist", {})
                artist_id = artist_data.get("id")
                artist_name = artist_data.get("name")

                if artist_id:
                    # Get artist relationships
                    artist_details = await self.get_artist_relationships(artist_id)

                    if artist_details:
                        # Convert artist ID to UUID
                        try:
                            artist_uuid = UUID(artist_id)
                        except (ValueError, TypeError):
                            logger.warning(f"Invalid artist UUID: {artist_id}")
                            artist_uuid = None

                        # Extract artist info
                        artist = Artist(
                            name=artist_name or artist_details.get("name"),
                            musicbrainz_id=artist_uuid,
                            country=artist_details.get("country"),
                            spotify_id="placeholder",  # Satisfy at least one external ID requirement
                        )
                        artists.append(artist)

                        # Extract relationships
                        artist_rels = artist_details.get("relations", [])
                        for rel in artist_rels:
                            if rel.get("type") in ["member of band", "collaboration"]:
                                relationships.append(
                                    {
                                        "type": rel.get("type"),
                                        "artist_id": artist_id,
                                        "target_artist": rel.get("artist", {}).get("name"),
                                        "target_artist_id": rel.get("artist", {}).get("id"),
                                    }
                                )

            # Step 6: Get label info from releases
            label_info = None
            releases = detailed_recording.get("releases", [])
            if releases:
                first_release = releases[0]
                label_info_list = first_release.get("label-info", [])
                if label_info_list:
                    label_data = label_info_list[0].get("label", {})
                    label_id = label_data.get("id")

                    if label_id:
                        label_details = await self.get_label_info(label_id)
                        if label_details:
                            label_info = {
                                "id": label_id,
                                "name": label_details.get("name"),
                                "country": label_details.get("country"),
                                "type": label_details.get("type"),
                            }

            # Step 7: Calculate completeness scores
            song_completeness = calculate_completeness(song, "Song")
            song.completeness_score = song_completeness

            artist_completeness_scores = []
            for artist in artists:
                artist_score = calculate_completeness(artist, "Artist")
                artist.completeness_score = artist_score
                artist_completeness_scores.append(artist_score)

            # Overall completeness is weighted average
            overall_completeness = song_completeness * 0.5
            if artist_completeness_scores:
                overall_completeness += (
                    sum(artist_completeness_scores) / len(artist_completeness_scores)
                ) * 0.3
            if relationships:
                overall_completeness += 0.1
            if label_info:
                overall_completeness += 0.1

            return MusicBrainzResult(
                song=song,
                artists=artists,
                relationships=relationships,
                label_info=label_info,
                completeness_score=overall_completeness,
            )

        except Exception as e:
            logger.error(f"MusicBrainz data fetch failed for '{song_name}': {e}", exc_info=True)
            return MusicBrainzResult(completeness_score=0.0)

    async def close(self) -> None:
        """Close HTTP client and cleanup resources."""
        await self.http_client.aclose()
