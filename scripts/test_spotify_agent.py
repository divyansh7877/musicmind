"""Manual test script for Spotify agent with real API calls.

This script demonstrates the Spotify agent fetching real data from Spotify API.
Run with: python scripts/test_spotify_agent.py
"""

import asyncio
import logging
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.agents.spotify_agent import SpotifyAgent

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)


async def test_spotify_agent():
    """Test Spotify agent with real API calls."""
    print("=" * 60)
    print("Spotify Agent Test")
    print("=" * 60)

    agent = SpotifyAgent()

    try:
        # Test 1: Search for a popular song
        print("\n[Test 1] Fetching data for 'Bohemian Rhapsody'...")
        result = await agent.fetch_spotify_data("Bohemian Rhapsody")

        if result.song:
            print(f"\n✓ Song found: {result.song.title}")
            print(f"  - Spotify ID: {result.song.spotify_id}")
            print(f"  - Duration: {result.song.duration_ms / 1000:.1f} seconds")
            
            if result.song.audio_features:
                print(f"  - Tempo: {result.song.audio_features.tempo} BPM")
                print(f"  - Energy: {result.song.audio_features.energy}")
                print(f"  - Danceability: {result.song.audio_features.danceability}")

            if result.artists:
                print(f"\n✓ Artists ({len(result.artists)}):")
                for artist in result.artists:
                    print(f"  - {artist.name}")
                    print(f"    Genres: {', '.join(artist.genres[:3])}")
                    print(f"    Popularity: {artist.popularity}/100")

            if result.album:
                print(f"\n✓ Album: {result.album.title}")
                print(f"  - Type: {result.album.album_type}")
                print(f"  - Release Date: {result.album.release_date}")
                print(f"  - Label: {result.album.label}")

            print(f"\n✓ Overall Completeness: {result.completeness_score:.2%}")
        else:
            print("✗ Song not found")

        # Test 2: Search for another song
        print("\n" + "=" * 60)
        print("\n[Test 2] Fetching data for 'Blinding Lights'...")
        result2 = await agent.fetch_spotify_data("Blinding Lights")

        if result2.song:
            print(f"\n✓ Song found: {result2.song.title}")
            print(f"  - Artist: {result2.artists[0].name if result2.artists else 'Unknown'}")
            print(f"  - Completeness: {result2.completeness_score:.2%}")
        else:
            print("✗ Song not found")

        # Test 3: Test rate limiting with multiple requests
        print("\n" + "=" * 60)
        print("\n[Test 3] Testing rate limiting with 5 rapid requests...")
        
        songs = ["Shape of You", "Levitating", "Watermelon Sugar", "Circles", "Memories"]
        tasks = [agent.fetch_spotify_data(song) for song in songs]
        
        import time
        start = time.time()
        results = await asyncio.gather(*tasks)
        elapsed = time.time() - start
        
        successful = sum(1 for r in results if r.song is not None)
        print(f"\n✓ Completed {successful}/{len(songs)} requests in {elapsed:.2f}s")
        print(f"  - Average: {elapsed/len(songs):.2f}s per request")

        print("\n" + "=" * 60)
        print("All tests completed successfully!")
        print("=" * 60)

    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()

    finally:
        await agent.close()


if __name__ == "__main__":
    asyncio.run(test_spotify_agent())
