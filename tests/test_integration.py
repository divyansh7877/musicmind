"""Integration tests for Task 2 - Graph schema and database operations."""

import pytest
from datetime import date
from uuid import uuid4

from src.models.nodes import Song, Artist, Album
from src.models.edges import PerformedInEdge, PartOfAlbumEdge
from src.utils.metrics import calculate_completeness


class TestTask2Integration:
    """Integration tests for Task 2 implementation."""

    def test_create_song_with_completeness(self):
        """Test creating a song and calculating its completeness score."""
        song = Song(
            title="Bohemian Rhapsody",
            duration_ms=354000,
            release_date=date(1975, 10, 31),
            spotify_id="test_spotify_id",
            tags=["rock", "classic rock", "progressive rock"],
            play_count=1000000,
        )

        # Calculate completeness
        completeness = calculate_completeness(song, "Song")

        assert song.title == "Bohemian Rhapsody"
        assert song.duration_ms == 354000
        assert 0.0 <= completeness <= 1.0
        assert completeness > 0.4  # Should have decent completeness

    def test_create_artist_with_validation(self):
        """Test creating an artist with validation rules."""
        artist = Artist(
            name="Queen",
            genres=["rock", "progressive rock"],
            country="UK",
            formed_date=date(1970, 1, 1),
            spotify_id="test_artist_id",
            popularity=95,
        )

        completeness = calculate_completeness(artist, "Artist")

        assert artist.name == "Queen"
        assert len(artist.genres) == 2
        assert artist.popularity == 95
        assert 0.0 <= completeness <= 1.0

    def test_create_album_with_type_validation(self):
        """Test creating an album with type validation."""
        album = Album(
            title="A Night at the Opera",
            album_type="album",
            release_date=date(1975, 11, 21),
            total_tracks=12,
        )

        assert album.title == "A Night at the Opera"
        assert album.album_type == "album"
        assert album.total_tracks == 12

    def test_create_edges_between_nodes(self):
        """Test creating edges between nodes."""
        artist_id = uuid4()
        song_id = uuid4()
        album_id = uuid4()

        # Create PERFORMED_IN edge
        performed_edge = PerformedInEdge(
            from_node_id=artist_id, to_node_id=song_id, is_lead=True, role="lead vocals"
        )

        assert performed_edge.from_node_id == artist_id
        assert performed_edge.to_node_id == song_id
        assert performed_edge.edge_type == "PERFORMED_IN"
        assert performed_edge.is_lead is True

        # Create PART_OF_ALBUM edge
        album_edge = PartOfAlbumEdge(
            from_node_id=song_id, to_node_id=album_id, track_number=11, disc_number=1
        )

        assert album_edge.from_node_id == song_id
        assert album_edge.to_node_id == album_id
        assert album_edge.edge_type == "PART_OF_ALBUM"
        assert album_edge.track_number == 11

    def test_completeness_increases_with_more_data(self):
        """Test that completeness score increases as more fields are populated."""
        # Minimal song
        song1 = Song(title="Test Song", spotify_id="test123")
        score1 = calculate_completeness(song1, "Song")

        # Song with more fields
        song2 = Song(
            title="Test Song",
            duration_ms=180000,
            release_date=date(2024, 1, 1),
            spotify_id="test123",
            tags=["rock"],
            play_count=1000,
        )
        score2 = calculate_completeness(song2, "Song")

        # More populated song should have higher completeness
        assert score2 > score1
        assert 0.0 <= score1 <= 1.0
        assert 0.0 <= score2 <= 1.0

    def test_validation_prevents_invalid_data(self):
        """Test that validation rules prevent invalid data."""
        # Test invalid duration
        with pytest.raises(Exception):
            Song(title="Test", spotify_id="test123", duration_ms=-100)

        # Test invalid popularity
        with pytest.raises(Exception):
            Artist(name="Test", spotify_id="test123", popularity=150)

        # Test invalid album type
        with pytest.raises(Exception):
            Album(title="Test", album_type="invalid_type")

        # Test invalid latitude
        from src.models.nodes import Venue

        with pytest.raises(Exception):
            Venue(name="Test", city="NYC", country="USA", latitude=100.0)

    def test_external_id_requirement(self):
        """Test that at least one external ID is required for songs and artists."""
        # Should fail without any external ID
        with pytest.raises(ValueError, match="At least one external ID must be present"):
            Song(title="Test Song")

        with pytest.raises(ValueError, match="At least one external ID must be present"):
            Artist(name="Test Artist")

        # Should succeed with any external ID
        song1 = Song(title="Test", spotify_id="test123")
        assert song1.spotify_id == "test123"

        song2 = Song(title="Test", musicbrainz_id=uuid4())
        assert song2.musicbrainz_id is not None

        song3 = Song(title="Test", lastfm_url="https://last.fm/test")
        assert song3.lastfm_url is not None
