"""
Pydantic models for representing PyRAT tank data.

This module defines the data structures for tanks retrieved from the PyRAT API,
including age information and status tracking.
"""

from datetime import datetime
from typing import Optional, Literal
from pydantic import BaseModel, Field, computed_field


# Age status based on fish age thresholds
AgeStatus = Literal["URGENT", "WARNING", "OK", "UNKNOWN"]


class PyRATTank(BaseModel):
    """Represents a tank from the PyRAT API with age monitoring."""

    # Core identification
    tank_id: int = Field(..., description="Unique identifier for the tank")
    tank_label: Optional[str] = Field(default=None, description="Human-readable tank label")

    # Location fields
    tank_position: Optional[str] = Field(default=None, description="Position within the rack")
    location_rack_name: Optional[str] = Field(default=None, description="Name of the rack")
    location_room_name: Optional[str] = Field(default=None, description="Name of the room")
    location_area_name: Optional[str] = Field(default=None, description="Name of the area")
    location_building_name: Optional[str] = Field(default=None, description="Name of the building")

    # Responsible person info
    responsible_id: Optional[int] = Field(default=None, description="ID of the responsible person")
    responsible_fullname: Optional[str] = Field(default=None, description="Full name of responsible person")
    owner_fullname: Optional[str] = Field(default=None, description="Full name of the owner")

    # Tank status and strain
    status: Optional[str] = Field(default=None, description="Tank status (open, closed, exported, joined)")
    strain_name_with_id: Optional[str] = Field(default=None, description="Strain name with ID")
    age_level: Optional[str] = Field(default=None, description="Age level from PyRAT")

    # Fish counts
    number_of_male: int = Field(default=0, description="Number of male fish")
    number_of_female: int = Field(default=0, description="Number of female fish")
    number_of_unknown: int = Field(default=0, description="Number of fish with unknown sex")

    # Date fields
    date_of_birth: Optional[str] = Field(default=None, description="Birth date of fish in tank")
    date_of_release: Optional[str] = Field(default=None, description="Release date")
    export_date: Optional[str] = Field(default=None, description="Export date")
    close_date: Optional[str] = Field(default=None, description="Close date")

    # Calculated age fields (added by add_age_information)
    age_days: Optional[int] = Field(default=None, description="Age in days")
    age_weeks: Optional[int] = Field(default=None, description="Age in weeks")
    age_months: Optional[int] = Field(default=None, description="Age in months")
    age_status: AgeStatus = Field(default="UNKNOWN", description="Age status for monitoring")

    @computed_field
    @property
    def total_fish(self) -> int:
        """Total number of fish in the tank."""
        return self.number_of_male + self.number_of_female + self.number_of_unknown

    @computed_field
    @property
    def location_display(self) -> str:
        """Formatted location string for display."""
        parts = []
        if self.location_building_name:
            parts.append(self.location_building_name)
        if self.location_room_name:
            parts.append(self.location_room_name)
        if self.location_rack_name:
            parts.append(self.location_rack_name)
        if self.tank_position:
            parts.append(f"Pos: {self.tank_position}")
        return " / ".join(parts) if parts else "Unknown location"

    @classmethod
    def from_api_dict(cls, data: dict) -> "PyRATTank":
        """
        Create a PyRATTank instance from a raw API dictionary.

        Handles missing fields gracefully by using defaults.
        """
        return cls(
            tank_id=data.get("tank_id", 0),
            tank_label=data.get("tank_label"),
            tank_position=data.get("tank_position"),
            location_rack_name=data.get("location_rack_name"),
            location_room_name=data.get("location_room_name"),
            location_area_name=data.get("location_area_name"),
            location_building_name=data.get("location_building_name"),
            responsible_id=data.get("responsible_id"),
            responsible_fullname=data.get("responsible_fullname"),
            owner_fullname=data.get("owner_fullname"),
            status=data.get("status"),
            strain_name_with_id=data.get("strain_name_with_id"),
            age_level=data.get("age_level"),
            number_of_male=data.get("number_of_male", 0) or 0,
            number_of_female=data.get("number_of_female", 0) or 0,
            number_of_unknown=data.get("number_of_unknown", 0) or 0,
            date_of_birth=data.get("date_of_birth"),
            date_of_release=data.get("date_of_release"),
            export_date=data.get("export_date"),
            close_date=data.get("close_date"),
            age_days=data.get("age_days"),
            age_weeks=data.get("age_weeks"),
            age_months=data.get("age_months"),
            age_status=data.get("age_status", "UNKNOWN"),
        )

    class Config:
        from_attributes = True
