"""
Controller for agarose-related operations.

This module contains business logic for managing agarose bottles and solutions.
"""

import logging
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple

from ..models.agarose import AgaroseBottle, AgaroseSolution
from ..data.data_manager import data_manager

logger = logging.getLogger(__name__)


class AgaroseController:
    """
    Controller for agarose-related operations.
    
    This class provides methods for managing agarose bottles and solutions.
    """
    
    def __init__(self):
        """Initialize the controller."""
        pass
        
    def get_all_bottles(self) -> Dict[str, AgaroseBottle]:
        """
        Get all agarose bottles.
        
        Returns:
            Dict mapping bottle IDs to AgaroseBottle objects
        """
        bottles_dict = data_manager.get_agarose_bottles()
        result = {}
        
        for bottle_id, bottle_data in bottles_dict.items():
            try:
                result[bottle_id] = AgaroseBottle(**bottle_data)
            except Exception as e:
                logger.error(f"Error parsing bottle {bottle_id}: {str(e)}")
                
        return result
        
    def get_all_solutions(self) -> Dict[str, AgaroseSolution]:
        """
        Get all agarose solutions.
        
        Returns:
            Dict mapping solution IDs to AgaroseSolution objects
        """
        solutions_dict = data_manager.get_agarose_solutions()
        result = {}
        
        for solution_id, solution_data in solutions_dict.items():
            try:
                result[solution_id] = AgaroseSolution(**solution_data)
            except Exception as e:
                logger.error(f"Error parsing solution {solution_id}: {str(e)}")
                
        return result
        
    def get_bottle(self, bottle_id: str) -> Optional[AgaroseBottle]:
        """
        Get a specific agarose bottle.
        
        Args:
            bottle_id: ID of the bottle to retrieve
            
        Returns:
            AgaroseBottle if found, None otherwise
        """
        bottles = data_manager.get_agarose_bottles()
        bottle_data = bottles.get(bottle_id)
        
        if not bottle_data:
            return None
            
        try:
            return AgaroseBottle(**bottle_data)
        except Exception as e:
            logger.error(f"Error parsing bottle {bottle_id}: {str(e)}")
            return None
            
    def get_solution(self, solution_id: str) -> Optional[AgaroseSolution]:
        """
        Get a specific agarose solution.
        
        Args:
            solution_id: ID of the solution to retrieve
            
        Returns:
            AgaroseSolution if found, None otherwise
        """
        solutions = data_manager.get_agarose_solutions()
        solution_data = solutions.get(solution_id)
        
        if not solution_data:
            return None
            
        try:
            return AgaroseSolution(**solution_data)
        except Exception as e:
            logger.error(f"Error parsing solution {solution_id}: {str(e)}")
            return None
            
    def create_solution(
        self,
        concentration: float,
        agarose_bottle_id: str,
        fish_water_batch_id: str,
        volume_prepared_mL: float,
        prepared_by: str = "Lab Staff"
    ) -> Tuple[bool, str, Optional[AgaroseSolution]]:
        """
        Create a new agarose solution.
        
        Args:
            concentration: Concentration value (0-1)
            agarose_bottle_id: ID of the source bottle
            fish_water_batch_id: ID of the fish water batch used
            volume_prepared_mL: Volume in milliliters
            prepared_by: Name of the preparer
            
        Returns:
            Tuple containing:
            - Success flag (bool)
            - Solution ID (str)
            - AgaroseSolution object or None if failed
        """
        try:
            # Validate inputs
            if concentration <= 0 or concentration > 1:
                return False, "", None
                
            if not agarose_bottle_id:
                return False, "", None
                
            if not fish_water_batch_id:
                return False, "", None
                
            if volume_prepared_mL <= 0:
                return False, "", None
            
            # Create a new solution
            today = datetime.now().strftime("%Y%m%d")
            solution_id = f"AGSOL_{today}"
            
            # Check if solution ID already exists
            solutions = data_manager.get_agarose_solutions()
            if solution_id in solutions:
                # Find next available ID
                i = 1
                while f"{solution_id}_{i}" in solutions:
                    i += 1
                solution_id = f"{solution_id}_{i}"
                
            # Create solution object
            solution = AgaroseSolution.create_new(
                concentration=concentration,
                agarose_bottle_id=agarose_bottle_id,
                fish_water_batch_id=fish_water_batch_id,
                volume_prepared_mL=volume_prepared_mL,
                prepared_by=prepared_by
            )
            
            # Add to data manager
            success = data_manager.add_agarose_solution(solution_id, solution.dict())
            
            if success:
                return True, solution_id, solution
            else:
                return False, "", None
                
        except Exception as e:
            logger.error(f"Error creating agarose solution: {str(e)}")
            return False, "", None


# Create a singleton instance for global access
agarose_controller = AgaroseController()