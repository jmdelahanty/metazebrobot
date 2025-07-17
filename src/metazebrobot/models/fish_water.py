"""
Fish water models for MetaZebrobot.
"""

from datetime import datetime
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field, field_validator


class FishWaterBatch(BaseModel):
    """Model for a fish water batch (simplified structure)."""
    source: str = Field(..., description="Source of the water (e.g., Janelia System)")
    preparation_date: str = Field(..., description="Date prepared (YYYY-MM-DD format)")
    volume_prepared_mL: Optional[float] = Field(None, gt=0, description="Volume prepared in mL")
    prepared_by: Optional[str] = Field(None, description="Person who prepared the batch")
    notes: Optional[str] = None
    
    @field_validator('preparation_date')
    @classmethod
    def validate_date_format(cls, v: str) -> str:
        """Validate date format (accepts YYYY-MM-DD or YYYYMMDD)."""
        if v:
            # Try different date formats
            for fmt in ["%Y-%m-%d", "%Y%m%d"]:
                try:
                    datetime.strptime(v, fmt)
                    return v
                except ValueError:
                    continue
            raise ValueError(f"Invalid date format: {v}. Expected YYYY-MM-DD or YYYYMMDD")
        raise ValueError("preparation_date is required")
    
    @classmethod
    def create_new(
        cls,
        source: str = "Janelia System",
        volume_prepared_mL: Optional[float] = None,
        prepared_by: str = "Lab Staff",
        preparation_date: Optional[str] = None,
        notes: Optional[str] = None
    ) -> 'FishWaterBatch':
        """Create a new fish water batch."""
        if not preparation_date:
            preparation_date = datetime.now().strftime("%Y-%m-%d")
        
        return cls(
            source=source,
            preparation_date=preparation_date,
            volume_prepared_mL=volume_prepared_mL,
            prepared_by=prepared_by,
            notes=notes
        )


class FishWaterDerivative(BaseModel):
    """Model for fish water derivative (flattened structure)."""
    source_batch_id: str = Field(..., description="ID of the source water batch")
    type: str = Field(..., description="Type of derivative (e.g., filtered)")
    date_prepared: str = Field(..., description="Date prepared (YYYYMMDD)")
    prepared_by: str = Field(..., description="Person who prepared the derivative")
    volume_prepared_mL: float = Field(..., gt=0, description="Volume prepared in mL")
    
    # Flattened storage fields
    storage_location: str = Field(..., description="Storage location")
    
    # Flattened processing fields (optional)
    filter_type: Optional[str] = Field(None, description="Type of filter used")
    filter_size: Optional[str] = Field(None, description="Filter size")
    processing_method: Optional[str] = Field(None, description="Processing method")
    
    # Flattened quality check fields (optional)
    visual_inspection: Optional[str] = Field(None, description="Visual inspection results")
    ph: Optional[float] = Field(None, ge=0, le=14, description="pH level")
    conductivity: Optional[int] = Field(None, ge=0, description="Conductivity in μS/cm")
    
    # General notes
    notes: Optional[str] = None
    
    @field_validator('date_prepared')
    @classmethod
    def validate_date_format(cls, v: str) -> str:
        """Validate date format (YYYYMMDD)."""
        if v:
            try:
                datetime.strptime(v, "%Y%m%d")
                return v
            except ValueError:
                raise ValueError(f"Invalid date format: {v}. Expected format: YYYYMMDD")
        raise ValueError("date_prepared is required")
    
    @classmethod
    def create_new(
        cls,
        source_batch_id: str,
        derivative_type: str = "filtered",
        volume_prepared_mL: float = 250.0,
        storage_location: str = "2E.260-7-B",
        prepared_by: str = "Lab Staff",
        date_prepared: Optional[str] = None,
        filter_type: Optional[str] = "vacuum",
        filter_size: Optional[str] = "20um",
        processing_method: Optional[str] = None,
        visual_inspection: str = "clear, no particles",
        ph: Optional[float] = None,
        conductivity: Optional[int] = None,
        notes: Optional[str] = None
    ) -> 'FishWaterDerivative':
        """Create a new fish water derivative."""
        if not date_prepared:
            date_prepared = datetime.now().strftime("%Y%m%d")
        
        return cls(
            source_batch_id=source_batch_id,
            type=derivative_type,
            date_prepared=date_prepared,
            prepared_by=prepared_by,
            volume_prepared_mL=volume_prepared_mL,
            storage_location=storage_location,
            filter_type=filter_type,
            filter_size=filter_size,
            processing_method=processing_method,
            visual_inspection=visual_inspection,
            ph=ph,
            conductivity=conductivity,
            notes=notes
        )