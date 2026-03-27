"""Test script for Web Scraper Agent."""

import asyncio
import logging

from src.agents.scraper_agent import WebScraperAgent

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

logger = logging.getLogger(__name__)


async def test_scraper_agent():
    """Test the web scraper agent."""
    logger.info("=" * 60)
    logger.info("Testing Web Scraper Agent")
    logger.info("=" * 60)

    # Create agent
    agent = WebScraperAgent(min_crawl_delay=1.0)

    try:
        # Test 1: Scrape web data for a song
        logger.info("\n1. Testing scrape_web_data()...")
        result = await agent.scrape_web_data("Bohemian Rhapsody", "Queen")

        logger.info(f"Status: {result.status}")
        logger.info(f"Completeness Score: {result.completeness_score:.2f}")
        logger.info(f"Concerts Found: {len(result.concerts)}")
        logger.info(f"Venues Found: {len(result.venues)}")
        logger.info(f"Setlists Found: {len(result.setlists)}")

        if result.venues:
            logger.info("\nVenue Details:")
            for venue in result.venues:
                logger.info(f"  - {venue.name} ({venue.city}, {venue.country})")
                logger.info(f"    Completeness: {venue.completeness_score:.2f}")

        # Test 2: Test robots.txt checking
        logger.info("\n2. Testing robots.txt checking...")
        allowed = await agent._check_robots_txt("https://www.example.com/test")
        logger.info(f"Example.com allows crawling: {allowed}")

        # Test 3: Test HTML parsing
        logger.info("\n3. Testing HTML parsing...")
        test_html = """
        <html>
            <body>
                <div class="event">
                    <span class="date">2024-03-15</span>
                    <span class="venue">Test Venue</span>
                    <span class="city">Test City</span>
                </div>
            </body>
        </html>
        """
        soup = agent._parse_html(test_html)
        concerts = agent._extract_concert_data(soup, "Test Artist")
        logger.info(f"Extracted {len(concerts)} concerts from test HTML")
        if concerts:
            logger.info(f"  - {concerts[0]}")

        logger.info("\n" + "=" * 60)
        logger.info("Web Scraper Agent Test Complete!")
        logger.info("=" * 60)

    except Exception as e:
        logger.error(f"Test failed: {e}", exc_info=True)

    finally:
        await agent.close()


if __name__ == "__main__":
    asyncio.run(test_scraper_agent())
