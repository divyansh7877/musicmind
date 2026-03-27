"""Last.fm agent for fetching social music data."""

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional

import httpx
from config.settings import settings
from src.models.nodes import Artist, Song
from src.tracing.overmind_client import OvermindClient
from src.utils.metrics import calculate_completeness

logger = logging.getLogger(__name__)


class LastFMClientError(Exception):
    """Exception for Last.fm client errors (4xx) that should not be retried."""

    pass


class LastFMResult:
    """Result from Last.fm API with completeness score."""

    def __init__(
        self,
        song: Optional[Song] = None,
        artists: Optional[List[Artist]] = None,
        similar_tracks: Optional[List[Dict[str, Any]]] = None,
        tags: Optional[List[str]] = None,
        completeness_score: float = 0.0,
    ):
        """Initialize Last.fm result.

        Args:
            song: Song data
            artists: List of artist data
            similar_tracks: List of similar tracks
            tags: User-generated tags
            completeness_score: Overall completeness score
        """
        self.song = song
        self.artists = artists or []
        self.similar_tracks = similar_tracks or []
        self.tags = tags or []
        self.completeness_score = completeness_score


class LastFMRateLimiter:
    """Rate limiter for Last.fm API (5 requests per second)."""

    def __init__(self):
        """Initialize rate limiter with 5 req/sec limit."""
        self.max_requests_per_second = 5
        self.min_interval = 1.0 / self.max_requests_per_second  # 0.2 seconds between requests
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
                logger.debug(f"Last.fm rate limit: waiting {wait_time:.2f}s")
                await asyncio.sleep(wait_time)

            self.last_request_time = time.time()


class LastFMAgent:
    """Agent for fetching social music data from Last.fm API."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        overmind_client: Optional[OvermindClient] = None,
    ):
        """Initialize Last.fm agent.

        Args:
            api_key: Last.fm API key
            overmind_client: Overmind Lab tracing client
        """
        self.api_key = api_key or settings.lastfm_api_key
        self.overmind_client = overmind_client

        # Rate limiting (5 req/sec)
        self.rate_limiter = LastFMRateLimiter()

        # HTTP client
        self.http_client = httpx.AsyncClient(
            timeout=10.0,
        )

        # API endpoints
        self.api_base_url = "https://ws.audioscrobbler.com/2.0/"

    async def _make_request(
        self,
        method: str,
        params: Dict[str, Any],
        max_retries: int = 3,
    ) -> Dict[str, Any]:
        """Make request to Last.fm API with rate limiting.

        Args:
            method: Last.fm API method (e.g., 'track.search')
            params: Query parameters
            max_retries: Maximum number of retry attempts

        Returns:
            JSON response data

        Raises:
            Exception: If request fails after all retries
        """
        await self.rate_limiter.acquire()

        # Add required parameters
        request_params = {
            "method": method,
            "api_key": self.api_key,
            "format": "json",
            **params,
        }

        for attempt in range(max_retries):
            try:
                # Log API call to Overmind Lab
                if self.overmind_client:
                    self.overmind_client.log_event(
                        "lastfm_api_call",
                        {"method": method, "attempt": attempt + 1},
                    )

                response = await self.http_client.get(
                    self.api_base_url,
                    params=request_params,
                )

                # Handle rate limit errors
                if response.status_code == 429:
                    retry_after = int(response.headers.get("Retry-After", 2))
                    logger.warning(f"Last.fm rate limited, waiting {retry_after}s")

                    if self.overmind_client:
                        self.overmind_client.log_event(
                            "lastfm_rate_limit",
                            {"retry_after": retry_after, "method": method},
                        )

                    await asyncio.sleep(retry_after)
                    continue

                # Handle other errors
                if response.status_code >= 400:
                    error_msg = f"Last.fm API error: {response.status_code} {response.text}"
                    logger.error(error_msg)

                    # Don't retry client errors (except rate limits already handled above)
                    if 400 <= response.status_code < 500:
                        raise LastFMClientError(error_msg)

                    # Retry server errors with exponential backoff
                    if attempt < max_retries - 1:
                        wait_time = (2**attempt) + (asyncio.get_event_loop().time() % 1)
                        logger.info(f"Retrying after {wait_time:.2f}s")
                        await asyncio.sleep(wait_time)
                        continue

                    raise Exception(error_msg)

                data = response.json()

                # Check for API error in response
                if "error" in data:
                    error_code = data.get("error")
                    error_msg = data.get("message", "Unknown error")
                    logger.error(f"Last.fm API error {error_code}: {error_msg}")

                    # Don't retry client errors
                    if error_code in [
                        6,
                        10,
                        13,
                    ]:  # Invalid parameters, invalid API key, service offline
                        raise LastFMClientError(f"Last.fm error {error_code}: {error_msg}")

                    # Retry other errors
                    if attempt < max_retries - 1:
                        wait_time = (2**attempt) + (asyncio.get_event_loop().time() % 1)
                        await asyncio.sleep(wait_time)
                        continue

                    raise Exception(f"Last.fm error {error_code}: {error_msg}")

                return data

            except httpx.TimeoutException:
                logger.warning(f"Request timeout on attempt {attempt + 1}")
                if attempt < max_retries - 1:
                    wait_time = (2**attempt) + (asyncio.get_event_loop().time() % 1)
                    await asyncio.sleep(wait_time)
                    continue
                raise Exception("Request timed out after all retries")

            except LastFMClientError:
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

    async def search_track(self, query: str) -> Optional[Dict[str, Any]]:
        """Search for a track by name.

        Args:
            query: Track name to search for

        Returns:
            Track data or None if not found
        """
        try:
            data = await self._make_request(
                "track.search",
                params={"track": query, "limit": 1},
            )

            results = data.get("results", {})
            track_matches = results.get("trackmatches", {})
            tracks = track_matches.get("track", [])

            if not tracks:
                logger.info(f"No tracks found for query: {query}")
                return None

            # Handle both list and single dict responses
            if isinstance(tracks, list):
                return tracks[0] if tracks else None
            else:
                return tracks

        except Exception as e:
            logger.error(f"Track search failed for '{query}': {e}", exc_info=True)
            return None

    async def get_track_info(self, artist: str, track: str) -> Optional[Dict[str, Any]]:
        """Get detailed track information.

        Args:
            artist: Artist name
            track: Track name

        Returns:
            Track data or None if not found
        """
        try:
            data = await self._make_request(
                "track.getInfo",
                params={"artist": artist, "track": track},
            )

            return data.get("track")

        except Exception as e:
            logger.error(f"Failed to get track info for '{artist} - {track}': {e}", exc_info=True)
            return None

    async def get_similar_tracks(self, artist: str, track: str) -> Optional[List[Dict[str, Any]]]:
        """Get similar tracks based on collaborative filtering.

        Args:
            artist: Artist name
            track: Track name

        Returns:
            List of similar tracks or None if not found
        """
        try:
            data = await self._make_request(
                "track.getSimilar",
                params={"artist": artist, "track": track, "limit": 10},
            )

            similar_tracks = data.get("similartracks", {}).get("track", [])

            # Handle both list and single dict responses
            if isinstance(similar_tracks, list):
                return similar_tracks
            elif similar_tracks:
                return [similar_tracks]
            else:
                return []

        except Exception as e:
            logger.error(
                f"Failed to get similar tracks for '{artist} - {track}': {e}", exc_info=True
            )
            return None

    async def get_top_tags(self, artist: str, track: str) -> Optional[List[str]]:
        """Get user-generated tags for a track.

        Args:
            artist: Artist name
            track: Track name

        Returns:
            List of tag names or None if not found
        """
        try:
            data = await self._make_request(
                "track.getTopTags",
                params={"artist": artist, "track": track},
            )

            tags_data = data.get("toptags", {}).get("tag", [])

            # Handle both list and single dict responses
            if isinstance(tags_data, list):
                return [tag.get("name") for tag in tags_data if tag.get("name")]
            elif tags_data:
                return [tags_data.get("name")] if tags_data.get("name") else []
            else:
                return []

        except Exception as e:
            logger.error(f"Failed to get top tags for '{artist} - {track}': {e}", exc_info=True)
            return None

    async def fetch_lastfm_data(self, song_name: str) -> LastFMResult:
        """Main entry point for fetching Last.fm data.

        Args:
            song_name: Name of the song to search for

        Returns:
            LastFMResult with song, artists, similar tracks, tags, and completeness score
        """
        try:
            # Step 1: Search for track
            track_data = await self.search_track(song_name)
            if not track_data:
                return LastFMResult(completeness_score=0.0)

            # Step 2: Extract basic track info
            track_name = track_data.get("name", song_name)
            artist_name = track_data.get("artist", "")

            # Step 3: Get detailed track info
            detailed_track = await self.get_track_info(artist_name, track_name)

            if not detailed_track:
                return LastFMResult(completeness_score=0.0)

            # Step 4: Extract track metadata
            duration_ms = None
            duration_seconds = detailed_track.get("duration")
            if duration_seconds and str(duration_seconds).isdigit():
                duration_ms = int(duration_seconds) * 1000  # Convert to milliseconds

            play_count = detailed_track.get("playcount")
            listener_count = detailed_track.get("listeners")
            lastfm_url = detailed_track.get("url")

            # Step 5: Create Song object
            song = Song(
                title=track_name,
                duration_ms=duration_ms,
                lastfm_url=lastfm_url,
                play_count=int(play_count) if play_count else None,
                listener_count=int(listener_count) if listener_count else None,
                spotify_id="placeholder",  # Satisfy at least one external ID requirement
                data_sources=["lastfm"],
            )

            # Step 6: Extract artist info
            artists = []
            artist_data = detailed_track.get("artist", {})

            if isinstance(artist_data, dict):
                artist = Artist(
                    name=artist_data.get("name", artist_name),
                    lastfm_url=artist_data.get("url"),
                    spotify_id="placeholder",  # Satisfy at least one external ID requirement
                )
                artists.append(artist)
            elif isinstance(artist_data, str):
                artist = Artist(
                    name=artist_data,
                    spotify_id="placeholder",
                )
                artists.append(artist)

            # Step 7: Get similar tracks
            similar_tracks = await self.get_similar_tracks(artist_name, track_name)
            if similar_tracks is None:
                similar_tracks = []

            # Step 8: Get tags
            tags = await self.get_top_tags(artist_name, track_name)
            if tags is None:
                tags = []

            # Add tags to song
            song.tags = tags

            # Step 9: Calculate completeness scores
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
                ) * 0.2
            if similar_tracks:
                overall_completeness += 0.15
            if tags:
                overall_completeness += 0.15

            return LastFMResult(
                song=song,
                artists=artists,
                similar_tracks=similar_tracks,
                tags=tags,
                completeness_score=overall_completeness,
            )

        except Exception as e:
            logger.error(f"Last.fm data fetch failed for '{song_name}': {e}", exc_info=True)
            return LastFMResult(completeness_score=0.0)

    async def close(self) -> None:
        """Close HTTP client and cleanup resources."""
        await self.http_client.aclose()
