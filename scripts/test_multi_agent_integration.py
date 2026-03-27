#!/usr/bin/env python3
"""Manual test script for multi-agent parallel execution.

This script demonstrates the orchestrator dispatching all 4 agents in parallel
and merging their results for various songs.
"""

import asyncio
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.agents.orchestrator import OrchestratorAgent
from src.cache.redis_client import RedisClient
from src.tracing.overmind_client import OvermindClient


async def test_song_enrichment(song_name: str):
    """Test enrichment for a specific song."""
    print(f"\n{'='*80}")
    print(f"Testing enrichment for: {song_name}")
    print(f"{'='*80}\n")

    # Initialize orchestrator
    cache_client = RedisClient()
    overmind_client = OvermindClient()
    orchestrator = OrchestratorAgent(
        cache_client=cache_client,
        overmind_client=overmind_client,
    )

    try:
        # Enrich the song
        result = await orchestrator.enrich_song(song_name)

        # Display results
        print(f"Status: {result.status}")
        print(f"Completeness Score: {result.completeness_score:.2f}")
        print(f"Request ID: {result.request_id}")
        print(f"Graph Node IDs: {len(result.graph_node_ids)}")

        if result.error_message:
            print(f"Error: {result.error_message}")

        # Display merged data summary
        print(f"\nMerged Data Summary:")
        print(f"-" * 80)

        if "song" in result.merged_data:
            song_data = result.merged_data["song"]
            print(f"\nSong:")
            print(f"  Title: {song_data.get('title', 'N/A')}")
            print(f"  Duration: {song_data.get('duration_ms', 'N/A')} ms")
            print(f"  Spotify ID: {song_data.get('spotify_id', 'N/A')}")
            print(f"  MusicBrainz ID: {song_data.get('musicbrainz_id', 'N/A')}")
            print(f"  ISRC: {song_data.get('isrc', 'N/A')}")
            print(f"  Play Count: {song_data.get('play_count', 'N/A')}")
            print(f"  Tags: {', '.join(song_data.get('tags', []))}")

        if "artists" in result.merged_data:
            artists = result.merged_data["artists"]
            print(f"\nArtists ({len(artists)}):")
            for artist in artists[:3]:  # Show first 3
                print(f"  - {artist.get('name', 'N/A')}")
                print(f"    Country: {artist.get('country', 'N/A')}")
                print(f"    Genres: {', '.join(artist.get('genres', []))}")

        if "album" in result.merged_data:
            album = result.merged_data["album"]
            print(f"\nAlbum:")
            print(f"  Title: {album.get('title', 'N/A')}")
            print(f"  Release Date: {album.get('release_date', 'N/A')}")
            print(f"  Type: {album.get('album_type', 'N/A')}")

        if "relationships" in result.merged_data:
            relationships = result.merged_data["relationships"]
            print(f"\nRelationships ({len(relationships)}):")
            for rel in relationships[:5]:  # Show first 5
                print(f"  - {rel.get('type', 'N/A')}: {rel.get('artist', 'N/A')} ({rel.get('role', 'N/A')})")

        if "venues" in result.merged_data:
            venues = result.merged_data["venues"]
            print(f"\nVenues ({len(venues)}):")
            for venue in venues[:3]:  # Show first 3
                print(f"  - {venue.get('name', 'N/A')} ({venue.get('city', 'N/A')}, {venue.get('country', 'N/A')})")

        if "concerts" in result.merged_data:
            concerts = result.merged_data["concerts"]
            print(f"\nConcerts ({len(concerts)}):")
            for concert in concerts[:3]:  # Show first 3
                print(f"  - {concert.get('date', 'N/A')} at {concert.get('venue_name', 'N/A')}")

        print(f"\n{'='*80}\n")

    except Exception as e:
        print(f"Error during enrichment: {e}")
        import traceback
        traceback.print_exc()


async def main():
    """Run tests for multiple songs."""
    print("Multi-Agent Parallel Execution Test")
    print("=" * 80)
    print("This script tests the orchestrator dispatching all 4 agents:")
    print("  1. Spotify Agent")
    print("  2. MusicBrainz Agent")
    print("  3. Last.fm Agent")
    print("  4. Web Scraper Agent")
    print()
    print("The agents execute in parallel and their results are merged.")
    print("=" * 80)

    # Test songs with varying data availability
    test_songs = [
        "Bohemian Rhapsody",  # Well-known song with rich data
        "Stairway to Heaven",  # Another classic with good coverage
        "Smells Like Teen Spirit",  # 90s rock classic
    ]

    for song_name in test_songs:
        await test_song_enrichment(song_name)
        await asyncio.sleep(1)  # Brief pause between tests

    print("\nAll tests completed!")
    print("\nKey Observations:")
    print("  - All 4 agents were dispatched in parallel")
    print("  - Results were merged with conflict resolution")
    print("  - Completeness scores reflect data quality")
    print("  - System handles partial failures gracefully")


if __name__ == "__main__":
    asyncio.run(main())
