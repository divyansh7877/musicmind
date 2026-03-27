"""Spotify agent for fetching music data from Spotify Web API."""

import asyncio
import logging
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from uuid import UUID

import httpx
from config.settings import settings
from src.agents.orchestrator import AgentResult
from src.models.nodes import Album, Artist, AudioFeatures, Song
from src.tracing.overmind_client import OvermindClient
from src.utils.metrics import calculate_completeness

logger = logging.getLogger(__name__)


class SpotifyResult:
    """Result from Spotify API with completeness score."""

    def __init__(
        self,
        song: Optional[Song] = None,
        artists: Optional[List[Artist]] = None,
        album: Optional[Album] = None,
        completeness_score: float = 0.0,
    ):
        """Initialize Spotify result.

        Args:
            song: Song data
            artists: List of artist data
            album: Album data
            completeness_score: Overall completeness score
        """
        self.song = song
        self.artists = artists or []
        self.album = album
        self.completeness_score = completeness_score


class RateLimiter:
    """Token bucket rate limiter for API requests."""

    def __init__(self, requests_per_minute: int = 100, burst_allowance: int = 10):
        """Initialize rate limiter.

        Args:
            requests_per_minute: Maximum requests per minute
            burst_allowance: Additional burst capacity
        """
        self.requests_per_minute = requests_per_minute
        self.burst_allowance = burst_allowance
        self.max_tokens = requests_per_minute + burst_allowance
        self.tokens = self.max_tokens
        self.last_update = time.time()
        self.lock = asyncio.Lock()

    async def acquire(self) -> None:
        """Acquire permission to make a request (blocks if rate limit reached)."""
        async with self.lock:
            now = time.time()
            elapsed = now - self.last_update

            # Refill tokens based on elapsed time
            tokens_to_add = elapsed * (self.requests_per_minute / 60.0)
            self.tokens = min(self.max_tokens, self.tokens + tokens_to_add)
            self.last_update = now

            # Wait if no tokens available
            if self.tokens < 1.0:
                wait_time = (1.0 - self.tokens) / (self.requests_per_minute / 60.0)
                logger.debug(f"Rate limit reached, waiting {wait_time:.2f}s")
                await asyncio.sleep(wait_time)
                self.tokens = 1.0
                self.last_update = time.time()

            # Consume one token
            self.tokens -= 1.0


class SpotifyAgent:
    """Agent for fetching music data from Spotify Web API."""

    def __init__(
        self,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        overmind_client: Optional[OvermindClient] = None,
    ):
        """Initialize Spotify agent.

        Args:
            client_id: Spotify API client ID
            client_secret: Spotify API client secret
            overmind_client: Overmind Lab tracing client
        """
        self.client_id = client_id or settings.spotify_client_id
        self.client_secret = client_secret or settings.spotify_client_secret
        self.overmind_client = overmind_client

        # OAuth2 token management
        self.access_token: Optional[str] = None
        self.token_expires_at: Optional[datetime] = None

        # Rate limiting
        self.rate_limiter = RateLimiter(requests_per_minute=100, burst_allowance=10)

        # HTTP client
        self.http_client = httpx.AsyncClient(timeout=10.0)

        # API endpoints
        self.token_url = "https://accounts.spotify.com/api/token"
        self.api_base_url = "https://api.spotify.com/v1"

    async def _authenticate(self) -> None:
        """Authenticate with Spotify API using OAuth2 client credentials flow."""
        try:
            response = await self.http_client.post(
                self.token_url,
                data={
                    "grant_type": "client_credentials",
                },
                auth=(self.client_id, self.client_secret),
            )

            if response.status_code != 200:
                raise Exception(f"Authentication failed: {response.status_code} {response.text}")

            data = response.json()
            self.access_token = data["access_token"]
            expires_in = data.get("expires_in", 3600)

            # Set expiration with 5-minute buffer
            self.token_expires_at = datetime.utcnow() + timedelta(seconds=expires_in - 300)

            logger.info("Spotify authentication successful")

        except Exception as e:
            logger.error(f"Spotify authentication failed: {e}", exc_info=True)
            raise

    async def _ensure_authenticated(self) -> None:
        """Ensure we have a valid access token, refreshing if necessary."""
        if not self.access_token or not self.token_expires_at:
            await self._authenticate()
        elif datetime.utcnow() >= self.token_expires_at:
            logger.info("Access token expired, refreshing")
            await self._authenticate()

    async def _make_request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        max_retries: int = 3,
    ) -> Dict[str, Any]:
        """Make authenticated request to Spotify API with rate limiting and retries.

        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint path
            params: Query parameters
            max_retries: Maximum number of retry attempts

        Returns:
            JSON response data

        Raises:
            Exception: If request fails after all retries
        """
        await self._ensure_authenticated()
        await self.rate_limiter.acquire()

        url = f"{self.api_base_url}/{endpoint}"
        headers = {"Authorization": f"Bearer {self.access_token}"}

        for attempt in range(max_retries):
            try:
                # Log API call to Overmind Lab
                if self.overmind_client:
                    self.overmind_client.log_event(
                        "spotify_api_call",
                        {"endpoint": endpoint, "attempt": attempt + 1},
                    )

                response = await self.http_client.request(
                    method, url, headers=headers, params=params
                )

                # Handle rate limit errors
                if response.status_code == 429:
                    retry_after = int(response.headers.get("Retry-After", 1))
                    logger.warning(f"Rate limited by Spotify, waiting {retry_after}s")

                    if self.overmind_client:
                        self.overmind_client.log_event(
                            "spotify_rate_limit",
                            {"retry_after": retry_after, "endpoint": endpoint},
                        )

                    await asyncio.sleep(retry_after)
                    continue

                # Handle other errors
                if response.status_code >= 400:
                    error_msg = f"Spotify API error: {response.status_code} {response.text}"
                    logger.error(error_msg)

                    # Don't retry client errors (except rate limits)
                    if 400 <= response.status_code < 500:
                        raise Exception(error_msg)

                    # Retry server errors with exponential backoff
                    if attempt < max_retries - 1:
                        wait_time = (2 ** attempt) + (asyncio.get_event_loop().time() % 1)
                        logger.info(f"Retrying after {wait_time:.2f}s")
                        await asyncio.sleep(wait_time)
                        continue

                    raise Exception(error_msg)

                return response.json()

            except httpx.TimeoutException:
                logger.warning(f"Request timeout on attempt {attempt + 1}")
                if attempt < max_retries - 1:
                    wait_time = (2 ** attempt) + (asyncio.get_event_loop().time() % 1)
                    await asyncio.sleep(wait_time)
                    continue
                raise Exception("Request timed out after all retries")

            except Exception as e:
                if attempt < max_retries - 1:
                    wait_time = (2 ** attempt) + (asyncio.get_event_loop().time() % 1)
                    logger.warning(f"Request failed, retrying after {wait_time:.2f}s: {e}")
                    await asyncio.sleep(wait_time)
                    continue
                raise

        raise Exception("Request failed after all retries")

    async def search_track(self, query: str) -> Optional[Dict[str, Any]]:
        """Search for a track by name.

        Args:
            query: Song name to search for

        Returns:
            Track data or None if not found
        """
        try:
            data = await self._make_request(
                "GET",
                "search",
                params={"q": query, "type": "track", "limit": 1},
            )

            tracks = data.get("tracks", {}).get("items", [])
            if not tracks:
                logger.info(f"No tracks found for query: {query}")
                return None

            return tracks[0]

        except Exception as e:
            logger.error(f"Track search failed for '{query}': {e}", exc_info=True)
            return None

    async def get_artist_details(self, artist_id: str) -> Optional[Dict[str, Any]]:
        """Get detailed artist information.

        Args:
            artist_id: Spotify artist ID

        Returns:
            Artist data or None if not found
        """
        try:
            return await self._make_request("GET", f"artists/{artist_id}")
        except Exception as e:
            logger.error(f"Failed to get artist details for {artist_id}: {e}", exc_info=True)
            return None

    async def get_album_details(self, album_id: str) -> Optional[Dict[str, Any]]:
        """Get detailed album information.

        Args:
            album_id: Spotify album ID

        Returns:
            Album data or None if not found
        """
        try:
            return await self._make_request("GET", f"albums/{album_id}")
        except Exception as e:
            logger.error(f"Failed to get album details for {album_id}: {e}", exc_info=True)
            return None

    async def get_audio_features(self, track_id: str) -> Optional[Dict[str, Any]]:
        """Get audio features for a track.

        Args:
            track_id: Spotify track ID

        Returns:
            Audio features data or None if not found
        """
        try:
            return await self._make_request("GET", f"audio-features/{track_id}")
        except Exception as e:
            logger.error(f"Failed to get audio features for {track_id}: {e}", exc_info=True)
            return None

    async def fetch_spotify_data(self, song_name: str) -> SpotifyResult:
        """Main entry point for fetching Spotify data.

        Args:
            song_name: Name of the song to search for

        Returns:
            SpotifyResult with song, artists, album, and completeness score
        """
        try:
            # Step 1: Search for track
            track_data = await self.search_track(song_name)
            if not track_data:
                return SpotifyResult(completeness_score=0.0)

            # Step 2: Extract basic track info
            track_id = track_data["id"]
            track_name = track_data["name"]
            duration_ms = track_data.get("duration_ms")
            track_popularity = track_data.get("popularity")

            # Step 3: Get audio features
            audio_features_data = await self.get_audio_features(track_id)
            audio_features = None
            if audio_features_data:
                audio_features = AudioFeatures(
                    tempo=audio_features_data.get("tempo"),
                    key=audio_features_data.get("key"),
                    mode=audio_features_data.get("mode"),
                    time_signature=audio_features_data.get("time_signature"),
                    energy=audio_features_data.get("energy"),
                    danceability=audio_features_data.get("danceability"),
                    valence=audio_features_data.get("valence"),
                    acousticness=audio_features_data.get("acousticness"),
                )

            # Step 4: Create Song object
            song = Song(
                title=track_name,
                duration_ms=duration_ms,
                spotify_id=track_id,
                audio_features=audio_features,
                data_sources=["spotify"],
            )

            # Step 5: Get artist details
            artists = []
            artist_data_list = track_data.get("artists", [])
            for artist_data in artist_data_list:
                artist_id = artist_data["id"]
                detailed_artist = await self.get_artist_details(artist_id)

                if detailed_artist:
                    artist = Artist(
                        name=detailed_artist["name"],
                        genres=detailed_artist.get("genres", []),
                        spotify_id=artist_id,
                        popularity=detailed_artist.get("popularity"),
                        follower_count=detailed_artist.get("followers", {}).get("total"),
                        image_urls=[img["url"] for img in detailed_artist.get("images", [])],
                    )
                    artists.append(artist)

            # Step 6: Get album details
            album = None
            album_data = track_data.get("album")
            if album_data:
                album_id = album_data["id"]
                detailed_album = await self.get_album_details(album_id)

                if detailed_album:
                    # Parse release date
                    release_date = None
                    release_date_str = detailed_album.get("release_date")
                    if release_date_str:
                        try:
                            # Handle different date formats (YYYY, YYYY-MM, YYYY-MM-DD)
                            if len(release_date_str) == 4:
                                release_date = datetime.strptime(release_date_str, "%Y").date()
                            elif len(release_date_str) == 7:
                                release_date = datetime.strptime(release_date_str, "%Y-%m").date()
                            else:
                                release_date = datetime.strptime(release_date_str, "%Y-%m-%d").date()
                        except ValueError:
                            logger.warning(f"Invalid release date format: {release_date_str}")

                    album = Album(
                        title=detailed_album["name"],
                        release_date=release_date,
                        album_type=detailed_album.get("album_type", "album"),
                        total_tracks=detailed_album.get("total_tracks"),
                        spotify_id=album_id,
                        label=detailed_album.get("label"),
                        cover_art_url=detailed_album.get("images", [{}])[0].get("url") if detailed_album.get("images") else None,
                    )

            # Step 7: Calculate completeness scores
            song_completeness = calculate_completeness(song, "Song")
            song.completeness_score = song_completeness

            artist_completeness_scores = []
            for artist in artists:
                artist_score = calculate_completeness(artist, "Artist")
                artist.completeness_score = artist_score
                artist_completeness_scores.append(artist_score)

            album_completeness = 0.0
            if album:
                album_completeness = calculate_completeness(album, "Album")
                album.completeness_score = album_completeness

            # Overall completeness is weighted average
            overall_completeness = song_completeness * 0.5
            if artist_completeness_scores:
                overall_completeness += (sum(artist_completeness_scores) / len(artist_completeness_scores)) * 0.3
            if album:
                overall_completeness += album_completeness * 0.2

            return SpotifyResult(
                song=song,
                artists=artists,
                album=album,
                completeness_score=overall_completeness,
            )

        except Exception as e:
            logger.error(f"Spotify data fetch failed for '{song_name}': {e}", exc_info=True)
            return SpotifyResult(completeness_score=0.0)

    async def close(self) -> None:
        """Close HTTP client and cleanup resources."""
        await self.http_client.aclose()
