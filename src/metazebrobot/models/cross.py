"""
Pydantic models for representing zebrafish crosses.

This module defines the data structures for crosses, including parent information
and details specific to transgenic crosses.
"""

from datetime import datetime
# Removed unused 'validator' import
from typing import Optional, List, Literal, Dict, Any, Tuple
from pydantic import BaseModel, Field, field_validator

# Define allowed cross types using Literal for validation
CrossType = Literal["Standard", "Transgenic"]

class Parent(BaseModel):
    """Represents a parent fish used in a cross."""
    identifier: str = Field(..., description="Unique identifier for the parent, e.g., tank number and location 'M11:E5 (5187)'")
    sex: Optional[Literal["M", "F", "unknown"]] = Field(default="unknown", description="Sex of the parent, if known")
    genotype: Optional[str] = Field(default=None, description="Genotype of the parent, if known beyond the identifier")

class TransgenicIndicator(BaseModel):
    """Describes an expected transgenic indicator for a cross."""
    name: str = Field(..., description="Name of the transgene or indicator, e.g., 'gfap:TRPV1-T2A-GFP'")
    expected_expression: str = Field(..., description="Expected expression pattern, e.g., 'pan-glial', 'pan-neuronal', 'specific_structure:habenula'")

class AggregateResults(BaseModel):
    """Optional aggregated results after screening all dishes from a cross."""
    total_positive_final: Optional[int] = Field(default=None, description="Sum of final_positive_count from all screened dishes of this cross")
    total_initially_produced: Optional[int] = Field(default=None, description="Sum of initial_fish_count from all dishes of this cross")
    yield_percentage: Optional[float] = Field(default=None, description="Calculated percentage of final positive fish from initial total")
    date_aggregated: Optional[str] = Field(default=None, description="Date when these aggregate results were calculated (YYYYMMDD)")

    @field_validator('date_aggregated', mode='before')
    @classmethod
    def validate_date_format(cls, v: Optional[str]) -> Optional[str]:
        """Validate date format (YYYYMMDD) if provided."""
        if v:
            try:
                datetime.strptime(v, "%Y%m%d")
                return v
            except ValueError:
                # Completed the error message
                raise ValueError(f"Invalid date format: {v}. Expected format: YYYYMMDD")
        return v # Allow None

class TransgenicDetails(BaseModel):
    """Holds details specific to transgenic crosses."""
    indicators: List[TransgenicIndicator] = Field(..., description="List of expected transgenic indicators")
    aggregate_results: Optional[AggregateResults] = Field(default=None, description="Aggregated screening results across all dishes (filled in later)")

class Cross(BaseModel):
    """Model representing a single zebrafish cross."""
    cross_id: str = Field(..., description="Unique identifier for the cross, e.g., '15238'")
    request_date: str = Field(..., description="Date the cross was requested/set up (YYYYMMDD)")
    responsible_requestor: str = Field(..., description="Person who requested or is responsible for the cross")
    line_strain: str = Field(..., description="Description of the line(s) being crossed, e.g., 'Tgigfap:TRPVL-T2A-GFP; Tgrelev13(RGECO1b)'")
    parents: Tuple[Parent, Parent] = Field(..., description="Tuple containing exactly two parents used in the cross")
    requested_groups: int = Field(..., ge=0, description="Number of dishes/groups requested for this cross")
    cross_type: CrossType = Field(..., description="Type of cross (Standard or Transgenic)")
    notes: Optional[str] = Field(default=None, description="General notes about the cross request or setup")
    transgenic_details: Optional[TransgenicDetails] = Field(default=None, description="Details specific to transgenic crosses, null otherwise")
    cross_status: Optional[Literal["Requested", "Performed", "Screening", "Completed", "Archived"]] = Field(default="Requested", description="Overall status of the cross")

    @field_validator('request_date', mode='before')
    @classmethod
    def validate_date_format(cls, v: str) -> str:
        """Validate date format (YYYYMMDD)."""
        if v:
            try:
                datetime.strptime(v, "%Y%m%d")
                return v
            except ValueError:
                raise ValueError(f"Invalid date format: {v}. Expected format: YYYYMMDD")
        raise ValueError("request_date is required")

    @field_validator('parents')
    @classmethod
    def check_parents_length(cls, v: Tuple[Parent, Parent]) -> Tuple[Parent, Parent]:
        """
        Validate the parents tuple.

        Note: In Pydantic V2, the type hint Tuple[Parent, Parent] primarily enforces
        that the input must be a tuple containing exactly two valid Parent objects.
        This validator runs after that initial check and can be used for more complex
        logic if needed in the future.
        """
        # Example of a potential future check (currently commented out):
        # if v[0].identifier == v[1].identifier:
        #     raise ValueError("Parents must have different identifiers.")
        return v

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Cross':
        """Create a Cross instance from a dictionary."""
        return cls(**data)

    def to_dict(self) -> Dict[str, Any]:
        """Convert the model to a dictionary, excluding None values by default."""
        # Use model_dump for Pydantic v2+
        return self.model_dump(exclude_none=True)

