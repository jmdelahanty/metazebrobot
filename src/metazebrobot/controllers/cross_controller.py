"""
Controller for cross-related operations.

This module contains business logic for managing zebrafish crosses.
"""

import logging
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple, Callable

# Import the Cross model and potentially nested models if needed directly
from ..models.cross import Cross, Parent, TransgenicDetails, CrossType
from ..data.data_manager import data_manager
from pydantic import ValidationError

logger = logging.getLogger(__name__)


class CrossController:
    """
    Controller for cross-related operations.

    Provides methods for creating, retrieving, updating, sorting,
    filtering, and searching crosses.
    """

    def __init__(self):
        """Initialize the controller."""
        # Initialization logic can go here if needed in the future
        pass

    def get_all_crosses(self) -> Dict[str, Cross]:
        """
        Get all crosses from the data manager's cache and parse them into Cross objects.

        Returns:
            Dict mapping cross IDs to Cross objects.
        """
        crosses_dict = data_manager.get_crosses() # Gets the cached raw dicts
        result: Dict[str, Cross] = {}

        for cross_id, cross_data in crosses_dict.items():
            try:
                # Parse the raw dictionary into a Cross Pydantic model
                cross_obj = Cross(**cross_data)
                result[cross_id] = cross_obj
            except ValidationError as e:
                logger.error(f"Validation error parsing cross {cross_id}: {e}")
            except Exception as e:
                logger.error(f"Unexpected error parsing cross {cross_id}: {str(e)}", exc_info=True)

        return result

    def get_cross(self, cross_id: str) -> Optional[Cross]:
        """
        Get a specific cross by its ID. Loads from file if not in cache or potentially stale.

        Args:
            cross_id: ID of the cross to retrieve.

        Returns:
            Cross object if found and valid, None otherwise.
        """
        try:
            # Load the specific cross data dictionary from storage
            cross_data = data_manager.load_single_cross(cross_id)
            if not cross_data:
                logger.warning(f"Cross with ID '{cross_id}' not found in storage.")
                return None

            # Parse into a Cross object
            cross_obj = Cross(**cross_data)
            # Optionally update cache here if needed, though load_all_data handles initial load
            # data_manager.data_cache['crosses'][cross_id] = cross_data
            return cross_obj
        except ValidationError as e:
            logger.error(f"Validation error parsing loaded cross {cross_id}: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error loading cross {cross_id}: {str(e)}", exc_info=True)
            return None

    def create_cross(self, cross_data: Dict[str, Any]) -> Tuple[bool, str, Optional[Cross]]:
        """
        Create a new cross, validate it, and save it.

        Args:
            cross_data: A dictionary containing the data for the new cross.
                        Keys should match the fields of the Cross model.

        Returns:
            Tuple containing:
            - Success flag (bool)
            - Cross ID or error message (str)
            - Created Cross object or None if failed
        """
        try:
            # Validate data and create Cross object using Pydantic
            # This automatically runs the model's validators
            new_cross = Cross(**cross_data)
            cross_id = new_cross.cross_id

            # Check if cross already exists (using cached data primarily)
            if cross_id in data_manager.get_crosses():
                 # Optionally double-check by trying to load from file
                 if data_manager.load_single_cross(cross_id):
                     message = f"Cross {cross_id} already exists."
                     logger.warning(message)
                     return False, message, None

            # Convert validated Pydantic model back to dict for saving
            cross_dict_to_save = new_cross.to_dict() # exclude_none=True by default

            # Save the cross using DataManager
            if data_manager.save_cross(cross_dict_to_save):
                logger.info(f"Successfully created and saved cross {cross_id}")
                # Return the validated Pydantic object
                return True, cross_id, new_cross
            else:
                message = f"Failed to save cross {cross_id} using DataManager."
                logger.error(message)
                return False, message, None

        except ValidationError as e:
            # Pydantic validation failed
            logger.error(f"Validation failed for new cross data: {e}")
            # Provide a more user-friendly error message if possible
            error_details = e.errors()
            message = f"Validation Error: {error_details[0]['msg']} (field: {error_details[0]['loc'][0]})" if error_details else str(e)
            return False, message, None
        except Exception as e:
            # Other unexpected errors
            logger.error(f"Unexpected error creating cross: {str(e)}", exc_info=True)
            return False, f"An unexpected error occurred: {str(e)}", None

    def update_cross(self, cross_id: str, update_data: Dict[str, Any]) -> Tuple[bool, str, Optional[Cross]]:
        """
        Update an existing cross. Loads, updates, validates, and saves.

        Args:
            cross_id: The ID of the cross to update.
            update_data: A dictionary containing the fields to update.

        Returns:
            Tuple containing:
            - Success flag (bool)
            - Message (str)
            - Updated Cross object or None if failed
        """
        try:
            # Load existing cross data
            existing_cross_data = data_manager.load_single_cross(cross_id)
            if not existing_cross_data:
                message = f"Cannot update: Cross {cross_id} not found."
                logger.error(message)
                return False, message, None

            # Create a mutable copy and update it
            updated_data = existing_cross_data.copy()
            updated_data.update(update_data)

            # Re-validate the entire updated data by creating a new Cross object
            updated_cross = Cross(**updated_data)

            # Convert validated object back to dict for saving
            cross_dict_to_save = updated_cross.to_dict()

            # Save the updated cross
            if data_manager.save_cross(cross_dict_to_save):
                logger.info(f"Successfully updated and saved cross {cross_id}")
                return True, f"Cross {cross_id} updated successfully.", updated_cross
            else:
                message = f"Failed to save updated cross {cross_id}."
                logger.error(message)
                return False, message, None

        except ValidationError as e:
            logger.error(f"Validation failed updating cross {cross_id}: {e}")
            error_details = e.errors()
            message = f"Validation Error: {error_details[0]['msg']} (field: {error_details[0]['loc'][0]})" if error_details else str(e)
            return False, message, None
        except Exception as e:
            logger.error(f"Unexpected error updating cross {cross_id}: {str(e)}", exc_info=True)
            return False, f"An unexpected error occurred: {str(e)}", None

    def delete_cross(self, cross_id: str) -> Tuple[bool, str]:
        """
        Delete a cross file.

        Args:
            cross_id: The ID of the cross to delete.

        Returns:
            Tuple of (success, message)
        """
        if not data_manager.cross_storage:
             return False, "Cross storage handler not initialized."

        logger.warning(f"Attempting to delete cross {cross_id}. This action is permanent.")
        try:
            filename = f"{cross_id}.json"
            if data_manager.cross_storage.delete(filename):
                # Also remove from cache
                if cross_id in data_manager.data_cache.get('crosses', {}):
                    del data_manager.data_cache['crosses'][cross_id]
                    logger.debug(f"Removed cross {cross_id} from cache.")
                logger.info(f"Successfully deleted cross file: {filename}")
                return True, f"Cross {cross_id} deleted successfully."
            else:
                # Check if file existed in the first place
                if not data_manager.cross_storage.exists(filename):
                     message = f"Cross {cross_id} not found, cannot delete."
                     logger.error(message)
                     return False, message
                else:
                     message = f"Failed to delete cross file {filename}."
                     logger.error(message)
                     return False, message
        except Exception as e:
            logger.error(f"Error deleting cross {cross_id}: {str(e)}", exc_info=True)
            return False, f"An unexpected error occurred during deletion: {str(e)}"

    # --- Utility Methods ---

    def sort_crosses(
        self,
        crosses: Dict[str, Cross],
        sort_key: str,
        ascending: bool = True
    ) -> Dict[str, Cross]:
        """
        Sort crosses by a specific key.

        Args:
            crosses: Dictionary of Cross objects to sort.
            sort_key: Key to sort by (e.g., 'cross_id', 'request_date', 'line_strain').
            ascending: Sort direction.

        Returns:
            Sorted dictionary of crosses.
        """
        def get_sort_value(cross: Cross, key: str) -> Any:
            """Helper to extract sortable value from Cross object."""
            if hasattr(cross, key):
                return getattr(cross, key)
            # Add more complex cases if needed, e.g., sorting by parent identifier
            # elif key == 'parent1_id': return cross.parents[0].identifier if cross.parents else ''
            else:
                logger.warning(f"Attempting to sort crosses by unknown key: {key}. Defaulting to cross_id.")
                return cross.cross_id # Default fallback

        try:
            sorted_items = sorted(
                crosses.items(),
                key=lambda item: get_sort_value(item[1], sort_key),
                reverse=not ascending
            )
            return dict(sorted_items)
        except Exception as e:
             logger.error(f"Error sorting crosses by key '{sort_key}': {e}", exc_info=True)
             return crosses # Return unsorted on error

    def filter_crosses(
        self,
        crosses: Dict[str, Cross],
        filter_func: Callable[[Cross], bool]
    ) -> Dict[str, Cross]:
        """
        Filter crosses based on a filter function.

        Args:
            crosses: Dictionary of Cross objects to filter.
            filter_func: Function that returns True for crosses to keep.

        Returns:
            Filtered dictionary of crosses.
        """
        try:
            return {k: v for k, v in crosses.items() if filter_func(v)}
        except Exception as e:
            logger.error(f"Error applying filter function to crosses: {e}", exc_info=True)
            return crosses # Return unfiltered on error

    def search_crosses(
        self,
        crosses: Dict[str, Cross],
        search_text: str,
        case_sensitive: bool = False
    ) -> Dict[str, Cross]:
        """
        Search crosses for text in various fields.

        Args:
            crosses: Dictionary of Cross objects to search.
            search_text: Text to search for.
            case_sensitive: Whether to perform case-sensitive search.

        Returns:
            Dictionary of crosses matching the search.
        """
        if not search_text:
            return crosses

        result: Dict[str, Cross] = {}
        search_lower = search_text.lower() if not case_sensitive else search_text

        for cross_id, cross in crosses.items():
            try:
                # Fields to search within
                fields_to_check = [
                    cross.cross_id,
                    cross.request_date,
                    cross.responsible_requestor,
                    cross.line_strain,
                    cross.cross_type,
                    cross.notes or "",
                    cross.cross_status or ""
                ]
                # Add parent identifiers
                fields_to_check.extend([p.identifier for p in cross.parents])
                fields_to_check.extend([p.genotype or "" for p in cross.parents])

                # Add transgenic indicator names/expression if present
                if cross.transgenic_details:
                    fields_to_check.extend([ind.name for ind in cross.transgenic_details.indicators])
                    fields_to_check.extend([ind.expected_expression for ind in cross.transgenic_details.indicators])

                # Perform search
                match_found = False
                for field_value in fields_to_check:
                    if field_value: # Ensure field is not None
                        field_str = str(field_value)
                        check_value = field_str if case_sensitive else field_str.lower()
                        if search_lower in check_value:
                            match_found = True
                            break # Found a match in this cross, move to next cross

                if match_found:
                    result[cross_id] = cross

            except Exception as e:
                 logger.error(f"Error searching within cross {cross_id}: {e}", exc_info=True)
                 # Optionally skip this cross or handle differently

        return result


# Create a singleton instance for global access
cross_controller = CrossController()
