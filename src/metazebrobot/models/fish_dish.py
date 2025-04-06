import logging
from datetime import datetime
from typing import Optional, Dict, Any, List, Literal
from pydantic import BaseModel, Field, field_validator


class LightCycle(BaseModel):
    """Light cycle information for a fish dish."""
    light_duration: str  # Format: "HH:MM"
    dawn_dusk: str  # Format: "HH:MM"


class Enclosure(BaseModel):
    """Enclosure information for a fish dish."""
    temperature: float = Field(ge=18, le=30)  # Temperature in Celsius
    light_cycle: LightCycle
    room: str = "2E.282"  # Default room
    in_beaker: bool = False, # Whether the fish are in a beaker
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
                raise ValueError(f"Invalid datetime format: {v}. Expected format:<x_bin_880>MMDDTHH:MM:SS. {str(e)}")
        return v

class ScreeningStep(BaseModel):
    """Data for a single screening step performed on a dish."""
    screening_datetime: str # Format: YYYYMMDDTHH:MM:SS
    dpf_screened: int
    indicator_screened: str # e.g., "GFP", "RGECO1b", "Pigment", "Both/Final"
    criteria: str
    fish_removed: int = Field(ge=0)
    fish_remaining_after: int = Field(ge=0)
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
    dish_number: int = None
    dof: str  # Date of fertilization (YYYYMMDD)
    genotype: str
    sex: Literal["unknown", "M", "F"] = "unknown"
    species: str = "Danio rerio"
    responsible: str # Person managing dish day-to-day
    fish_count: int = Field(ge=0) # Initial fish count
    breeding: Breeding
    enclosure: Enclosure
    quality_checks: Dict[str, Any] = {}
    screening_results: Optional[ScreeningResults] = None # To store screening steps/results
    notes: Optional[str] = None # General notes for the dish itself
    status: Literal["active", "inactive"] = "active"
    termination_date: Optional[str] = None # Format: YYYYMMDD
    termination_reason: Optional[str] = None

    @field_validator('date_created', 'dof', 'termination_date', mode='before')
    @classmethod
    def validate_date_format(cls, v: Optional[str], info) -> Optional[str]:
        """Validate date format (YYYYMMDD) if provided."""
        field_name = info.field_name if hasattr(info, 'field_name') else 'date field'
        if v:
            try:
                datetime.strptime(v, "%Y%m%d")
                return v
            except ValueError:
                raise ValueError(f"Invalid date format for {field_name}: {v}. Expected format: YYYYMMDD")
        return v

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'FishDish':
        """Create a FishDish instance from a dictionary."""
        if 'screening_results' in data and isinstance(data['screening_results'], dict):
             try:
                 if 'screenings' in data['screening_results'] and isinstance(data['screening_results']['screenings'], list):
                     for step in data['screening_results']['screenings']:
                         if isinstance(step, dict) and 'screening_date' in step and 'screening_datetime' not in step:
                             # If old format found, convert date to datetime with default time
                             step['screening_datetime'] = f"{step['screening_date']}T00:00:00"
                             del step['screening_date'] # Remove old field
                 data['screening_results'] = ScreeningResults(**data['screening_results'])
             except Exception as e:
                 logging.error(f"Error parsing nested screening_results: {e}")
                 data['screening_results'] = None
        return cls(**data)


    def to_dict(self) -> Dict[str, Any]:
        """Convert the model to a dictionary."""
        return self.model_dump(exclude_none=True, mode='json')

    @classmethod
    def create_new(
        cls,
        cross_id: str,
        dish_number: int,
        genotype: str,
        responsible: str,
        dof: Optional[str] = None,
        sex: str = "unknown",
        species: str = "Danio rerio",
        fish_count: int = 1, # Represents initial count
        parents: List[str] = None,
        temperature: float = 28.5,
        light_duration: str = "14:10",
        dawn_dusk: str = "8:00",
        room: str = "2E.282",
        in_beaker: bool = False,
        vol_water_total: Optional[int] = None,
        notes: Optional[str] = None
    ) -> 'FishDish':
        """
        Create a new fish dish with default values.
        """
        if dof is None:
            dof = datetime.now().strftime("%Y%m%d")

        if parents is None:
            parents = []

        today = datetime.now().strftime("%Y%m%d")
        dish_id = f"{cross_id}_{dish_number}"

        return cls(
            dish_id=dish_id,
            date_created=today,
            cross_id=cross_id,
            dish_number=dish_number,
            dof=dof,
            genotype=genotype,
            sex=sex,
            species=species,
            responsible=responsible,
            fish_count=fish_count, # Initial count
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
            screening_results=None, # Initialize as None
            notes=notes, # Initialize general notes
            status="active"
        )

    def add_quality_check(self, check_data: QualityCheckData) -> None:
        """
        Add a quality check to the dish.
        """
        check_time = check_data.check_time
        self.quality_checks[check_time] = check_data.model_dump(exclude_none=True, mode='json')

    def add_screening_step(self, step_data: ScreeningStep) -> None:
        """Add a screening step to the dish's screening results."""
        if self.screening_results is None:
            self.screening_results = ScreeningResults(screenings=[])
        self.screening_results.screenings.append(step_data)
        # Sort screenings by datetime
        try:
           self.screening_results.screenings.sort(key=lambda x: datetime.strptime(x.screening_datetime, "%Y%m%dT%H:%M:%S"))
        except ValueError:
           logging.warning("Could not sort screening steps by datetime.")


    def finalize_screening(self, final_count: int, date_finalized: str) -> None:
        """Set the final positive count and date finalized for screening."""
        if self.screening_results is None:
            self.screening_results = ScreeningResults(screenings=[])
        try:
            datetime.strptime(date_finalized, "%Y%m%d")
            self.screening_results.date_finalized = date_finalized
        except ValueError:
             print(f"Error: Invalid date format '{date_finalized}' for date_finalized. Not setting.")

        if final_count >= 0:
            self.screening_results.final_positive_count = final_count
        else:
             print(f"Error: Invalid final_count '{final_count}'. Must be non-negative.")

    def terminate(self, reason: str) -> None:
        """
        Terminate the dish.
        """
        self.status = "inactive"
        self.termination_date = datetime.now().strftime("%Y%m%d")
        self.termination_reason = reason

