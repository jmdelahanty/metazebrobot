# src/metazebrobot/models/fish_dish.py

import logging
from datetime import datetime
from typing import Optional, Dict, Any, List, Literal
from pydantic import BaseModel, Field, field_validator

# Define allowed population types
DishPopulationType = Literal["primary", "negative_screened", "positive_screened", "other"] # Added more options

class LightCycle(BaseModel):
    """Light cycle information for a fish dish."""
    light_duration: str  # Format: "HH:MM"
    dawn_dusk: str  # Format: "HH:MM"


class Enclosure(BaseModel):
    """Enclosure information for a fish dish."""
    temperature: float = Field(ge=18, le=30)  # Temperature in Celsius
    light_cycle: LightCycle
    room: str = "2E.282"  # Default room
    in_beaker: bool = False # Whether the fish are in a beaker
    vol_water_total: Optional[int] = None  # Total volume of water in the enclosure


class Breeding(BaseModel):
    """Breeding information for a fish dish."""
    parents: List[str] = []


class QualityCheckData(BaseModel):
    """Data for a quality check."""
    check_time: str  # Format: "YYYYMMDDTHH:MM:SS" (ISO 8601)
    fed: bool = False
    feed_type: Optional[str] = None
    water_changed: bool = False
    vol_water_changed: Optional[int] = None
    num_dead: int = 0
    notes: Optional[str] = None

    @field_validator('check_time')
    @classmethod
    def validate_check_time_format(cls, v: str) -> str:
        """Validate check_time format follows ISO 8601 (YYYYMMDDTHH:MM:SS)."""
        if v:
            try:
                # Check for the 'T' separator
                if 'T' not in v:
                    raise ValueError("Missing 'T' separator between date and time")

                # Split into date and time parts
                date_part, time_part = v.split('T')

                # Validate date part (YYYYMMDD)
                datetime.strptime(date_part, "%Y%m%d")

                # Validate time part (HH:MM:SS)
                datetime.strptime(time_part, "%H:%M:%S")

                return v
            except ValueError as e:
                raise ValueError(f"Invalid datetime format: {v}. Expected format:YYYYMMDDTHH:MM:SS. {str(e)}")
        return v

class ScreeningStep(BaseModel):
    """Data for a single screening step performed on a dish."""
    screening_datetime: str # Format: YYYYMMDDTHH:MM:SS
    dpf_screened: int
    indicator_screened: str # e.g., "GFP", "RGECO1b", "Pigment", "Both/Final"
    criteria: str
    # --- FIELD ADDED ---
    count_screened_this_step: int = Field(..., ge=0, description="Total number of fish actually screened in this specific step")
    # --- FIELD KEPT ---
    number_positive: int = Field(..., ge=0, description="Number of fish positive for the indicator(s) in this step")
    # ---------------------
    tricaine_used: bool = False
    notes: Optional[str] = None

    @field_validator('screening_datetime', mode='before')
    @classmethod
    def validate_screening_datetime_format(cls, v: str) -> str:
        """Validate screening_datetime format (YYYYMMDDTHH:MM:SS)."""
        if v:
            try:
                if 'T' not in v:
                    raise ValueError("Missing 'T' separator between date and time")
                date_part, time_part = v.split('T')
                datetime.strptime(date_part, "%Y%m%d")
                datetime.strptime(time_part, "%H:%M:%S")
                return v
            except ValueError as e:
                raise ValueError(f"Invalid datetime format for screening_datetime: {v}. Expected format: YYYYMMDDTHH:MM:SS. Error: {str(e)}")
        # This field is mandatory, so raise error if empty or None
        raise ValueError("screening_datetime is required")


class ScreeningResults(BaseModel):
    """Holds the results of the multi-step screening process for a dish."""
    screenings: List[ScreeningStep] = [] # List to store each screening step
    final_positive_count: Optional[int] = Field(default=None, ge=0) # Final count after all screening
    date_finalized: Optional[str] = None # Format: YYYYMMDD

    @field_validator('date_finalized', mode='before')
    @classmethod
    def validate_finalized_date_format(cls, v: Optional[str]) -> Optional[str]:
        """Validate date format (YYYYMMDD) if provided."""
        if v:
            try:
                datetime.strptime(v, "%Y%m%d")
                return v
            except ValueError:
                raise ValueError(f"Invalid date format for date_finalized: {v}. Expected format: YYYYMMDD")
        return v # Allow None


class FishDish(BaseModel):
    """Model for a fish dish."""
    dish_id: str
    date_created: str  # Format: YYYYMMDD
    cross_id: str
    source_group_id: Optional[str] = Field(
        default=None,
        description="Identifier for the specific source group/tank provided by aquatics (e.g., '15178-G1')"
    )
    dish_number: Optional[int] = None # Now clearly the sub-dish number
    dof: str  # Date of fertilization (YYYYMMDD)
    genotype: str
    sex: Literal["unknown", "M", "F"] = "unknown"
    species: str = "Danio rerio"
    responsible: str # Person managing dish day-to-day
    # --- DESCRIPTION CLARIFIED ---
    fish_count: int = Field(..., ge=0, description="Initial fish count when dish record created (can be an estimate)")
    # --- FIELDS ADDED ---
    parent_dish_id: Optional[str] = Field(default=None, description="ID of the dish this one was split from, if any")
    dish_population_type: DishPopulationType = Field(default="primary", description="Type indicating lineage (e.g., primary, negative_screened)")
    # -------------------
    breeding: Breeding
    enclosure: Enclosure
    quality_checks: Dict[str, Any] = {}
    screening_results: Optional[ScreeningResults] = None
    notes: Optional[str] = None
    status: Literal["active", "inactive"] = "active"
    termination_date: Optional[str] = None
    termination_reason: Optional[str] = None

    @field_validator('date_created', 'dof', 'termination_date', mode='before')
    @classmethod
    def validate_yyyymmdd_format(cls, v: Optional[str]) -> Optional[str]:
        """Validate date format (YYYYMMDD) for multiple fields."""
        if v: # Only validate if not None
            try:
                datetime.strptime(v, "%Y%m%d")
                return v
            except ValueError:
                raise ValueError(f"Invalid date format: {v}. Expected format: YYYYMMDD")
        return v # Allow None for optional fields like termination_date


    # NOTE: create_new might need updating if derived dishes are created via a different path
    @classmethod
    def create_new(
        cls,
        cross_id: str,
        dish_number: int, # Usually for primary dishes
        genotype: str,
        responsible: str,
        fish_count: int, # This is the initial estimate or calculated count for derived
        dof: str, # Required DOF
        dish_id: Optional[str] = None, # Allow overriding dish_id for derived dishes
        source_group_id: Optional[str] = None,
        sex: str = "unknown",
        species: str = "Danio rerio",
        parents: Optional[List[str]] = None,
        temperature: float = 28.5,
        light_duration: str = "14:10",
        dawn_dusk: str = "8:00",
        room: str = "2E.282",
        in_beaker: bool = False,
        vol_water_total: Optional[int] = None,
        notes: Optional[str] = None,
        parent_dish_id: Optional[str] = None,
        dish_population_type: DishPopulationType = "primary"
    ) -> 'FishDish':
        """
        Create a new fish dish with default values. Handles primary and derived dishes.
        """
        try:
            datetime.strptime(dof, "%Y%m%d")
        except ValueError:
             raise ValueError(f"Invalid DOF format: {dof}. Expected YYYYMMDD")

        if parents is None:
            parents = []

        today = datetime.now().strftime("%Y%m%d")

        # Generate dish_id if not provided (typically for primary)
        if dish_id is None:
            if dish_number is None or dish_number <= 0:
                 raise ValueError("dish_number is required for generating primary dish_id")
            dish_id = f"{cross_id}_{dish_number}"
        # Else, use the provided dish_id (for derived dishes)

        return cls(
            dish_id=dish_id,
            date_created=today,
            cross_id=cross_id,
            source_group_id=source_group_id,
            dish_number=dish_number if dish_population_type == "primary" else None, # Only store for primary?
            dof=dof,
            genotype=genotype,
            sex=sex,
            species=species,
            responsible=responsible,
            fish_count=fish_count, # Use provided count
            parent_dish_id=parent_dish_id, # Added
            dish_population_type=dish_population_type, # Added
            breeding=Breeding(parents=parents),
            enclosure=Enclosure(
                temperature=temperature,
                light_cycle=LightCycle(
                    light_duration=light_duration,
                    dawn_dusk=dawn_dusk
                ),
                room=room,
                in_beaker=in_beaker,
                vol_water_total=vol_water_total
            ),
            quality_checks={},
            screening_results=None, # Derived dishes start with no screening history
            notes=notes,
            status="active"
        )

    def add_quality_check(self, check_data: QualityCheckData) -> None:
        """
        Add a quality check to the dish.
        Uses the validated QualityCheckData object.
        """
        check_time = check_data.check_time
        # Store the validated data as a dictionary
        self.quality_checks[check_time] = check_data.model_dump(exclude_none=True, mode='json')

    def add_screening_step(self, step_data: ScreeningStep) -> None:
        """
        Add a screening step to the dish's screening results.
        Uses the validated ScreeningStep object.
        """
        if self.screening_results is None:
            self.screening_results = ScreeningResults(screenings=[])
        # Append the validated ScreeningStep object directly
        self.screening_results.screenings.append(step_data)
        # Sort screenings by datetime
        try:
           # Sort using the screening_datetime attribute of the ScreeningStep objects
           self.screening_results.screenings.sort(key=lambda x: datetime.strptime(x.screening_datetime, "%Y%m%dT%H:%M:%S"))
        except (ValueError, TypeError): # Added TypeError
           logging.warning(f"Could not sort screening steps by datetime for dish {self.dish_id}.")


    def finalize_screening(self, final_count: int, date_finalized: str) -> None:
        """Set the final positive count and date finalized for screening."""
        if self.screening_results is None:
            self.screening_results = ScreeningResults(screenings=[])
        try:
            # Validate date format before assigning
            datetime.strptime(date_finalized, "%Y%m%d")
            self.screening_results.date_finalized = date_finalized
        except ValueError:
             # Raise error to be caught by the controller/caller
             raise ValueError(f"Invalid date format '{date_finalized}' for date_finalized. Expected YYYYMMDD.")

        if final_count >= 0:
            self.screening_results.final_positive_count = final_count
        else:
             # Raise error to be caught by the controller/caller
             raise ValueError(f"Invalid final_count '{final_count}'. Must be non-negative.")

    def terminate(self, reason: str) -> None:
        """
        Terminate the dish. Sets status to inactive and records termination date/reason.
        """
        self.status = "inactive"
        self.termination_date = datetime.now().strftime("%Y%m%d")
        self.termination_reason = reason