import logging
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple, Union, Callable

# Import the updated models
from ..models.fish_dish import FishDish, QualityCheckData, ScreeningStep, ScreeningResults, DishPopulationType
# Import AggregateResults for type hinting if needed later
from ..models.cross import AggregateResults
from ..data.data_manager import data_manager
from pydantic import ValidationError

logger = logging.getLogger(__name__)


class FishDishController:
    """
    Controller for fish dish-related operations.

    This class provides methods for managing fish dishes, including screening results
    and creation of derived dishes from splits.
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
            # Catch Pydantic validation errors specifically during loading
            except ValidationError as e:
                 logger.error(f"Validation error parsing dish {dish_id} from storage: {e}")
            except Exception as e:
                logger.error(f"Unexpected error parsing dish {dish_id}: {str(e)}", exc_info=True)

        return result

    def get_dish(self, dish_id: str) -> Optional[FishDish]:
        """
        Get a specific fish dish by loading its file.

        Args:
            dish_id: ID of the dish to retrieve

        Returns:
            FishDish object if found and valid, None otherwise.
        """
        # Always load fresh data from storage for getting a single dish
        dish_data = data_manager.load_single_dish(dish_id)

        if not dish_data:
            logger.warning(f"Dish with ID '{dish_id}' not found in storage.")
            return None

        try:
            dish_obj = FishDish(**dish_data)
             # Optional: Update cache if necessary, though maybe not needed for single gets
            # data_manager.data_cache['fish_dishes'][dish_id] = dish_data
            return dish_obj
        except ValidationError as e:
            logger.error(f"Validation error parsing loaded dish {dish_id}: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error loading/parsing dish {dish_id}: {str(e)}", exc_info=True)
            return None

    def create_dish(
        self,
        cross_id: str,
        dish_number: int,
        genotype: str,
        responsible: str,
        dof: str, # Made DOF mandatory for primary dish creation
        fish_count: int = 1, # Initial estimate
        source_group_id: Optional[str] = None,
        sex: str = "unknown",
        species: str = "Danio rerio",
        parents: Optional[List[str]] = None,
        temperature: float = 28.5,
        light_duration: str = "14:10",
        dawn_dusk: str = "8:00",
        room: str = "2E.282",
        in_beaker: bool = False,
        vol_water_total: Optional[int] = None,
        notes: Optional[str] = None
        # Lineage fields default to primary here
    ) -> Tuple[bool, str, Optional[FishDish]]:
        """
        Create a new PRIMARY fish dish. Use create_derived_dish for splits.
        """
        try:
            # Use the updated classmethod, explicitly setting type to primary
            dish = FishDish.create_new(
                cross_id=cross_id,
                dish_number=dish_number,
                genotype=genotype,
                responsible=responsible,
                source_group_id=source_group_id,
                dof=dof, # Pass validated DOF
                sex=sex,
                species=species,
                fish_count=fish_count, # Initial estimate
                parents=parents,
                temperature=temperature,
                light_duration=light_duration,
                dawn_dusk=dawn_dusk,
                room=room,
                in_beaker=in_beaker,
                vol_water_total=vol_water_total,
                notes=notes,
                parent_dish_id=None, # Explicitly None for primary
                dish_population_type="primary" # Explicitly primary
            )

            # Check if dish already exists (using load_single_dish is more robust)
            if data_manager.load_single_dish(dish.dish_id):
                message = f"Dish {dish.dish_id} already exists in storage."
                logger.warning(message)
                return False, message, None

            # Save the dish using the updated model's model_dump method
            if data_manager.save_fish_dish(dish.model_dump(mode='json', exclude_none=True)):
                logger.info(f"Successfully created and saved dish {dish.dish_id}")
                # Add to cache after successful save
                data_manager.data_cache['fish_dishes'][dish.dish_id] = dish.model_dump(mode='json', exclude_none=True)
                return True, dish.dish_id, dish
            else:
                message = f"Failed to save dish {dish.dish_id} using DataManager."
                logger.error(message)
                return False, message, None

        except ValidationError as e:
             # Pydantic validation failed during FishDish.create_new()
            logger.error(f"Validation failed for new dish data: {e}")
            error_details = e.errors()
            message = f"Validation Error: {error_details[0]['msg']} (field: {error_details[0]['loc'][0]})" if error_details else str(e)
            return False, message, None
        except ValueError as e: # Catch specific ValueErrors from create_new (e.g., invalid DOF)
             logger.error(f"Value error creating dish: {e}")
             return False, str(e), None
        except Exception as e:
            # Other unexpected errors
            logger.error(f"Unexpected error creating dish: {str(e)}", exc_info=True)
            return False, f"An unexpected error occurred: {str(e)}", None

    def create_derived_dish(
        self,
        parent_dish_id: str,
        population_type: DishPopulationType, # e.g., "negative_screened"
        originating_screening_step: ScreeningStep # Pass the step object
    ) -> Tuple[bool, str, Optional[FishDish]]:
        """
        Creates a new dish derived from a screening step of a parent dish.

        Args:
            parent_dish_id: The ID of the dish this new one is split from.
            population_type: The type of the new dish population (e.g., "negative_screened").
            originating_screening_step: The ScreeningStep object from the parent dish
                                         that triggered this split.

        Returns:
            Tuple containing:
            - Success flag (bool)
            - New Dish ID or error message (str)
            - Created FishDish object or None if failed
        """
        logger.info(f"Attempting to create derived dish from parent {parent_dish_id} (type: {population_type})")

        try:
            # 1. Get Parent Dish Data
            parent_dish = self.get_dish(parent_dish_id)
            if not parent_dish:
                return False, f"Parent dish {parent_dish_id} not found.", None

            # 2. Validate Screening Step Data & Calculate Count
            if not hasattr(originating_screening_step, 'count_screened_this_step') or \
               not hasattr(originating_screening_step, 'number_positive'):
                msg = "Originating screening step data is missing required count fields."
                logger.error(msg)
                return False, msg, None

            count_screened = originating_screening_step.count_screened_this_step
            num_positive = originating_screening_step.number_positive

            if count_screened < num_positive:
                msg = f"Error: Count screened ({count_screened}) is less than number positive ({num_positive}) for parent {parent_dish_id}, step {originating_screening_step.screening_datetime}."
                logger.error(msg)
                return False, msg, None

            new_dish_count = 0
            id_suffix_base = ""
            if population_type == "negative_screened":
                new_dish_count = count_screened - num_positive
                id_suffix_base = "_neg"
            elif population_type == "positive_screened": # If splitting positives
                new_dish_count = num_positive
                id_suffix_base = "_pos"
            else:
                msg = f"Unsupported population_type '{population_type}' for splitting."
                logger.error(msg)
                return False, msg, None

            # Optional: Check if new_fish_count is zero
            if new_dish_count <= 0:
                 msg = f"No fish calculated for new {population_type} dish (Screened: {count_screened}, Positive: {num_positive}). Dish not created."
                 logger.warning(msg)
                 return True, msg, None # Operation valid, but no dish needed


            # 3. Generate New Dish ID (Handles potential collisions)
            i = 1
            new_dish_id = f"{parent_dish_id}{id_suffix_base}{i}"
            while data_manager.load_single_dish(new_dish_id): # Check if ID exists
                i += 1
                new_dish_id = f"{parent_dish_id}{id_suffix_base}{i}"
                # Add a safety break for excessive loops if necessary
                if i > 99: # Example limit
                    msg = f"Could not generate unique derived dish ID for parent {parent_dish_id} after many attempts."
                    logger.error(msg)
                    return False, msg, None
            logger.debug(f"Generated new derived dish ID: {new_dish_id}")

            # 4. Create New Dish Object using the model's classmethod
            new_dish = FishDish.create_new(
                dish_id=new_dish_id, # Provide the generated ID
                cross_id=parent_dish.cross_id,
                genotype=parent_dish.genotype,
                responsible=parent_dish.responsible,
                dof=parent_dish.dof,
                fish_count=new_dish_count, # Use calculated count
                parent_dish_id=parent_dish_id, # Set parent link
                dish_population_type=population_type, # Set population type
                # Inherit other relevant fields
                species=parent_dish.species,
                sex=parent_dish.sex,
                parents=parent_dish.breeding.parents,
                temperature=parent_dish.enclosure.temperature,
                light_duration=parent_dish.enclosure.light_cycle.light_duration,
                dawn_dusk=parent_dish.enclosure.light_cycle.dawn_dusk,
                room=parent_dish.enclosure.room,
                in_beaker=parent_dish.enclosure.in_beaker,
                vol_water_total=parent_dish.enclosure.vol_water_total, # Defaulting to parent's volume
                notes=f"Derived ({population_type}) from {parent_dish_id} on {datetime.now().strftime('%Y%m%d')}.",
                dish_number=None # Derived dishes don't use dish_number
            )

            # 5. Save the new dish
            if data_manager.save_fish_dish(new_dish.model_dump(mode='json', exclude_none=True)):
                logger.info(f"Successfully created and saved derived dish {new_dish_id}")
                # Add to cache
                data_manager.data_cache['fish_dishes'][new_dish_id] = new_dish.model_dump(mode='json', exclude_none=True)
                return True, new_dish_id, new_dish
            else:
                message = f"Failed to save derived dish {new_dish_id} using DataManager."
                logger.error(message)
                return False, message, None

        except ValidationError as e:
            logger.error(f"Validation failed creating derived dish from {parent_dish_id}: {e}")
            error_details = e.errors()
            message = f"Validation Error: {error_details[0]['msg']} (field: {error_details[0]['loc'][0]})" if error_details else str(e)
            return False, message, None
        except Exception as e:
            logger.error(f"Unexpected error creating derived dish from {parent_dish_id}: {str(e)}", exc_info=True)
            return False, f"An unexpected error occurred: {str(e)}", None

    def add_quality_check(
        self,
        dish_id: str,
        check_time: str,  # Format should be YYYYMMDDTHH:MM:SS
        fed: bool = False,
        feed_type: Optional[str] = None,
        water_changed: bool = False,
        vol_water_changed: Optional[int] = None,
        num_dead: int = 0,
        notes: Optional[str] = None
    ) -> Tuple[bool, str]:
        """
        Add a quality check to a dish. Handles validation and saving.
        """
        try:
            # Get the dish - use get_dish to ensure we load latest data
            dish = self.get_dish(dish_id)
            if not dish:
                return False, f"Dish {dish_id} not found"

            # Create quality check data object (this validates the input data)
            check_data = QualityCheckData(
                check_time=check_time,
                fed=fed,
                feed_type=feed_type if fed else None,
                water_changed=water_changed,
                vol_water_changed=vol_water_changed if water_changed else None,
                num_dead=num_dead,
                notes=notes
            )

            # Add to the dish using the model's method
            dish.add_quality_check(check_data)

            # Save the entire updated dish object
            if data_manager.save_fish_dish(dish.model_dump(mode='json', exclude_none=True)):
                 # Update cache
                 data_manager.data_cache['fish_dishes'][dish_id] = dish.model_dump(mode='json', exclude_none=True)
                 logger.info(f"Successfully added quality check to dish {dish_id} at {check_time}")
                 return True, "Quality check added successfully"
            else:
                 logger.error(f"Failed to save dish {dish_id} after adding quality check.")
                 return False, "Failed to save quality check"

        except ValidationError as e:
             logger.error(f"Validation failed for quality check data for dish {dish_id}: {e}")
             error_details = e.errors()
             message = f"Validation Error: {error_details[0]['msg']} (field: {error_details[0]['loc'][0]})" if error_details else str(e)
             return False, message
        except Exception as e:
            logger.error(f"Error adding quality check to dish {dish_id}: {str(e)}", exc_info=True)
            return False, f"An unexpected error occurred: {str(e)}"

    def add_screening_step(self, dish_id: str, step_data: Dict[str, Any]) -> Tuple[bool, str, Optional[ScreeningStep]]:
        """
        Adds a screening step to the specified dish. Now includes count_screened_this_step.

        Args:
            dish_id: The ID of the dish to update.
            step_data: A dictionary containing the data for the screening step,
                       matching the ScreeningStep model fields (including count_screened_this_step).

        Returns:
            Tuple of (success, message, added_step_object or None)
        """
        try:
            dish = self.get_dish(dish_id)
            if not dish:
                return False, f"Dish {dish_id} not found", None

            # Validate the input data against the ScreeningStep model
            validated_step = ScreeningStep(**step_data)

            # Add the validated step using the model's method
            dish.add_screening_step(validated_step)

            # Save the updated dish
            if data_manager.save_fish_dish(dish.model_dump(mode='json', exclude_none=True)):
                # Update cache
                data_manager.data_cache['fish_dishes'][dish_id] = dish.model_dump(mode='json', exclude_none=True)
                logger.info(f"Successfully added screening step to dish {dish_id} for date {validated_step.screening_datetime}")
                return True, "Screening step added successfully.", validated_step # Return the step object
            else:
                logger.error(f"Failed to save dish {dish_id} after adding screening step.")
                return False, "Failed to save dish after adding screening step.", None

        except ValidationError as e:
            logger.error(f"Validation failed for screening step data for dish {dish_id}: {e}")
            error_details = e.errors()
            message = f"Validation Error: {error_details[0]['msg']} (field: {error_details[0]['loc'][0]})" if error_details else str(e)
            return False, message, None
        except Exception as e:
            logger.error(f"Error adding screening step to dish {dish_id}: {str(e)}", exc_info=True)
            return False, f"An unexpected error occurred: {str(e)}", None

    def finalize_screening(self, dish_id: str, final_count: int, date_finalized: str) -> Tuple[bool, str]:
        """
        Updates the screening results with the final positive count and date.

        Args:
            dish_id: The ID of the dish to update.
            final_count: The final number of fish passing screening.
            date_finalized: The date the final count was determined (YYYYMMDD).

        Returns:
            Tuple of (success, message)
        """
        try:
            dish = self.get_dish(dish_id)
            if not dish:
                return False, f"Dish {dish_id} not found"

            # Call the model's method to update final screening info
            # The model method handles validation of date and count
            dish.finalize_screening(final_count=final_count, date_finalized=date_finalized)

            # Save the updated dish
            if data_manager.save_fish_dish(dish.model_dump(mode='json', exclude_none=True)):
                 # Update cache
                 data_manager.data_cache['fish_dishes'][dish_id] = dish.model_dump(mode='json', exclude_none=True)
                 logger.info(f"Successfully finalized screening for dish {dish_id} on {date_finalized} with count {final_count}")
                 return True, "Screening finalized successfully."
            else:
                 logger.error(f"Failed to save dish {dish_id} after finalizing screening.")
                 return False, "Failed to save dish after finalizing screening."

        except ValueError as e: # Catch potential validation errors from the model method
             logger.error(f"Input validation error finalizing screening for dish {dish_id}: {e}")
             return False, str(e)
        except Exception as e:
            logger.error(f"Error finalizing screening for dish {dish_id}: {str(e)}", exc_info=True)
            return False, f"An unexpected error occurred: {str(e)}"

    def update_dish_status(
        self,
        dish_id: str,
        status: str, # Should be Literal["active", "inactive"]
        termination_date: Optional[str] = None, # Format YYYYMMDD
        termination_reason: Optional[str] = None
    ) -> Tuple[bool, str]:
        """
        Update the status of a dish.
        """
        try:
            dish = self.get_dish(dish_id)
            if not dish:
                return False, f"Dish {dish_id} not found"

            # Basic validation for status literal
            if status not in ["active", "inactive"]:
                 return False, f"Invalid status '{status}'. Must be 'active' or 'inactive'."

            dish.status = status

            if status == "inactive":
                # Validate termination_date format if provided
                if termination_date:
                    try:
                        datetime.strptime(termination_date, "%Y%m%d")
                        dish.termination_date = termination_date
                    except ValueError:
                         msg = f"Invalid termination date format: {termination_date}. Expected YYYYMMDD."
                         logger.error(msg)
                         # Option: Use today's date as fallback? Or return error?
                         # dish.termination_date = datetime.now().strftime("%Y%m%d")
                         return False, msg
                else:
                    # Default to today if terminating and no date provided
                    dish.termination_date = datetime.now().strftime("%Y%m%d")

                dish.termination_reason = termination_reason
            else:
                # Clear termination fields if setting back to active
                dish.termination_date = None
                dish.termination_reason = None

            # Save the dish
            if data_manager.save_fish_dish(dish.model_dump(mode='json', exclude_none=True)):
                # Update cache
                data_manager.data_cache['fish_dishes'][dish_id] = dish.model_dump(mode='json', exclude_none=True)
                logger.info(f"Successfully updated status for dish {dish_id} to {status}")
                return True, "Dish status updated successfully"
            else:
                logger.error(f"Failed to save dish {dish_id} after updating status.")
                return False, "Failed to update dish status"

        except Exception as e:
            logger.error(f"Error updating dish status for {dish_id}: {str(e)}", exc_info=True)
            return False, f"An unexpected error occurred: {str(e)}"


    def sort_dishes(
        self,
        dishes: Dict[str, FishDish],
        sort_key: str,
        ascending: bool = True
    ) -> Dict[str, FishDish]:
        """Sort dishes by a specific key."""
        def get_sort_value(dish: FishDish, key: str) -> Any:
            """Helper to extract sortable value from FishDish object."""
            # Handle nested attributes for sorting
            if '.' in key:
                parts = key.split('.', 1)
                obj = getattr(dish, parts[0], None)
                # Handle potential None values in nested objects gracefully
                if obj is None: return None
                # Use getattr again for the second part
                return getattr(obj, parts[1], None)

            # Handle direct attributes
            elif hasattr(dish, key):
                return getattr(dish, key)
            else:
                logger.warning(f"Attempting to sort dishes by unknown key: {key}. Defaulting to dish_id.")
                return dish.dish_id # Default fallback

        try:
            # Ensure consistent handling of None values during sorting (e.g., put them first or last)
            sorted_items = sorted(
                dishes.items(),
                # Put None values first when ascending, last when descending
                key=lambda item: (get_sort_value(item[1], sort_key) is None, get_sort_value(item[1], sort_key)),
                reverse=not ascending
            )
            return dict(sorted_items)
        except Exception as e:
             logger.error(f"Error sorting dishes by key '{sort_key}': {e}", exc_info=True)
             return dishes # Return unsorted on error


    def filter_dishes(
        self,
        dishes: Dict[str, FishDish],
        filter_func: Callable[[FishDish], bool]
    ) -> Dict[str, FishDish]:
        """Filter dishes based on a filter function."""
        try:
            return {k: v for k, v in dishes.items() if filter_func(v)}
        except Exception as e:
            logger.error(f"Error applying filter function to dishes: {e}", exc_info=True)
            return dishes # Return unfiltered on error


    def search_dishes(
        self,
        dishes: Dict[str, FishDish],
        search_text: str,
        case_sensitive: bool = False
    ) -> Dict[str, FishDish]:
        """Search dishes for text in various fields."""
        if not search_text:
            return dishes

        result: Dict[str, FishDish] = {}
        search_lower = search_text.lower() if not case_sensitive else search_text

        for dish_id, dish in dishes.items():
            try:
                # Fields to search within
                fields_to_check = [
                    dish.dish_id,
                    dish.cross_id,
                    dish.genotype,
                    dish.responsible,
                    dish.species,
                    dish.status,
                    dish.notes, # Include the notes field
                    dish.termination_reason,
                    str(dish.fish_count), # Initial fish count
                    dish.dish_population_type, # Added population type
                    dish.parent_dish_id, # Added parent dish ID
                    # Nested fields
                    dish.enclosure.room,
                ]
                # Add parents
                fields_to_check.extend(dish.breeding.parents)

                # Add notes from quality checks
                if dish.quality_checks:
                    for qc_data_dict in dish.quality_checks.values():
                         # Check if it's a dict and has notes
                         if isinstance(qc_data_dict, dict) and qc_data_dict.get("notes"):
                             fields_to_check.append(qc_data_dict["notes"])

                # Add notes from screening steps
                if dish.screening_results and dish.screening_results.screenings:
                    for step in dish.screening_results.screenings:
                        if step.notes:
                            fields_to_check.append(step.notes)
                        # Also search indicator and criteria
                        fields_to_check.append(step.indicator_screened)
                        fields_to_check.append(step.criteria)


                # Perform search
                match_found = False
                for field_value in fields_to_check:
                    if field_value: # Ensure field is not None or empty string
                        field_str = str(field_value)
                        check_value = field_str if case_sensitive else field_str.lower()
                        if search_lower in check_value:
                            match_found = True
                            break # Found a match in this dish, move to next dish

                if match_found:
                    result[dish_id] = dish

            except Exception as e:
                 logger.error(f"Error searching within dish {dish_id}: {e}", exc_info=True)

        return result


# Create a singleton instance for global access
fish_dish_controller = FishDishController()