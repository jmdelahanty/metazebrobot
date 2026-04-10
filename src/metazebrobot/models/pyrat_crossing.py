"""
Pydantic models for representing PyRAT crossing data.

This module defines the data structures for crossings retrieved from the PyRAT API,
including parsed requested groups from descriptions and performance calculations.
"""

import re
from datetime import datetime
from typing import Optional, List, Literal
from pydantic import BaseModel, Field, computed_field


# Crossing status from PyRAT
CrossingStatus = Literal["recorded", "set-up", "raised", "discarded"]


class CrossingTank(BaseModel):
    """Represents a tank involved in a crossing (parent or child)."""

    tank_id: int = Field(..., description="Tank ID")
    tank_label: Optional[str] = Field(default=None, description="Tank label")
    status: Optional[str] = Field(default=None, description="Tank status")
    strain_name: Optional[str] = Field(default=None, description="Strain name")
    number_of_male: int = Field(default=0, description="Number of males")
    number_of_female: int = Field(default=0, description="Number of females")
    number_of_unknown: int = Field(default=0, description="Number of unknown sex")
    alive_count: Optional[int] = Field(default=None, description="Number alive")
    date_of_birth: Optional[str] = Field(default=None, description="Date of birth")

    # Location fields
    location_rack_name: Optional[str] = Field(default=None, description="Rack name (e.g., M11)")
    location_room_name: Optional[str] = Field(default=None, description="Room name")
    tank_position: Optional[str] = Field(default=None, description="Position on rack (e.g., E1)")

    @computed_field
    @property
    def total_fish(self) -> int:
        """Total number of fish in the tank."""
        return self.number_of_male + self.number_of_female + self.number_of_unknown

    @computed_field
    @property
    def location_display(self) -> str:
        """Human-readable identifier like #5182_M11>E1."""
        rack = self.location_rack_name
        pos = self.tank_position
        if rack and pos:
            return f"#{self.tank_id}_{rack}>{pos}"
        return f"#{self.tank_id}"


class PyRATCrossing(BaseModel):
    """Represents a crossing from the PyRAT API."""

    # Core identification
    crossing_id: int = Field(..., description="Unique identifier for the crossing")
    status: Optional[CrossingStatus] = Field(default=None, description="Crossing status")

    # Dates
    date_of_record: Optional[str] = Field(default=None, description="Date recorded")
    date_of_set_up: Optional[str] = Field(default=None, description="Date set up")
    date_of_raise: Optional[str] = Field(default=None, description="Date raised")
    completed: Optional[bool] = Field(default=None, description="Completed flag from backend/v1")

    # Responsible person
    responsible_id: Optional[int] = Field(default=None, description="Responsible person ID")
    responsible_fullname: Optional[str] = Field(default=None, description="Responsible person name")

    # Strain info
    strain_id: Optional[int] = Field(default=None, description="Strain ID")
    strain_name: Optional[str] = Field(default=None, description="Strain name")
    strain_name_with_id: Optional[str] = Field(default=None, description="Strain name with ID")

    # Description
    description: Optional[str] = Field(default=None, description="Crossing description/notes")

    # Performance-related fields from backend/v1 crossing detail
    crossing_tanks: Optional[int] = Field(default=None, description="Authoritative denominator from backend/v1")
    raised_tanks: Optional[int] = Field(default=None, description="Preferred raised tank count from backend/v1")
    really_raised_tanks: Optional[int] = Field(default=None, description="Fallback raised tank count from backend/v1")

    # Related tanks
    parent_tanks: List[CrossingTank] = Field(default_factory=list, description="Parent tanks")
    child_tanks: List[CrossingTank] = Field(default_factory=list, description="Child/raised tanks")

    @computed_field
    @property
    def raised_count(self) -> int:
        """Best available number of tanks raised from this crossing."""
        if self.raised_tanks is not None:
            return self.raised_tanks
        if self.really_raised_tanks is not None:
            return self.really_raised_tanks
        return len(self.child_tanks)

    @computed_field
    @property
    def performance_target_count(self) -> Optional[int]:
        """Best available denominator for crossing performance."""
        if self.crossing_tanks is not None and self.crossing_tanks > 0:
            return self.crossing_tanks
        return self.requested_groups

    @computed_field
    @property
    def requested_groups(self) -> Optional[int]:
        """
        Parse the number of requested groups from the description.

        Looks for patterns like:
        - "3 groups"
        - "One group"
        - "2 additional groups"
        """
        if not self.description:
            return None

        desc_lower = self.description.lower()

        # Map spelled-out numbers
        word_to_num = {
            'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5,
            'six': 6, 'seven': 7, 'eight': 8, 'nine': 9, 'ten': 10
        }

        # Pattern 1: digit + optional words + group(s)
        match = re.search(r'(\d+)\s+(?:\w+\s+)*groups?\b', desc_lower)
        if match:
            return int(match.group(1))

        # Pattern 2: spelled-out number + optional words + group(s)
        for word, num in word_to_num.items():
            if re.search(rf'\b{word}\b\s+(?:\w+\s+)*groups?\b', desc_lower):
                return num

        return None

    @computed_field
    @property
    def estimated_crossing_tanks(self) -> Optional[int]:
        """
        Estimate the number of crossing tanks from parent fish count.

        Formula: (total parent fish) / 2
        Note: This may not match actual if manually changed in PyRAT.
        """
        if not self.parent_tanks:
            return None

        total_parent_fish = sum(t.total_fish for t in self.parent_tanks)
        if total_parent_fish == 0:
            return None

        return total_parent_fish // 2

    @computed_field
    @property
    def performance(self) -> Optional[float]:
        """
        Calculate performance as raised_count / performance_target_count.

        Returns None if no denominator can be determined.
        """
        denominator = self.performance_target_count
        if denominator is None or denominator == 0:
            return None
        return self.raised_count / denominator

    @computed_field
    @property
    def performance_display(self) -> str:
        """Formatted performance string for display."""
        perf = self.performance
        if perf is None:
            return "N/A"
        return f"{perf:.0%}"

    @computed_field
    @property
    def performance_ratio_display(self) -> str:
        """Formatted raised/target ratio for display."""
        denominator = self.performance_target_count
        if denominator is None or denominator == 0:
            return "N/A"
        return f"{self.raised_count} / {denominator}"

    @computed_field
    @property
    def date_display(self) -> str:
        """Primary date for display (most recent relevant date)."""
        # Prefer date_of_raise, then date_of_set_up, then date_of_record
        date_str = self.date_of_raise or self.date_of_set_up or self.date_of_record
        if not date_str:
            return "N/A"
        # Parse and format nicely
        try:
            if 'T' in date_str:
                dt = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
            else:
                dt = datetime.strptime(date_str, '%Y-%m-%d')
            return dt.strftime('%Y-%m-%d')
        except (ValueError, TypeError):
            return date_str[:10] if len(date_str) >= 10 else date_str

    @classmethod
    def from_api_dict(cls, data: dict) -> "PyRATCrossing":
        """
        Create a PyRATCrossing instance from a raw API dictionary.
        """
        # Parse tanks structure
        tanks_data = data.get('tanks', {}) or {}

        parent_tanks = []
        for tank_dict in tanks_data.get('parents', []) or []:
            parent_tanks.append(CrossingTank(
                tank_id=tank_dict.get('tank_id', 0),
                tank_label=tank_dict.get('tank_label'),
                status=tank_dict.get('status'),
                strain_name=tank_dict.get('strain_name'),
                number_of_male=tank_dict.get('number_of_male', 0) or 0,
                number_of_female=tank_dict.get('number_of_female', 0) or 0,
                number_of_unknown=tank_dict.get('number_of_unknown', 0) or 0,
                alive_count=tank_dict.get('alive_count'),
                date_of_birth=tank_dict.get('date_of_birth'),
                location_rack_name=tank_dict.get('location_rack_name'),
                location_room_name=tank_dict.get('location_room_name'),
                tank_position=tank_dict.get('tank_position'),
            ))

        child_tanks = []
        for tank_dict in tanks_data.get('children', []) or []:
            child_tanks.append(CrossingTank(
                tank_id=tank_dict.get('tank_id', 0),
                tank_label=tank_dict.get('tank_label'),
                status=tank_dict.get('status'),
                strain_name=tank_dict.get('strain_name'),
                number_of_male=tank_dict.get('number_of_male', 0) or 0,
                number_of_female=tank_dict.get('number_of_female', 0) or 0,
                number_of_unknown=tank_dict.get('number_of_unknown', 0) or 0,
                alive_count=tank_dict.get('alive_count'),
                date_of_birth=tank_dict.get('date_of_birth'),
                location_rack_name=tank_dict.get('location_rack_name'),
                location_room_name=tank_dict.get('location_room_name'),
                tank_position=tank_dict.get('tank_position'),
            ))

        return cls(
            crossing_id=data.get('crossing_id', 0),
            status=data.get('status'),
            date_of_record=data.get('date_of_record'),
            date_of_set_up=data.get('date_of_set_up'),
            date_of_raise=data.get('date_of_raise'),
            completed=data.get('completed'),
            responsible_id=data.get('responsible_id'),
            responsible_fullname=data.get('responsible_fullname'),
            strain_id=data.get('strain_id'),
            strain_name=data.get('strain_name'),
            strain_name_with_id=data.get('strain_name_with_id'),
            description=data.get('description'),
            crossing_tanks=data.get('crossing_tanks'),
            raised_tanks=data.get('raised_tanks'),
            really_raised_tanks=data.get('really_raised_tanks'),
            parent_tanks=parent_tanks,
            child_tanks=child_tanks,
        )

    class Config:
        from_attributes = True
