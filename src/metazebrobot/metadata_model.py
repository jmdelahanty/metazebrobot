from pydantic import BaseModel, Field
from typing import Optional, Dict, Literal
from datetime import date

class StorageLocation(BaseModel):
    location: str
    container: Optional[str] = None
    expiration: Optional[str] = None
    expiration_date: Optional[str] = None

class QualityChecks(BaseModel):
    visual_inspection: str

class Processing(BaseModel):
    filter_type: Literal["vacuum"]
    filter_size: str

class AgaroseBottle(BaseModel):
    source_number: str
    manufacturer: str
    date_received: str
    expiration_date: str
    storage_location: str
    notes: Optional[str] = None

class AgaroseBottles(BaseModel):
    agarose_bottles: Dict[str, AgaroseBottle]

class AgaroseSolution(BaseModel):
    concentration: float = Field(ge=0, le=1)  # Concentration between 0 and 1
    date_prepared: str
    prepared_by: str
    agarose_bottle_id: str
    fish_water_batch_id: str
    volume_prepared_mL: float = Field(gt=0)  # Volume must be positive
    storage: StorageLocation
    quality_checks: QualityChecks
    notes: Optional[str] = None

class AgaroseSolutions(BaseModel):
    agarose_solutions: Dict[str, AgaroseSolution]

class FishWaterBatch(BaseModel):
    source: Literal["Janelia System"]
    preparation_date: str
    notes: Optional[str] = None

class FishWaterBatches(BaseModel):
    fish_water_batches: Dict[str, FishWaterBatch]

class FishWaterDerivative(BaseModel):
    source_batch_id: str
    type: Literal["filtered"]
    date_prepared: str
    prepared_by: str
    volume_prepared_mL: float = Field(gt=0)
    storage: StorageLocation
    processing: Processing
    quality_checks: QualityChecks
    notes: Optional[str] = None

class FishWaterDerivatives(BaseModel):
    fish_water_derivatives: Dict[str, FishWaterDerivative]

class PolyLSerineBottle(BaseModel):
    manufacturer: str
    date_received: Optional[str] = None
    expiration_date: str
    storage_location: str
    notes: Optional[str] = None

class PolyLSerineBottles(BaseModel):
    poly_l_serine_bottles: Dict[str, PolyLSerineBottle]

class PolyLSerineDerivative(BaseModel):
    source_bottle_id: str
    type: Literal["aliquot"]
    date_prepared: str
    prepared_by: str
    volume_prepared: float = Field(gt=0)
    storage: StorageLocation
    notes: Optional[str] = None

class PolyLSerineDerivatives(BaseModel):
    poly_l_serine_derivatives: Dict[str, PolyLSerineDerivative]

# Complete inventory model that includes all components
class LabInventory(BaseModel):
    agarose_bottles: AgaroseBottles
    agarose_solutions: AgaroseSolutions
    fish_water_sources: FishWaterBatches
    fish_water_derivatives: FishWaterDerivatives
    poly_l_serine_bottles: PolyLSerineBottles
    poly_l_serine_derivatives: PolyLSerineDerivatives

class LightCycle(BaseModel):
    light_duration: str
    dawn_dusk: str

class IncubatorProperties(BaseModel):
    temperature: float = Field(ge=18, le=30)  # Reasonable temperature range for zebrafish
    light_cycle: LightCycle
    room: str

class Dish(BaseModel):
    dish_number: int = Field(gt=0)

class Breeding(BaseModel):
    parents: List[str]

class FishDishMetadata(BaseModel):
    cross_id: str
    dish_id: Dish
    dof: str  # Date of fertilization
    genotype: str
    sex: Literal["M", "F", "unknown"]
    species: str
    responsible: str
    breeding: Breeding
    enclosure: IncubatorProperties
    notes: Optional[str] = None

class FishDish(BaseModel):
    dish_id: str  # Format: DISH_YYYYMMDD_XX where XX is sequential number
    date_created: str
    metadata: FishMetadata
    quality_checks: Dict[str, str] = Field(default_factory=dict)  # Date: observation
    status: Literal["active", "terminated", "transferred"] = "active"
    termination_date: Optional[str] = None
    termination_reason: Optional[str] = None

class FishDishes(BaseModel):
    fish_dishes: Dict[str, FishDish]


# Example usage:
"""
# Load data
with open('config.json', 'r') as f:
    config_data = json.load(f)
    
# Validate entire inventory
inventory = LabInventory.model_validate(config_data)

# Validate individual components
agarose_solution = AgaroseSolution(
    concentration=0.02,
    date_prepared="20250127",
    prepared_by="Jeremy Delahanty",
    agarose_bottle_id="0000367498",
    fish_water_batch_id="FW_2025_0002",
    volume_prepared_mL=200,
    storage={
        "location": "2E.260-6-3",
        "container": "incubator",
        "expiration": "20250330"
    },
    quality_checks={
        "visual_inspection": "Clear, no particles"
    }
)
"""