"""
Controller for fish dish-related operations.

This module contains business logic for managing fish dishes.
"""

import logging
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple, Union, Callable

from ..models.fish_dish import FishDish, QualityCheckData
from ..data.data_manager import data_manager

logger = logging.getLogger(__name__)


class FishDishController:
    """
    Controller for fish dish-related operations.
    
    This class provides methods for managing fish dishes.
    """
    
    def __init__(self):
        """Initialize the controller."""
        pass
        
    def get_all_dishes(self, include_inactive: bool = True) -> Dict[str, FishDish]:
        """
        Get all fish dishes.
        
        Args:
            include_inactive: Whether to include inactive dishes
            
        Returns:
            Dict mapping dish IDs to FishDish objects
        """
        dishes_dict = data_manager.get_fish_dishes()
        result = {}
        
        for dish_id, dish_data in dishes_dict.items():
            try:
                dish = FishDish(**dish_data)
                
                # Filter inactive dishes if requested
                if not include_inactive and dish.status == "inactive":
                    continue
                    
                result[dish_id] = dish
            except Exception as e:
                logger.error(f"Error parsing dish {dish_id}: {str(e)}")
                
        return result
        
    def get_dish(self, dish_id: str) -> Optional[FishDish]:
        """
        Get a specific fish dish.
        
        Args:
            dish_id: ID of the dish to retrieve
            
        Returns:
            FishDish if found, None otherwise
        """
        dish_data = data_manager.load_single_dish(dish_id)
        
        if not dish_data:
            return None
            
        try:
            return FishDish(**dish_data)
        except Exception as e:
            logger.error(f"Error parsing dish {dish_id}: {str(e)}")
            return None
            
    def create_dish(
        self,
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
    ) -> Tuple[bool, str, Optional[FishDish]]:
        """
        Create a new fish dish.
        
        Args:
            (see FishDish.create_new for parameter descriptions)
            
        Returns:
            Tuple containing:
            - Success flag (bool)
            - Dish ID or error message (str)
            - FishDish object or None if failed
        """
        try:
            # Create the dish object
            dish = FishDish.create_new(
                cross_id=cross_id,
                dish_number=dish_number,
                genotype=genotype,
                responsible=responsible,
                dof=dof,
                sex=sex,
                species=species,
                fish_count=fish_count,
                parents=parents,
                temperature=temperature,
                light_duration=light_duration,
                dawn_dusk=dawn_dusk,
                room=room,
                in_beaker=in_beaker
            )
            
            # Check if dish already exists
            existing_dish = self.get_dish(dish.dish_id)
            if existing_dish:
                return False, f"Dish {dish.dish_id} already exists", None
                
            # Save the dish
            success = data_manager.save_fish_dish(dish.dict(exclude_none=True))
            
            if success:
                return True, dish.dish_id, dish
            else:
                return False, "Failed to save dish", None
                
        except Exception as e:
            logger.error(f"Error creating fish dish: {str(e)}")
            return False, str(e), None
            
    def add_quality_check(
        self,
        dish_id: str,
        check_time: str,
        fed: bool = False,
        feed_type: Optional[str] = None,
        water_changed: bool = False,
        vol_water_changed: Optional[int] = None,
        num_dead: int = 0,
        notes: Optional[str] = None
    ) -> Tuple[bool, str]:
        """
        Add a quality check to a dish.
        
        Args:
            dish_id: ID of the dish
            check_time: Time of the check (YYYYMMDDhh:mm:ss)
            fed: Whether fish were fed
            feed_type: Type of feed
            water_changed: Whether water was changed
            vol_water_changed: Volume of water changed (mL)
            num_dead: Number of dead fish
            notes: Additional notes
            
        Returns:
            Tuple of (success, message)
        """
        try:
            # Get the dish
            dish = self.get_dish(dish_id)
            if not dish:
                return False, f"Dish {dish_id} not found"
                
            # Create quality check data
            check_data = QualityCheckData(
                check_time=check_time,
                fed=fed,
                feed_type=feed_type if fed else None,
                water_changed=water_changed,
                vol_water_changed=vol_water_changed if water_changed else None,
                num_dead=num_dead,
                notes=notes
            )
            
            # Add to the dish
            dish.add_quality_check(check_data)
            
            # Save the dish
            success = data_manager.save_fish_dish(dish.dict(exclude_none=True))
            
            if success:
                return True, "Quality check added successfully"
            else:
                return False, "Failed to save quality check"
                
        except Exception as e:
            logger.error(f"Error adding quality check: {str(e)}")
            return False, str(e)
            
    def update_dish_status(
        self,
        dish_id: str,
        status: str,
        termination_date: Optional[str] = None,
        termination_reason: Optional[str] = None
    ) -> Tuple[bool, str]:
        """
        Update the status of a dish.
        
        Args:
            dish_id: ID of the dish
            status: New status ("active" or "inactive")
            termination_date: Date of termination (YYYYMMDD)
            termination_reason: Reason for termination
            
        Returns:
            Tuple of (success, message)
        """
        try:
            # Get the dish
            dish = self.get_dish(dish_id)
            if not dish:
                return False, f"Dish {dish_id} not found"
                
            # Update status
            dish.status = status
            
            # Update termination info if status is inactive
            if status == "inactive":
                dish.termination_date = termination_date or datetime.now().strftime("%Y%m%d")
                dish.termination_reason = termination_reason
            else:
                dish.termination_date = None
                dish.termination_reason = None
                
            # Save the dish
            success = data_manager.save_fish_dish(dish.dict(exclude_none=True))
            
            if success:
                return True, "Dish status updated successfully"
            else:
                return False, "Failed to update dish status"
                
        except Exception as e:
            logger.error(f"Error updating dish status: {str(e)}")
            return False, str(e)
            
    def sort_dishes(
        self, 
        dishes: Dict[str, FishDish], 
        sort_key: str, 
        ascending: bool = True
    ) -> Dict[str, FishDish]:
        """
        Sort dishes by a specific key.
        
        Args:
            dishes: Dictionary of dishes to sort
            sort_key: Key to sort by
            ascending: Sort direction
            
        Returns:
            Sorted dictionary of dishes
        """
        def get_sort_value(dish: FishDish, key: str) -> Any:
            """Extract a value for sorting based on the key."""
            if key == "dish_id":
                return dish.dish_id
            elif key == "date_created":
                return dish.date_created
            elif key == "genotype":
                return dish.genotype
            elif key == "responsible":
                return dish.responsible
            elif key == "status":
                return dish.status
            elif key == "room":
                return dish.enclosure.room
            elif key == "fish_count":
                return dish.fish_count
            elif key == "dof":
                return dish.dof
            else:
                # Default to dish_id
                return dish.dish_id
                
        # Sort the dishes
        sorted_items = sorted(
            dishes.items(),
            key=lambda x: get_sort_value(x[1], sort_key),
            reverse=not ascending
        )
        
        # Return as dictionary
        return {k: v for k, v in sorted_items}
            
    def filter_dishes(
        self, 
        dishes: Dict[str, FishDish], 
        filter_func: Callable[[FishDish], bool]
    ) -> Dict[str, FishDish]:
        """
        Filter dishes based on a filter function.
        
        Args:
            dishes: Dictionary of dishes to filter
            filter_func: Function that returns True for dishes to keep
            
        Returns:
            Filtered dictionary of dishes
        """
        return {k: v for k, v in dishes.items() if filter_func(v)}
        
    def search_dishes(
        self, 
        dishes: Dict[str, FishDish], 
        search_text: str, 
        case_sensitive: bool = False
    ) -> Dict[str, FishDish]:
        """
        Search dishes for text in various fields.
        
        Args:
            dishes: Dictionary of dishes to search
            search_text: Text to search for
            case_sensitive: Whether to perform case-sensitive search
            
        Returns:
            Dictionary of dishes matching the search
        """
        if not search_text:
            return dishes
            
        result = {}
        
        # Convert search text to lowercase if not case sensitive
        if not case_sensitive:
            search_text = search_text.lower()
            
        for dish_id, dish in dishes.items():
            # Fields to search in
            searchable_fields = [
                dish_id,
                dish.genotype,
                dish.add_quality_checkresponsible,
                dish.species,
                dish.cross_id,
                dish.enclosure.room,
                str(dish.fish_count)
            ]
            
            # Add parents to searchable fields
            for parent in dish.breeding.parents:
                searchable_fields.append(parent)
                
            # Add notes from quality checks
            for check_data in dish.quality_checks.values():
                if isinstance(check_data, dict) and 'notes' in check_data:
                    searchable_fields.append(str(check_data['notes']))
                    
            # Convert fields to lowercase if not case sensitive
            if not case_sensitive:
                searchable_fields = [field.lower() for field in searchable_fields if field]
                
            # Check if any field contains the search text
            for field in searchable_fields:
                if search_text in field:
                    result[dish_id] = dish
                    break
                    
        return result


# Create a singleton instance for global access
fish_dish_controller = FishDishController()