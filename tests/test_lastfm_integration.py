"""Integration tests for Last.fm agent."""

from src.agents import LastFMAgent, LastFMResult


class TestLastFMIntegration:
    """Integration tests for Last.fm agent."""

    def test_lastfm_agent_can_be_imported(self):
        """Test that Last.fm agent can be imported from agents module."""
        assert LastFMAgent is not None
        assert LastFMResult is not None

    def test_lastfm_agent_can_be_instantiated(self):
        """Test that Last.fm agent can be instantiated."""
        agent = LastFMAgent(api_key="test_key")
        assert agent is not None
        assert agent.api_key == "test_key"
        assert agent.rate_limiter is not None

    def test_lastfm_agent_has_required_methods(self):
        """Test that Last.fm agent has all required methods."""
        agent = LastFMAgent(api_key="test_key")

        assert hasattr(agent, "search_track")
        assert hasattr(agent, "get_track_info")
        assert hasattr(agent, "get_similar_tracks")
        assert hasattr(agent, "get_top_tags")
        assert hasattr(agent, "fetch_lastfm_data")
        assert hasattr(agent, "close")

    def test_lastfm_result_structure(self):
        """Test that Last.fm result has expected structure."""
        result = LastFMResult()

        assert hasattr(result, "song")
        assert hasattr(result, "artists")
        assert hasattr(result, "similar_tracks")
        assert hasattr(result, "tags")
        assert hasattr(result, "completeness_score")

        assert result.song is None
        assert result.artists == []
        assert result.similar_tracks == []
        assert result.tags == []
        assert result.completeness_score == 0.0

    def test_lastfm_rate_limiter_configuration(self):
        """Test that Last.fm rate limiter is configured correctly."""
        agent = LastFMAgent(api_key="test_key")

        # Should enforce 5 requests per second
        assert agent.rate_limiter.max_requests_per_second == 5
        assert agent.rate_limiter.min_interval == 0.2  # 1/5 = 0.2 seconds
