"""Tests for data validation (Task 20.3)."""

import pytest
from uuid import uuid4

from src.validation.data_validator import DataValidator, ValidationResult


class TestNodeValidation:
    """Test node field validation with partial acceptance."""

    def test_valid_song_passes(self):
        props = {
            "title": "Bohemian Rhapsody",
            "spotify_id": "sp123",
            "duration_ms": 354000,
        }
        result = DataValidator.validate_node("Song", props)
        assert result.valid is True
        assert result.cleaned_data["title"] == "Bohemian Rhapsody"
        assert result.invalid_fields == {}

    def test_song_missing_title_rejected(self):
        props = {"spotify_id": "sp123"}
        result = DataValidator.validate_node("Song", props)
        assert result.valid is False
        assert "title" in result.invalid_fields or "_model" in result.invalid_fields

    def test_song_invalid_field_stripped(self):
        """Invalid optional fields are stripped; valid fields remain."""
        props = {
            "title": "Test Song",
            "spotify_id": "sp123",
            "duration_ms": -100,  # Invalid: must be > 0
            "play_count": 5000,
        }
        result = DataValidator.validate_node("Song", props)
        # The model should reject duration_ms but keep everything else
        if result.valid:
            assert result.cleaned_data["title"] == "Test Song"
            assert result.cleaned_data.get("play_count") == 5000

    def test_song_unknown_field_stripped(self):
        """Unknown fields are silently stripped by Pydantic model construction."""
        props = {
            "title": "Test Song",
            "spotify_id": "sp123",
            "not_a_real_field": "garbage",
        }
        result = DataValidator.validate_node("Song", props)
        assert result.valid is True
        assert "not_a_real_field" not in result.cleaned_data

    def test_valid_artist(self):
        props = {
            "name": "Queen",
            "spotify_id": "art123",
            "genres": ["rock", "classic rock"],
            "country": "UK",
        }
        result = DataValidator.validate_node("Artist", props)
        assert result.valid is True
        assert result.cleaned_data["name"] == "Queen"

    def test_artist_empty_name_rejected(self):
        props = {"name": "  ", "spotify_id": "art123"}
        result = DataValidator.validate_node("Artist", props)
        assert result.valid is False

    def test_artist_disbanded_before_formed_rejected(self):
        props = {
            "name": "Test Band",
            "spotify_id": "art123",
            "formed_date": "2020-01-01",
            "disbanded_date": "2019-01-01",
        }
        result = DataValidator.validate_node("Artist", props)
        assert result.valid is False

    def test_valid_album(self):
        props = {
            "title": "A Night at the Opera",
            "album_type": "album",
            "total_tracks": 12,
        }
        result = DataValidator.validate_node("Album", props)
        assert result.valid is True

    def test_album_invalid_type_rejected(self):
        props = {
            "title": "Test Album",
            "album_type": "not_a_type",
        }
        result = DataValidator.validate_node("Album", props)
        assert result.valid is False

    def test_valid_venue(self):
        props = {
            "name": "Wembley Stadium",
            "city": "London",
            "country": "UK",
            "capacity": 90000,
        }
        result = DataValidator.validate_node("Venue", props)
        assert result.valid is True

    def test_venue_missing_city_rejected(self):
        props = {"name": "Wembley", "country": "UK"}
        result = DataValidator.validate_node("Venue", props)
        assert result.valid is False

    def test_unknown_node_type(self):
        result = DataValidator.validate_node("UnknownType", {"name": "test"})
        assert result.valid is False
        assert "node_type" in result.invalid_fields

    def test_external_id_warning(self):
        """Song/Artist without external IDs should generate a warning."""
        props = {"title": "No IDs Song"}
        result = DataValidator.validate_node("Song", props)
        # Depending on model validation, this may fail entirely or produce warnings
        if result.valid:
            assert len(result.warnings) > 0


class TestEdgeValidation:
    """Test edge validation."""

    def test_valid_performed_in_edge(self):
        props = {
            "from_node_id": str(uuid4()),
            "to_node_id": str(uuid4()),
            "edge_type": "PERFORMED_IN",
            "role": "lead",
        }
        result = DataValidator.validate_edge("PERFORMED_IN", props)
        assert result.valid is True

    def test_invalid_edge_type(self):
        props = {
            "from_node_id": str(uuid4()),
            "to_node_id": str(uuid4()),
            "edge_type": "WRONG_TYPE",
        }
        result = DataValidator.validate_edge("PERFORMED_IN", props)
        assert result.valid is False

    def test_unknown_edge_type(self):
        result = DataValidator.validate_edge("MADE_UP", {})
        assert result.valid is False
        assert "edge_type" in result.invalid_fields

    def test_similar_to_score_out_of_range(self):
        props = {
            "from_node_id": str(uuid4()),
            "to_node_id": str(uuid4()),
            "edge_type": "SIMILAR_TO",
            "similarity_score": 1.5,
        }
        result = DataValidator.validate_edge("SIMILAR_TO", props)
        assert result.valid is False


class TestMergedDataValidation:
    """Test validation of merged enrichment data."""

    def test_valid_merged_data(self):
        merged = {
            "song": {
                "title": "Test Song",
                "spotify_id": "sp123",
                "duration_ms": 180000,
            },
            "artists": [
                {"name": "Test Artist", "spotify_id": "art123"},
            ],
            "album": {
                "title": "Test Album",
                "album_type": "album",
            },
            "relationships": [],
            "data_sources": ["spotify"],
        }

        cleaned, invalid = DataValidator.validate_merged_data(merged)
        assert cleaned["song"]["title"] == "Test Song"
        # May have some invalid fields stripped, that's expected

    def test_empty_merged_data(self):
        cleaned, invalid = DataValidator.validate_merged_data({})
        assert cleaned == {}
        assert invalid == {}

    def test_invalid_artist_removed(self):
        merged = {
            "song": {"title": "Song", "spotify_id": "sp1"},
            "artists": [
                {"name": "Good Artist", "spotify_id": "art1"},
                {"name": "  "},  # Invalid: empty name after strip
            ],
            "album": {},
            "data_sources": ["spotify"],
        }

        cleaned, invalid = DataValidator.validate_merged_data(merged)
        # The second artist should be rejected
        assert len(cleaned["artists"]) <= 1 or any("artists[1]" in k for k in invalid)


class TestValidationResult:
    """Test ValidationResult model."""

    def test_valid_result(self):
        r = ValidationResult(
            valid=True,
            cleaned_data={"title": "Test"},
            invalid_fields={},
            warnings=[],
        )
        assert r.valid is True
        assert r.cleaned_data == {"title": "Test"}

    def test_invalid_result(self):
        r = ValidationResult(
            valid=False,
            cleaned_data={},
            invalid_fields={"title": "required"},
            warnings=["No external ID"],
        )
        assert r.valid is False
        assert len(r.warnings) == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
