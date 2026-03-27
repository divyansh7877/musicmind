"""Agent module for orchestrator and sub-agents."""

from src.agents.lastfm_agent import LastFMAgent, LastFMResult
from src.agents.musicbrainz_agent import MusicBrainzAgent, MusicBrainzResult
from src.agents.orchestrator import AgentResult, OrchestratorAgent
from src.agents.scraper_agent import ScraperResult, WebScraperAgent
from src.agents.spotify_agent import SpotifyAgent, SpotifyResult

__all__ = [
    "LastFMAgent",
    "LastFMResult",
    "MusicBrainzAgent",
    "MusicBrainzResult",
    "OrchestratorAgent",
    "AgentResult",
    "ScraperResult",
    "WebScraperAgent",
    "SpotifyAgent",
    "SpotifyResult",
]
