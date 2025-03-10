"""
Data manager for MetaZebrobot.

This module provides the main interface for accessing and manipulating application data.
"""

import logging
from pathlib import Path
from typing import Dict, Any, Optional, List, Union, Tuple

from ..utils.config import config
from .json_storage import CategoryJsonStorage

logger = logging.getLogger(__name__)


class DataManager:
    """
    Manages all data operations for the application.
    
    This class centralizes access to all data storage and retrieval operations,
    providing a clean interface for the rest of the application.
    """
    
    # File name constants
    AGAROSE_BOTTLES_FILE = "agarose_bottles.json"
    AGAROSE_SOLUTIONS_FILE = "agarose_solutions.json"
    FISH_WATER_SOURCES_FILE = "fish_water_sources.json"
    FISH_WATER_DERIVATIVES_FILE = "fish_water_derivatives.json"
    POLY_L_SERINE_BOTTLES_FILE = "poly-l-serine_bottles.json"
    POLY_L_SERINE_DERIVATIVES_FILE = "poly-l-serine_derivatives.json"
    
    def __init__(self):
        """Initialize the data manager with default values."""
        # Initialize with empty paths - will be set properly in initialize()
        self.material_data_dir = None
        self.dish_data_dir = None
        
        # Storage handlers - will be initialized in initialize()
        self.agarose_bottles = None
        self.agarose_solutions = None
        self.fish_water_sources = None
        self.fish_water_derivatives = None
        self.poly_l_serine_bottles = None
        self.poly_l_serine_derivatives = None
        self.dish_storage = None
        
        # In-memory cache of all data
        self.data_cache: Dict[str, Dict[str, Any]] = {
            'agarose_bottles': {},
            'agarose_solutions': {},
            'fish_water_sources': {},
            'fish_water_derivatives': {},
            'poly_l_serine_bottles': {},
            'poly_l_serine_derivatives': {},
            'fish_dishes': {}
        }
        
        # Flag to track initialization state
        self._is_initialized = False
        
    def initialize(self) -> bool:
        """
        Initialize the data manager with configuration settings.
        This should be called after config is loaded.
        
        Returns:
            bool: True if initialization successful
        """
        import logging
        logger = logging.getLogger(__name__)
        
        # Get paths from config
        from ..utils.config import config
        
        self.material_data_dir = config.material_data_dir
        self.dish_data_dir = config.dish_data_dir
        
        # Fall back to local directories if remote ones don't exist
        from pathlib import Path
        
        if not self.material_data_dir:
            logger.warning("No material directory configured, using local directory")
            self.material_data_dir = Path.cwd().parent / "materials"
            
        if not self.dish_data_dir:
            logger.warning("No dish directory configured, using local directory")
            self.dish_data_dir = Path.cwd().parent / "dishes"
        
        # Ensure directories exist
        from ..utils.file_operations import ensure_directory
        ensure_directory(self.material_data_dir)
        ensure_directory(self.dish_data_dir)
        
        # Initialize storage handlers
        from .json_storage import CategoryJsonStorage
        
        self.agarose_bottles = CategoryJsonStorage(
            self.material_data_dir, "agarose_bottles"
        )
        self.agarose_solutions = CategoryJsonStorage(
            self.material_data_dir, "agarose_solutions"
        )
        self.fish_water_sources = CategoryJsonStorage(
            self.material_data_dir, "fish_water_batches"
        )
        self.fish_water_derivatives = CategoryJsonStorage(
            self.material_data_dir, "fish_water_derivatives"
        )
        self.poly_l_serine_bottles = CategoryJsonStorage(
            self.material_data_dir, "poly_l_serine_bottles"
        )
        self.poly_l_serine_derivatives = CategoryJsonStorage(
            self.material_data_dir, "poly_l_serine_derivatives"
        )
        
        # Generic storage for fish dishes (one file per dish)
        self.dish_storage = CategoryJsonStorage(self.dish_data_dir, "fish_dishes")
        
        # Mark as initialized
        self._is_initialized = True
        return True
    
    @property
    def is_initialized(self) -> bool:
        """Check if data manager has been initialized."""
        return self._is_initialized
        
    def load_all_data(self) -> bool:
        """
        Load all data from storage into memory.
        
        Returns:
            bool: True if all data was loaded successfully, False if there were any errors
        """
        success = True
        
        # Load material data
        try:
            self.data_cache['agarose_bottles'] = {
                'agarose_bottles': self.agarose_bottles.load_category(self.AGAROSE_BOTTLES_FILE)
            }
            
            self.data_cache['agarose_solutions'] = {
                'agarose_solutions': self.agarose_solutions.load_category(self.AGAROSE_SOLUTIONS_FILE)
            }
            
            self.data_cache['fish_water_sources'] = {
                'fish_water_batches': self.fish_water_sources.load_category(self.FISH_WATER_SOURCES_FILE)
            }
            
            self.data_cache['fish_water_derivatives'] = {
                'fish_water_derivatives': self.fish_water_derivatives.load_category(self.FISH_WATER_DERIVATIVES_FILE)
            }
            
            self.data_cache['poly_l_serine_bottles'] = {
                'poly_l_serine_bottles': self.poly_l_serine_bottles.load_category(self.POLY_L_SERINE_BOTTLES_FILE)
            }
            
            self.data_cache['poly_l_serine_derivatives'] = {
                'poly_l_serine_derivatives': self.poly_l_serine_derivatives.load_category(self.POLY_L_SERINE_DERIVATIVES_FILE)
            }
            
            # Load fish dishes
            self.data_cache['fish_dishes'] = self.load_fish_dishes()
            
        except Exception as e:
            logger.error(f"Error loading material data: {str(e)}")
            success = False
            
        return success
        
    def save_fish_dish(self, dish_data: Dict[str, Any]) -> bool:
        """
        Save a fish dish to its own file.
        
        Args:
            dish_data: Fish dish data to save
            
        Returns:
            bool: True if saved successfully, False otherwise
        """
        try:
            # Extract dish ID and date of fertilization
            dish_id = dish_data.get('dish_id', '')
            dof = dish_data.get('dof', '')
            logging.info(f"Saving dish {dish_id}, dof {dof}")
            
            if not dish_id or not dof:
                logger.error("Cannot save dish: missing dish_id or dof")
                return False
                
            # Generate filename
            filename = f"{dish_id}_{dof}.json"
            
            # Ensure dish directory exists
            from ..utils.file_operations import ensure_directory
            if not ensure_directory(self.dish_data_dir):
                logger.error(f"Cannot save dish {dish_id}: failed to create directory")
                return False
                
            # Save dish to file
            file_path = self.dish_data_dir / filename
            
            from ..utils.file_operations import save_json_file
            if not save_json_file(file_path, dish_data):
                return False
                
            # Update cache
            if 'fish_dishes' not in self.data_cache:
                self.data_cache['fish_dishes'] = {'fish_dishes': {}}
                
            self.data_cache['fish_dishes']['fish_dishes'][dish_id] = dish_data
            return True
            
        except Exception as e:
            logger.error(f"Error saving fish dish: {str(e)}")
            return False
            
    def load_single_dish(self, dish_id: str) -> Optional[Dict[str, Any]]:
        """
        Load a single dish file.
        
        Args:
            dish_id: The ID of the dish to load
            
        Returns:
            Dict or None: Dish data if found, None otherwise
        """
        try:
            # Find the dish file
            dish_files = list(self.dish_data_dir.glob(f"{dish_id}_*.json"))
            if not dish_files:
                return None
                
            # Load the dish data
            from ..utils.file_operations import load_json_file
            return load_json_file(dish_files[0])
                
        except Exception as e:
            logger.error(f"Error loading dish {dish_id}: {str(e)}")
            return None
            
    def update_dish_quality_check(self, dish_id: str, check_data: Dict[str, Any]) -> bool:
        """
        Update the quality checks for a dish.
        
        Args:
            dish_id: ID of the dish to update
            check_data: Quality check data to add
            
        Returns:
            bool: True if update was successful, False otherwise
        """
        try:
            # Load current dish data
            dish_data = self.load_single_dish(dish_id)
            if not dish_data:
                logger.error(f"Cannot update dish {dish_id}: dish not found")
                return False
                
            # Add new quality check
            check_time = check_data.get('check_time', '')
            if not check_time:
                logger.error("Cannot update dish: missing check_time")
                return False
                
            # Ensure quality_checks dict exists
            if 'quality_checks' not in dish_data:
                dish_data['quality_checks'] = {}
                
            dish_data['quality_checks'][check_time] = check_data
            
            # Save updated dish data
            return self.save_fish_dish(dish_data)
            
        except Exception as e:
            logger.error(f"Error updating dish {dish_id}: {str(e)}")
            return False
            
    def validate_data_structure(self) -> bool:
        """
        Validate the data structure has all required keys.
        
        Returns:
            bool: True if structure is valid
        """
        required_structure = {
            'agarose_bottles': ['agarose_bottles'],
            'agarose_solutions': ['agarose_solutions'],
            'fish_water_sources': ['fish_water_batches'],
            'fish_water_derivatives': ['fish_water_derivatives'],
            'poly_l_serine_bottles': ['poly_l_serine_bottles'],
            'poly_l_serine_derivatives': ['poly_l_serine_derivatives'],
            'fish_dishes': ['fish_dishes']
        }
        
        for key, subkeys in required_structure.items():
            if key not in self.data_cache:
                logger.warning(f"Missing top-level key: {key}")
                self.data_cache[key] = {}
            
            for subkey in subkeys:
                if key in self.data_cache and subkey not in self.data_cache[key]:
                    logger.warning(f"Missing subkey {subkey} in {key}")
                    self.data_cache[key][subkey] = {}
                    
        return True
        
    def get_category_data(self, category: str, subcategory: str = None) -> Dict[str, Any]:
        """
        Get data for a specific category.
        
        Args:
            category: The main category to retrieve
            subcategory: Optional subcategory name
            
        Returns:
            Dict: The requested data
        """
        if category not in self.data_cache:
            logger.warning(f"Requested unknown category: {category}")
            return {}
            
        if subcategory:
            return self.data_cache[category].get(subcategory, {})
        
        return self.data_cache[category]
        
    # Convenience methods for common operations
    
    def get_agarose_bottles(self) -> Dict[str, Any]:
        """Get all agarose bottles."""
        return self.get_category_data('agarose_bottles', 'agarose_bottles')
        
    def get_agarose_solutions(self) -> Dict[str, Any]:
        """Get all agarose solutions."""
        return self.get_category_data('agarose_solutions', 'agarose_solutions')
        
    def get_fish_water_batches(self) -> Dict[str, Any]:
        """Get all fish water batches."""
        return self.get_category_data('fish_water_sources', 'fish_water_batches')
        
    def get_fish_water_derivatives(self) -> Dict[str, Any]:
        """Get all fish water derivatives."""
        return self.get_category_data('fish_water_derivatives', 'fish_water_derivatives')
        
    def get_poly_l_serine_bottles(self) -> Dict[str, Any]:
        """Get all poly-l-serine bottles."""
        return self.get_category_data('poly_l_serine_bottles', 'poly_l_serine_bottles')
        
    def get_poly_l_serine_derivatives(self) -> Dict[str, Any]:
        """Get all poly-l-serine derivatives."""
        return self.get_category_data('poly_l_serine_derivatives', 'poly_l_serine_derivatives')
        
    def get_fish_dishes(self) -> Dict[str, Any]:
        """Get all fish dishes."""
        return self.get_category_data('fish_dishes', 'fish_dishes')
        
    def add_agarose_solution(self, solution_id: str, solution_data: Dict[str, Any]) -> bool:
        """
        Add a new agarose solution.
        
        Args:
            solution_id: ID for the new solution
            solution_data: Data for the solution
            
        Returns:
            bool: True if added successfully, False otherwise
        """
        try:
            self.data_cache['agarose_solutions']['agarose_solutions'][solution_id] = solution_data
            return self.agarose_solutions.save_category(
                self.AGAROSE_SOLUTIONS_FILE, 
                self.data_cache['agarose_solutions']['agarose_solutions']
            )
        except Exception as e:
            logger.error(f"Error adding agarose solution: {str(e)}")
            return False

    def load_fish_dishes(self) -> Dict[str, Any]:
        """
        Load all fish dishes from individual files.
        
        Returns:
            Dict containing all fish dishes
        """
        dishes = {}
        
        try:
            # Ensure dish directory exists
            if not self.dish_data_dir.exists():
                logger.warning(f"Dish directory does not exist: {self.dish_data_dir}")
                return {'fish_dishes': {}}
                
            # Find all dish JSON files
            dish_files = list(self.dish_data_dir.glob("*.json"))
            
            # Load each dish
            for dish_file in dish_files:
                try:
                    with open(dish_file, 'r') as f:
                        import json
                        dish_data = json.load(f)
                        dish_id = dish_data.get('dish_id', '')
                        if dish_id:
                            dishes[dish_id] = dish_data
                except Exception as e:
                    logger.error(f"Error loading dish file {dish_file}: {str(e)}")
                    
            return {'fish_dishes': dishes}
            
        except Exception as e:
            logger.error(f"Error loading fish dishes: {str(e)}")
            return {'fish_dishes': {}}
            
    def save_all_data(self) -> bool:
        """
        Save all data from memory to storage.
        
        Returns:
            bool: True if all data was saved successfully, False if there were any errors
        """
        success = True
        
        # Save material data
        try:
            # Agarose bottles
            if not self.agarose_bottles.save_category(
                self.AGAROSE_BOTTLES_FILE,
                self.data_cache['agarose_bottles'].get('agarose_bottles', {})
            ):
                success = False
                
            # Agarose solutions
            if not self.agarose_solutions.save_category(
                self.AGAROSE_SOLUTIONS_FILE,
                self.data_cache['agarose_solutions'].get('agarose_solutions', {})
            ):
                success = False
                
            # Fish water sources
            if not self.fish_water_sources.save_category(
                self.FISH_WATER_SOURCES_FILE,
                self.data_cache['fish_water_sources'].get('fish_water_batches', {})
            ):
                success = False
                
            # Fish water derivatives
            if not self.fish_water_derivatives.save_category(
                self.FISH_WATER_DERIVATIVES_FILE,
                self.data_cache['fish_water_derivatives'].get('fish_water_derivatives', {})
            ):
                success = False
                
            # Poly-L-Serine bottles
            if not self.poly_l_serine_bottles.save_category(
                self.POLY_L_SERINE_BOTTLES_FILE,
                self.data_cache['poly_l_serine_bottles'].get('poly_l_serine_bottles', {})
            ):
                success = False
                
            # Poly-L-Serine derivatives
            if not self.poly_l_serine_derivatives.save_category(
                self.POLY_L_SERINE_DERIVATIVES_FILE,
                self.data_cache['poly_l_serine_derivatives'].get('poly_l_serine_derivatives', {})
            ):
                success = False
                
        except Exception as e:
            logger.error(f"Error saving material data: {str(e)}")
            success = False
            
        return success


# Create a singleton instance for global access
data_manager = DataManager()