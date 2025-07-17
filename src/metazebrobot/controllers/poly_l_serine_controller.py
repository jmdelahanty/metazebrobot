"""
Controller for poly-L-serine-related operations.

This module contains business logic for managing poly-L-serine bottles and derivatives.
"""

import logging
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple, Callable

from ..models.poly_l_serine import PolyLSerineBottle, PolyLSerineDerivative
from ..data.data_manager import data_manager
from pydantic import ValidationError

logger = logging.getLogger(__name__)


class PolyLSerineController:
    """
    Controller for poly-L-serine-related operations.
    
    This class provides methods for managing poly-L-serine bottles and derivatives.
    """
    
    def __init__(self):
        """Initialize the controller."""
        pass
        
    def get_all_bottles(self) -> Dict[str, PolyLSerineBottle]:
        """
        Get all poly-L-serine bottles.
        
        Returns:
            Dict mapping bottle IDs to PolyLSerineBottle objects
        """
        bottles_dict = data_manager.get_poly_l_serine_bottles()
        result = {}
        
        for bottle_id, bottle_data in bottles_dict.items():
            try:
                # Handle nested structure if it exists
                if bottle_id == "poly_l_serine_bottles" and isinstance(bottle_data, dict):
                    for nested_bottle_id, nested_bottle_data in bottle_data.items():
                        result[nested_bottle_id] = PolyLSerineBottle(**nested_bottle_data)
                else:
                    result[bottle_id] = PolyLSerineBottle(**bottle_data)
            except ValidationError as e:
                logger.error(f"Validation error parsing bottle {bottle_id}: {e}")
            except Exception as e:
                logger.error(f"Error parsing bottle {bottle_id}: {str(e)}")
                
        return result
        
    def get_all_derivatives(self) -> Dict[str, PolyLSerineDerivative]:
        """
        Get all poly-L-serine derivatives.
        
        Returns:
            Dict mapping derivative IDs to PolyLSerineDerivative objects
        """
        derivatives_dict = data_manager.get_poly_l_serine_derivatives()
        result = {}
        
        for derivative_id, derivative_data in derivatives_dict.items():
            try:
                # Handle nested structure if it exists
                if derivative_id == "poly_l_serine_derivatives" and isinstance(derivative_data, dict):
                    for nested_derivative_id, nested_derivative_data in derivative_data.items():
                        transformed_data = self._transform_derivative_data(nested_derivative_data)
                        if transformed_data:
                            result[nested_derivative_id] = PolyLSerineDerivative(**transformed_data)
                else:
                    transformed_data = self._transform_derivative_data(derivative_data)
                    if transformed_data:
                        result[derivative_id] = PolyLSerineDerivative(**transformed_data)
            except ValidationError as e:
                logger.error(f"Validation error parsing derivative {derivative_id}: {e}")
            except Exception as e:
                logger.error(f"Error parsing derivative {derivative_id}: {str(e)}")
                
        return result
    
    def _transform_derivative_data(self, derivative_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Transform legacy derivative data from nested to flat structure.
        
        Args:
            derivative_data: Raw derivative data from storage
            
        Returns:
            Transformed data or None if transformation fails
        """
        if not isinstance(derivative_data, dict):
            logger.warning(f"Derivative data is not a dictionary: {type(derivative_data)}")
            return None
            
        try:
            # Start with basic fields
            transformed = {
                'source_bottle_id': derivative_data.get('source_bottle_id'),
                'type': derivative_data.get('type'),
                'date_prepared': derivative_data.get('date_prepared'),
                'prepared_by': derivative_data.get('prepared_by'),
                'volume_prepared': derivative_data.get('volume_prepared'),
                'notes': derivative_data.get('notes')
            }
            
            # Handle storage field (might be nested)
            storage = derivative_data.get('storage')
            if isinstance(storage, dict):
                # Flatten nested storage
                transformed['storage_location'] = storage.get('location')
                transformed['storage_container'] = storage.get('container')
                transformed['storage_expiration_date'] = storage.get('expiration_date')
            else:
                # Already flat or missing
                transformed['storage_location'] = derivative_data.get('storage_location')
                transformed['storage_container'] = derivative_data.get('storage_container')
                transformed['storage_expiration_date'] = derivative_data.get('storage_expiration_date')
            
            # Validate required fields
            if not transformed['source_bottle_id']:
                logger.error(f"Missing required source_bottle_id in derivative data: {derivative_data}")
                return None
            
            if not transformed['date_prepared']:
                logger.error(f"Missing required date_prepared in derivative data: {derivative_data}")
                return None
                
            return transformed
            
        except Exception as e:
            logger.error(f"Error transforming derivative data: {e}", exc_info=True)
            return None
        
    def get_bottle(self, bottle_id: str) -> Optional[PolyLSerineBottle]:
        """
        Get a specific poly-L-serine bottle.
        
        Args:
            bottle_id: ID of the bottle to retrieve
            
        Returns:
            PolyLSerineBottle if found, None otherwise
        """
        bottles = data_manager.get_poly_l_serine_bottles()
        bottle_data = bottles.get(bottle_id)
        
        if not bottle_data:
            return None
            
        try:
            return PolyLSerineBottle(**bottle_data)
        except Exception as e:
            logger.error(f"Error parsing bottle {bottle_id}: {str(e)}")
            return None
            
    def get_derivative(self, derivative_id: str) -> Optional[PolyLSerineDerivative]:
        """
        Get a specific poly-L-serine derivative.
        
        Args:
            derivative_id: ID of the derivative to retrieve
            
        Returns:
            PolyLSerineDerivative if found, None otherwise
        """
        derivatives = data_manager.get_poly_l_serine_derivatives()
        derivative_data = derivatives.get(derivative_id)
        
        if not derivative_data:
            return None
            
        try:
            transformed_data = self._transform_derivative_data(derivative_data)
            if transformed_data:
                return PolyLSerineDerivative(**transformed_data)
            return None
        except Exception as e:
            logger.error(f"Error parsing derivative {derivative_id}: {str(e)}")
            return None
            
    def create_bottle(
        self,
        bottle_id: str,
        bottle_data: Dict[str, Any]
    ) -> Tuple[bool, str]:
        """
        Create a new poly-L-serine bottle.
        
        Args:
            bottle_id: Unique identifier for the bottle
            bottle_data: Dictionary containing bottle information
            
        Returns:
            Tuple containing:
            - Success flag (bool)
            - Message (str)
        """
        try:
            # Validate the data by creating a model instance
            bottle = PolyLSerineBottle.create_new(**bottle_data)
            
            # Check if bottle already exists
            existing_bottles = data_manager.get_poly_l_serine_bottles()
            if bottle_id in existing_bottles:
                return False, f"Bottle {bottle_id} already exists"
            
            # Save to database via data manager
            success = data_manager.add_poly_l_serine_bottle(bottle_id, bottle.model_dump(exclude_none=True))
            
            if success:
                logger.info(f"Successfully created poly-L-serine bottle: {bottle_id}")
                return True, bottle_id
            else:
                return False, "Failed to save bottle to database"
                
        except ValidationError as e:
            logger.error(f"Validation failed for new bottle {bottle_id}: {e}")
            error_details = e.errors()
            message = f"Validation Error: {error_details[0]['msg']} (field: {error_details[0]['loc'][0]})" if error_details else str(e)
            return False, message
        except Exception as e:
            logger.error(f"Error creating bottle {bottle_id}: {str(e)}")
            return False, f"An unexpected error occurred: {str(e)}"
            
    def create_derivative(
        self,
        derivative_id: str,
        derivative_data: Dict[str, Any]
    ) -> Tuple[bool, str]:
        """
        Create a new poly-L-serine derivative.
        
        Args:
            derivative_id: Unique identifier for the derivative
            derivative_data: Dictionary containing derivative information
            
        Returns:
            Tuple containing:
            - Success flag (bool)
            - Message (str)
        """
        try:
            # Validate source bottle exists
            source_bottle_id = derivative_data.get('source_bottle_id')
            if not source_bottle_id:
                return False, "Source bottle ID is required"
                
            source_bottle = self.get_bottle(source_bottle_id)
            if not source_bottle:
                return False, f"Source bottle {source_bottle_id} not found"
            
            # Validate the data by creating a model instance
            derivative = PolyLSerineDerivative.create_new(**derivative_data)
            
            # Check if derivative already exists
            existing_derivatives = data_manager.get_poly_l_serine_derivatives()
            if derivative_id in existing_derivatives:
                return False, f"Derivative {derivative_id} already exists"
            
            # Save to database via data manager
            success = data_manager.add_poly_l_serine_solution(derivative_id, derivative.model_dump(exclude_none=True))
            
            if success:
                logger.info(f"Successfully created poly-L-serine derivative: {derivative_id}")
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
    
    def sort_bottles(
        self,
        bottles: Dict[str, PolyLSerineBottle],
        sort_key: str,
        ascending: bool = True
    ) -> Dict[str, PolyLSerineBottle]:
        """Sort bottles by a specific key."""
        def get_sort_value(bottle: PolyLSerineBottle, key: str) -> Any:
            if hasattr(bottle, key):
                return getattr(bottle, key)
            else:
                logger.warning(f"Unknown sort key for bottles: {key}")
                return ""

        try:
            sorted_items = sorted(
                bottles.items(),
                key=lambda item: (get_sort_value(item[1], sort_key) is None, get_sort_value(item[1], sort_key)),
                reverse=not ascending
            )
            return dict(sorted_items)
        except Exception as e:
            logger.error(f"Error sorting bottles by key '{sort_key}': {e}")
            return bottles
    
    def sort_derivatives(
        self,
        derivatives: Dict[str, PolyLSerineDerivative],
        sort_key: str,
        ascending: bool = True
    ) -> Dict[str, PolyLSerineDerivative]:
        """Sort derivatives by a specific key."""
        def get_sort_value(derivative: PolyLSerineDerivative, key: str) -> Any:
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

    def filter_bottles(
        self,
        bottles: Dict[str, PolyLSerineBottle],
        filter_func: Callable[[PolyLSerineBottle], bool]
    ) -> Dict[str, PolyLSerineBottle]:
        """Filter bottles based on a filter function."""
        try:
            return {k: v for k, v in bottles.items() if filter_func(v)}
        except Exception as e:
            logger.error(f"Error applying filter function to bottles: {e}")
            return bottles

    def filter_derivatives(
        self,
        derivatives: Dict[str, PolyLSerineDerivative],
        filter_func: Callable[[PolyLSerineDerivative], bool]
    ) -> Dict[str, PolyLSerineDerivative]:
        """Filter derivatives based on a filter function."""
        try:
            return {k: v for k, v in derivatives.items() if filter_func(v)}
        except Exception as e:
            logger.error(f"Error applying filter function to derivatives: {e}")
            return derivatives

    def search_bottles(
        self,
        bottles: Dict[str, PolyLSerineBottle],
        search_text: str,
        case_sensitive: bool = False
    ) -> Dict[str, PolyLSerineBottle]:
        """Search bottles for text in various fields."""
        if not search_text:
            return bottles

        result = {}
        search_lower = search_text.lower() if not case_sensitive else search_text

        for bottle_id, bottle in bottles.items():
            try:
                fields_to_check = [
                    bottle_id, bottle.manufacturer, bottle.storage_location, bottle.notes or ""
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
                    result[bottle_id] = bottle

            except Exception as e:
                logger.error(f"Error searching within bottle {bottle_id}: {e}")

        return result

    def search_derivatives(
        self,
        derivatives: Dict[str, PolyLSerineDerivative],
        search_text: str,
        case_sensitive: bool = False
    ) -> Dict[str, PolyLSerineDerivative]:
        """Search derivatives for text in various fields."""
        if not search_text:
            return derivatives

        result = {}
        search_lower = search_text.lower() if not case_sensitive else search_text

        for derivative_id, derivative in derivatives.items():
            try:
                fields_to_check = [
                    derivative_id, derivative.source_bottle_id, derivative.type,
                    derivative.prepared_by, derivative.storage_location, 
                    derivative.storage_container or "", derivative.notes or ""
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
poly_l_serine_controller = PolyLSerineController()