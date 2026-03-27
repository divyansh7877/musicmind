"""Web scraper agent for extracting concert and venue data from web sources."""

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup
from src.models.nodes import Concert, Venue
from src.tracing.overmind_client import OvermindClient
from src.utils.metrics import calculate_completeness

logger = logging.getLogger(__name__)


class ScraperClientError(Exception):
    """Exception for scraper client errors (4xx) that should not be retried."""

    pass


class ScraperResult:
    """Result from web scraping with completeness score."""

    def __init__(
        self,
        concerts: Optional[List[Concert]] = None,
        venues: Optional[List[Venue]] = None,
        setlists: Optional[List[Dict[str, Any]]] = None,
        completeness_score: float = 0.0,
        status: str = "success",
    ):
        """Initialize scraper result.

        Args:
            concerts: List of concert data
            venues: List of venue data
            setlists: List of setlist data
            completeness_score: Overall completeness score
            status: Status of scraping operation ("success", "failed", "blocked")
        """
        self.concerts = concerts or []
        self.venues = venues or []
        self.setlists = setlists or []
        self.completeness_score = completeness_score
        self.status = status


class PoliteRateLimiter:
    """Polite rate limiter for web scraping with configurable delays."""

    def __init__(self, min_delay: float = 2.0):
        """Initialize rate limiter with minimum delay between requests.

        Args:
            min_delay: Minimum seconds between requests (default 2.0 for polite crawling)
        """
        self.min_delay = min_delay
        self.last_request_time = 0.0
        self.lock = asyncio.Lock()

    async def acquire(self) -> None:
        """Acquire permission to make a request (blocks if rate limit reached)."""
        async with self.lock:
            now = time.time()
            time_since_last = now - self.last_request_time

            if time_since_last < self.min_delay:
                wait_time = self.min_delay - time_since_last
                logger.debug(f"Polite crawling delay: waiting {wait_time:.2f}s")
                await asyncio.sleep(wait_time)

            self.last_request_time = time.time()


class WebScraperAgent:
    """Agent for scraping concert and venue data from web sources."""

    def __init__(
        self,
        overmind_client: Optional[OvermindClient] = None,
        min_crawl_delay: float = 2.0,
    ):
        """Initialize web scraper agent.

        Args:
            overmind_client: Overmind Lab tracing client
            min_crawl_delay: Minimum delay between requests in seconds
        """
        self.overmind_client = overmind_client

        # Polite rate limiting (2 seconds between requests by default)
        self.rate_limiter = PoliteRateLimiter(min_delay=min_crawl_delay)

        # HTTP client with browser-like headers
        self.http_client = httpx.AsyncClient(
            timeout=15.0,
            headers={
                "User-Agent": "MusicMind-Bot/1.0 (Educational/Research; +https://github.com/musicmind)",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.5",
                "Accept-Encoding": "gzip, deflate",
                "DNT": "1",
                "Connection": "keep-alive",
                "Upgrade-Insecure-Requests": "1",
            },
            follow_redirects=True,
        )

        # Robots.txt cache
        self.robots_cache: Dict[str, bool] = {}

    async def _check_robots_txt(self, url: str) -> bool:
        """Check if URL is allowed by robots.txt.

        Args:
            url: URL to check

        Returns:
            True if allowed, False if disallowed
        """
        parsed = urlparse(url)
        base_url = f"{parsed.scheme}://{parsed.netloc}"

        # Check cache
        if base_url in self.robots_cache:
            return self.robots_cache[base_url]

        try:
            robots_url = urljoin(base_url, "/robots.txt")
            response = await self.http_client.get(robots_url, timeout=5.0)

            if response.status_code == 200:
                robots_txt = response.text
                # Simple check for Disallow: / (blocks all)
                # Must be on same line or consecutive lines with User-agent: *
                lines = robots_txt.split("\n")
                user_agent_all = False
                for line in lines:
                    line = line.strip()
                    if line.startswith("User-agent:") and "*" in line:
                        user_agent_all = True
                    elif user_agent_all and line == "Disallow: /":
                        logger.warning(f"Robots.txt disallows crawling: {base_url}")
                        self.robots_cache[base_url] = False
                        return False
                    elif line.startswith("User-agent:"):
                        user_agent_all = False

            # If robots.txt not found or doesn't block, allow
            self.robots_cache[base_url] = True
            return True

        except Exception as e:
            logger.debug(f"Could not fetch robots.txt for {base_url}: {e}")
            # If we can't fetch robots.txt, be conservative and allow
            self.robots_cache[base_url] = True
            return True

    async def _make_request(
        self,
        url: str,
        max_retries: int = 3,
    ) -> Optional[str]:
        """Make HTTP request with rate limiting and robots.txt respect.

        Args:
            url: URL to fetch
            max_retries: Maximum number of retry attempts

        Returns:
            HTML content or None if request fails

        Raises:
            ScraperClientError: If request is blocked or fails with client error
        """
        # Check robots.txt
        if not await self._check_robots_txt(url):
            raise ScraperClientError(f"Blocked by robots.txt: {url}")

        await self.rate_limiter.acquire()

        for attempt in range(max_retries):
            try:
                # Log scraping attempt to Overmind Lab
                if self.overmind_client:
                    self.overmind_client.log_event(
                        "scraper_request",
                        {"url": url, "attempt": attempt + 1},
                    )

                response = await self.http_client.get(url)

                # Handle rate limit or blocking
                if response.status_code == 429 or response.status_code == 403:
                    error_msg = f"Scraping blocked or rate limited: {response.status_code}"
                    logger.warning(error_msg)

                    if self.overmind_client:
                        self.overmind_client.log_event(
                            "scraper_blocked",
                            {"url": url, "status_code": response.status_code},
                        )

                    raise ScraperClientError(error_msg)

                # Handle other errors
                if response.status_code >= 400:
                    error_msg = f"Scraper error: {response.status_code} for {url}"
                    logger.error(error_msg)

                    # Don't retry client errors
                    if 400 <= response.status_code < 500:
                        raise ScraperClientError(error_msg)

                    # Retry server errors with exponential backoff
                    if attempt < max_retries - 1:
                        wait_time = (2**attempt) + (asyncio.get_event_loop().time() % 1)
                        logger.info(f"Retrying after {wait_time:.2f}s")
                        await asyncio.sleep(wait_time)
                        continue

                    return None

                return response.text

            except httpx.TimeoutException:
                logger.warning(f"Request timeout on attempt {attempt + 1} for {url}")
                if attempt < max_retries - 1:
                    wait_time = (2**attempt) + (asyncio.get_event_loop().time() % 1)
                    await asyncio.sleep(wait_time)
                    continue
                return None

            except ScraperClientError:
                # Don't retry client errors
                raise

            except Exception as e:
                if attempt < max_retries - 1:
                    wait_time = (2**attempt) + (asyncio.get_event_loop().time() % 1)
                    logger.warning(f"Request failed, retrying after {wait_time:.2f}s: {e}")
                    await asyncio.sleep(wait_time)
                    continue
                logger.error(f"Request failed after all retries: {e}", exc_info=True)
                return None

        return None

    def _parse_html(self, html: str) -> BeautifulSoup:
        """Parse HTML content using BeautifulSoup.

        Args:
            html: HTML content

        Returns:
            BeautifulSoup object
        """
        return BeautifulSoup(html, "lxml")

    def _extract_concert_data(self, soup: BeautifulSoup, artist_name: str) -> List[Dict[str, Any]]:
        """Extract concert data from parsed HTML.

        Args:
            soup: BeautifulSoup parsed HTML
            artist_name: Artist name for context

        Returns:
            List of concert data dictionaries
        """
        concerts = []

        # This is a generic implementation - in production, you'd have
        # site-specific extractors for setlist.fm, songkick.com, etc.

        # Look for common concert/event patterns
        event_selectors = [
            ".event",
            ".concert",
            ".show",
            "[itemtype*='Event']",
            ".setlist",
        ]

        for selector in event_selectors:
            events = soup.select(selector)

            for event in events[:10]:  # Limit to 10 events
                try:
                    # Extract date
                    date_elem = event.select_one(".date, .event-date, [itemprop='startDate']")
                    date_str = date_elem.get_text(strip=True) if date_elem else None

                    # Extract venue
                    venue_elem = event.select_one(".venue, .location, [itemprop='location']")
                    venue_name = venue_elem.get_text(strip=True) if venue_elem else None

                    # Extract city
                    city_elem = event.select_one(".city, .event-city")
                    city = city_elem.get_text(strip=True) if city_elem else None

                    if date_str or venue_name:
                        concerts.append(
                            {
                                "artist": artist_name,
                                "date": date_str,
                                "venue": venue_name,
                                "city": city,
                            }
                        )

                except Exception as e:
                    logger.debug(f"Failed to extract concert data from element: {e}")
                    continue

            if concerts:
                break  # Found concerts, no need to try other selectors

        return concerts

    def _extract_venue_info(self, soup: BeautifulSoup) -> Optional[Dict[str, Any]]:
        """Extract venue information from parsed HTML.

        Args:
            soup: BeautifulSoup parsed HTML

        Returns:
            Venue data dictionary or None
        """
        try:
            # Look for venue information
            venue_name = None
            city = None
            country = None
            capacity = None
            address = None

            # Try common venue selectors
            name_elem = soup.select_one(".venue-name, h1.venue, [itemprop='name']")
            if name_elem:
                venue_name = name_elem.get_text(strip=True)

            city_elem = soup.select_one(".venue-city, .city, [itemprop='addressLocality']")
            if city_elem:
                city = city_elem.get_text(strip=True)

            country_elem = soup.select_one(".venue-country, .country, [itemprop='addressCountry']")
            if country_elem:
                country = country_elem.get_text(strip=True)

            capacity_elem = soup.select_one(".capacity, .venue-capacity")
            if capacity_elem:
                capacity_text = capacity_elem.get_text(strip=True)
                # Extract numbers from text
                import re

                capacity_match = re.search(r"\d+", capacity_text.replace(",", ""))
                if capacity_match:
                    capacity = int(capacity_match.group())

            address_elem = soup.select_one(".address, [itemprop='streetAddress']")
            if address_elem:
                address = address_elem.get_text(strip=True)

            if venue_name:
                return {
                    "name": venue_name,
                    "city": city,
                    "country": country,
                    "capacity": capacity,
                    "address": address,
                }

        except Exception as e:
            logger.debug(f"Failed to extract venue info: {e}")

        return None

    def _extract_setlists(self, soup: BeautifulSoup) -> List[Dict[str, Any]]:
        """Extract setlist data from parsed HTML.

        Args:
            soup: BeautifulSoup parsed HTML

        Returns:
            List of setlist data dictionaries
        """
        setlists = []

        try:
            # Look for setlist patterns
            setlist_selectors = [
                ".setlist",
                ".tracklist",
                "[itemtype*='MusicPlaylist']",
            ]

            for selector in setlist_selectors:
                setlist_containers = soup.select(selector)

                for container in setlist_containers[:5]:  # Limit to 5 setlists
                    songs = []

                    # Extract song titles
                    song_elems = container.select(".song, .track, [itemprop='track']")
                    for song_elem in song_elems:
                        song_title = song_elem.get_text(strip=True)
                        if song_title:
                            songs.append(song_title)

                    if songs:
                        setlists.append(
                            {
                                "songs": songs,
                                "song_count": len(songs),
                            }
                        )

                if setlists:
                    break  # Found setlists, no need to try other selectors

        except Exception as e:
            logger.debug(f"Failed to extract setlists: {e}")

        return setlists

    async def scrape_concert_data(self, artist_name: str) -> List[Dict[str, Any]]:
        """Scrape concert data for an artist.

        Args:
            artist_name: Name of the artist

        Returns:
            List of concert data dictionaries
        """
        try:
            # In production, you'd query specific concert sites
            # For now, return empty list as we don't have real URLs
            logger.info(f"Concert scraping for '{artist_name}' - no real URLs configured")
            return []

        except ScraperClientError as e:
            logger.warning(f"Concert scraping blocked for '{artist_name}': {e}")
            return []
        except Exception as e:
            logger.error(f"Concert scraping failed for '{artist_name}': {e}", exc_info=True)
            return []

    async def scrape_venue_info(self, venue_name: str) -> Optional[Dict[str, Any]]:
        """Scrape venue information.

        Args:
            venue_name: Name of the venue

        Returns:
            Venue data dictionary or None
        """
        try:
            # In production, you'd query specific venue sites
            # For now, return None as we don't have real URLs
            logger.info(f"Venue scraping for '{venue_name}' - no real URLs configured")
            return None

        except ScraperClientError as e:
            logger.warning(f"Venue scraping blocked for '{venue_name}': {e}")
            return None
        except Exception as e:
            logger.error(f"Venue scraping failed for '{venue_name}': {e}", exc_info=True)
            return None

    async def scrape_setlists(self, artist_name: str) -> List[Dict[str, Any]]:
        """Scrape setlist data for an artist.

        Args:
            artist_name: Name of the artist

        Returns:
            List of setlist data dictionaries
        """
        try:
            # In production, you'd query setlist.fm or similar
            # For now, return empty list as we don't have real URLs
            logger.info(f"Setlist scraping for '{artist_name}' - no real URLs configured")
            return []

        except ScraperClientError as e:
            logger.warning(f"Setlist scraping blocked for '{artist_name}': {e}")
            return []
        except Exception as e:
            logger.error(f"Setlist scraping failed for '{artist_name}': {e}", exc_info=True)
            return []

    async def scrape_web_data(
        self, song_name: str, artist_name: Optional[str] = None
    ) -> ScraperResult:
        """Main entry point for scraping web data.

        Args:
            song_name: Name of the song
            artist_name: Optional artist name for context

        Returns:
            ScraperResult with concerts, venues, setlists, and completeness score
        """
        try:
            # Log scraping start to Overmind Lab
            if self.overmind_client:
                self.overmind_client.log_event(
                    "scraper_start",
                    {"song_name": song_name, "artist_name": artist_name},
                )

            # Use artist name if provided, otherwise use song name as fallback
            search_name = artist_name or song_name

            # Scrape concert data
            concert_data = await self.scrape_concert_data(search_name)

            # Scrape setlists
            setlist_data = await self.scrape_setlists(search_name)

            # Create Concert objects from scraped data
            concerts = []
            venues = []
            venue_names_seen = set()

            for concert_dict in concert_data:
                try:
                    # Create venue if we have venue info
                    venue_name = concert_dict.get("venue")

                    if venue_name and venue_name not in venue_names_seen:
                        venue_names_seen.add(venue_name)

                        # Try to get more venue details
                        venue_info = await self.scrape_venue_info(venue_name)

                        if venue_info:
                            # Only create venue if we have required fields
                            city = venue_info.get("city") or concert_dict.get("city")
                            country = venue_info.get("country")

                            if city and country:
                                venue = Venue(
                                    name=venue_info.get("name", venue_name),
                                    city=city,
                                    country=country,
                                    capacity=venue_info.get("capacity"),
                                    address=venue_info.get("address"),
                                )
                                venues.append(venue)
                            elif city and venue_name:
                                # Fallback: create basic venue with "Unknown" country
                                venue = Venue(
                                    name=venue_name,
                                    city=city,
                                    country="Unknown",
                                )
                                venues.append(venue)
                        elif venue_name:
                            # Create basic venue from concert data only if we have required fields
                            city = concert_dict.get("city")
                            if city and venue_name:
                                # Use "Unknown" as placeholder for country if not available
                                venue = Venue(
                                    name=venue_name,
                                    city=city,
                                    country="Unknown",
                                )
                                venues.append(venue)

                    # Note: In production, you'd parse the date string properly
                    # For now, we'll skip creating Concert objects without proper date parsing

                except Exception as e:
                    logger.debug(f"Failed to create concert/venue objects: {e}")
                    continue

            # Calculate completeness scores
            venue_completeness_scores = []
            for venue in venues:
                venue_score = calculate_completeness(venue, "Venue")
                venue.completeness_score = venue_score
                venue_completeness_scores.append(venue_score)

            # Overall completeness
            overall_completeness = 0.0
            if concert_data:
                overall_completeness += 0.4
            if venues:
                overall_completeness += (
                    sum(venue_completeness_scores) / len(venue_completeness_scores)
                ) * 0.3
            if setlist_data:
                overall_completeness += 0.3

            # Log completion to Overmind Lab
            if self.overmind_client:
                self.overmind_client.log_event(
                    "scraper_complete",
                    {
                        "song_name": song_name,
                        "concerts_found": len(concerts),
                        "venues_found": len(venues),
                        "setlists_found": len(setlist_data),
                        "completeness": overall_completeness,
                    },
                )

            return ScraperResult(
                concerts=concerts,
                venues=venues,
                setlists=setlist_data,
                completeness_score=overall_completeness,
                status="success",
            )

        except ScraperClientError as e:
            logger.warning(f"Web scraping blocked for '{song_name}': {e}")

            if self.overmind_client:
                self.overmind_client.log_event(
                    "scraper_blocked",
                    {"song_name": song_name, "error": str(e)},
                )

            return ScraperResult(
                completeness_score=0.0,
                status="blocked",
            )

        except Exception as e:
            logger.error(f"Web scraping failed for '{song_name}': {e}", exc_info=True)

            if self.overmind_client:
                self.overmind_client.log_event(
                    "scraper_error",
                    {"song_name": song_name, "error": str(e)},
                )

            return ScraperResult(
                completeness_score=0.0,
                status="failed",
            )

    async def close(self) -> None:
        """Close HTTP client and cleanup resources."""
        await self.http_client.aclose()
