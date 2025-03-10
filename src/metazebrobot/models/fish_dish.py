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
    room: str
    in_beaker: bool = False


class Breeding(BaseModel):
    """Breeding information for a fish dish."""
    parents: List[str] = []


class QualityCheckData(BaseModel):
    """Data for a quality check."""
    check_time: str  # Format: "YYYYMMDDhh:mm:ss"
    fed: bool = False
    feed_type: Optional[str] = None
    water_changed: bool = False
    vol_water_changed: Optional[int] = None
    num_dead: int = 0
    notes: Optional[str] = None


class FishDish(BaseModel):
    """Model for a fish dish."""
    dish_id: str
    date_created: str  # Format: YYYYMMDD
    cross_id: str
    dof: str  # Date of fertilization (YYYYMMDD)
    genotype: str
    sex: Literal["unknown", "M", "F"] = "unknown"
    species: str = "Danio rerio"
    responsible: str
    fish_count: int = Field(ge=0)
    breeding: Breeding
    enclosure: Enclosure
    quality_checks: Dict[str, Any] = {}
    status: Literal["active", "inactive"] = "active"
    termination_date: Optional[str] = None
    termination_reason: Optional[str] = None

    @field_validator('date_created', 'dof', 'termination_date', mode='before')
    @classmethod
    def validate_date_format(cls, v: str, field) -> str:
        """Validate date format (YYYYMMDD) if provided."""
        if v:
            try:
                datetime.strptime(v, "%Y%m%d")
                return v
            except ValueError:
                raise ValueError(f"Invalid date format for {field.name}: {v}. Expected format: YYYYMMDD")
        return v

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'FishDish':
        """Create a FishDish instance from a dictionary."""
        return cls(**data)

    def to_dict(self) -> Dict[str, Any]:
        """Convert the model to a dictionary."""
        return self.model_dump(exclude_none=True)  # `model_dump()` replaces `dict()` in Pydantic v2

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
        fish_count: int = 1,
        parents: List[str] = None,
        temperature: float = 28.5,
        light_duration: str = "14:10",
        dawn_dusk: str = "8:00",
        room: str = "2E.282",
        in_beaker: bool = False
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
            dof=dof,
            genotype=genotype,
            sex=sex,
            species=species,
            responsible=responsible,
            fish_count=fish_count,
            breeding=Breeding(parents=parents),
            enclosure=Enclosure(
                temperature=temperature,
                light_cycle=LightCycle(
                    light_duration=light_duration,
                    dawn_dusk=dawn_dusk
                ),
                room=room,
                in_beaker=in_beaker
            ),
            quality_checks={
                today: {
                    "check_time": f"{today}00:00:00",
                    "notes": "Created and checked - normal"
                }
            },
            status="active"
        )

    def add_quality_check(self, check_data: QualityCheckData) -> None:
        """
        Add a quality check to the dish.
        """
        check_time = check_data.check_time
        self.quality_checks[check_time] = check_data.model_dump(exclude_none=True)

    def terminate(self, reason: str) -> None:
        """
        Terminate the dish.
        """
        self.status = "inactive"
        self.termination_date = datetime.now().strftime("%Y%m%d")
        self.termination_reason = reason
