"""Graph edge data models for relationships between music entities."""

from datetime import date
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class PerformedInEdge(BaseModel):
    """Edge representing an artist performing in a song."""

    from_node_id: UUID = Field(..., description="Artist node ID")
    to_node_id: UUID = Field(..., description="Song node ID")
    edge_type: str = Field(default="PERFORMED_IN", description="Edge type")
    role: Optional[str] = Field(None, description="Performance role (e.g., lead, backing)")
    is_lead: bool = Field(default=False, description="Whether this is the lead performer")

    @field_validator("edge_type")
    @classmethod
    def validate_edge_type(cls, v: str) -> str:
        """Ensure edge_type is correct."""
        if v != "PERFORMED_IN":
            raise ValueError("edge_type must be 'PERFORMED_IN'")
        return v


class PlayedInstrumentEdge(BaseModel):
    """Edge representing an artist playing an instrument."""

    from_node_id: UUID = Field(..., description="Artist node ID")
    to_node_id: UUID = Field(..., description="Instrument node ID")
    edge_type: str = Field(default="PLAYED_INSTRUMENT", description="Edge type")
    song_id: Optional[UUID] = Field(None, description="Song ID where instrument was played")
    is_primary: bool = Field(default=False, description="Whether this is the primary instrument")

    @field_validator("edge_type")
    @classmethod
    def validate_edge_type(cls, v: str) -> str:
        """Ensure edge_type is correct."""
        if v != "PLAYED_INSTRUMENT":
            raise ValueError("edge_type must be 'PLAYED_INSTRUMENT'")
        return v


class SignedWithEdge(BaseModel):
    """Edge representing an artist signed with a record label."""

    from_node_id: UUID = Field(..., description="Artist node ID")
    to_node_id: UUID = Field(..., description="RecordLabel node ID")
    edge_type: str = Field(default="SIGNED_WITH", description="Edge type")
    start_date: Optional[date] = Field(None, description="Contract start date")
    end_date: Optional[date] = Field(None, description="Contract end date")
    contract_type: Optional[str] = Field(None, description="Type of contract")

    @field_validator("edge_type")
    @classmethod
    def validate_edge_type(cls, v: str) -> str:
        """Ensure edge_type is correct."""
        if v != "SIGNED_WITH":
            raise ValueError("edge_type must be 'SIGNED_WITH'")
        return v

    @field_validator("end_date")
    @classmethod
    def validate_end_after_start(cls, v: Optional[date], info) -> Optional[date]:
        """Ensure end_date is after start_date if both present."""
        if v and info.data.get("start_date") and v < info.data["start_date"]:
            raise ValueError("end_date must be after start_date")
        return v


class PartOfAlbumEdge(BaseModel):
    """Edge representing a song being part of an album."""

    from_node_id: UUID = Field(..., description="Song node ID")
    to_node_id: UUID = Field(..., description="Album node ID")
    edge_type: str = Field(default="PART_OF_ALBUM", description="Edge type")
    track_number: Optional[int] = Field(None, gt=0, description="Track number on album")
    disc_number: Optional[int] = Field(None, gt=0, description="Disc number")

    @field_validator("edge_type")
    @classmethod
    def validate_edge_type(cls, v: str) -> str:
        """Ensure edge_type is correct."""
        if v != "PART_OF_ALBUM":
            raise ValueError("edge_type must be 'PART_OF_ALBUM'")
        return v


class PerformedAtEdge(BaseModel):
    """Edge representing an artist performing at a concert."""

    from_node_id: UUID = Field(..., description="Artist node ID")
    to_node_id: UUID = Field(..., description="Concert node ID")
    edge_type: str = Field(default="PERFORMED_AT", description="Edge type")
    performance_order: Optional[int] = Field(None, gt=0, description="Order in the concert lineup")
    duration_minutes: Optional[int] = Field(None, gt=0, description="Performance duration")

    @field_validator("edge_type")
    @classmethod
    def validate_edge_type(cls, v: str) -> str:
        """Ensure edge_type is correct."""
        if v != "PERFORMED_AT":
            raise ValueError("edge_type must be 'PERFORMED_AT'")
        return v


class SimilarToEdge(BaseModel):
    """Edge representing similarity between two songs."""

    from_node_id: UUID = Field(..., description="Song node ID")
    to_node_id: UUID = Field(..., description="Similar song node ID")
    edge_type: str = Field(default="SIMILAR_TO", description="Edge type")
    similarity_score: float = Field(
        ..., ge=0.0, le=1.0, description="Similarity score (0.0 to 1.0)"
    )
    source: Optional[str] = Field(None, description="Source of similarity data")

    @field_validator("edge_type")
    @classmethod
    def validate_edge_type(cls, v: str) -> str:
        """Ensure edge_type is correct."""
        if v != "SIMILAR_TO":
            raise ValueError("edge_type must be 'SIMILAR_TO'")
        return v
