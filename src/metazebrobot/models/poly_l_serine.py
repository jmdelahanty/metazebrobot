"""
Poly-L-Serine models for MetaZebrobot.

This module defines the data models for poly-L-serine bottles and solutions.
"""

from datetime import datetime
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field, field_validator


class PolyLSerineBottle(BaseModel):
    """Model for a poly-L-serine bottle in inventory."""
    manufacturer: str = Field(..., description="Manufacturer of the poly-L-serine")
    date_received: Optional[str] = Field(None, description="Date received (YYYYMMDD)")
    expiration_date: str = Field(..., description="Expiration date (YYYYMMDD)")
    storage_location: str = Field(..., description="Storage location")
    notes: Optional[str] = None
    
    @field_validator('date_received', 'expiration_date')
    @classmethod
    def validate_date_format(cls, v: Optional[str]) -> Optional[str]:
        """Validate date format (YYYYMMDD)."""
        if v:
            try:
                datetime.strptime(v, "%Y%m%d")
                return v
            except ValueError:
                raise ValueError(f"Invalid date format: {v}. Expected format: YYYYMMDD")
        return v

    @classmethod
    def create_new(
        cls,
        manufacturer: str,
        expiration_date: str,
        storage_location: str = "2E.254",
        date_received: Optional[str] = None,
        notes: Optional[str] = None
    ) -> 'PolyLSerineBottle':
        """Create a new poly-L-serine bottle."""
        return cls(
            manufacturer=manufacturer,
            date_received=date_received,
            expiration_date=expiration_date,
            storage_location=storage_location,
            notes=notes
        )


class PolyLSerineDerivative(BaseModel):
    """Model for a poly-L-serine derivative (aliquot, solution, etc.)."""
    source_bottle_id: str = Field(..., description="ID of the source bottle")
    type: str = Field(..., description="Type of derivative (e.g., aliquot, solution)")
    date_prepared: str = Field(..., description="Date prepared (YYYYMMDD)")
    prepared_by: str = Field(..., description="Person who prepared the derivative")
    volume_prepared: float = Field(..., gt=0, description="Volume prepared in mL")
    
    # Storage information (flattened from nested structure)
    storage_location: str = Field(..., description="Storage location")
    storage_container: Optional[str] = Field(None, description="Storage container type")
    storage_expiration_date: Optional[str] = Field(None, description="Storage expiration date (YYYYMMDD)")
    
    notes: Optional[str] = None
    
    @field_validator('date_prepared', 'storage_expiration_date')
    @classmethod
    def validate_date_format(cls, v: Optional[str]) -> Optional[str]:
        """Validate date format (YYYYMMDD)."""
        if v:
            try:
                datetime.strptime(v, "%Y%m%d")
                return v
            except ValueError:
                raise ValueError(f"Invalid date format: {v}. Expected format: YYYYMMDD")
        return v
    
    @classmethod
    def create_new(
        cls,
        source_bottle_id: str,
        derivative_type: str = "aliquot",
        volume_prepared: float = 50.0,
        prepared_by: str = "Lab Staff",
        storage_location: str = "2E.254",
        storage_container: str = "50mL tube",
        date_prepared: Optional[str] = None,
        storage_expiration_date: Optional[str] = None,
        notes: Optional[str] = None
    ) -> 'PolyLSerineDerivative':
        """Create a new poly-L-serine derivative."""
        if not date_prepared:
            date_prepared = datetime.now().strftime("%Y%m%d")
        
        return cls(
            source_bottle_id=source_bottle_id,
            type=derivative_type,
            date_prepared=date_prepared,
            prepared_by=prepared_by,
            volume_prepared=volume_prepared,
            storage_location=storage_location,
            storage_container=storage_container,
            storage_expiration_date=storage_expiration_date,
            notes=notes
        )