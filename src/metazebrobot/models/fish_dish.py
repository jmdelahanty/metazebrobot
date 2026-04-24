# src/metazebrobot/models/fish_dish.py

import logging
from datetime import datetime
from typing import Optional, Dict, Any, List, Literal, Tuple
from pydantic import BaseModel, Field, field_validator, model_validator

TERMINATION_REASON_EUTHANASIA = "euthanasia"
TERMINATION_REASON_PROPAGATION = "propagation"
TERMINATION_REASON_CATEGORIES: Tuple[str, ...] = (
    TERMINATION_REASON_EUTHANASIA,
    TERMINATION_REASON_PROPAGATION,
)
TERMINATION_REASON_LABELS = {
    TERMINATION_REASON_EUTHANASIA: "Euthanasia",
    TERMINATION_REASON_PROPAGATION: "Propagation",
}
TERMINATION_REASON_OPTIONS = tuple(
    {"value": reason, "label": TERMINATION_REASON_LABELS[reason]}
    for reason in TERMINATION_REASON_CATEGORIES
)

_TERMINATION_REASON_ALIASES = {
    reason.casefold(): reason
    for reason in TERMINATION_REASON_CATEGORIES
}
_TERMINATION_REASON_ALIASES.update({
    label.casefold(): reason
    for reason, label in TERMINATION_REASON_LABELS.items()
})
_TERMINATION_REASON_ALIASES.update({
    "aquatics propagation handoff": TERMINATION_REASON_PROPAGATION,
    "aquatics_propagation_handoff": TERMINATION_REASON_PROPAGATION,
    "handoff_to_aquatics_for_propagation": TERMINATION_REASON_PROPAGATION,
    "handed_off_to_aquatics_for_propagation": TERMINATION_REASON_PROPAGATION,
    "handed off to aquatics for propagation": TERMINATION_REASON_PROPAGATION,
})


def normalize_termination_reason(reason: Optional[str]) -> Optional[str]:
    """Return the canonical stored termination reason, if it is recognized."""
    normalized = (reason or "").strip()
    if not normalized:
        return None
    return _TERMINATION_REASON_ALIASES.get(normalized.casefold())


def termination_reason_label(reason: Optional[str]) -> str:
    """Return the display label for a stored or legacy termination reason."""
    canonical_reason = normalize_termination_reason(reason)
    if canonical_reason:
        return TERMINATION_REASON_LABELS[canonical_reason]
    return reason or ""


def termination_reason_options_text() -> str:
    """Human-readable list of allowed termination reasons."""
    return ", ".join(TERMINATION_REASON_CATEGORIES)


# Define allowed population types
DishPopulationType = Literal[
    "primary",
    "negative_screened",
    "positive_screened",
    "pigmented_screened",
    "other",
]

ScreeningAllocationBucket = Literal[
    "remaining_in_parent",
    "positive_screened",
    "negative_screened",
    "pigmented_screened",
    "other",
]

ScreeningAllocationDisposition = Literal[
    "remain_parent",
    "derived_dish",
    "discarded",
]

class LightCycle(BaseModel):
    """Light cycle information for a fish dish."""
    light_duration: Optional[str] = None  # Format: "HH:MM"
    dawn_dusk: Optional[str] = None  # Format: "HH:MM"


class Enclosure(BaseModel):
    """Enclosure information for a fish dish."""
    temperature: Optional[float] = Field(default=None, ge=18, le=30)  # Temperature in Celsius
    light_cycle: Optional[LightCycle] = None
    room: Optional[str] = "2E.282"  # Default room
    container_type: Optional[Literal[
        "petri_dish", "beaker", "well_plate", "tank"
    ]] = "petri_dish"
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


class ScreeningStepAllocation(BaseModel):
    """Outcome allocation recorded for a single screening step."""
    bucket: ScreeningAllocationBucket
    disposition: ScreeningAllocationDisposition
    count: int = Field(..., ge=1)
    destination_dish_id: Optional[str] = Field(
        default=None,
        description="Dish receiving allocated fish; replaces derived_dish_id for new allocation semantics",
    )
    derived_dish_id: Optional[str] = None
    notes: Optional[str] = None

    @model_validator(mode='after')
    def validate_destination_dish_link(self):
        """Only derived-dish allocations should carry a destination dish reference."""
        if self.derived_dish_id and not self.destination_dish_id:
            self.destination_dish_id = self.derived_dish_id
        if self.destination_dish_id and not self.derived_dish_id:
            self.derived_dish_id = self.destination_dish_id

        if self.disposition == "derived_dish" and not self.destination_dish_id:
            raise ValueError("destination_dish_id is required when disposition is derived_dish")
        if self.disposition != "derived_dish" and self.destination_dish_id:
            raise ValueError("destination_dish_id is only valid for derived_dish allocations")
        return self

class ScreeningStep(BaseModel):
    """Data for a single screening step performed on a dish.

    Supports multiple screening scenarios:
    - Pigment-only removal (indicators_screened=[], pigment_screened=True)
    - Single indicator screen (indicators_screened=["GFP"])
    - Multi-indicator + pigment (indicators_screened=["GFP","jRGECO"], pigment_screened=True)
    """
    screening_datetime: str  # Format: YYYYMMDDTHH:MM:SS
    dpf_screened: int = Field(..., ge=0)
    indicators_screened: List[str] = Field(default_factory=list, description="Indicators assessed (e.g. ['GFP','jRGECO']); empty for pigment-only")
    pigment_screened: bool = Field(default=False, description="Whether pigmentation was assessed this step")
    criteria: Optional[str] = Field(default=None, description="Free-text screening criteria (e.g. 'fluorescence', 'brightest')")
    count_screened_this_step: int = Field(..., ge=0, description="Total number of fish actually screened in this specific step")
    count_before_step: Optional[int] = Field(
        default=None,
        ge=0,
        description="Computed number of fish present in the dish immediately before this screening step",
    )
    count_after_step: Optional[int] = Field(
        default=None,
        ge=0,
        description="Computed number of fish remaining in the dish immediately after this screening step",
    )
    allocations: List[ScreeningStepAllocation] = Field(
        default_factory=list,
        description="Explicit per-step outcome allocations (e.g. derived dish, discarded, remain in parent)",
    )
    number_kept: Optional[int] = Field(default=None, ge=0, description="Legacy compatibility field; prefer allocations")
    number_removed_pigmented: Optional[int] = Field(default=None, ge=0, description="Legacy compatibility field; prefer allocations")
    number_removed_negative: Optional[int] = Field(default=None, ge=0, description="Legacy compatibility field; prefer allocations")
    number_removed_other: Optional[int] = Field(default=None, ge=0, description="Legacy compatibility field; prefer allocations")
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

    @model_validator(mode='after')
    def validate_allocations(self):
        """Prevent step allocations from exceeding the number screened in that step."""
        total_allocated = self.total_allocated_count
        if total_allocated > self.count_screened_this_step:
            raise ValueError(
                f"Total allocated fish ({total_allocated}) exceeds count_screened_this_step "
                f"({self.count_screened_this_step})"
            )
        return self

    @property
    def total_allocated_count(self) -> int:
        """Total fish assigned to explicit allocations."""
        return sum(allocation.count for allocation in self.allocations)

    @property
    def unallocated_count(self) -> int:
        """Fish screened in this step but not yet assigned to an explicit allocation."""
        return max(self.count_screened_this_step - self.total_allocated_count, 0)

    def allocations_for_bucket(self, bucket: ScreeningAllocationBucket) -> List[ScreeningStepAllocation]:
        """Return allocations matching a specific bucket."""
        return [allocation for allocation in self.allocations if allocation.bucket == bucket]

    @property
    def outgoing_count(self) -> int:
        """Fish that leave the parent dish during this step."""
        return sum(
            allocation.count
            for allocation in self.allocations
            if allocation.disposition in {"derived_dish", "discarded"}
        )


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
    cross_setup_date: Optional[str] = Field(default=None, description="PyRAT cross setup date (YYYYMMDD)")
    dof_source: Optional[str] = Field(default=None, description="How the DOF value was derived or set")
    dof: str  # Date of fertilization (YYYYMMDD)
    genotype: str
    sex: Literal["unknown", "M", "F"] = "unknown"
    species: str = "Danio rerio"
    responsible: str # Person managing dish day-to-day
    # --- DESCRIPTION CLARIFIED ---
    fish_count: int = Field(..., ge=0, description="Initial fish count when dish record created (can be an estimate)")
    current_fish_count: Optional[int] = Field(
        default=None,
        ge=0,
        description="Current fish count for this physical dish, derived from screening/care events",
    )
    # --- FIELDS ADDED ---
    parent_dish_id: Optional[str] = Field(default=None, description="ID of the dish this one was split from, if any")
    dish_population_type: Optional[DishPopulationType] = Field(default="primary", description="Type indicating lineage (e.g., primary, negative_screened)")
    source_screening_datetime: Optional[str] = Field(
        default=None,
        description="Screening step datetime (YYYYMMDDTHH:MM:SS) that produced this derived dish",
    )
    source_screening_bucket: Optional[str] = Field(
        default=None,
        description="Bucket from the source screening step (e.g. positive_screened, negative_screened, pigmented_screened, other)",
    )
    # -------------------
    breeding: Breeding
    enclosure: Enclosure
    quality_checks: Dict[str, Any] = {}
    screening_results: Optional[ScreeningResults] = None
    notes: Optional[str] = None
    status: Literal["active", "inactive"] = "active"
    termination_date: Optional[str] = None
    termination_reason: Optional[str] = None

    @field_validator('date_created', 'dof', 'cross_setup_date', 'termination_date', mode='before')
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

    @field_validator('source_screening_datetime', mode='before')
    @classmethod
    def validate_screening_datetime_format(cls, v: Optional[str]) -> Optional[str]:
        """Validate screening datetime format (YYYYMMDDTHH:MM:SS) if provided."""
        if v:
            try:
                if 'T' not in v:
                    raise ValueError("Missing 'T' separator between date and time")
                date_part, time_part = v.split('T')
                datetime.strptime(date_part, "%Y%m%d")
                datetime.strptime(time_part, "%H:%M:%S")
                return v
            except ValueError as e:
                raise ValueError(
                    f"Invalid screening datetime format: {v}. Expected YYYYMMDDTHH:MM:SS. {str(e)}"
                )
        return v

    @model_validator(mode='after')
    def refresh_counts_after_validation(self):
        """Keep screening-derived count history in sync whenever the dish model is instantiated."""
        self.refresh_screening_state()
        return self


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
        cross_setup_date: Optional[str] = None,
        dof_source: Optional[str] = None,
        sex: str = "unknown",
        species: str = "Danio rerio",
        parents: Optional[List[str]] = None,
        temperature: float = 28.5,
        light_duration: str = "14:10",
        dawn_dusk: str = "8:00",
        room: str = "2E.282",
        container_type: str = "petri_dish",
        vol_water_total: Optional[int] = None,
        notes: Optional[str] = None,
        parent_dish_id: Optional[str] = None,
        dish_population_type: DishPopulationType = "primary",
        source_screening_datetime: Optional[str] = None,
        source_screening_bucket: Optional[str] = None,
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
            cross_setup_date=cross_setup_date,
            dof_source=dof_source,
            dof=dof,
            genotype=genotype,
            sex=sex,
            species=species,
            responsible=responsible,
            fish_count=fish_count, # Use provided count
            current_fish_count=fish_count,
            parent_dish_id=parent_dish_id, # Added
            dish_population_type=dish_population_type, # Added
            source_screening_datetime=source_screening_datetime,
            source_screening_bucket=source_screening_bucket,
            breeding=Breeding(parents=parents),
            enclosure=Enclosure(
                temperature=temperature,
                light_cycle=LightCycle(
                    light_duration=light_duration,
                    dawn_dusk=dawn_dusk
                ),
                room=room,
                container_type=container_type,
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
        self.refresh_screening_state()

    def get_screening_step(self, screening_datetime: str) -> Optional[ScreeningStep]:
        """Return the screening step matching the provided datetime, if present."""
        if not self.screening_results:
            return None
        return next(
            (step for step in self.screening_results.screenings if step.screening_datetime == screening_datetime),
            None,
        )

    def add_screening_step_allocation(
        self,
        screening_datetime: str,
        allocation: ScreeningStepAllocation,
    ) -> None:
        """Attach an explicit allocation to an existing screening step."""
        step = self.get_screening_step(screening_datetime)
        if not step:
            raise ValueError(f"Screening step {screening_datetime} not found on dish {self.dish_id}")

        new_total = step.total_allocated_count + allocation.count
        if new_total > step.count_screened_this_step:
            raise ValueError(
                f"Allocation would over-assign step {screening_datetime}: "
                f"{new_total} > {step.count_screened_this_step}"
            )
        step.allocations.append(allocation)
        self.refresh_screening_state()

    def refresh_screening_state(self) -> None:
        """Recompute per-step before/after counts and the dish's current fish count."""
        current_count = self.fish_count
        if self.screening_results is None:
            self.current_fish_count = current_count
            return

        try:
            self.screening_results.screenings.sort(
                key=lambda x: datetime.strptime(x.screening_datetime, "%Y%m%dT%H:%M:%S")
            )
        except (ValueError, TypeError):
            logging.warning(f"Could not sort screening steps by datetime for dish {self.dish_id}.")

        for step in self.screening_results.screenings:
            step.count_before_step = current_count
            current_count = max(current_count - step.outgoing_count, 0)
            step.count_after_step = current_count

        self.current_fish_count = current_count


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
        canonical_reason = normalize_termination_reason(reason)
        if not canonical_reason:
            raise ValueError(
                "Termination reason is required and must be one of: "
                f"{termination_reason_options_text()}."
            )
        self.status = "inactive"
        self.termination_date = datetime.now().strftime("%Y%m%d")
        self.termination_reason = canonical_reason
