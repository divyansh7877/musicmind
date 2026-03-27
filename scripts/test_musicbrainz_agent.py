"""Test script for MusicBrainz agent."""

import asyncio
import logging

from src.agents.musicbrainz_agent import MusicBrainzAgent

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

logger = logging.getLogger(__name__)


async def main():
    """Test MusicBrainz agent with a sample song."""
    agent = MusicBrainzAgent(
        user_agent="MusicMindTestAgent/1.0 (test@example.com)"
    )

    try:
        logger.info("Testing MusicBrainz agent...")
        logger.info("=" * 60)

        # Test with a well-known song
        song_name = "Bohemian Rhapsody"
        logger.info(f"Fetching data for: {song_name}")

        result = await agent.fetch_musicbrainz_data(song_name)

        logger.info(f"Completeness Score: {result.completeness_score:.2f}")
        logger.info("=" * 60)

        if result.song:
            logger.info("Song Information:")
            logger.info(f"  Title: {result.song.title}")
            logger.info(f"  Duration: {result.song.duration_ms}ms")
            logger.info(f"  MusicBrainz ID: {result.song.musicbrainz_id}")
            logger.info(f"  Data Sources: {result.song.data_sources}")
        else:
            logger.warning("No song data found")

        if result.artists:
            logger.info(f"\nArtists ({len(result.artists)}):")
            for artist in result.artists:
                logger.info(f"  - {artist.name} (Country: {artist.country})")
                logger.info(f"    MusicBrainz ID: {artist.musicbrainz_id}")
        else:
            logger.warning("No artist data found")

        if result.relationships:
            logger.info(f"\nRelationships ({len(result.relationships)}):")
            for rel in result.relationships:
                logger.info(f"  - {rel['type']}: {rel.get('target_artist', 'N/A')}")
        else:
            logger.info("\nNo relationships found")

        if result.label_info:
            logger.info("\nLabel Information:")
            logger.info(f"  Name: {result.label_info.get('name')}")
            logger.info(f"  Country: {result.label_info.get('country')}")
            logger.info(f"  Type: {result.label_info.get('type')}")
        else:
            logger.info("\nNo label information found")

        logger.info("=" * 60)
        logger.info("MusicBrainz agent test completed successfully!")

    except Exception as e:
        logger.error(f"Error testing MusicBrainz agent: {e}", exc_info=True)
    finally:
        await agent.close()


if __name__ == "__main__":
    asyncio.run(main())
