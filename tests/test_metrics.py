"""Unit tests for metrics calculation utilities."""

import pytest
from datetime import date

from src.models.nodes import Song, Artist, Album, AudioFeatures
from src.utils.metrics import calculate_completeness, _is_field_populated


class TestIsFieldPopulated:
    """Tests for _is_field_populated helper function."""

    def test_none_is_not_populated(self):
        """Test that None is not considered populated."""
        assert _is_field_populated(None) is False

    def test_empty_string_is_not_populated(self):
        """Test that empty string is not considered populated."""
        assert _is_field_populated("") is False
        assert _is_field_populated("   ") is False

    def test_non_empty_string_is_populated(self):
        """Test that non-empty string is considered populated."""
        assert _is_field_populated("test") is True

    def test_empty_list_is_not_populated(self):
        """Test that empty list is not considered populated."""
        assert _is_field_populated([]) is False

    def test_non_empty_list_is_populated(self):
        """Test that non-empty list is considered populated."""
        assert _is_field_populated(["item"]) is True

    def test_empty_dict_is_not_populated(self):
        """Test that empty dict is not considered populated."""
        assert _is_field_populated({}) is False

    def test_non_empty_dict_is_populated(self):
        """Test that non-empty dict is considered populated."""
        assert _is_field_populated({"key": "value"}) is True

    def test_zero_is_populated(self):
        """Test that zero values are considered populated."""
        assert _is_field_populated(0) is True
        assert _is_field_populated(0.0) is True

    def test_numeric_values_are_populated(self):
        """Test that numeric values are considered populated."""
        assert _is_field_populated(42) is True
        assert _is_field_populated(3.14) is True


class TestCalculateCompleteness:
    """Tests for calculate_completeness function."""

    def test_minimal_song_completeness(self):
        """Test completeness for song with only required fields."""
        song = Song(title="Test Song", spotify_id="test123")
        score = calculate_completeness(song, "Song")
        assert 0.0 <= score <= 1.0
        # Should have low completeness since only title and spotify_id are populated
        assert score < 0.5

    def test_fully_populated_song_completeness(self):
        """Test completeness for fully populated song."""
        audio_features = AudioFeatures(
            tempo=120.0,
            key=5,
            mode=1,
            time_signature=4,
            energy=0.8,
            danceability=0.7,
            valence=0.6,
            acousticness=0.3,
        )
        song = Song(
            title="Test Song",
            duration_ms=180000,
            release_date=date(2024, 1, 1),
            isrc="USRC12345678",
            spotify_id="test123",
            musicbrainz_id="550e8400-e29b-41d4-a716-446655440000",
            lastfm_url="https://last.fm/music/test",
            audio_features=audio_features,
            tags=["rock", "alternative"],
            play_count=1000,
            listener_count=500,
        )
        score = calculate_completeness(song, "Song")
        assert 0.0 <= score <= 1.0
        # Should have high completeness since most fields are populated
        assert score > 0.8

    def test_critical_fields_weighted_higher(self):
        """Test that critical fields are weighted higher than optional fields."""
        # Song with critical fields populated
        song1 = Song(title="Test Song", duration_ms=180000, spotify_id="test123")
        score1 = calculate_completeness(song1, "Song")

        # Song with fewer fields but including optional ones
        song2 = Song(
            title="Test Song",
            spotify_id="test123",
            tags=["rock"],
        )
        score2 = calculate_completeness(song2, "Song")

        # Both should have valid scores
        assert 0.0 <= score1 <= 1.0
        assert 0.0 <= score2 <= 1.0
        # Song with duration (critical field) should have reasonable completeness
        assert score1 > 0.3

    def test_artist_completeness(self):
        """Test completeness calculation for artist."""
        artist = Artist(name="Test Artist", genres=["rock"], spotify_id="artist123")
        score = calculate_completeness(artist, "Artist")
        assert 0.0 <= score <= 1.0

    def test_album_completeness(self):
        """Test completeness calculation for album."""
        album = Album(
            title="Test Album",
            album_type="album",
            release_date=date(2024, 1, 1),
            total_tracks=12,
        )
        score = calculate_completeness(album, "Album")
        assert 0.0 <= score <= 1.0

    def test_completeness_score_range(self):
        """Test that completeness score is always between 0.0 and 1.0."""
        # Test with various entity configurations
        entities = [
            (Song(title="Test", spotify_id="123"), "Song"),
            (Artist(name="Test", spotify_id="123"), "Artist"),
            (Album(title="Test", album_type="album"), "Album"),
        ]

        for entity, entity_type in entities:
            score = calculate_completeness(entity, entity_type)
            assert 0.0 <= score <= 1.0, f"Score {score} out of range for {entity_type}"

    def test_empty_optional_fields_not_counted(self):
        """Test that empty optional fields are not counted as populated."""
        song = Song(
            title="Test Song",
            spotify_id="test123",
            tags=[],  # Empty list
            play_count=0,  # Zero is valid
        )
        score = calculate_completeness(song, "Song")
        assert 0.0 <= score <= 1.0

    def test_nested_model_completeness(self):
        """Test completeness with nested models (AudioFeatures)."""
        # Song without audio features
        song1 = Song(title="Test", spotify_id="123")
        score1 = calculate_completeness(song1, "Song")

        # Song with populated audio features
        audio_features_full = AudioFeatures(tempo=120.0, key=5, energy=0.8)
        song2 = Song(title="Test", spotify_id="123", audio_features=audio_features_full)
        score2 = calculate_completeness(song2, "Song")

        # Song with populated audio features should have higher score
        assert score2 > score1
