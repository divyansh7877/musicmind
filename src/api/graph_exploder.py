"""Graph explosion service for expanding the knowledge graph.

This service takes an existing graph and "explodes" it by fetching additional
information for each node. For each artist, it fetches top songs and albums.
For each song, it fetches similar tracks from LastFM.
"""

import asyncio
import hashlib
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

from src.agents.spotify_agent import SpotifyAgent
from src.agents.lastfm_agent import LastFMAgent
from src.cache.redis_client import RedisClient
from src.tracing.overmind_client import OvermindClient

logger = logging.getLogger(__name__)

MAX_ITEMS_PER_CATEGORY = 3  # Limit for each category during explosion


class GraphExploder:
    """Explodes an existing graph by enriching each node with additional data."""

    def __init__(
        self,
        cache_client: Optional[RedisClient] = None,
        overmind_client: Optional[OvermindClient] = None,
        db_client: Optional[Any] = None,
    ):
        """Initialize graph exploder.

        Args:
            cache_client: Redis cache client
            overmind_client: Overmind Lab tracing client
            db_client: Aerospike database client for graph operations
        """
        self.cache_client = cache_client or RedisClient()
        self.overmind_client = overmind_client
        self.db_client = db_client

    def _deterministic_id(self, namespace: str, name: str) -> str:
        """Generate a deterministic ID from namespace and name."""
        h = hashlib.sha256(f"{namespace}:{name.lower().strip()}".encode()).hexdigest()
        return str(UUID(h[:32]))

    async def explode_graph(
        self,
        nodes: List[Dict[str, Any]],
        edges: List[Dict[str, Any]],
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Explode the graph by enriching each node.

        For each artist in the graph, fetches top songs and albums (up to MAX_ITEMS_PER_CATEGORY).
        For each song, fetches similar tracks from LastFM (up to MAX_ITEMS_PER_CATEGORY).
        For each album, fetches album tracks (up to MAX_ITEMS_PER_CATEGORY).

        Args:
            nodes: Current graph nodes
            edges: Current graph edges

        Returns:
            Tuple of (new_nodes, new_edges) to add to the graph
        """
        artists = [n for n in nodes if n.get("type") == "Artist"]
        songs = [n for n in nodes if n.get("type") == "Song"]
        albums = [n for n in nodes if n.get("type") == "Album"]

        logger.info(
            f"[EXPLODE] Starting explosion: {len(artists)} artists, "
            f"{len(songs)} songs, {len(albums)} albums"
        )

        new_nodes: List[Dict[str, Any]] = []
        new_edges: List[Dict[str, Any]] = []

        # Explode artists: get top songs and albums for each
        artist_tasks = [
            self._explode_artist(artist, songs, new_nodes, new_edges)
            for artist in artists
        ]
        await asyncio.gather(*artist_tasks, return_exceptions=True)

        # Explode songs: get similar tracks from LastFM
        song_tasks = [
            self._explode_song(song, new_nodes, new_edges)
            for song in songs
        ]
        await asyncio.gather(*song_tasks, return_exceptions=True)

        # Explode albums: get tracks from Spotify
        album_tasks = [
            self._explode_album(album, new_nodes, new_edges)
            for album in albums
        ]
        await asyncio.gather(*album_tasks, return_exceptions=True)

        logger.info(
            f"[EXPLODE] Explosion complete: {len(new_nodes)} new nodes, {len(new_edges)} new edges"
        )

        return new_nodes, new_edges

    async def _explode_artist(
        self,
        artist: Dict[str, Any],
        existing_songs: List[Dict[str, Any]],
        new_nodes: List[Dict[str, Any]],
        new_edges: List[Dict[str, Any]],
    ) -> None:
        """Explode an artist node by fetching top songs and albums.

        Args:
            artist: Artist node data
            existing_songs: List of existing song nodes to avoid duplicates
            new_nodes: Output list for new nodes
            new_edges: Output list for new edges
        """
        artist_name = artist.get("data", {}).get("name") or artist.get("data", {}).get("label", "")
        if not artist_name:
            return

        spotify_id = artist.get("data", {}).get("spotify_id")

        # Determine existing song titles to avoid duplicates
        existing_titles = {
            s.get("data", {}).get("title", "").lower()
            for s in existing_songs
        }
        existing_titles.update(
            n.get("data", {}).get("title", "").lower()
            for n in new_nodes if n.get("type") == "Song"
        )

        spotify_agent = SpotifyAgent(overmind_client=self.overmind_client)
        try:
            # Resolve spotify_id: skip if placeholder and search by artist name
            if not spotify_id or spotify_id == "placeholder":
                logger.debug(f"[EXPLODE] Searching Spotify for artist '{artist_name}'")
                resolved = await spotify_agent.search_artist(artist_name)
                if not resolved:
                    logger.debug(f"[EXPLODE] No Spotify result for artist '{artist_name}'")
                    return
                spotify_id = resolved.get("id")
                if not spotify_id:
                    return

            # Fetch top tracks and albums in parallel
            top_tracks, albums_data = await asyncio.gather(
                spotify_agent.get_artist_top_tracks(spotify_id, limit=MAX_ITEMS_PER_CATEGORY),
                spotify_agent.get_artist_albums(spotify_id, limit=MAX_ITEMS_PER_CATEGORY),
            )

            # Add new song nodes from top tracks
            for track in top_tracks:
                track_title = track.get("name", "")
                if not track_title or track_title.lower() in existing_titles:
                    continue

                track_id = self._deterministic_id("song", track_title)
                album_data = track.get("album", {})
                album_name = album_data.get("name", "")

                song_node = {
                    "id": track_id,
                    "type": "Song",
                    "data": {
                        "id": track_id,
                        "title": track_title,
                        "spotify_id": track.get("id"),
                        "duration_ms": track.get("duration_ms"),
                        "popularity": track.get("popularity"),
                        "label": track_title,
                        "last_enriched": datetime.utcnow().isoformat(),
                    },
                }
                new_nodes.append(song_node)
                existing_titles.add(track_title.lower())

                # Edge: Artist --PERFORMED_IN--> Song
                artist_id = artist.get("id", self._deterministic_id("artist", artist_name))
                new_edges.append({
                    "from_node_id": artist_id,
                    "to_node_id": track_id,
                    "edge_type": "PERFORMED_IN",
                    "properties": {},
                })

                # If we have album info, create album node too
                if album_name:
                    album_id = self._deterministic_id("album", album_name)
                    if not any(
                        n.get("id") == album_id for n in new_nodes + [artist]
                    ):
                        album_node = {
                            "id": album_id,
                            "type": "Album",
                            "data": {
                                "id": album_id,
                                "title": album_name,
                                "spotify_id": album_data.get("id"),
                                "label": album_name,
                                "last_enriched": datetime.utcnow().isoformat(),
                            },
                        }
                        new_nodes.append(album_node)

                        # Edge: Song --PART_OF_ALBUM--> Album
                        new_edges.append({
                            "from_node_id": track_id,
                            "to_node_id": album_id,
                            "edge_type": "PART_OF_ALBUM",
                            "properties": {},
                        })

            # Add new album nodes
            for album_data in albums_data:
                album_name = album_data.get("name", "")
                if not album_name:
                    continue

                album_id = self._deterministic_id("album", album_name)
                # Skip if album already exists
                if any(n.get("id") == album_id for n in new_nodes + [artist]):
                    continue

                album_node = {
                    "id": album_id,
                    "type": "Album",
                    "data": {
                        "id": album_id,
                        "title": album_name,
                        "spotify_id": album_data.get("id"),
                        "label": album_name,
                        "album_type": album_data.get("album_type", "album"),
                        "release_date": album_data.get("release_date"),
                        "total_tracks": album_data.get("total_tracks"),
                        "last_enriched": datetime.utcnow().isoformat(),
                    },
                }
                new_nodes.append(album_node)

                # Edge: Artist --PART_OF_ALBUM_IN--> Album
                artist_id = artist.get("id", self._deterministic_id("artist", artist_name))
                new_edges.append({
                    "from_node_id": artist_id,
                    "to_node_id": album_id,
                    "edge_type": "PART_OF_ALBUM_IN",
                    "properties": {},
                })

            logger.info(
                f"[EXPLODE] Artist '{artist_name}': "
                f"+{len(top_tracks)} songs, +{len(albums_data)} albums"
            )
        except Exception as e:
            logger.error(f"[EXPLODE] Failed to explode artist '{artist_name}': {e}", exc_info=True)
        finally:
            await spotify_agent.close()

    async def _explode_song(
        self,
        song: Dict[str, Any],
        new_nodes: List[Dict[str, Any]],
        new_edges: List[Dict[str, Any]],
    ) -> None:
        """Explode a song node by fetching similar tracks from LastFM.

        Args:
            song: Song node data
            new_nodes: Output list for new nodes
            new_edges: Output list for new edges
        """
        song_data = song.get("data", {})
        song_title = song_data.get("title") or song_data.get("label", "")
        if not song_title:
            return

        # Get artist name from the song's data or edges
        artist_name = song_data.get("artist_name", "")

        # Try to get artist name from edges
        if not artist_name:
            # Look for PERFORMED_IN edge where this song is the target
            # We don't have edges here, so skip if no artist name
            logger.debug(f"[EXPLODE] No artist name for song '{song_title}', skipping similar tracks")
            return

        # Determine existing song titles to avoid duplicates
        existing_titles = {
            n.get("data", {}).get("title", "").lower()
            for n in new_nodes
        }

        lastfm_agent = LastFMAgent(overmind_client=self.overmind_client)
        try:
            similar = await lastfm_agent.get_similar_tracks(artist_name, song_title)
            if not similar:
                return

            song_id = song.get("id", self._deterministic_id("song", song_title))

            for track in similar[:MAX_ITEMS_PER_CATEGORY]:
                track_title = track.get("name", "")
                track_artist = track.get("artist", {}).get("name", "") if isinstance(track.get("artist"), dict) else track.get("artist", "")
                if not track_title or track_title.lower() in existing_titles:
                    continue

                track_id = self._deterministic_id("song", track_title)
                similar_song_node = {
                    "id": track_id,
                    "type": "Song",
                    "data": {
                        "id": track_id,
                        "title": track_title,
                        "artist_name": track_artist,
                        "lastfm_url": track.get("url"),
                        "label": track_title,
                        "last_enriched": datetime.utcnow().isoformat(),
                    },
                }
                new_nodes.append(similar_song_node)
                existing_titles.add(track_title.lower())

                # Edge: Song --SIMILAR_TO--> SimilarSong
                new_edges.append({
                    "from_node_id": song_id,
                    "to_node_id": track_id,
                    "edge_type": "SIMILAR_TO",
                    "properties": {},
                })

                # Create artist node for similar track if we have artist name
                if track_artist:
                    artist_id = self._deterministic_id("artist", track_artist)
                    if not any(n.get("id") == artist_id for n in new_nodes):
                        artist_node = {
                            "id": artist_id,
                            "type": "Artist",
                            "data": {
                                "id": artist_id,
                                "name": track_artist,
                                "label": track_artist,
                                "last_enriched": datetime.utcnow().isoformat(),
                            },
                        }
                        new_nodes.append(artist_node)

                    # Edge: SimilarArtist --PERFORMED_IN--> SimilarSong
                    new_edges.append({
                        "from_node_id": artist_id,
                        "to_node_id": track_id,
                        "edge_type": "PERFORMED_IN",
                        "properties": {},
                    })

            logger.info(
                f"[EXPLODE] Song '{song_title}': +{min(len(similar), MAX_ITEMS_PER_CATEGORY)} similar tracks"
            )
        except Exception as e:
            logger.error(f"[EXPLODE] Failed to explode song '{song_title}': {e}", exc_info=True)
        finally:
            await lastfm_agent.close()

    async def _explode_album(
        self,
        album: Dict[str, Any],
        new_nodes: List[Dict[str, Any]],
        new_edges: List[Dict[str, Any]],
    ) -> None:
        """Explode an album node by fetching its tracks from Spotify.

        Args:
            album: Album node data
            new_nodes: Output list for new nodes
            new_edges: Output list for new edges
        """
        album_data = album.get("data", {})
        album_name = album_data.get("title") or album_data.get("label", "")
        if not album_name:
            return

        spotify_id = album_data.get("spotify_id")

        # Determine existing song titles to avoid duplicates
        existing_titles = {
            n.get("data", {}).get("title", "").lower()
            for n in new_nodes
        }

        spotify_agent = SpotifyAgent(overmind_client=self.overmind_client)
        try:
            # Resolve spotify_id: search by album name if placeholder/missing
            if not spotify_id or spotify_id == "placeholder":
                logger.debug(f"[EXPLODE] Searching Spotify for album '{album_name}'")
                resolved = await spotify_agent.search_album(album_name)
                if not resolved:
                    logger.debug(f"[EXPLODE] No Spotify result for album '{album_name}'")
                    return
                spotify_id = resolved.get("id")
                if not spotify_id:
                    return

            album_details = await spotify_agent.get_album_details(spotify_id)
            if not album_details:
                return

            album_id = album.get("id", self._deterministic_id("album", album_name))
            tracks = album_details.get("tracks", {}).get("items", [])

            for track in tracks[:MAX_ITEMS_PER_CATEGORY]:
                track_title = track.get("name", "")
                if not track_title or track_title.lower() in existing_titles:
                    continue

                track_id = self._deterministic_id("song", track_title)
                track_node = {
                    "id": track_id,
                    "type": "Song",
                    "data": {
                        "id": track_id,
                        "title": track_title,
                        "spotify_id": track.get("id"),
                        "duration_ms": track.get("duration_ms"),
                        "label": track_title,
                        "last_enriched": datetime.utcnow().isoformat(),
                    },
                }
                new_nodes.append(track_node)
                existing_titles.add(track_title.lower())

                # Edge: Song --PART_OF_ALBUM--> Album
                new_edges.append({
                    "from_node_id": track_id,
                    "to_node_id": album_id,
                    "edge_type": "PART_OF_ALBUM",
                    "properties": {"track_number": track.get("track_number")},
                })

            logger.info(
                f"[EXPLODE] Album '{album_name}': +{min(len(tracks), MAX_ITEMS_PER_CATEGORY)} tracks"
            )
        except Exception as e:
            logger.error(f"[EXPLODE] Failed to explode album '{album_name}': {e}", exc_info=True)
        finally:
            await spotify_agent.close()
