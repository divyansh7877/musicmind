"""Metrics calculation utilities for data quality and completeness."""

from typing import Any, Dict, Set
from pydantic import BaseModel


# Define critical fields for each entity type with higher weights
CRITICAL_FIELDS: Dict[str, Set[str]] = {
    "Song": {"title", "duration_ms"},
    "Artist": {"name", "genres"},
    "Album": {"title", "album_type"},
    "RecordLabel": {"name"},
    "Instrument": {"name", "category"},
    "Venue": {"name", "city", "country"},
    "Concert": {"concert_date", "venue_id"},
}

# Weight for critical fields vs optional fields
CRITICAL_FIELD_WEIGHT = 2.0
OPTIONAL_FIELD_WEIGHT = 1.0


def calculate_completeness(entity: BaseModel, entity_type: str) -> float:
    """Calculate completeness score for an entity.

    The completeness score is calculated as a weighted average of populated fields.
    Critical fields (like title, name) are weighted higher than optional fields.

    Args:
        entity: Pydantic model instance of the entity
        entity_type: Type of entity (Song, Artist, Album, etc.)

    Returns:
        Float between 0.0 and 1.0 representing completeness

    Example:
        >>> song = Song(title="Test Song", duration_ms=180000)
        >>> score = calculate_completeness(song, "Song")
        >>> assert 0.0 <= score <= 1.0
    """
    # Get all fields from the model
    entity_dict = entity.model_dump()

    # Get critical fields for this entity type
    critical_fields = CRITICAL_FIELDS.get(entity_type, set())

    # Count populated fields with weights
    total_weight = 0.0
    populated_weight = 0.0

    for field_name, field_value in entity_dict.items():
        # Skip internal fields
        if field_name in {"id", "completeness_score", "last_enriched"}:
            continue

        # Determine weight for this field
        is_critical = field_name in critical_fields
        field_weight = CRITICAL_FIELD_WEIGHT if is_critical else OPTIONAL_FIELD_WEIGHT

        total_weight += field_weight

        # Check if field is populated
        if _is_field_populated(field_value):
            populated_weight += field_weight

    # Calculate completeness score
    if total_weight == 0:
        return 0.0

    score = populated_weight / total_weight

    # Ensure score is between 0.0 and 1.0
    return max(0.0, min(1.0, score))


def _is_field_populated(value: Any) -> bool:
    """Check if a field value is considered populated.

    Args:
        value: Field value to check

    Returns:
        True if field is populated, False otherwise
    """
    # None is not populated
    if value is None:
        return False

    # Empty strings are not populated
    if isinstance(value, str) and not value.strip():
        return False

    # Empty lists are not populated
    if isinstance(value, list) and len(value) == 0:
        return False

    # Empty dicts are not populated
    if isinstance(value, dict) and len(value) == 0:
        return False

    # Zero values for numeric fields are considered populated
    # (e.g., play_count=0 is valid data)
    if isinstance(value, (int, float)):
        return True

    # Nested models - check if they have any populated fields
    if isinstance(value, BaseModel):
        nested_dict = value.model_dump()
        return any(_is_field_populated(v) for v in nested_dict.values())

    # All other non-None values are populated
    return True
