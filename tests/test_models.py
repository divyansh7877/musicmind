"""Unit tests for graph node and edge models."""

import pytest
from datetime import date, datetime, timedelta
from uuid import uuid4

from src.models.nodes import (
    Song,
    Artist,
    Album,
    RecordLabel,
    Instrument,
    Venue,
    Concert,
    AudioFeatures,
)
from src.models.edges import (
    PerformedInEdge,
    PlayedInstrumentEdge,
    SignedWithEdge,
    PartOfAlbumEdge,
    PerformedAtEdge,
    SimilarToEdge,
)


class TestSongNode:
    """Tests for Song node model."""

    def test_song_creation_with_required_fields(self):
        """Test creating a song with only required fields."""
        song = Song(title="Test Song", spotify_id="test123")
        assert song.title == "Test Song"
        assert song.spotify_id == "test123"
        assert 0.0 <= song.completeness_score <= 1.0

    def test_song_title_cannot_be_empty(self):
        """Test that song title cannot be empty."""
        with pytest.raises(Exception):  # Pydantic ValidationError
            Song(title="", spotify_id="test123")

    def test_song_title_strips_whitespace(self):
        """Test that song title strips whitespace."""
        song = Song(title="  Test Song  ", spotify_id="test123")
        assert song.title == "Test Song"

    def test_song_requires_external_id(self):
        """Test that at least one external ID is required."""
        with pytest.raises(ValueError, match="At least one external ID must be present"):
            Song(title="Test Song")

    def test_song_duration_must_be_positive(self):
        """Test that duration must be positive."""
        with pytest.raises(ValueError):
            Song(title="Test Song", spotify_id="test123", duration_ms=-100)

    def test_song_last_enriched_not_future(self):
        """Test that last_enriched cannot be in the future."""
        future_date = datetime.utcnow() + timedelta(days=1)
        with pytest.raises(ValueError, match="last_enriched cannot be in the future"):
            Song(title="Test Song", spotify_id="test123", last_enriched=future_date)

    def test_song_with_audio_features(self):
        """Test creating a song with audio features."""
        audio_features = AudioFeatures(
            tempo=120.0, key=5, mode=1, energy=0.8, danceability=0.7
        )
        song = Song(title="Test Song", spotify_id="test123", audio_features=audio_features)
        assert song.audio_features.tempo == 120.0
        assert song.audio_features.key == 5


class TestArtistNode:
    """Tests for Artist node model."""

    def test_artist_creation_with_required_fields(self):
        """Test creating an artist with only required fields."""
        artist = Artist(name="Test Artist", spotify_id="artist123")
        assert artist.name == "Test Artist"
        assert artist.spotify_id == "artist123"

    def test_artist_name_cannot_be_empty(self):
        """Test that artist name cannot be empty."""
        with pytest.raises(Exception):  # Pydantic ValidationError
            Artist(name="", spotify_id="artist123")

    def test_artist_requires_external_id(self):
        """Test that at least one external ID is required."""
        with pytest.raises(ValueError, match="At least one external ID must be present"):
            Artist(name="Test Artist")

    def test_artist_popularity_range(self):
        """Test that popularity must be between 0 and 100."""
        with pytest.raises(ValueError):
            Artist(name="Test Artist", spotify_id="artist123", popularity=150)

    def test_artist_disbanded_after_formed(self):
        """Test that disbanded_date must be after formed_date."""
        with pytest.raises(ValueError, match="disbanded_date must be after formed_date"):
            Artist(
                name="Test Artist",
                spotify_id="artist123",
                formed_date=date(2000, 1, 1),
                disbanded_date=date(1999, 1, 1),
            )


class TestAlbumNode:
    """Tests for Album node model."""

    def test_album_creation_with_required_fields(self):
        """Test creating an album with only required fields."""
        album = Album(title="Test Album", album_type="album")
        assert album.title == "Test Album"
        assert album.album_type == "album"

    def test_album_type_validation(self):
        """Test that album_type must be valid."""
        with pytest.raises(ValueError, match="album_type must be one of"):
            Album(title="Test Album", album_type="invalid")

    def test_album_type_case_insensitive(self):
        """Test that album_type is case insensitive."""
        album = Album(title="Test Album", album_type="SINGLE")
        assert album.album_type == "single"

    def test_album_total_tracks_positive(self):
        """Test that total_tracks must be positive."""
        with pytest.raises(ValueError):
            Album(title="Test Album", album_type="album", total_tracks=0)


class TestInstrumentNode:
    """Tests for Instrument node model."""

    def test_instrument_creation(self):
        """Test creating an instrument."""
        instrument = Instrument(name="Guitar", category="string")
        assert instrument.name == "Guitar"
        assert instrument.category == "string"

    def test_instrument_category_validation(self):
        """Test that category must be valid."""
        with pytest.raises(ValueError, match="category must be one of"):
            Instrument(name="Guitar", category="invalid")

    def test_instrument_category_case_insensitive(self):
        """Test that category is case insensitive."""
        instrument = Instrument(name="Drums", category="PERCUSSION")
        assert instrument.category == "percussion"


class TestVenueNode:
    """Tests for Venue node model."""

    def test_venue_creation(self):
        """Test creating a venue."""
        venue = Venue(name="Test Venue", city="New York", country="USA")
        assert venue.name == "Test Venue"
        assert venue.city == "New York"
        assert venue.country == "USA"

    def test_venue_latitude_range(self):
        """Test that latitude must be between -90 and 90."""
        with pytest.raises(ValueError):
            Venue(name="Test Venue", city="New York", country="USA", latitude=100.0)

    def test_venue_longitude_range(self):
        """Test that longitude must be between -180 and 180."""
        with pytest.raises(ValueError):
            Venue(name="Test Venue", city="New York", country="USA", longitude=200.0)

    def test_venue_capacity_positive(self):
        """Test that capacity must be positive."""
        with pytest.raises(ValueError):
            Venue(name="Test Venue", city="New York", country="USA", capacity=0)


class TestConcertNode:
    """Tests for Concert node model."""

    def test_concert_creation(self):
        """Test creating a concert."""
        venue_id = uuid4()
        concert = Concert(concert_date=date(2024, 1, 1), venue_id=venue_id)
        assert concert.concert_date == date(2024, 1, 1)
        assert concert.venue_id == venue_id


class TestEdges:
    """Tests for edge models."""

    def test_performed_in_edge(self):
        """Test creating a PERFORMED_IN edge."""
        artist_id = uuid4()
        song_id = uuid4()
        edge = PerformedInEdge(from_node_id=artist_id, to_node_id=song_id, is_lead=True)
        assert edge.from_node_id == artist_id
        assert edge.to_node_id == song_id
        assert edge.edge_type == "PERFORMED_IN"
        assert edge.is_lead is True

    def test_played_instrument_edge(self):
        """Test creating a PLAYED_INSTRUMENT edge."""
        artist_id = uuid4()
        instrument_id = uuid4()
        edge = PlayedInstrumentEdge(from_node_id=artist_id, to_node_id=instrument_id)
        assert edge.edge_type == "PLAYED_INSTRUMENT"

    def test_signed_with_edge(self):
        """Test creating a SIGNED_WITH edge."""
        artist_id = uuid4()
        label_id = uuid4()
        edge = SignedWithEdge(
            from_node_id=artist_id,
            to_node_id=label_id,
            start_date=date(2020, 1, 1),
            end_date=date(2023, 1, 1),
        )
        assert edge.edge_type == "SIGNED_WITH"

    def test_signed_with_edge_date_validation(self):
        """Test that end_date must be after start_date."""
        artist_id = uuid4()
        label_id = uuid4()
        with pytest.raises(ValueError, match="end_date must be after start_date"):
            SignedWithEdge(
                from_node_id=artist_id,
                to_node_id=label_id,
                start_date=date(2023, 1, 1),
                end_date=date(2020, 1, 1),
            )

    def test_part_of_album_edge(self):
        """Test creating a PART_OF_ALBUM edge."""
        song_id = uuid4()
        album_id = uuid4()
        edge = PartOfAlbumEdge(
            from_node_id=song_id, to_node_id=album_id, track_number=3, disc_number=1
        )
        assert edge.edge_type == "PART_OF_ALBUM"
        assert edge.track_number == 3

    def test_performed_at_edge(self):
        """Test creating a PERFORMED_AT edge."""
        artist_id = uuid4()
        concert_id = uuid4()
        edge = PerformedAtEdge(from_node_id=artist_id, to_node_id=concert_id)
        assert edge.edge_type == "PERFORMED_AT"

    def test_similar_to_edge(self):
        """Test creating a SIMILAR_TO edge."""
        song1_id = uuid4()
        song2_id = uuid4()
        edge = SimilarToEdge(
            from_node_id=song1_id, to_node_id=song2_id, similarity_score=0.85, source="lastfm"
        )
        assert edge.edge_type == "SIMILAR_TO"
        assert edge.similarity_score == 0.85

    def test_similar_to_edge_score_range(self):
        """Test that similarity_score must be between 0 and 1."""
        song1_id = uuid4()
        song2_id = uuid4()
        with pytest.raises(ValueError):
            SimilarToEdge(from_node_id=song1_id, to_node_id=song2_id, similarity_score=1.5)
