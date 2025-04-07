"""
Controller for cross-related operations.

This module contains business logic for managing zebrafish crosses,
including calculating aggregate results based on screening data.
"""

import logging
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple, Callable

from ..controllers.fish_dish_controller import fish_dish_controller
from ..models.cross import Cross, Parent, TransgenicDetails, AggregateResults # Import AggregateResults
from ..models.fish_dish import FishDish, ScreeningStep # Import FishDish and ScreeningStep
from ..data.data_manager import data_manager
from pydantic import ValidationError

logger = logging.getLogger(__name__)


class CrossController:
    """
    Controller for cross-related operations.

    Provides methods for creating, retrieving, updating, sorting,
    filtering, searching crosses, and calculating aggregate results.
    """

    def __init__(self):
        """Initialize the controller."""
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
            cross_dict_to_save = new_cross.model_dump(exclude_none=True, mode='json') # Use mode='json'

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
            # Need deep update for nested fields like aggregate_results
            # Basic update only works for top-level fields
            # Consider using a helper for deep updates or Pydantic's update_forward_refs
            # For simplicity here, we'll assume update_data might contain nested dicts
            # A more robust way is to load into Pydantic obj, update fields, then dump

            # Load into Pydantic model first
            existing_cross_obj = Cross(**existing_cross_data)

            # Update fields - This requires careful handling of nested updates
            # Example: Updating total_positive_final in aggregate_results
            # if 'aggregate_results' in update_data and isinstance(update_data['aggregate_results'], dict):
            #     if existing_cross_obj.aggregate_results:
            #         existing_cross_obj.aggregate_results = existing_cross_obj.aggregate_results.model_copy(
            #             update=update_data['aggregate_results']
            #         )
            #     else:
            #          # Need to create AggregateResults if it doesn't exist
            #          try:
            #              existing_cross_obj.aggregate_results = AggregateResults(**update_data['aggregate_results'])
            #          except ValidationError as agg_val_err:
            #              logger.error(f"Validation error creating AggregateResults during update: {agg_val_err}")
            #              return False, f"Validation Error for aggregate_results: {agg_val_err}", None

            #     del update_data['aggregate_results'] # Remove from top-level update

            # # Update remaining top-level fields
            # existing_cross_obj = existing_cross_obj.model_copy(update=update_data)

            # --- Simpler approach: Re-create from merged dict (less safe for nested) ---
            updated_data_dict = existing_cross_data.copy()
            updated_data_dict.update(update_data) # Note: This is a shallow update
            updated_cross = Cross(**updated_data_dict)
            # --------------------------------------------------------------------


            # Convert validated object back to dict for saving
            cross_dict_to_save = updated_cross.model_dump(exclude_none=True, mode='json')

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
            # Handle sorting by nested fields like parent identifiers if needed
            elif key == 'parent1_id':
                 return cross.parents[0].identifier if cross.parents and len(cross.parents) > 0 else ''
            elif key == 'parent2_id':
                 return cross.parents[1].identifier if cross.parents and len(cross.parents) > 1 else ''
            # Add more complex cases if needed
            else:
                logger.warning(f"Attempting to sort crosses by unknown key: {key}. Defaulting to cross_id.")
                return cross.cross_id # Default fallback

        try:
            # Ensure consistent handling of None values during sorting
            sorted_items = sorted(
                crosses.items(),
                key=lambda item: (get_sort_value(item[1], sort_key) is None, get_sort_value(item[1], sort_key)),
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
                # Add parent identifiers and genotypes
                if cross.parents:
                    for p in cross.parents:
                        fields_to_check.append(p.identifier)
                        if p.genotype: fields_to_check.append(p.genotype)

                # Add transgenic indicator details if present
                if cross.transgenic_details and cross.transgenic_details.indicators:
                    for ind in cross.transgenic_details.indicators:
                        if ind.promoter_driver: fields_to_check.append(ind.promoter_driver)
                        fields_to_check.append(ind.reporter_effector)
                        if ind.color: fields_to_check.append(ind.color)
                        if ind.expected_expression: fields_to_check.append(ind.expected_expression)
                        fields_to_check.append(ind.standard_notation) # Search computed field too

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

    def update_cross_status(self, cross_id: str, new_status: str) -> Tuple[bool, str]:
        """
        Update the status of a specific cross.

        Args:
            cross_id: The ID of the cross to update.
            new_status: The new status value.

        Returns:
            Tuple containing:
            - Success flag (bool)
            - Message (str)
        """
        logger.info(f"Attempting to update status for cross {cross_id} to {new_status}")

        # Validate the new status against the allowed values from the model
        allowed_statuses = list(Cross.model_fields['cross_status'].annotation.__args__)
        if new_status not in allowed_statuses:
            message = f"Invalid status '{new_status}'. Must be one of: {', '.join(allowed_statuses)}"
            logger.error(message)
            return False, message

        # Use update_cross method for consistency and validation
        success, msg, _ = self.update_cross(cross_id, {"cross_status": new_status})

        if success:
             return True, f"Status updated to {new_status}"
        else:
             # msg from update_cross already contains error details
             return False, msg

    def update_aggregate_results(self, cross_id: str) -> Tuple[bool, str]:
        """
        Calculates aggregate results based on screening data for a cross
        and updates the Cross object.

        Specifically calculates:
        - total_initially_produced: Sum of count_screened_this_step from the
          first screening step of all *primary* dishes.
        - total_positive_final: Sum of final_positive_count from *all*
          screened dishes (primary and derived) linked to the cross.
        - yield_percentage: Based on total_positive_final / total_initially_produced.
        - date_aggregated: Current date.

        Args:
            cross_id: The ID of the cross to process.

        Returns:
            Tuple containing:
            - Success flag (bool)
            - Message (str)
        """
        logger.info(f"Calculating and updating aggregate results for cross {cross_id}")

        try:
            # 1. Get the target cross object
            cross = self.get_cross(cross_id)
            if not cross:
                return False, f"Cross {cross_id} not found."

            # 2. Get all fish dishes (including inactive for historical data)
            all_dishes = fish_dish_controller.get_all_dishes(include_inactive=True)

            # 3. Filter dishes belonging to this cross
            relevant_dishes = [
                dish for dish in all_dishes.values() if dish.cross_id == cross_id
            ]
            if not relevant_dishes:
                 logger.warning(f"No dishes found for cross {cross_id}. Cannot calculate aggregates.")
                 # Optionally clear existing aggregates?
                 # Or just return success with message?
                 return True, "No dishes found for cross, aggregates not calculated."


            # --- Calculate total_initially_produced ---
            total_initial_prod = 0
            primary_dishes = [d for d in relevant_dishes if d.dish_population_type == "primary"]
            logger.debug(f"Found {len(primary_dishes)} primary dishes for cross {cross_id}.")

            for dish in primary_dishes:
                if dish.screening_results and dish.screening_results.screenings:
                    # Sort screenings by datetime to ensure we get the first one
                    try:
                         sorted_screenings = sorted(
                             dish.screening_results.screenings,
                             key=lambda s: datetime.strptime(s.screening_datetime, "%Y%m%dT%H:%M:%S")
                         )
                         first_step = sorted_screenings[0]
                         # Safely access the count
                         count_in_step = getattr(first_step, 'count_screened_this_step', 0)
                         if isinstance(count_in_step, int) and count_in_step >= 0:
                              total_initial_prod += count_in_step
                              logger.debug(f"Dish {dish.dish_id}: Added {count_in_step} from first screening step.")
                         else:
                              logger.warning(f"Dish {dish.dish_id}: Invalid count_screened_this_step ({count_in_step}) in first screening step. Skipping.")

                    except (ValueError, TypeError, IndexError) as sort_err:
                         logger.warning(f"Dish {dish.dish_id}: Could not process first screening step for initial count. Error: {sort_err}")
                else:
                     logger.warning(f"Dish {dish.dish_id}: No screening steps found to determine initial produced count.")

            logger.info(f"Calculated total_initially_produced for cross {cross_id}: {total_initial_prod}")

            # --- Calculate total_positive_final ---
            total_positive_fin = 0
            for dish in relevant_dishes: # Iterate through ALL relevant dishes (primary and derived)
                if dish.screening_results and dish.screening_results.final_positive_count is not None:
                    if isinstance(dish.screening_results.final_positive_count, int) and dish.screening_results.final_positive_count >= 0:
                        total_positive_fin += dish.screening_results.final_positive_count
                        logger.debug(f"Dish {dish.dish_id}: Added {dish.screening_results.final_positive_count} to final positive count.")
                    else:
                         logger.warning(f"Dish {dish.dish_id}: Invalid final_positive_count ({dish.screening_results.final_positive_count}). Skipping.")

            logger.info(f"Calculated total_positive_final for cross {cross_id}: {total_positive_fin}")

            # --- Calculate yield_percentage ---
            yield_perc = None
            if total_initial_prod > 0:
                yield_perc = (total_positive_fin / total_initial_prod) * 100.0
                logger.info(f"Calculated yield_percentage for cross {cross_id}: {yield_perc:.2f}%")
            else:
                 logger.warning(f"Cannot calculate yield percentage for cross {cross_id} because total_initially_produced is zero.")

            # --- Prepare AggregateResults update ---
            today_str = datetime.now().strftime("%Y%m%d")
            new_aggregate_data = {
                "total_initially_produced": total_initial_prod,
                "total_positive_final": total_positive_fin,
                "yield_percentage": yield_perc,
                "date_aggregated": today_str
            }

            # --- Update the Cross object's aggregates ---
            # Determine where to store: transgenic_details or top-level aggregate_results
            target_aggregate_obj = None
            if cross.transgenic_details:
                 if cross.transgenic_details.aggregate_results is None:
                      cross.transgenic_details.aggregate_results = AggregateResults(**new_aggregate_data)
                 else:
                      # Update existing object
                      cross.transgenic_details.aggregate_results = cross.transgenic_details.aggregate_results.model_copy(update=new_aggregate_data)
                 target_aggregate_obj = cross.transgenic_details.aggregate_results
                 logger.debug(f"Updated aggregate_results within transgenic_details for cross {cross_id}")
            elif hasattr(cross, 'aggregate_results'): # Check if top-level attribute exists
                 if cross.aggregate_results is None:
                      cross.aggregate_results = AggregateResults(**new_aggregate_data)
                 else:
                      cross.aggregate_results = cross.aggregate_results.model_copy(update=new_aggregate_data)
                 target_aggregate_obj = cross.aggregate_results
                 logger.debug(f"Updated top-level aggregate_results for cross {cross_id}")
            else:
                 logger.error(f"Could not determine where to store AggregateResults for cross {cross_id}. Model structure might be inconsistent.")
                 return False, "Model structure error for storing aggregates."

            # --- Save the updated cross ---
            if data_manager.save_cross(cross.model_dump(exclude_none=True, mode='json')):
                # Update cache manually if needed (save_cross might not update cache)
                if cross_id in data_manager.data_cache.get('crosses', {}):
                     # Update cache with the new aggregate object
                     cached_cross_data = data_manager.data_cache['crosses'][cross_id]
                     if cross.transgenic_details and 'transgenic_details' in cached_cross_data:
                          if not cached_cross_data['transgenic_details']: # Ensure dict exists
                               cached_cross_data['transgenic_details'] = {}
                          cached_cross_data['transgenic_details']['aggregate_results'] = target_aggregate_obj.model_dump()
                     elif 'aggregate_results' in cached_cross_data:
                          cached_cross_data['aggregate_results'] = target_aggregate_obj.model_dump()
                     logger.debug(f"Updated aggregate info in cache for cross {cross_id}")

                logger.info(f"Successfully updated and saved aggregate results for cross {cross_id}")
                return True, f"Aggregates updated: Initial={total_initial_prod}, Final={total_positive_fin}, Yield={yield_perc:.1f}%" if yield_perc is not None else "Yield=N/A"
            else:
                message = f"Failed to save updated aggregate results for cross {cross_id}."
                logger.error(message)
                return False, message

        except Exception as e:
            logger.error(f"Error calculating/updating aggregate results for cross {cross_id}: {str(e)}", exc_info=True)
            return False, f"An unexpected error occurred: {str(e)}"

# Create a singleton instance for global access
cross_controller = CrossController()