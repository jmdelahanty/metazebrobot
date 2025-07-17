"""
Simplified controller for fish water operations (works with flattened models).
"""

import logging
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple, Callable

from ..models.fish_water import FishWaterBatch, FishWaterDerivative
from ..data.data_manager import data_manager
from pydantic import ValidationError

logger = logging.getLogger(__name__)


class FishWaterController:
    """Simplified controller for fish water operations."""
    
    def __init__(self):
        """Initialize the controller."""
        pass
        
    def get_all_batches(self) -> Dict[str, FishWaterBatch]:
        """Get all fish water batches."""
        batches_dict = data_manager.get_fish_water_batches()
        result = {}
        
        for batch_id, batch_data in batches_dict.items():
            try:
                # Handle nested structure if it exists
                if batch_id == "fish_water_batches" and isinstance(batch_data, dict):
                    for nested_batch_id, nested_batch_data in batch_data.items():
                        transformed_data = self._transform_batch_data(nested_batch_data)
                        if transformed_data:
                            result[nested_batch_id] = FishWaterBatch(**transformed_data)
                else:
                    transformed_data = self._transform_batch_data(batch_data)
                    if transformed_data:
                        result[batch_id] = FishWaterBatch(**transformed_data)
            except ValidationError as e:
                logger.error(f"Validation error parsing batch {batch_id}: {e}")
            except Exception as e:
                logger.error(f"Error parsing batch {batch_id}: {str(e)}")
                
        return result
    
    def _transform_batch_data(self, batch_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Transform batch data to handle typos and missing fields."""
        if not isinstance(batch_data, dict):
            return None
            
        transformed = {}
        transformed['source'] = batch_data.get('source', 'Unknown')
        
        # Handle the typo in preparation date
        prep_date = (batch_data.get('preparation_date') or 
                    batch_data.get('preparataion_date'))  # Handle typo
        
        if not prep_date:
            prep_date = "2025-01-01"
            
        transformed['preparation_date'] = prep_date
        transformed['notes'] = batch_data.get('notes')
        transformed['volume_prepared_mL'] = batch_data.get('volume_prepared_mL')
        transformed['prepared_by'] = batch_data.get('prepared_by')
        
        return transformed
        
    def get_all_derivatives(self) -> Dict[str, FishWaterDerivative]:
        """Get all fish water derivatives."""
        derivatives_dict = data_manager.get_fish_water_derivatives()
        result = {}
        
        for derivative_id, derivative_data in derivatives_dict.items():
            try:
                # Handle nested structure if it exists
                if derivative_id == "fish_water_derivatives" and isinstance(derivative_data, dict):
                    for nested_derivative_id, nested_derivative_data in derivative_data.items():
                        # Data should already be flattened after migration
                        result[nested_derivative_id] = FishWaterDerivative(**nested_derivative_data)
                else:
                    result[derivative_id] = FishWaterDerivative(**derivative_data)
            except ValidationError as e:
                logger.error(f"Validation error parsing derivative {derivative_id}: {e}")
            except Exception as e:
                logger.error(f"Error parsing derivative {derivative_id}: {str(e)}")
                
        return result
        
    def get_batch(self, batch_id: str) -> Optional[FishWaterBatch]:
        """Get a specific fish water batch."""
        batches = data_manager.get_fish_water_batches()
        batch_data = batches.get(batch_id)
        
        if not batch_data:
            return None
            
        try:
            transformed_data = self._transform_batch_data(batch_data)
            if transformed_data:
                return FishWaterBatch(**transformed_data)
            return None
        except Exception as e:
            logger.error(f"Error parsing batch {batch_id}: {str(e)}")
            return None
            
    def get_derivative(self, derivative_id: str) -> Optional[FishWaterDerivative]:
        """Get a specific fish water derivative."""
        derivatives = data_manager.get_fish_water_derivatives()
        derivative_data = derivatives.get(derivative_id)
        
        if not derivative_data:
            return None
            
        try:
            return FishWaterDerivative(**derivative_data)
        except Exception as e:
            logger.error(f"Error parsing derivative {derivative_id}: {str(e)}")
            return None
            
    def create_batch(self, batch_id: str, batch_data: Dict[str, Any]) -> Tuple[bool, str]:
        """Create a new fish water batch."""
        try:
            batch = FishWaterBatch.create_new(**batch_data)
            
            existing_batches = data_manager.get_fish_water_batches()
            if batch_id in existing_batches:
                return False, f"Batch {batch_id} already exists"
            
            success = data_manager.add_fish_water_batch(batch_id, batch.model_dump(exclude_none=True))
            
            if success:
                logger.info(f"Successfully created fish water batch: {batch_id}")
                return True, batch_id
            else:
                return False, "Failed to save batch to database"
                
        except ValidationError as e:
            logger.error(f"Validation failed for new batch {batch_id}: {e}")
            error_details = e.errors()
            message = f"Validation Error: {error_details[0]['msg']} (field: {error_details[0]['loc'][0]})" if error_details else str(e)
            return False, message
        except Exception as e:
            logger.error(f"Error creating batch {batch_id}: {str(e)}")
            return False, f"An unexpected error occurred: {str(e)}"
            
    def create_derivative(self, derivative_id: str, derivative_data: Dict[str, Any]) -> Tuple[bool, str]:
        """Create a new fish water derivative."""
        try:
            source_batch_id = derivative_data.get('source_batch_id')
            if not source_batch_id:
                return False, "Source batch ID is required"
                
            source_batch = self.get_batch(source_batch_id)
            if not source_batch:
                return False, f"Source batch {source_batch_id} not found"
            
            derivative = FishWaterDerivative.create_new(**derivative_data)
            
            existing_derivatives = data_manager.get_fish_water_derivatives()
            if derivative_id in existing_derivatives:
                return False, f"Derivative {derivative_id} already exists"
            
            success = data_manager.add_fish_water_derivative(derivative_id, derivative.model_dump(exclude_none=True))
            
            if success:
                logger.info(f"Successfully created fish water derivative: {derivative_id}")
                return True, derivative_id
            else:
                return False, "Failed to save derivative to database"
                
        except ValidationError as e:
            logger.error(f"Validation failed for new derivative {derivative_id}: {e}")
            error_details = e.errors()
            message = f"Validation Error: {error_details[0]['msg']} (field: {error_details[0]['loc'][0]})" if error_details else str(e)
            return False, message
        except Exception as e:
            logger.error(f"Error creating derivative {derivative_id}: {str(e)}")
            return False, f"An unexpected error occurred: {str(e)}"
    
    def sort_batches(self, batches: Dict[str, FishWaterBatch], sort_key: str, ascending: bool = True) -> Dict[str, FishWaterBatch]:
        """Sort batches by a specific key."""
        def get_sort_value(batch: FishWaterBatch, key: str) -> Any:
            if hasattr(batch, key):
                return getattr(batch, key)
            else:
                logger.warning(f"Unknown sort key for batches: {key}")
                return ""

        try:
            sorted_items = sorted(
                batches.items(),
                key=lambda item: (get_sort_value(item[1], sort_key) is None, get_sort_value(item[1], sort_key)),
                reverse=not ascending
            )
            return dict(sorted_items)
        except Exception as e:
            logger.error(f"Error sorting batches by key '{sort_key}': {e}")
            return batches
    
    def sort_derivatives(self, derivatives: Dict[str, FishWaterDerivative], sort_key: str, ascending: bool = True) -> Dict[str, FishWaterDerivative]:
        """Sort derivatives by a specific key."""
        def get_sort_value(derivative: FishWaterDerivative, key: str) -> Any:
            if hasattr(derivative, key):
                return getattr(derivative, key)
            else:
                logger.warning(f"Unknown sort key for derivatives: {key}")
                return ""

        try:
            sorted_items = sorted(
                derivatives.items(),
                key=lambda item: (get_sort_value(item[1], sort_key) is None, get_sort_value(item[1], sort_key)),
                reverse=not ascending
            )
            return dict(sorted_items)
        except Exception as e:
            logger.error(f"Error sorting derivatives by key '{sort_key}': {e}")
            return derivatives

    def filter_batches(self, batches: Dict[str, FishWaterBatch], filter_func: Callable[[FishWaterBatch], bool]) -> Dict[str, FishWaterBatch]:
        """Filter batches based on a filter function."""
        try:
            return {k: v for k, v in batches.items() if filter_func(v)}
        except Exception as e:
            logger.error(f"Error applying filter function to batches: {e}")
            return batches

    def filter_derivatives(self, derivatives: Dict[str, FishWaterDerivative], filter_func: Callable[[FishWaterDerivative], bool]) -> Dict[str, FishWaterDerivative]:
        """Filter derivatives based on a filter function."""
        try:
            return {k: v for k, v in derivatives.items() if filter_func(v)}
        except Exception as e:
            logger.error(f"Error applying filter function to derivatives: {e}")
            return derivatives

    def search_batches(self, batches: Dict[str, FishWaterBatch], search_text: str, case_sensitive: bool = False) -> Dict[str, FishWaterBatch]:
        """Search batches for text in various fields."""
        if not search_text:
            return batches

        result = {}
        search_lower = search_text.lower() if not case_sensitive else search_text

        for batch_id, batch in batches.items():
            try:
                fields_to_check = [
                    batch_id, batch.source, batch.prepared_by or "", batch.notes or ""
                ]

                match_found = False
                for field_value in fields_to_check:
                    if field_value:
                        field_str = str(field_value)
                        check_value = field_str if case_sensitive else field_str.lower()
                        if search_lower in check_value:
                            match_found = True
                            break

                if match_found:
                    result[batch_id] = batch

            except Exception as e:
                logger.error(f"Error searching within batch {batch_id}: {e}")

        return result

    def search_derivatives(self, derivatives: Dict[str, FishWaterDerivative], search_text: str, case_sensitive: bool = False) -> Dict[str, FishWaterDerivative]:
        """Search derivatives for text in various fields."""
        if not search_text:
            return derivatives

        result = {}
        search_lower = search_text.lower() if not case_sensitive else search_text

        for derivative_id, derivative in derivatives.items():
            try:
                fields_to_check = [
                    derivative_id, derivative.source_batch_id, derivative.type,
                    derivative.prepared_by, derivative.storage_location, derivative.notes or ""
                ]

                match_found = False
                for field_value in fields_to_check:
                    if field_value:
                        field_str = str(field_value)
                        check_value = field_str if case_sensitive else field_str.lower()
                        if search_lower in check_value:
                            match_found = True
                            break

                if match_found:
                    result[derivative_id] = derivative

            except Exception as e:
                logger.error(f"Error searching within derivative {derivative_id}: {e}")

        return result


# Create a singleton instance for global access
fish_water_controller = FishWaterController()