"""
Survivability exporter for MetaZebrobot.

This module provides functions for exporting fish dish survivability data
using Polars for high performance.
"""

import logging
import polars as pl
from typing import Dict, Any, List, Optional
from pathlib import Path
from datetime import datetime

from ..data.data_manager import data_manager
from ..data.survival_data_processor import process_survival_data, create_survival_summary
from ..utils.file_operations import save_json_file
from ..controllers.fish_dish_controller import fish_dish_controller
from ..controllers.pyrat_tanks_controller import pyrat_tanks_controller

logger = logging.getLogger(__name__)

def get_survivability_data() -> pl.DataFrame:
    """
    Extract survivability data from fish dishes.

    Returns:
        pl.DataFrame: DataFrame containing survivability data.
    """
    logger.info("Extracting survivability data from fish dishes...")

    # Get all fish dishes
    dishes = data_manager.get_fish_dishes()

    # Prepare list to hold all records
    records = []

    # Process each dish
    for dish_id, dish_data in dishes.items():
        try:
            # Basic dish information
            base_info = {
                'dish_id': dish_id,
                'cross_id': dish_data.get('cross_id'),
                'genotype': dish_data.get('genotype'),
                'date_fertilized': dish_data.get('dof'),
                'date_created': dish_data.get('date_created'),
                'initial_count': dish_data.get('fish_count'),
                'status': dish_data.get('status'),
                'termination_date': dish_data.get('termination_date'),
                'termination_reason': dish_data.get('termination_reason'),
                'responsible': dish_data.get('responsible'),
                'in_beaker': 'Yes' if dish_data.get('enclosure', {}).get('in_beaker') else 'No',
                'vol_water_total': dish_data.get('enclosure', {}).get('vol_water_total', 0),
                'room': dish_data.get('enclosure', {}).get('room')
            }

            # Process quality checks
            quality_checks = dish_data.get('quality_checks', {})
            if not quality_checks:
                 pass # Still skipping dishes with no quality checks for now
            else:
                for check_time, check_data in quality_checks.items():
                    if not isinstance(check_data, dict):
                        continue

                    record = base_info.copy()
                    record.update({
                        'check_date': check_time.split('T')[0] if 'T' in check_time else check_time,
                        'check_time': check_time,
                        'fish_deaths': check_data.get('num_dead', 0),
                        'water_changed': 'Yes' if check_data.get('water_changed') else 'No',
                        'vol_water_changed': check_data.get('vol_water_changed', 0),
                        'notes': check_data.get('notes')
                    })
                    records.append(record)
        except Exception as e:
            logger.error(f"Error processing dish {dish_id}: {str(e)}")

    # Convert to DataFrame
    if not records:
        logger.warning("No survivability data found or extracted")
        return pl.DataFrame([])

    logger.info(f"Extracted {len(records)} records from fish dishes")

    # Define the schema explicitly
    schema = {
        'dish_id': pl.Utf8, 'cross_id': pl.Utf8, 'genotype': pl.Utf8,
        'date_fertilized': pl.Utf8, 'date_created': pl.Utf8,
        'initial_count': pl.Int64, 'status': pl.Categorical,
        'termination_date': pl.Utf8, 'termination_reason': pl.Utf8,
        'responsible': pl.Utf8, 'in_beaker': pl.Categorical,
        'vol_water_total': pl.Int64, 'room': pl.Utf8,
        'check_date': pl.Utf8, 'check_time': pl.Utf8,
        'fish_deaths': pl.Int64, 'water_changed': pl.Categorical,
        'vol_water_changed': pl.Int64,
        'notes': pl.Utf8
    }

    df = None # Initialize df
    try:
        # Create Polars DataFrame with the defined schema
        df = pl.DataFrame(records, schema=schema)
    except pl.exceptions.SchemaError as e:
        logger.error(f"Schema error while creating DataFrame: {e}")
        return pl.DataFrame([])
    except Exception as e:
        logger.error(f"Error creating DataFrame with schema: {e}. Trying with schema inference.")
        try:
            df = pl.DataFrame(records, infer_schema_length=10000)
        except Exception as fallback_e:
            logger.error(f"Fallback DataFrame creation failed: {fallback_e}")
            return pl.DataFrame([])

    if df is None or df.height == 0:
         logger.warning("DataFrame is empty after creation attempts.")
         return pl.DataFrame([])

    return df # Return the raw DataFrame

def export_lineage_json(output_path: str) -> bool:
    """
    Exports the lineage data (PyRAT crossings, parent tanks, dishes, relationships)
    as a JSON file suitable for graph visualization.

    Args:
        output_path: Path to save the JSON file.

    Returns:
        bool: True if export was successful, False otherwise.
    """
    logger.info(f"Exporting lineage data to JSON: {output_path}")
    try:
        # 1. Gather Data
        crossings = pyrat_tanks_controller.cached_crossings
        all_dishes = fish_dish_controller.get_all_dishes(include_inactive=True)

        if not crossings and not all_dishes:
            logger.warning("No crossings or dishes found. Exporting empty lineage.")
            return save_json_file(output_path, {"nodes": [], "links": []})

        nodes = []
        links = []
        added_node_ids = set()

        # 2. Process PyRAT crossings and their parent tanks
        for crossing in crossings:
            crossing_id = str(crossing.crossing_id)
            if crossing_id not in added_node_ids:
                nodes.append({
                    "id": crossing_id,
                    "type": "cross",
                    "label": f"Crossing {crossing_id}\n({crossing.strain_name or 'N/A'})"
                })
                added_node_ids.add(crossing_id)

            # Process parent tanks
            if crossing.parent_tanks:
                for tank in crossing.parent_tanks:
                    parent_id = tank.location_display
                    if parent_id not in added_node_ids:
                        nodes.append({
                            "id": parent_id,
                            "type": "original_parent",
                            "label": f"Parent:\n{parent_id}"
                        })
                        added_node_ids.add(parent_id)
                    links.append({
                        "source": parent_id,
                        "target": crossing_id,
                        "label": "Parent"
                    })

        # 3. Process Dishes (Nodes and Links from Crossing/Parent Dish)
        for dish_id, dish in all_dishes.items():
            if dish_id not in added_node_ids:
                node_label = f"Dish {dish_id}\n"
                if dish.dish_population_type != "primary":
                    node_label += f"({dish.dish_population_type})\n"
                node_label += f"Count: {dish.fish_count}"

                nodes.append({
                    "id": dish_id,
                    "type": dish.dish_population_type,
                    "label": node_label,
                    "initial_count": dish.fish_count
                })
                added_node_ids.add(dish_id)

            source_id = None
            link_label = ""
            value = dish.fish_count

            if dish.dish_population_type == "primary":
                source_id = dish.cross_id
                link_label = "Primary Dish"
                if source_id and source_id not in added_node_ids:
                    crossing = pyrat_tanks_controller.get_crossing_by_id(source_id)
                    cross_label = f"Crossing {source_id}"
                    if crossing:
                        cross_label += f"\n({crossing.strain_name or 'N/A'})"
                    nodes.append({"id": source_id, "type": "cross", "label": cross_label})
                    added_node_ids.add(source_id)

            elif dish.parent_dish_id:
                source_id = dish.parent_dish_id
                pop_type_map = {
                    "negative_screened": "Screened Negatives",
                    "positive_screened": "Screened Positives",
                    "other": "Derived (Other)"
                }
                link_label = pop_type_map.get(dish.dish_population_type, f"Derived ({dish.dish_population_type})")
                if source_id not in added_node_ids:
                    logger.warning(f"Parent dish node {source_id} for derived dish {dish_id} not found.")
                    source_id = None

            if source_id:
                links.append({
                    "source": source_id,
                    "target": dish_id,
                    "value": value,
                    "label": link_label
                })

        # 4. Format and Save
        output_data = {"nodes": nodes, "links": links}
        if save_json_file(output_path, output_data):
            logger.info(f"Successfully exported lineage JSON with {len(nodes)} nodes and {len(links)} links.")
            return True
        else:
            logger.error(f"Failed to save lineage JSON to {output_path}")
            return False

    except Exception as e:
        logger.error(f"Error exporting lineage JSON: {str(e)}", exc_info=True)
        return False

def export_survivability_report(output_path: str) -> bool:
    """
    Export detailed survivability report to CSV.
    
    Args:
        output_path: Path to save the CSV file.
        
    Returns:
        bool: True if export was successful, False otherwise.
    """
    try:
        logger.info(f"Exporting detailed survivability report to {output_path}")
        
        # Get survivability data
        df = get_survivability_data()
        
        if df.height == 0:
            logger.warning("No data to export")
            return False
            
        # Process the data with our new processor
        processed_df = process_survival_data(df)
        
        # Export to CSV
        processed_df.write_csv(output_path)
        
        logger.info(f"Successfully exported {processed_df.height} records to {output_path}")
        return True
    except Exception as e:
        logger.error(f"Error exporting survivability report: {str(e)}")
        return False

def export_survivability_summary(output_path: str) -> bool:
    """
    Export summarized survivability report to CSV.
    
    Args:
        output_path: Path to save the CSV file.
        
    Returns:
        bool: True if export was successful, False otherwise.
    """
    try:
        logger.info(f"Exporting survivability summary to {output_path}")
        
        # Get and process survivability data
        df = get_survivability_data()
        
        if df.height == 0:
            logger.warning("No data to export")
            return False
            
        # Process the data
        processed_df = process_survival_data(df)
        
        # Create summary
        summary_df = create_survival_summary(processed_df)
        
        # Export to CSV
        summary_df.write_csv(output_path)
        
        logger.info(f"Successfully exported summary with {summary_df.height} rows to {output_path}")
        return True
    except Exception as e:
        logger.error(f"Error exporting survivability summary: {str(e)}")
        return False
