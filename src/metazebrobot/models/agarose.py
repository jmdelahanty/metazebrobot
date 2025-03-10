"""
Agarose models for MetaZebrobot.

This module defines the data models for agarose bottles and solutions.
"""

from datetime import datetime
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field, validator


class StorageLocation(BaseModel):
    """Storage location for materials."""
    location: str
    container: Optional[str] = None
    expiration: Optional[str] = None


class QualityChecks(BaseModel):
    """Quality check information."""
    visual_inspection: str


class AgaroseBottle(BaseModel):
    """Model for an agarose bottle in inventory."""
    source_number: str
    manufacturer: str
    date_received: str
    expiration_date: str
    storage_location: str
    notes: Optional[str] = None
    
    @validator('date_received', 'expiration_date')
    def validate_date_format(cls, v):
        """Validate date format (YYYYMMDD)."""
        if not v:
            return v
        try:
            datetime.strptime(v, "%Y%m%d")
            return v
        except ValueError:
            raise ValueError(f"Invalid date format: {v}. Expected format: YYYYMMDD")


class AgaroseSolution(BaseModel):
    """Model for an agarose solution."""
    concentration: float = Field(ge=0, le=1)  # Concentration between 0 and 1
    date_prepared: str
    prepared_by: str
    agarose_bottle_id: str
    fish_water_batch_id: str
    volume_prepared_mL: float = Field(gt=0)  # Volume must be positive
    storage: StorageLocation
    quality_checks: QualityChecks
    notes: Optional[str] = None

    @validator('date_prepared')
    def validate_date_format(cls, v):
        """Validate date format (YYYYMMDD)."""
        if not v:
            return v
        try:
            datetime.strptime(v, "%Y%m%d")
            return v
        except ValueError:
            raise ValueError(f"Invalid date format: {v}. Expected format: YYYYMMDD")
            
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'AgaroseSolution':
        """Create an AgaroseSolution instance from a dictionary."""
        return cls(**data)
        
    def to_dict(self) -> Dict[str, Any]:
        """Convert the model to a dictionary."""
        return self.dict()
        
    @classmethod
    def create_new(
        cls,
        concentration: float,
        agarose_bottle_id: str,
        fish_water_batch_id: str,
        volume_prepared_mL: float,
        prepared_by: str = "Lab Staff",
        storage_location: str = "2E.260-6-3",
        container: str = "incubator",
        expiration_days: int = 60,
        notes: Optional[str] = None
    ) -> 'AgaroseSolution':
        """
        Create a new agarose solution with defaults.
        
        Args:
            concentration: Concentration value (0-1)
            agarose_bottle_id: ID of the source bottle
            fish_water_batch_id: ID of the fish water batch used
            volume_prepared_mL: Volume in milliliters
            prepared_by: Name of the preparer
            storage_location: Where the solution is stored
            container: Container type
            expiration_days: Days until expiration
            notes: Additional notes
            
        Returns:
            A new AgaroseSolution instance
        """
        today = datetime.now().strftime("%Y%m%d")
        expiration = (datetime.now().replace(day=datetime.now().day + expiration_days)
                     .strftime("%Y%m%d"))
        
        return cls(
            concentration=concentration,
            date_prepared=today,
            prepared_by=prepared_by,
            agarose_bottle_id=agarose_bottle_id,
            fish_water_batch_id=fish_water_batch_id,
            volume_prepared_mL=volume_prepared_mL,
            storage=StorageLocation(
                location=storage_location,
                container=container,
                expiration=expiration
            ),
            quality_checks=QualityChecks(
                visual_inspection="Clear, no particles"
            ),
            notes=notes
        )