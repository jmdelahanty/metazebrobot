import logging
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple, Union, Callable

from pydantic import BaseModel, Field, field_validator

# Import the updated models
from ..models.fish_dish import (
    FishDish,
    QualityCheckData,
    ScreeningStep,
    ScreeningStepAllocation,
    ScreeningResults,
    DishPopulationType,
    normalize_termination_reason,
    termination_reason_options_text,
)
from ..data.data_manager import data_manager
from pydantic import ValidationError


class AggregateResults(BaseModel):
    """Aggregated screening results computed on demand from dish data."""
    total_initially_produced: Optional[int] = Field(default=None)
    total_positive_final: Optional[int] = Field(default=None)
    yield_percentage: Optional[float] = Field(default=None)
    date_aggregated: Optional[str] = Field(default=None)

    @field_validator('date_aggregated', mode='before')
    @classmethod
    def validate_date_format(cls, v: Optional[str]) -> Optional[str]:
        if v:
            try:
                datetime.strptime(v, "%Y%m%d")
                return v
            except ValueError:
                raise ValueError(f"Invalid date format: {v}. Expected format: YYYYMMDD")
        return v

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
        cross_setup_date: Optional[str] = None,
        dof_source: Optional[str] = None,
        sex: str = "unknown",
        species: str = "Danio rerio",
        parents: Optional[List[str]] = None,
        temperature: float = 28.5,
        light_duration: str = "14:10",
        dawn_dusk: str = "8:00",
        room: str = "2E.282",
        container_type: str = "petri_dish",
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
                cross_setup_date=cross_setup_date,
                dof_source=dof_source,
                dof=dof, # Pass validated DOF
                sex=sex,
                species=species,
                fish_count=fish_count, # Initial estimate
                parents=parents,
                temperature=temperature,
                light_duration=light_duration,
                dawn_dusk=dawn_dusk,
                room=room,
                container_type=container_type,
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
        population_type: DishPopulationType,
        fish_count: int,
        container_type: Optional[str] = None,
        notes: Optional[str] = None,
        source_screening_datetime: Optional[str] = None,
        source_screening_bucket: Optional[str] = None,
    ) -> Tuple[bool, str, Optional[FishDish]]:
        """
        Creates a new dish derived from a parent dish.

        Args:
            parent_dish_id: The ID of the dish this new one is split from.
            population_type: The type of the new dish population.
            fish_count: Number of fish going into the new dish.
            container_type: Container for the new dish (defaults to parent's).
            notes: Optional notes for the new dish.

        Returns:
            Tuple of (success, new_dish_id_or_message, FishDish_or_None).
        """
        logger.info(f"Attempting to create derived dish from parent {parent_dish_id} "
                     f"(type: {population_type}, count: {fish_count})")

        try:
            parent_dish = self.get_dish(parent_dish_id)
            if not parent_dish:
                return False, f"Parent dish {parent_dish_id} not found.", None

            if fish_count <= 0:
                return False, "Fish count must be greater than zero.", None

            matched_step = None
            if source_screening_datetime:
                steps = parent_dish.screening_results.screenings if parent_dish.screening_results else []
                matched_step = next(
                    (step for step in steps if step.screening_datetime == source_screening_datetime),
                    None,
                )
                if not matched_step:
                    return False, (
                        f"Screening step {source_screening_datetime} was not found on parent dish "
                        f"{parent_dish_id}."
                    ), None

            # Generate ID suffix from population type
            suffix_map = {
                "positive_screened": "_pos",
                "negative_screened": "_neg",
                "pigmented_screened": "_pig",
                "other": "_other",
                "primary": "_split",
            }
            id_suffix_base = suffix_map.get(population_type, "_derived")

            # Generate unique dish ID
            i = 1
            new_dish_id = f"{parent_dish_id}{id_suffix_base}{i}"
            while data_manager.load_single_dish(new_dish_id):
                i += 1
                new_dish_id = f"{parent_dish_id}{id_suffix_base}{i}"
                if i > 99:
                    msg = f"Could not generate unique derived dish ID for parent {parent_dish_id}."
                    logger.error(msg)
                    return False, msg, None
            logger.debug(f"Generated new derived dish ID: {new_dish_id}")

            default_notes = notes
            if not default_notes:
                note_parts = [f"Derived ({population_type}) from {parent_dish_id}"]
                if matched_step:
                    note_parts.append(f"screening step {matched_step.screening_datetime}")
                    if source_screening_bucket:
                        note_parts.append(f"bucket {source_screening_bucket}")
                note_parts.append(f"on {datetime.now().strftime('%Y%m%d')}.")
                default_notes = " ".join(note_parts)

            new_dish = FishDish.create_new(
                dish_id=new_dish_id,
                cross_id=parent_dish.cross_id,
                genotype=parent_dish.genotype,
                responsible=parent_dish.responsible,
                cross_setup_date=parent_dish.cross_setup_date,
                dof_source=parent_dish.dof_source,
                dof=parent_dish.dof,
                fish_count=fish_count,
                parent_dish_id=parent_dish_id,
                dish_population_type=population_type,
                source_screening_datetime=source_screening_datetime,
                source_screening_bucket=source_screening_bucket or population_type,
                species=parent_dish.species,
                sex=parent_dish.sex,
                parents=parent_dish.breeding.parents,
                temperature=parent_dish.enclosure.temperature,
                light_duration=parent_dish.enclosure.light_cycle.light_duration if parent_dish.enclosure.light_cycle else None,
                dawn_dusk=parent_dish.enclosure.light_cycle.dawn_dusk if parent_dish.enclosure.light_cycle else None,
                room=parent_dish.enclosure.room,
                container_type=container_type or parent_dish.enclosure.container_type,
                vol_water_total=parent_dish.enclosure.vol_water_total,
                notes=default_notes,
                dish_number=None,
            )

            # 5. Save the new dish
            if data_manager.save_fish_dish(new_dish.model_dump(mode='json', exclude_none=True)):
                if matched_step:
                    try:
                        parent_dish.add_screening_step_allocation(
                            matched_step.screening_datetime,
                            ScreeningStepAllocation(
                                bucket=source_screening_bucket or population_type,
                                disposition="derived_dish",
                                count=fish_count,
                                destination_dish_id=new_dish_id,
                                derived_dish_id=new_dish_id,
                                notes=notes or None,
                            ),
                        )
                        if not data_manager.save_fish_dish(parent_dish.model_dump(mode='json', exclude_none=True)):
                            logger.error(
                                "Derived dish %s created, but failed to persist parent allocation on %s",
                                new_dish_id,
                                parent_dish_id,
                            )
                            return False, (
                                f"Derived dish {new_dish_id} was created, but recording its screening-step "
                                f"allocation failed. Please review the parent dish."
                            ), new_dish
                        data_manager.data_cache['fish_dishes'][parent_dish_id] = parent_dish.model_dump(
                            mode='json',
                            exclude_none=True,
                        )
                    except Exception as allocation_error:
                        logger.error(
                            "Derived dish %s created, but allocation recording failed: %s",
                            new_dish_id,
                            allocation_error,
                            exc_info=True,
                        )
                        return False, (
                            f"Derived dish {new_dish_id} was created, but its screening-step allocation "
                            f"could not be recorded: {allocation_error}"
                        ), new_dish
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

    def add_screening_step_allocation(
        self,
        dish_id: str,
        screening_datetime: str,
        allocation_data: Dict[str, Any],
    ) -> Tuple[bool, str, Optional[ScreeningStepAllocation]]:
        """
        Add an explicit disposition allocation to an existing screening step.
        """
        try:
            dish = self.get_dish(dish_id)
            if not dish:
                return False, f"Dish {dish_id} not found", None

            validated_allocation = ScreeningStepAllocation(**allocation_data)
            dish.add_screening_step_allocation(screening_datetime, validated_allocation)

            if data_manager.save_fish_dish(dish.model_dump(mode='json', exclude_none=True)):
                data_manager.data_cache['fish_dishes'][dish_id] = dish.model_dump(mode='json', exclude_none=True)
                logger.info(
                    "Successfully added screening allocation to dish %s for step %s",
                    dish_id,
                    screening_datetime,
                )
                return True, "Screening allocation recorded successfully.", validated_allocation

            logger.error(
                "Failed to save dish %s after adding screening allocation for step %s",
                dish_id,
                screening_datetime,
            )
            return False, "Failed to save dish after recording screening allocation.", None
        except ValidationError as e:
            logger.error(
                "Validation failed for screening allocation on dish %s step %s: %s",
                dish_id,
                screening_datetime,
                e,
            )
            error_details = e.errors()
            message = (
                f"Validation Error: {error_details[0]['msg']} (field: {error_details[0]['loc'][0]})"
                if error_details
                else str(e)
            )
            return False, message, None
        except Exception as e:
            logger.error(
                "Error adding screening allocation to dish %s step %s: %s",
                dish_id,
                screening_datetime,
                e,
                exc_info=True,
            )
            return False, f"An unexpected error occurred: {str(e)}", None

    def allocate_screening_step_to_existing_dish(
        self,
        source_dish_id: str,
        screening_datetime: str,
        bucket: str,
        count: int,
        destination_dish_id: str,
        notes: Optional[str] = None,
    ) -> Tuple[bool, str, Optional[ScreeningStepAllocation]]:
        """Move fish from a screening step into an existing same-cross dish."""
        try:
            if source_dish_id == destination_dish_id:
                return False, "Destination dish must be different from the source dish.", None

            source_dish = self.get_dish(source_dish_id)
            if not source_dish:
                return False, f"Source dish {source_dish_id} not found", None

            destination_dish = self.get_dish(destination_dish_id)
            if not destination_dish:
                return False, f"Destination dish {destination_dish_id} not found", None

            if destination_dish.status != "active":
                return False, f"Destination dish {destination_dish_id} is not active.", None

            if source_dish.cross_id != destination_dish.cross_id:
                return False, "Destination dish must have the same cross ID as the source dish.", None

            destination_population = destination_dish.dish_population_type or "primary"
            compatible_destination_types = {
                "positive_screened",
                "negative_screened",
                "pigmented_screened",
                "other",
            }
            if destination_population in compatible_destination_types and destination_population != bucket:
                return False, (
                    f"Destination dish population type ({destination_population}) does not match "
                    f"allocation bucket ({bucket})."
                ), None

            allocation = ScreeningStepAllocation(
                bucket=bucket,
                disposition="derived_dish",
                count=count,
                destination_dish_id=destination_dish_id,
                notes=notes or None,
            )
            source_dish.add_screening_step_allocation(screening_datetime, allocation)

            destination_dish.incoming_fish_count = (destination_dish.incoming_fish_count or 0) + count
            destination_dish.refresh_screening_state()

            if not data_manager.save_fish_dish(source_dish.model_dump(mode='json', exclude_none=True)):
                return False, "Failed to save source dish after recording allocation.", None

            if not data_manager.save_fish_dish(destination_dish.model_dump(mode='json', exclude_none=True)):
                return False, "Failed to save destination dish after updating current count.", None

            data_manager.data_cache['fish_dishes'][source_dish_id] = source_dish.model_dump(
                mode='json',
                exclude_none=True,
            )
            data_manager.data_cache['fish_dishes'][destination_dish_id] = destination_dish.model_dump(
                mode='json',
                exclude_none=True,
            )
            logger.info(
                "Allocated %s fish from %s step %s to existing dish %s",
                count,
                source_dish_id,
                screening_datetime,
                destination_dish_id,
            )
            return True, "Screening fish allocated to existing dish.", allocation

        except ValidationError as e:
            logger.error(
                "Validation failed allocating fish from dish %s step %s to %s: %s",
                source_dish_id,
                screening_datetime,
                destination_dish_id,
                e,
            )
            error_details = e.errors()
            message = (
                f"Validation Error: {error_details[0]['msg']} (field: {error_details[0]['loc'][0]})"
                if error_details
                else str(e)
            )
            return False, message, None
        except Exception as e:
            logger.error(
                "Error allocating fish from dish %s step %s to %s: %s",
                source_dish_id,
                screening_datetime,
                destination_dish_id,
                e,
                exc_info=True,
            )
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
                normalized_reason = normalize_termination_reason(termination_reason)
                if not normalized_reason:
                    return False, (
                        "Termination reason is required and must be one of: "
                        f"{termination_reason_options_text()}."
                    )

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

                dish.termination_reason = normalized_reason
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
                        # Also search indicators and criteria
                        fields_to_check.extend(step.indicators_screened)
                        if step.criteria:
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

    def compute_aggregate_results(self, cross_id: str) -> Optional[AggregateResults]:
        """
        Compute aggregate screening results on demand for a given cross_id.

        Calculates from dish data without depending on the local Cross model:
        - total_initially_produced: Sum of count_screened_this_step from the
          first screening step of all primary dishes.
        - total_positive_final: Sum of final_positive_count from all
          screened dishes (primary and derived).
        - yield_percentage: (total_positive_final / total_initially_produced) * 100.

        Args:
            cross_id: The crossing ID to compute aggregates for.

        Returns:
            AggregateResults object, or None if no dishes found for the cross.
        """
        try:
            all_dishes = self.get_all_dishes(include_inactive=True)
            relevant_dishes = [
                dish for dish in all_dishes.values() if dish.cross_id == cross_id
            ]
            if not relevant_dishes:
                logger.warning(f"No dishes found for cross {cross_id}.")
                return None

            # total_initially_produced: first screening step of primary dishes
            total_initial_prod = 0
            primary_dishes = [d for d in relevant_dishes if d.dish_population_type == "primary"]

            for dish in primary_dishes:
                if dish.screening_results and dish.screening_results.screenings:
                    try:
                        sorted_screenings = sorted(
                            dish.screening_results.screenings,
                            key=lambda s: datetime.strptime(s.screening_datetime, "%Y%m%dT%H:%M:%S")
                        )
                        first_step = sorted_screenings[0]
                        count = getattr(first_step, 'count_screened_this_step', 0)
                        if isinstance(count, int) and count >= 0:
                            total_initial_prod += count
                    except (ValueError, TypeError, IndexError) as e:
                        logger.warning(f"Dish {dish.dish_id}: Could not process first screening step: {e}")

            # total_positive_final: all dishes (primary + derived)
            total_positive_fin = 0
            for dish in relevant_dishes:
                if dish.screening_results and dish.screening_results.final_positive_count is not None:
                    count = dish.screening_results.final_positive_count
                    if isinstance(count, int) and count >= 0:
                        total_positive_fin += count

            # yield_percentage
            yield_perc = None
            if total_initial_prod > 0:
                yield_perc = (total_positive_fin / total_initial_prod) * 100.0

            return AggregateResults(
                total_initially_produced=total_initial_prod,
                total_positive_final=total_positive_fin,
                yield_percentage=yield_perc,
                date_aggregated=datetime.now().strftime("%Y%m%d")
            )

        except Exception as e:
            logger.error(f"Error computing aggregate results for cross {cross_id}: {e}", exc_info=True)
            return None


# Create a singleton instance for global access
fish_dish_controller = FishDishController()
