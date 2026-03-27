"""Integration test script for Last.fm agent."""

import asyncio
import logging
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.agents.lastfm_agent import LastFMAgent
from config.settings import settings

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

logger = logging.getLogger(__name__)


async def test_lastfm_agent():
    """Test Last.fm agent with real API."""
    logger.info("Starting Last.fm agent integration test")

    # Create agent
    agent = LastFMAgent(api_key=settings.lastfm_api_key)

    try:
        # Test 1: Search for a track
        logger.info("\n=== Test 1: Search Track ===")
        track_data = await agent.search_track("Bohemian Rhapsody")
        if track_data:
            logger.info(f"Found track: {track_data.get('name')} by {track_data.get('artist')}")
        else:
            logger.warning("No track found")

        # Test 2: Get track info
        logger.info("\n=== Test 2: Get Track Info ===")
        track_info = await agent.get_track_info("Queen", "Bohemian Rhapsody")
        if track_info:
            logger.info(f"Track: {track_info.get('name')}")
            logger.info(f"Play count: {track_info.get('playcount')}")
            logger.info(f"Listeners: {track_info.get('listeners')}")
            logger.info(f"Duration: {track_info.get('duration')} ms")
        else:
            logger.warning("No track info found")

        # Test 3: Get similar tracks
        logger.info("\n=== Test 3: Get Similar Tracks ===")
        similar_tracks = await agent.get_similar_tracks("Queen", "Bohemian Rhapsody")
        if similar_tracks:
            logger.info(f"Found {len(similar_tracks)} similar tracks:")
            for i, track in enumerate(similar_tracks[:5], 1):
                artist_name = track.get("artist", {})
                if isinstance(artist_name, dict):
                    artist_name = artist_name.get("name", "Unknown")
                logger.info(f"  {i}. {track.get('name')} by {artist_name}")
        else:
            logger.warning("No similar tracks found")

        # Test 4: Get top tags
        logger.info("\n=== Test 4: Get Top Tags ===")
        tags = await agent.get_top_tags("Queen", "Bohemian Rhapsody")
        if tags:
            logger.info(f"Found {len(tags)} tags: {', '.join(tags[:10])}")
        else:
            logger.warning("No tags found")

        # Test 5: Complete data fetch
        logger.info("\n=== Test 5: Complete Data Fetch ===")
        result = await agent.fetch_lastfm_data("Bohemian Rhapsody")
        
        logger.info(f"Completeness score: {result.completeness_score:.2f}")
        
        if result.song:
            logger.info(f"Song: {result.song.title}")
            logger.info(f"  Duration: {result.song.duration_ms} ms")
            logger.info(f"  Play count: {result.song.play_count}")
            logger.info(f"  Listeners: {result.song.listener_count}")
            logger.info(f"  URL: {result.song.lastfm_url}")
            logger.info(f"  Tags: {', '.join(result.song.tags[:5]) if result.song.tags else 'None'}")
        
        if result.artists:
            logger.info(f"Artists ({len(result.artists)}):")
            for artist in result.artists:
                logger.info(f"  - {artist.name}")
        
        if result.similar_tracks:
            logger.info(f"Similar tracks: {len(result.similar_tracks)}")
        
        logger.info("\n=== All Tests Completed Successfully ===")

    except Exception as e:
        logger.error(f"Test failed: {e}", exc_info=True)
        return False

    finally:
        await agent.close()

    return True


if __name__ == "__main__":
    success = asyncio.run(test_lastfm_agent())
    sys.exit(0 if success else 1)
