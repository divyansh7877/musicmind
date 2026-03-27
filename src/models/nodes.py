"""Graph node data models for music entities."""

from datetime import date, datetime
from typing import List, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, field_validator


class AudioFeatures(BaseModel):
    """Audio features for a song."""

    tempo: Optional[float] = Field(None, ge=0.0, description="Tempo in BPM")
    key: Optional[int] = Field(None, ge=0, le=11, description="Musical key (0-11)")
    mode: Optional[int] = Field(None, ge=0, le=1, description="Mode (0=minor, 1=major)")
    time_signature: Optional[int] = Field(None, ge=1, le=7, description="Time signature")
    energy: Optional[float] = Field(None, ge=0.0, le=1.0, description="Energy level")
    danceability: Optional[float] = Field(None, ge=0.0, le=1.0, description="Danceability")
    valence: Optional[float] = Field(None, ge=0.0, le=1.0, description="Musical positivity")
    acousticness: Optional[float] = Field(None, ge=0.0, le=1.0, description="Acousticness")


class Song(BaseModel):
    """Song node in the music graph."""

    id: UUID = Field(default_factory=uuid4, description="Unique identifier")
    title: str = Field(..., min_length=1, description="Song title")
    duration_ms: Optional[int] = Field(None, gt=0, description="Duration in milliseconds")
    release_date: Optional[date] = Field(None, description="Release date")
    isrc: Optional[str] = Field(None, description="International Standard Recording Code")
    spotify_id: Optional[str] = Field(None, description="Spotify track ID")
    musicbrainz_id: Optional[UUID] = Field(None, description="MusicBrainz recording ID")
    lastfm_url: Optional[str] = Field(None, description="Last.fm URL")
    audio_features: Optional[AudioFeatures] = Field(None, description="Audio features")
    tags: List[str] = Field(default_factory=list, description="User-generated tags")
    play_count: Optional[int] = Field(None, ge=0, description="Play count")
    listener_count: Optional[int] = Field(None, ge=0, description="Listener count")
    completeness_score: float = Field(
        default=0.0, ge=0.0, le=1.0, description="Data completeness score"
    )
    last_enriched: datetime = Field(
        default_factory=datetime.utcnow, description="Last enrichment timestamp"
    )
    data_sources: List[str] = Field(default_factory=list, description="Data source names")

    @field_validator("last_enriched")
    @classmethod
    def validate_last_enriched_not_future(cls, v: datetime) -> datetime:
        """Ensure last_enriched is not in the future."""
        if v > datetime.utcnow():
            raise ValueError("last_enriched cannot be in the future")
        return v

    @field_validator("title")
    @classmethod
    def validate_title_not_empty(cls, v: str) -> str:
        """Ensure title is not empty after stripping whitespace."""
        if not v.strip():
            raise ValueError("title cannot be empty")
        return v.strip()

    def model_post_init(self, __context) -> None:
        """Validate at least one external ID is present."""
        if not any([self.spotify_id, self.musicbrainz_id, self.lastfm_url]):
            raise ValueError("At least one external ID must be present")


class Artist(BaseModel):
    """Artist node in the music graph."""

    id: UUID = Field(default_factory=uuid4, description="Unique identifier")
    name: str = Field(..., min_length=1, description="Artist name")
    genres: List[str] = Field(default_factory=list, description="Music genres")
    country: Optional[str] = Field(None, description="Country of origin")
    formed_date: Optional[date] = Field(None, description="Formation date")
    disbanded_date: Optional[date] = Field(None, description="Disbandment date")
    spotify_id: Optional[str] = Field(None, description="Spotify artist ID")
    musicbrainz_id: Optional[UUID] = Field(None, description="MusicBrainz artist ID")
    lastfm_url: Optional[str] = Field(None, description="Last.fm URL")
    popularity: Optional[int] = Field(None, ge=0, le=100, description="Popularity score")
    follower_count: Optional[int] = Field(None, ge=0, description="Follower count")
    biography: Optional[str] = Field(None, description="Artist biography")
    image_urls: List[str] = Field(default_factory=list, description="Image URLs")
    completeness_score: float = Field(
        default=0.0, ge=0.0, le=1.0, description="Data completeness score"
    )
    last_enriched: datetime = Field(
        default_factory=datetime.utcnow, description="Last enrichment timestamp"
    )

    @field_validator("disbanded_date")
    @classmethod
    def validate_disbanded_after_formed(cls, v: Optional[date], info) -> Optional[date]:
        """Ensure disbanded_date is after formed_date if both present."""
        if v and info.data.get("formed_date") and v < info.data["formed_date"]:
            raise ValueError("disbanded_date must be after formed_date")
        return v

    @field_validator("name")
    @classmethod
    def validate_name_not_empty(cls, v: str) -> str:
        """Ensure name is not empty after stripping whitespace."""
        if not v.strip():
            raise ValueError("name cannot be empty")
        return v.strip()

    def model_post_init(self, __context) -> None:
        """Validate at least one external ID is present."""
        if not any([self.spotify_id, self.musicbrainz_id, self.lastfm_url]):
            raise ValueError("At least one external ID must be present")


class Album(BaseModel):
    """Album node in the music graph."""

    id: UUID = Field(default_factory=uuid4, description="Unique identifier")
    title: str = Field(..., min_length=1, description="Album title")
    release_date: Optional[date] = Field(None, description="Release date")
    album_type: str = Field(..., description="Album type: album, single, compilation, or ep")
    total_tracks: Optional[int] = Field(None, gt=0, description="Total number of tracks")
    spotify_id: Optional[str] = Field(None, description="Spotify album ID")
    musicbrainz_id: Optional[UUID] = Field(None, description="MusicBrainz release ID")
    label: Optional[str] = Field(None, description="Record label name")
    catalog_number: Optional[str] = Field(None, description="Catalog number")
    cover_art_url: Optional[str] = Field(None, description="Cover art URL")
    completeness_score: float = Field(
        default=0.0, ge=0.0, le=1.0, description="Data completeness score"
    )
    last_enriched: datetime = Field(
        default_factory=datetime.utcnow, description="Last enrichment timestamp"
    )

    @field_validator("album_type")
    @classmethod
    def validate_album_type(cls, v: str) -> str:
        """Ensure album_type is one of the valid values."""
        valid_types = {"album", "single", "compilation", "ep"}
        if v.lower() not in valid_types:
            raise ValueError(f"album_type must be one of: {', '.join(valid_types)}")
        return v.lower()

    @field_validator("title")
    @classmethod
    def validate_title_not_empty(cls, v: str) -> str:
        """Ensure title is not empty after stripping whitespace."""
        if not v.strip():
            raise ValueError("title cannot be empty")
        return v.strip()


class RecordLabel(BaseModel):
    """Record label node in the music graph."""

    id: UUID = Field(default_factory=uuid4, description="Unique identifier")
    name: str = Field(..., min_length=1, description="Label name")
    country: Optional[str] = Field(None, description="Country of origin")
    founded_date: Optional[date] = Field(None, description="Founded date")
    musicbrainz_id: Optional[UUID] = Field(None, description="MusicBrainz label ID")
    website_url: Optional[str] = Field(None, description="Official website URL")
    parent_label_id: Optional[UUID] = Field(None, description="Parent label ID")
    completeness_score: float = Field(
        default=0.0, ge=0.0, le=1.0, description="Data completeness score"
    )
    last_enriched: datetime = Field(
        default_factory=datetime.utcnow, description="Last enrichment timestamp"
    )

    @field_validator("name")
    @classmethod
    def validate_name_not_empty(cls, v: str) -> str:
        """Ensure name is not empty after stripping whitespace."""
        if not v.strip():
            raise ValueError("name cannot be empty")
        return v.strip()


class Instrument(BaseModel):
    """Instrument node in the music graph."""

    id: UUID = Field(default_factory=uuid4, description="Unique identifier")
    name: str = Field(..., min_length=1, description="Instrument name")
    category: str = Field(..., description="Instrument category")
    musicbrainz_id: Optional[UUID] = Field(None, description="MusicBrainz instrument ID")
    description: Optional[str] = Field(None, description="Instrument description")

    @field_validator("category")
    @classmethod
    def validate_category(cls, v: str) -> str:
        """Ensure category is one of the valid values."""
        valid_categories = {
            "string",
            "percussion",
            "wind",
            "keyboard",
            "electronic",
            "vocal",
            "other",
        }
        if v.lower() not in valid_categories:
            raise ValueError(f"category must be one of: {', '.join(valid_categories)}")
        return v.lower()

    @field_validator("name")
    @classmethod
    def validate_name_not_empty(cls, v: str) -> str:
        """Ensure name is not empty after stripping whitespace."""
        if not v.strip():
            raise ValueError("name cannot be empty")
        return v.strip()


class Venue(BaseModel):
    """Venue node in the music graph."""

    id: UUID = Field(default_factory=uuid4, description="Unique identifier")
    name: str = Field(..., min_length=1, description="Venue name")
    city: str = Field(..., min_length=1, description="City")
    country: str = Field(..., min_length=1, description="Country")
    capacity: Optional[int] = Field(None, gt=0, description="Venue capacity")
    latitude: Optional[float] = Field(None, ge=-90.0, le=90.0, description="Latitude")
    longitude: Optional[float] = Field(None, ge=-180.0, le=180.0, description="Longitude")
    address: Optional[str] = Field(None, description="Street address")
    website_url: Optional[str] = Field(None, description="Official website URL")
    completeness_score: float = Field(
        default=0.0, ge=0.0, le=1.0, description="Data completeness score"
    )
    last_enriched: datetime = Field(
        default_factory=datetime.utcnow, description="Last enrichment timestamp"
    )

    @field_validator("name", "city", "country")
    @classmethod
    def validate_not_empty(cls, v: str) -> str:
        """Ensure field is not empty after stripping whitespace."""
        if not v.strip():
            raise ValueError("field cannot be empty")
        return v.strip()


class Concert(BaseModel):
    """Concert node in the music graph."""

    id: UUID = Field(default_factory=uuid4, description="Unique identifier")
    concert_date: date = Field(..., description="Concert date")
    venue_id: UUID = Field(..., description="Venue ID")
    tour_name: Optional[str] = Field(None, description="Tour name")
    setlist: List[str] = Field(default_factory=list, description="Song titles in setlist")
    attendance: Optional[int] = Field(None, gt=0, description="Attendance count")
    ticket_price_range: Optional[str] = Field(None, description="Ticket price range")
    completeness_score: float = Field(
        default=0.0, ge=0.0, le=1.0, description="Data completeness score"
    )
    last_enriched: datetime = Field(
        default_factory=datetime.utcnow, description="Last enrichment timestamp"
    )
