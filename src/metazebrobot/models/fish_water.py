"""
Fish water models for MetaZebrobot.
"""

from datetime import datetime
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field, field_validator


class FishWaterStorage(BaseModel):
    """Storage information for fish water derivatives."""
    location: str = Field(..., description="Storage location")


class FishWaterProcessing(BaseModel):
    """Processing information for fish water derivatives."""
    filter_type: Optional[str] = Field(None, description="Type of filter used")
    filter_size: Optional[str] = Field(None, description="Filter size")
    method: Optional[str] = Field(None, description="Processing method")


class FishWaterQualityChecks(BaseModel):
    """Quality check information for fish water."""
    visual_inspection: Optional[str] = Field(None, description="Visual inspection results")
    ph: Optional[float] = Field(None, ge=0, le=14, description="pH level")
    conductivity: Optional[int] = Field(None, ge=0, description="Conductivity in μS/cm")


class FishWaterBatch(BaseModel):
    """Model for a fish water batch (matches your existing structure)."""
    source: str = Field(..., description="Source of the water (e.g., Janelia System)")
    preparation_date: str = Field(..., description="Date prepared (YYYY-MM-DD format)")
    notes: Optional[str] = None
    
    # Additional fields for new batches
    volume_prepared_mL: Optional[float] = Field(None, gt=0, description="Volume prepared in mL")
    prepared_by: Optional[str] = Field(None, description="Person who prepared the batch")
    
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
        """
        Create a new fish water batch.
        
        Args:
            source: Source of the water
            volume_prepared_mL: Volume prepared in mL
            prepared_by: Person who prepared the batch
            preparation_date: Date prepared (defaults to today in YYYY-MM-DD format)
            notes: Optional notes
            
        Returns:
            A new FishWaterBatch instance
        """
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
    """Model for fish water derivative (matches your existing structure)."""
    source_batch_id: str = Field(..., description="ID of the source water batch")
    type: str = Field(..., description="Type of derivative (e.g., filtered)")
    date_prepared: str = Field(..., description="Date prepared (YYYYMMDD)")
    prepared_by: str = Field(..., description="Person who prepared the derivative")
    volume_prepared_mL: float = Field(..., gt=0, description="Volume prepared in mL")
    storage: FishWaterStorage = Field(..., description="Storage information")
    processing: Optional[FishWaterProcessing] = Field(None, description="Processing information")
    quality_checks: Optional[FishWaterQualityChecks] = Field(None, description="Quality check results")
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
        visual_inspection: str = "clear, no particles",
        notes: Optional[str] = None
    ) -> 'FishWaterDerivative':
        """
        Create a new fish water derivative.
        
        Args:
            source_batch_id: ID of the source water batch
            derivative_type: Type of derivative (e.g., filtered)
            volume_prepared_mL: Volume prepared in mL
            storage_location: Storage location
            prepared_by: Person who prepared the derivative
            date_prepared: Date prepared (defaults to today in YYYYMMDD)
            filter_type: Type of filter used
            filter_size: Size of filter used
            visual_inspection: Visual inspection results
            notes: Optional notes
            
        Returns:
            A new FishWaterDerivative instance
        """
        if not date_prepared:
            date_prepared = datetime.now().strftime("%Y%m%d")
        
        return cls(
            source_batch_id=source_batch_id,
            type=derivative_type,
            date_prepared=date_prepared,
            prepared_by=prepared_by,
            volume_prepared_mL=volume_prepared_mL,
            storage=FishWaterStorage(location=storage_location),
            processing=FishWaterProcessing(
                filter_type=filter_type,
                filter_size=filter_size
            ) if filter_type else None,
            quality_checks=FishWaterQualityChecks(
                visual_inspection=visual_inspection
            ),
            notes=notes
        )