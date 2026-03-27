"""Unit tests for Web Scraper agent."""

import time
from unittest.mock import MagicMock, patch

import httpx
import pytest
from bs4 import BeautifulSoup

from src.agents.scraper_agent import (
    PoliteRateLimiter,
    ScraperClientError,
    ScraperResult,
    WebScraperAgent,
)
from src.models.nodes import Concert, Venue


@pytest.fixture
def scraper_agent():
    """Create web scraper agent for testing."""
    agent = WebScraperAgent(min_crawl_delay=0.1)  # Shorter delay for tests
    return agent


@pytest.fixture
def mock_html_concert_page():
    """Mock HTML page with concert data."""
    return """
    <html>
        <body>
            <div class="event">
                <span class="date">2024-03-15</span>
                <span class="venue">Madison Square Garden</span>
                <span class="city">New York</span>
            </div>
            <div class="event">
                <span class="date">2024-03-20</span>
                <span class="venue">The Forum</span>
                <span class="city">Los Angeles</span>
            </div>
        </body>
    </html>
    """


@pytest.fixture
def mock_html_venue_page():
    """Mock HTML page with venue data."""
    return """
    <html>
        <body>
            <h1 class="venue-name">Madison Square Garden</h1>
            <span class="venue-city">New York</span>
            <span class="venue-country">USA</span>
            <span class="capacity">20,000</span>
            <span class="address">4 Pennsylvania Plaza</span>
        </body>
    </html>
    """


@pytest.fixture
def mock_html_setlist_page():
    """Mock HTML page with setlist data."""
    return """
    <html>
        <body>
            <div class="setlist">
                <div class="song">Song 1</div>
                <div class="song">Song 2</div>
                <div class="song">Song 3</div>
            </div>
        </body>
    </html>
    """


@pytest.fixture
def mock_robots_txt_allow():
    """Mock robots.txt that allows crawling."""
    return """
    User-agent: *
    Disallow: /admin/
    """


@pytest.fixture
def mock_robots_txt_disallow():
    """Mock robots.txt that disallows crawling."""
    return """
    User-agent: *
    Disallow: /
    """


class TestPoliteRateLimiter:
    """Tests for PoliteRateLimiter class."""

    @pytest.mark.asyncio
    async def test_rate_limiter_allows_first_request(self):
        """Test that rate limiter allows first request immediately."""
        limiter = PoliteRateLimiter(min_delay=1.0)

        start_time = time.time()
        await limiter.acquire()
        end_time = time.time()

        # First request should be immediate
        assert end_time - start_time < 0.1

    @pytest.mark.asyncio
    async def test_rate_limiter_enforces_delay(self):
        """Test that rate limiter enforces minimum delay between requests."""
        limiter = PoliteRateLimiter(min_delay=0.5)

        # First request
        await limiter.acquire()

        # Second request should wait
        start_time = time.time()
        await limiter.acquire()
        end_time = time.time()

        # Should have waited at least min_delay
        # Allow small margin for timing precision
        assert end_time - start_time >= limiter.min_delay * 0.8

    @pytest.mark.asyncio
    async def test_rate_limiter_custom_delay(self):
        """Test rate limiter with custom delay."""
        limiter = PoliteRateLimiter(min_delay=2.0)

        assert limiter.min_delay == 2.0


class TestWebScraperAgent:
    """Tests for WebScraperAgent class."""

    @pytest.mark.asyncio
    async def test_check_robots_txt_allows(self, scraper_agent, mock_robots_txt_allow):
        """Test robots.txt check when crawling is allowed."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = mock_robots_txt_allow

        with patch.object(scraper_agent.http_client, "get", return_value=mock_response):
            allowed = await scraper_agent._check_robots_txt("https://example.com/page")

        assert allowed is True

    @pytest.mark.asyncio
    async def test_check_robots_txt_disallows(self, scraper_agent, mock_robots_txt_disallow):
        """Test robots.txt check when crawling is disallowed."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = mock_robots_txt_disallow

        with patch.object(scraper_agent.http_client, "get", return_value=mock_response):
            allowed = await scraper_agent._check_robots_txt("https://example.com/page")

        assert allowed is False

    @pytest.mark.asyncio
    async def test_check_robots_txt_not_found(self, scraper_agent):
        """Test robots.txt check when robots.txt doesn't exist."""
        mock_response = MagicMock()
        mock_response.status_code = 404

        with patch.object(scraper_agent.http_client, "get", return_value=mock_response):
            allowed = await scraper_agent._check_robots_txt("https://example.com/page")

        # Should allow when robots.txt not found
        assert allowed is True

    @pytest.mark.asyncio
    async def test_check_robots_txt_caching(self, scraper_agent, mock_robots_txt_allow):
        """Test that robots.txt results are cached."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = mock_robots_txt_allow

        with patch.object(scraper_agent.http_client, "get", return_value=mock_response) as mock_get:
            # First call
            await scraper_agent._check_robots_txt("https://example.com/page1")
            # Second call to same domain
            await scraper_agent._check_robots_txt("https://example.com/page2")

            # Should only fetch robots.txt once
            assert mock_get.call_count == 1

    @pytest.mark.asyncio
    async def test_make_request_success(self, scraper_agent, mock_html_concert_page):
        """Test successful HTTP request."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = mock_html_concert_page

        with (
            patch.object(scraper_agent, "_check_robots_txt", return_value=True),
            patch.object(scraper_agent.http_client, "get", return_value=mock_response),
        ):

            result = await scraper_agent._make_request("https://example.com/concerts")

        assert result == mock_html_concert_page

    @pytest.mark.asyncio
    async def test_make_request_blocked_by_robots(self, scraper_agent):
        """Test request blocked by robots.txt."""
        with patch.object(scraper_agent, "_check_robots_txt", return_value=False):
            with pytest.raises(ScraperClientError, match="Blocked by robots.txt"):
                await scraper_agent._make_request("https://example.com/concerts")

    @pytest.mark.asyncio
    async def test_make_request_rate_limited(self, scraper_agent):
        """Test handling of rate limit (429) response."""
        mock_response = MagicMock()
        mock_response.status_code = 429

        with (
            patch.object(scraper_agent, "_check_robots_txt", return_value=True),
            patch.object(scraper_agent.http_client, "get", return_value=mock_response),
        ):

            with pytest.raises(ScraperClientError, match="blocked or rate limited"):
                await scraper_agent._make_request("https://example.com/concerts")

    @pytest.mark.asyncio
    async def test_make_request_forbidden(self, scraper_agent):
        """Test handling of forbidden (403) response."""
        mock_response = MagicMock()
        mock_response.status_code = 403

        with (
            patch.object(scraper_agent, "_check_robots_txt", return_value=True),
            patch.object(scraper_agent.http_client, "get", return_value=mock_response),
        ):

            with pytest.raises(ScraperClientError, match="blocked or rate limited"):
                await scraper_agent._make_request("https://example.com/concerts")

    @pytest.mark.asyncio
    async def test_make_request_retries_server_error(self, scraper_agent, mock_html_concert_page):
        """Test that server errors trigger retries."""
        # First response: server error
        error_response = MagicMock()
        error_response.status_code = 500

        # Second response: success
        success_response = MagicMock()
        success_response.status_code = 200
        success_response.text = mock_html_concert_page

        with (
            patch.object(scraper_agent, "_check_robots_txt", return_value=True),
            patch.object(
                scraper_agent.http_client, "get", side_effect=[error_response, success_response]
            ),
        ):

            result = await scraper_agent._make_request("https://example.com/concerts")

        assert result == mock_html_concert_page

    @pytest.mark.asyncio
    async def test_make_request_client_error_no_retry(self, scraper_agent):
        """Test that client errors don't trigger retries."""
        mock_response = MagicMock()
        mock_response.status_code = 404

        with (
            patch.object(scraper_agent, "_check_robots_txt", return_value=True),
            patch.object(scraper_agent.http_client, "get", return_value=mock_response),
        ):

            with pytest.raises(ScraperClientError):
                await scraper_agent._make_request("https://example.com/concerts")

    @pytest.mark.asyncio
    async def test_make_request_timeout(self, scraper_agent):
        """Test handling of request timeout."""
        with (
            patch.object(scraper_agent, "_check_robots_txt", return_value=True),
            patch.object(
                scraper_agent.http_client, "get", side_effect=httpx.TimeoutException("Timeout")
            ),
        ):

            result = await scraper_agent._make_request("https://example.com/concerts")

        assert result is None

    def test_parse_html(self, scraper_agent, mock_html_concert_page):
        """Test HTML parsing."""
        soup = scraper_agent._parse_html(mock_html_concert_page)

        assert isinstance(soup, BeautifulSoup)
        events = soup.select(".event")
        assert len(events) == 2

    def test_extract_concert_data(self, scraper_agent, mock_html_concert_page):
        """Test concert data extraction from HTML."""
        soup = scraper_agent._parse_html(mock_html_concert_page)
        concerts = scraper_agent._extract_concert_data(soup, "Test Artist")

        assert len(concerts) == 2
        assert concerts[0]["date"] == "2024-03-15"
        assert concerts[0]["venue"] == "Madison Square Garden"
        assert concerts[0]["city"] == "New York"
        assert concerts[1]["venue"] == "The Forum"

    def test_extract_concert_data_empty(self, scraper_agent):
        """Test concert data extraction with no concerts."""
        html = "<html><body><p>No concerts</p></body></html>"
        soup = scraper_agent._parse_html(html)
        concerts = scraper_agent._extract_concert_data(soup, "Test Artist")

        assert concerts == []

    def test_extract_venue_info(self, scraper_agent, mock_html_venue_page):
        """Test venue information extraction from HTML."""
        soup = scraper_agent._parse_html(mock_html_venue_page)
        venue = scraper_agent._extract_venue_info(soup)

        assert venue is not None
        assert venue["name"] == "Madison Square Garden"
        assert venue["city"] == "New York"
        assert venue["country"] == "USA"
        assert venue["capacity"] == 20000
        assert venue["address"] == "4 Pennsylvania Plaza"

    def test_extract_venue_info_empty(self, scraper_agent):
        """Test venue information extraction with no venue data."""
        html = "<html><body><p>No venue info</p></body></html>"
        soup = scraper_agent._parse_html(html)
        venue = scraper_agent._extract_venue_info(soup)

        assert venue is None

    def test_extract_setlists(self, scraper_agent, mock_html_setlist_page):
        """Test setlist extraction from HTML."""
        soup = scraper_agent._parse_html(mock_html_setlist_page)
        setlists = scraper_agent._extract_setlists(soup)

        assert len(setlists) == 1
        assert setlists[0]["song_count"] == 3
        assert "Song 1" in setlists[0]["songs"]
        assert "Song 2" in setlists[0]["songs"]

    def test_extract_setlists_empty(self, scraper_agent):
        """Test setlist extraction with no setlists."""
        html = "<html><body><p>No setlists</p></body></html>"
        soup = scraper_agent._parse_html(html)
        setlists = scraper_agent._extract_setlists(soup)

        assert setlists == []

    @pytest.mark.asyncio
    async def test_scrape_concert_data(self, scraper_agent):
        """Test concert data scraping (returns empty for now)."""
        concerts = await scraper_agent.scrape_concert_data("Test Artist")

        # Currently returns empty list as no real URLs configured
        assert concerts == []

    @pytest.mark.asyncio
    async def test_scrape_venue_info(self, scraper_agent):
        """Test venue info scraping (returns None for now)."""
        venue = await scraper_agent.scrape_venue_info("Madison Square Garden")

        # Currently returns None as no real URLs configured
        assert venue is None

    @pytest.mark.asyncio
    async def test_scrape_setlists(self, scraper_agent):
        """Test setlist scraping (returns empty for now)."""
        setlists = await scraper_agent.scrape_setlists("Test Artist")

        # Currently returns empty list as no real URLs configured
        assert setlists == []

    @pytest.mark.asyncio
    async def test_scrape_web_data_success(self, scraper_agent):
        """Test complete web data scraping."""
        # Mock the scraping methods
        with (
            patch.object(scraper_agent, "scrape_concert_data", return_value=[]),
            patch.object(scraper_agent, "scrape_setlists", return_value=[]),
        ):

            result = await scraper_agent.scrape_web_data("Test Song", "Test Artist")

        assert isinstance(result, ScraperResult)
        assert result.status == "success"
        assert result.completeness_score >= 0.0

    @pytest.mark.asyncio
    async def test_scrape_web_data_with_concerts(self, scraper_agent):
        """Test web data scraping with concert data."""
        mock_concerts = [
            {
                "artist": "Test Artist",
                "date": "2024-03-15",
                "venue": "Madison Square Garden",
                "city": "New York",
            }
        ]

        mock_venue_info = {
            "name": "Madison Square Garden",
            "city": "New York",
            "country": "USA",
            "capacity": 20000,
        }

        with (
            patch.object(scraper_agent, "scrape_concert_data", return_value=mock_concerts),
            patch.object(scraper_agent, "scrape_venue_info", return_value=mock_venue_info),
            patch.object(scraper_agent, "scrape_setlists", return_value=[]),
        ):

            result = await scraper_agent.scrape_web_data("Test Song", "Test Artist")

        assert result.status == "success"
        assert len(result.venues) == 1
        assert result.venues[0].name == "Madison Square Garden"
        assert result.venues[0].city == "New York"
        assert result.completeness_score > 0.0

    @pytest.mark.asyncio
    async def test_scrape_web_data_with_setlists(self, scraper_agent):
        """Test web data scraping with setlist data."""
        mock_setlists = [
            {
                "songs": ["Song 1", "Song 2", "Song 3"],
                "song_count": 3,
            }
        ]

        with (
            patch.object(scraper_agent, "scrape_concert_data", return_value=[]),
            patch.object(scraper_agent, "scrape_setlists", return_value=mock_setlists),
        ):

            result = await scraper_agent.scrape_web_data("Test Song", "Test Artist")

        assert result.status == "success"
        assert len(result.setlists) == 1
        assert result.setlists[0]["song_count"] == 3
        assert result.completeness_score > 0.0

    @pytest.mark.asyncio
    async def test_scrape_web_data_blocked(self, scraper_agent):
        """Test web data scraping when blocked."""
        with patch.object(
            scraper_agent, "scrape_concert_data", side_effect=ScraperClientError("Blocked")
        ):
            result = await scraper_agent.scrape_web_data("Test Song", "Test Artist")

        assert isinstance(result, ScraperResult)
        assert result.status == "blocked"  # Should be "blocked" not "failed"
        assert result.completeness_score == 0.0

    @pytest.mark.asyncio
    async def test_scrape_web_data_exception(self, scraper_agent):
        """Test web data scraping with exception."""
        with patch.object(
            scraper_agent, "scrape_concert_data", side_effect=Exception("Unexpected error")
        ):
            result = await scraper_agent.scrape_web_data("Test Song", "Test Artist")

        assert isinstance(result, ScraperResult)
        assert result.status == "failed"
        assert result.completeness_score == 0.0

    @pytest.mark.asyncio
    async def test_scrape_web_data_venue_without_country(self, scraper_agent):
        """Test venue creation when country is missing."""
        mock_concerts = [
            {
                "artist": "Test Artist",
                "date": "2024-03-15",
                "venue": "Test Venue",
                "city": "Test City",
            }
        ]

        # Venue info without country - should not create venue
        mock_venue_info = {
            "name": "Test Venue",
            "city": "Test City",
            "country": None,  # Missing country
        }

        with (
            patch.object(scraper_agent, "scrape_concert_data", return_value=mock_concerts),
            patch.object(scraper_agent, "scrape_venue_info", return_value=mock_venue_info),
            patch.object(scraper_agent, "scrape_setlists", return_value=[]),
        ):

            result = await scraper_agent.scrape_web_data("Test Song", "Test Artist")

        # Should create venue with "Unknown" country from concert data fallback
        assert result.status == "success"
        assert len(result.venues) == 1
        assert result.venues[0].country == "Unknown"

    @pytest.mark.asyncio
    async def test_scrape_web_data_venue_without_city(self, scraper_agent):
        """Test venue creation when city is missing."""
        mock_concerts = [
            {
                "artist": "Test Artist",
                "date": "2024-03-15",
                "venue": "Test Venue",
                "city": None,  # Missing city
            }
        ]

        with (
            patch.object(scraper_agent, "scrape_concert_data", return_value=mock_concerts),
            patch.object(scraper_agent, "scrape_venue_info", return_value=None),
            patch.object(scraper_agent, "scrape_setlists", return_value=[]),
        ):

            result = await scraper_agent.scrape_web_data("Test Song", "Test Artist")

        # Should not create venue without city
        assert result.status == "success"
        assert len(result.venues) == 0

    @pytest.mark.asyncio
    async def test_close_cleanup(self, scraper_agent):
        """Test that close method cleans up resources."""
        with patch.object(scraper_agent.http_client, "aclose") as mock_close:
            await scraper_agent.close()
            mock_close.assert_called_once()


class TestScraperResult:
    """Tests for ScraperResult class."""

    def test_scraper_result_initialization(self):
        """Test ScraperResult initialization."""
        venue = Venue(
            name="Test Venue",
            city="Test City",
            country="Test Country",
        )
        concert = Concert(
            concert_date="2024-03-15",
            venue_id=venue.id,
        )
        setlists = [{"songs": ["Song 1", "Song 2"]}]

        result = ScraperResult(
            concerts=[concert],
            venues=[venue],
            setlists=setlists,
            completeness_score=0.75,
            status="success",
        )

        assert len(result.concerts) == 1
        assert len(result.venues) == 1
        assert len(result.setlists) == 1
        assert result.completeness_score == 0.75
        assert result.status == "success"

    def test_scraper_result_defaults(self):
        """Test ScraperResult with default values."""
        result = ScraperResult()

        assert result.concerts == []
        assert result.venues == []
        assert result.setlists == []
        assert result.completeness_score == 0.0
        assert result.status == "success"

    def test_scraper_result_blocked_status(self):
        """Test ScraperResult with blocked status."""
        result = ScraperResult(status="blocked")

        assert result.status == "blocked"
        assert result.completeness_score == 0.0

    def test_scraper_result_failed_status(self):
        """Test ScraperResult with failed status."""
        result = ScraperResult(status="failed")

        assert result.status == "failed"
        assert result.completeness_score == 0.0
