"""Data validation service for enrichment data.

Validates node and edge data before persistence, applying partial validation
so that invalid fields are rejected while valid fields are retained.
"""

import logging
from typing import Any, Dict, List, Optional, Tuple, Type

from pydantic import BaseModel, ValidationError

from src.models.nodes import (
    Album,
    Artist,
    Concert,
    Instrument,
    RecordLabel,
    Song,
    Venue,
)
from src.models.edges import (
    PartOfAlbumEdge,
    PerformedAtEdge,
    PerformedInEdge,
    PlayedInstrumentEdge,
    SignedWithEdge,
    SimilarToEdge,
)

logger = logging.getLogger(__name__)

NODE_MODEL_MAP: Dict[str, Type[BaseModel]] = {
    "Song": Song,
    "Artist": Artist,
    "Album": Album,
    "RecordLabel": RecordLabel,
    "Instrument": Instrument,
    "Venue": Venue,
    "Concert": Concert,
}

EDGE_MODEL_MAP: Dict[str, Type[BaseModel]] = {
    "PERFORMED_IN": PerformedInEdge,
    "PLAYED_INSTRUMENT": PlayedInstrumentEdge,
    "SIGNED_WITH": SignedWithEdge,
    "PART_OF_ALBUM": PartOfAlbumEdge,
    "PERFORMED_AT": PerformedAtEdge,
    "SIMILAR_TO": SimilarToEdge,
}

# Fields that must always be present for each node type
REQUIRED_FIELDS: Dict[str, List[str]] = {
    "Song": ["title"],
    "Artist": ["name"],
    "Album": ["title", "album_type"],
    "RecordLabel": ["name"],
    "Instrument": ["name", "category"],
    "Venue": ["name", "city", "country"],
    "Concert": ["concert_date", "venue_id"],
}

# Node types that require at least one external ID
EXTERNAL_ID_FIELDS: Dict[str, List[str]] = {
    "Song": ["spotify_id", "musicbrainz_id", "lastfm_url"],
    "Artist": ["spotify_id", "musicbrainz_id", "lastfm_url"],
}


class ValidationResult:
    """Result of a validation operation."""

    def __init__(
        self,
        valid: bool,
        cleaned_data: Dict[str, Any],
        invalid_fields: Dict[str, str],
        warnings: List[str],
    ):
        self.valid = valid
        self.cleaned_data = cleaned_data
        self.invalid_fields = invalid_fields
        self.warnings = warnings


class DataValidator:
    """Validates enrichment data before persistence.

    Supports partial validation: individual invalid fields are removed
    while the remaining valid fields are kept, as long as all required
    fields are present and valid.
    """

    @staticmethod
    def validate_node(
        node_type: str,
        properties: Dict[str, Any],
    ) -> ValidationResult:
        """Validate node properties, rejecting invalid fields but keeping valid ones.

        Args:
            node_type: Type of node (Song, Artist, etc.)
            properties: Raw properties dictionary

        Returns:
            ValidationResult with cleaned data and any rejected fields
        """
        invalid_fields: Dict[str, str] = {}
        warnings: List[str] = []

        model_cls = NODE_MODEL_MAP.get(node_type)
        if not model_cls:
            return ValidationResult(
                valid=False,
                cleaned_data={},
                invalid_fields={"node_type": f"Unknown node type: {node_type}"},
                warnings=[],
            )

        # Try full validation first
        try:
            validated = model_cls(**properties)
            return ValidationResult(
                valid=True,
                cleaned_data=validated.model_dump(mode="json"),
                invalid_fields={},
                warnings=[],
            )
        except ValidationError:
            pass  # Fall through to partial validation

        # Partial validation: try removing fields one at a time
        cleaned = dict(properties)
        model_fields = model_cls.model_fields

        # Validate individual fields
        for field_name, field_value in list(properties.items()):
            if field_name not in model_fields:
                invalid_fields[field_name] = "Unknown field"
                cleaned.pop(field_name, None)
                continue

            field_info = model_fields[field_name]
            # Quick type/constraint checks
            error = DataValidator._validate_field(field_name, field_value, field_info)
            if error:
                invalid_fields[field_name] = error
                cleaned.pop(field_name, None)

        # Check required fields are still present
        required = REQUIRED_FIELDS.get(node_type, [])
        for req_field in required:
            if req_field not in cleaned or cleaned[req_field] is None:
                return ValidationResult(
                    valid=False,
                    cleaned_data=cleaned,
                    invalid_fields={
                        **invalid_fields,
                        req_field: "Required field missing or invalid",
                    },
                    warnings=warnings,
                )

        # Check external ID requirement
        ext_id_fields = EXTERNAL_ID_FIELDS.get(node_type, [])
        if ext_id_fields and not any(cleaned.get(f) for f in ext_id_fields):
            warnings.append(
                f"No external ID present. Expected at least one of: {', '.join(ext_id_fields)}"
            )

        # Try to construct model with cleaned data
        try:
            validated = model_cls(**cleaned)
            return ValidationResult(
                valid=True,
                cleaned_data=validated.model_dump(mode="json"),
                invalid_fields=invalid_fields,
                warnings=warnings,
            )
        except ValidationError as e:
            return ValidationResult(
                valid=False,
                cleaned_data=cleaned,
                invalid_fields={**invalid_fields, "_model": str(e)},
                warnings=warnings,
            )

    @staticmethod
    def validate_edge(
        edge_type: str,
        properties: Dict[str, Any],
    ) -> ValidationResult:
        """Validate edge properties.

        Args:
            edge_type: Type of edge (PERFORMED_IN, etc.)
            properties: Raw properties dictionary

        Returns:
            ValidationResult with cleaned data and any rejected fields
        """
        model_cls = EDGE_MODEL_MAP.get(edge_type)
        if not model_cls:
            return ValidationResult(
                valid=False,
                cleaned_data={},
                invalid_fields={"edge_type": f"Unknown edge type: {edge_type}"},
                warnings=[],
            )

        try:
            validated = model_cls(**properties)
            return ValidationResult(
                valid=True,
                cleaned_data=validated.model_dump(mode="json"),
                invalid_fields={},
                warnings=[],
            )
        except ValidationError as e:
            return ValidationResult(
                valid=False,
                cleaned_data=properties,
                invalid_fields={"_model": str(e)},
                warnings=[],
            )

    @staticmethod
    def validate_merged_data(merged_data: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, str]]:
        """Validate merged enrichment data before persistence.

        Validates song, artist, and album data within merged results.
        Invalid fields are stripped; valid fields are retained.

        Args:
            merged_data: Merged data from orchestrator

        Returns:
            Tuple of (cleaned_data, invalid_fields_report)
        """
        cleaned = dict(merged_data)
        all_invalid: Dict[str, str] = {}

        # Validate song data
        song_data = merged_data.get("song", {})
        if song_data:
            result = DataValidator.validate_node("Song", song_data)
            cleaned["song"] = result.cleaned_data
            if result.invalid_fields:
                for k, v in result.invalid_fields.items():
                    all_invalid[f"song.{k}"] = v

        # Validate artist data
        artists = merged_data.get("artists", [])
        if artists:
            validated_artists = []
            for i, artist_data in enumerate(artists):
                if isinstance(artist_data, dict):
                    result = DataValidator.validate_node("Artist", artist_data)
                    if result.valid:
                        validated_artists.append(result.cleaned_data)
                    else:
                        for k, v in result.invalid_fields.items():
                            all_invalid[f"artists[{i}].{k}"] = v
            cleaned["artists"] = validated_artists

        # Validate album data
        album_data = merged_data.get("album", {})
        if album_data:
            result = DataValidator.validate_node("Album", album_data)
            cleaned["album"] = result.cleaned_data
            if result.invalid_fields:
                for k, v in result.invalid_fields.items():
                    all_invalid[f"album.{k}"] = v

        if all_invalid:
            logger.warning(f"Validation removed invalid fields: {all_invalid}")

        return cleaned, all_invalid

    @staticmethod
    def _validate_field(field_name: str, value: Any, field_info) -> Optional[str]:
        """Validate a single field value against its field info.

        Returns an error string if invalid, None if valid.
        """
        if value is None:
            return None

        annotation = field_info.annotation
        # Strip Optional wrapper
        origin = getattr(annotation, "__origin__", None)
        if origin is type(None):
            return None

        # Basic type checks for common types
        if annotation is str or (origin and str in getattr(annotation, "__args__", ())):
            if isinstance(value, str):
                metadata = field_info.metadata
                for m in metadata:
                    if hasattr(m, "min_length") and m.min_length and len(value) < m.min_length:
                        return f"String too short (min {m.min_length})"
                    if hasattr(m, "max_length") and m.max_length and len(value) > m.max_length:
                        return f"String too long (max {m.max_length})"
                return None

        if annotation is int:
            if not isinstance(value, int):
                return f"Expected int, got {type(value).__name__}"

        if annotation is float:
            if not isinstance(value, (int, float)):
                return f"Expected float, got {type(value).__name__}"

        return None
