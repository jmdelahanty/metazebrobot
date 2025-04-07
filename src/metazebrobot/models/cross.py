"""
Pydantic models for representing zebrafish crosses.

This module defines the data structures for crosses, including parent information
and details specific to transgenic crosses.
"""

from datetime import datetime
from typing import Optional, List, Literal, Dict, Any, Tuple
# Use computed_field from Pydantic v2 if available
from pydantic import BaseModel, Field, field_validator, computed_field

# Define allowed cross types using Literal for validation
CrossType = Literal["Standard", "Transgenic"]

class Parent(BaseModel):
    """Represents a parent fish used in a cross."""
    identifier: str = Field(..., description="Unique identifier for the parent, e.g., tank number and location 'M11:E5 (5187)'")
    sex: Optional[Literal["M", "F", "unknown"]] = Field(default="unknown", description="Sex of the parent, if known")
    genotype: Optional[str] = Field(default=None, description="Genotype of the parent, if known beyond the identifier")

class TransgenicIndicator(BaseModel):
    """Describes a specific genetic component, typically a transgene."""
    modification_type: Optional[Literal["tg", "mu", "other"]] = Field(default="tg", description="Type of genetic modification (transgene, mutant, etc.)")
    promoter_driver: Optional[str] = Field(default=None, description="Promoter/driver element (e.g., 'gfap', 'elavl3')")
    reporter_effector: str = Field(..., description="The gene/cassette expressed (e.g., 'TRPV1-T2A-GFP', 'jRGECO1b', 'mCherry')")
    color: Optional[str] = Field(default=None, description="Associated color of the fluorescent indicator (e.g., 'Green', 'Red', 'Cyan')")
    expected_expression: Optional[str] = Field(default=None, description="Expected expression pattern summary (e.g., 'pan-glial', 'pan-neuronal')")

    # Use Pydantic V2's computed_field to generate a standard notation
    @computed_field # type: ignore[misc]
    @property
    def standard_notation(self) -> str:
        """Constructs a standard notation string from components."""
        parts = []
        if self.promoter_driver:
            parts.append(f"{self.promoter_driver}:")
        parts.append(self.reporter_effector)
        base = "".join(parts)

        # Add prefix/suffix based on type, e.g., tg(...)
        if self.modification_type == "tg":
            return f"Tg({base})"
        elif self.modification_type == "mu":
             return f"mut({base})" # Adjust notation as needed
        else:
            return base

    class Config:
        # Required for Pydantic V2 when using @computed_field with @property
        from_attributes = True


class AggregateResults(BaseModel):
    """Optional aggregated results after screening all dishes from a cross."""
    # --- FIELD ADDED ---
    total_initially_produced: Optional[int] = Field(
        default=None,
        description="Sum of count_screened_this_step from the first screening step of all primary dishes for this cross (calculated later)"
    )
    # --- FIELD MODIFIED (Kept original, but note the difference from above) ---
    total_initial_fish: Optional[int] = Field(default=None, description="Sum of initial_fish_count from all dishes of this cross (initial estimate)") # Kept existing field for now
    # ---------------------
    total_positive_final: Optional[int] = Field(default=None, description="Sum of final_positive_count from all screened dishes of this cross")
    yield_percentage: Optional[float] = Field(default=None, description="Calculated percentage of final positive fish from initial total (calculated later)") # Definition might need update based on which 'initial total' is used
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
                # Ensure the full error message is present
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
    line_strain: str = Field(..., description="Overall description of the cross, potentially including multiple components e.g., 'Tg(gfap:TRPV1-T2A-GFP); Tg(elavl3:jRGECO1b)'")
    parents: Tuple[Parent, Parent] = Field(..., description="Tuple containing exactly two parents used in the cross")
    requested_groups: int = Field(..., ge=0, description="Number of dishes/groups requested for this cross")
    groups_produced: Optional[int] = Field(
        default=None,
        ge=0,
        description="Actual number of groups/dishes that produced offspring from this cross"
    )
    cross_type: CrossType = Field(..., description="Type of cross (Standard or Transgenic)")
    notes: Optional[str] = Field(default=None, description="General notes about the cross request or setup")
    transgenic_details: Optional[TransgenicDetails] = Field(default=None, description="Structured details for transgenic crosses, null otherwise")
    cross_status: Optional[Literal["Requested", "Performed", "Screening", "Completed", "Archived"]] = Field(default="Requested", description="Overall status of the cross")
    # --- FIELD ADDED to link AggregateResults directly if not transgenic ---
    aggregate_results: Optional[AggregateResults] = Field(default=None, description="Aggregated screening results across all dishes (filled in later, used if not transgenic)") # Consider if this duplicates transgenic_details.aggregate_results

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
        # This field is mandatory, so raise error if empty or None (though caught by Pydantic earlier)
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
        if len(v) != 2: # Explicit length check for robustness
             raise ValueError("Exactly two parents are required.")
        if v[0].identifier == v[1].identifier:
            raise ValueError("Parents must have different identifiers.")
        return v

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Cross':
        """Create a Cross instance from a dictionary."""
        # Handle potential nesting of aggregate_results
        if "transgenic_details" in data and data["transgenic_details"] and "aggregate_results" in data["transgenic_details"]:
             if "aggregate_results" not in data: # Move it to top level if needed, or decide on single source of truth
                  # data["aggregate_results"] = data["transgenic_details"]["aggregate_results"]
                  # Decide if aggregate_results should *only* be under transgenic_details for transgenic crosses
                  pass
        return cls(**data)

    def model_dump(self, *args, **kwargs) -> Dict[str, Any]:
        # Ensure aggregate_results are handled consistently on dump
        # (May need custom logic depending on where aggregate_results lives)
        dumped = super().model_dump(*args, **kwargs)
        # Example: Ensure aggregate_results is present if transgenic_details has it
        # if dumped.get("transgenic_details") and dumped["transgenic_details"].get("aggregate_results"):
        #     if "aggregate_results" not in dumped:
        #         dumped["aggregate_results"] = dumped["transgenic_details"]["aggregate_results"]
        return dumped