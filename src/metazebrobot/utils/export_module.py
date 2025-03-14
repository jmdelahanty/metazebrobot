"""
Export functionality for MetaZebrobot.

This module provides functions for exporting data from the application,
including survivability reports from fish dish data.
"""

import os
import json
import csv
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple, Set

import json
import csv
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple, Set

# Set up module logger
logger = logging.getLogger(__name__)

# Import data_manager - handle different import paths depending on context
try:
    # When imported as part of the package
    from ..data.data_manager import data_manager
except ImportError:
    try:
        # When running as a script
        from metazebrobot.data.data_manager import data_manager
    except ImportError:
        # Final fallback
        logger.error("Could not import data_manager module. Export functionality may not work correctly.")

logger = logging.getLogger(__name__)


class SurvivabilityExporter:
    """
    Exporter for fish dish survivability data.
    
    This class provides functionality to export survivability data from fish dishes
    to CSV format for further analysis.
    """
    
    def __init__(self):
        """Initialize the exporter."""
        pass
        
    def export_survivability_report(self, output_path: str) -> bool:
        """
        Export survivability report to a CSV file.
        
        Args:
            output_path: Path to save the CSV file
            
        Returns:
            bool: True if export was successful, False otherwise
        """
        try:
            # Get dish directory
            dish_dir = data_manager.dish_data_dir
            
            # Collect dish data
            dishes_data = self._collect_dishes_data(dish_dir)
            if not dishes_data:
                logger.error("No dish data found to export")
                return False
                
            # Process the data for the report
            report_data = self._process_survivability_data(dishes_data)
            
            # Write to CSV
            return self._write_csv_report(report_data, output_path)
            
        except Exception as e:
            logger.error(f"Error exporting survivability report: {str(e)}")
            return False
            
    def _collect_dishes_data(self, dish_dir: Path) -> List[Dict[str, Any]]:
        """
        Collect data from all dish JSON files.
        
        Args:
            dish_dir: Directory containing dish JSON files
            
        Returns:
            List of dish data dictionaries
        """
        dishes_data = []
        
        try:
            # Find all JSON files in the directory
            json_files = list(dish_dir.glob("*.json"))
            logger.info(f"Found {len(json_files)} dish JSON files")
            
            # Load each file
            for json_file in json_files:
                try:
                    with open(json_file, 'r') as f:
                        dish_data = json.load(f)
                        
                    # Basic validation of the data
                    if not isinstance(dish_data, dict) or 'dish_id' not in dish_data:
                        logger.warning(f"Skipping invalid dish file: {json_file}")
                        continue
                        
                    dishes_data.append(dish_data)
                    
                except Exception as e:
                    logger.error(f"Error loading dish file {json_file}: {str(e)}")
                    
            return dishes_data
            
        except Exception as e:
            logger.error(f"Error collecting dish data: {str(e)}")
            return []
            
    def _process_survivability_data(self, dishes_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Process dish data into survivability report data.
        
        Args:
            dishes_data: List of dish data dictionaries
            
        Returns:
            List of processed data rows for the report
        """
        report_rows = []
        
        for dish in dishes_data:
            try:
                dish_id = dish.get('dish_id', 'unknown')
                cross_id = dish.get('cross_id', 'unknown')
                date_created = dish.get('date_created', 'unknown')
                dof = dish.get('dof', 'unknown')
                genotype = dish.get('genotype', 'unknown')
                initial_count = dish.get('fish_count', 0)
                status = dish.get('status', 'unknown')
                termination_date = dish.get('termination_date')
                termination_reason = dish.get('termination_reason')
                
                # Get the new fields
                responsible = dish.get('responsible', 'unknown')
                
                # Extract enclosure information with safe fallbacks
                enclosure = dish.get('enclosure', {})
                in_beaker = enclosure.get('in_beaker', False)
                room = enclosure.get('room', 'unknown'),
                total_volume = enclosure.get('vol_water_total', 0)
                
                # Skip dishes without quality checks
                quality_checks = dish.get('quality_checks', {})
                if not quality_checks:
                    logger.warning(f"Skipping dish {dish_id} with no quality checks")
                    continue
                    
                # Extract quality check dates and dead counts
                check_data = []
                for check_time, check in quality_checks.items():
                    # Handle different formats of quality checks
                    if isinstance(check, dict):
                        # New format: check is a dictionary
                        num_dead = check.get('num_dead', 0)
                        
                        # Get water change information
                        water_changed = check.get('water_changed', False)
                        vol_water_changed = check.get('vol_water_changed', 0) if water_changed else 0
                        
                        # Format the check time to YYYYMMDD if it's not already
                        if ':' in check_time:
                            # This looks like a timestamp with time component
                            try:
                                # Try to extract the date part (first 8 characters)
                                check_date = check_time[:8]
                            except:
                                # Use the whole string as date if extraction fails
                                check_date = check_time
                        else:
                            # Already in date format
                            check_date = check_time
                        
                    elif isinstance(check, str):
                        # Old format: check is a string description
                        num_dead = 0  # No dead count in the old format
                        check_date = check_time
                        water_changed = False
                        vol_water_changed = 0
                    else:
                        # Skip invalid checks
                        continue
                        
                    check_data.append({
                        'date': check_date,
                        'num_dead': num_dead,
                        'water_changed': water_changed,
                        'vol_water_changed': vol_water_changed
                    })
                    
                # Sort check data by date
                check_data.sort(key=lambda x: x['date'])
                
                # Calculate cumulative deaths and remaining fish
                remaining = initial_count
                for i, check in enumerate(check_data):
                    num_dead = check['num_dead']
                    remaining -= num_dead
                    
                    # Create a row for this check
                    row = {
                        'dish_id': dish_id,
                        'cross_id': cross_id,
                        'genotype': genotype,
                        'date_fertilized': dof,
                        'date_created': date_created,
                        'initial_count': initial_count,
                        'check_date': check['date'],
                        'fish_deaths': num_dead,
                        'cumulative_deaths': initial_count - remaining,
                        'remaining': remaining,
                        'survival_rate': (remaining / initial_count * 100) if initial_count > 0 else 0,
                        'days_since_fertilization': self._calculate_days_between(dof, check['date']),
                        'status': status,
                        'termination_date': termination_date or '',
                        'termination_reason': termination_reason or '',
                        'responsible': responsible,
                        'in_beaker': 'Yes' if in_beaker else 'No',
                        'vol_water_total': total_volume,
                        'room': room,
                        'water_changed': 'Yes' if check['water_changed'] else 'No',
                        'vol_water_changed': check['vol_water_changed']
                    }
                    report_rows.append(row)
                    
            except Exception as e:
                logger.error(f"Error processing dish {dish.get('dish_id', 'unknown')}: {str(e)}")
                
        return report_rows
        
    def _calculate_days_between(self, date1: str, date2: str) -> int:
        """
        Calculate days between two dates in YYYYMMDD format.
        
        Args:
            date1: First date (YYYYMMDD)
            date2: Second date (YYYYMMDD)
            
        Returns:
            Number of days between the dates, or 0 if calculation fails
        """
        try:
            # Parse dates
            d1 = datetime.strptime(date1, "%Y%m%d")
            d2 = datetime.strptime(date2, "%Y%m%d")
            
            # Calculate difference in days
            delta = d2 - d1
            return delta.days
            
        except Exception as e:
            logger.warning(f"Error calculating days between {date1} and {date2}: {str(e)}")
            return 0
            
    def _write_csv_report(self, report_data: List[Dict[str, Any]], output_path: str) -> bool:
        """
        Write report data to CSV file.
        
        Args:
            report_data: List of data rows for the report
            output_path: Path to save the CSV file
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            if not report_data:
                logger.warning("No data to write to CSV")
                return False
                
            # Determine columns from data
            columns = list(report_data[0].keys())
            
            # Write to CSV
            with open(output_path, 'w', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=columns)
                writer.writeheader()
                writer.writerows(report_data)
                
            logger.info(f"Successfully wrote survivability report to {output_path}")
            return True
            
        except Exception as e:
            logger.error(f"Error writing CSV report: {str(e)}")
            return False
            
    def export_survivability_summary(self, output_path: str) -> bool:
        """
        Export a summarized survivability report grouping by cross ID and genotype.
        
        Args:
            output_path: Path to save the CSV file
            
        Returns:
            bool: True if export was successful, False otherwise
        """
        try:
            # Get dish directory
            dish_dir = data_manager.dish_data_dir
            
            # Collect dish data
            dishes_data = self._collect_dishes_data(dish_dir)
            if not dishes_data:
                logger.error("No dish data found to export")
                return False
                
            # Process the data for the summary report
            summary_data = self._process_summary_data(dishes_data)
            
            # Write to CSV
            return self._write_csv_report(summary_data, output_path)
            
        except Exception as e:
            logger.error(f"Error exporting survivability summary: {str(e)}")
            return False
            
    def _process_summary_data(self, dishes_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Process dish data into a summarized report by cross ID and genotype.
        
        Args:
            dishes_data: List of dish data dictionaries
            
        Returns:
            List of processed summary rows for the report
        """
        # Group data by cross ID and genotype
        summary = {}
        
        for dish in dishes_data:
            try:
                cross_id = dish.get('cross_id', 'unknown')
                genotype = dish.get('genotype', 'unknown')
                dof = dish.get('dof', 'unknown')
                initial_count = dish.get('fish_count', 0)
                
                # Skip dishes without quality checks
                quality_checks = dish.get('quality_checks', {})
                if not quality_checks:
                    continue
                    
                # Create a key for grouping
                group_key = f"{cross_id}_{genotype}_{dof}"
                
                if group_key not in summary:
                    summary[group_key] = {
                        'cross_id': cross_id,
                        'genotype': genotype,
                        'date_fertilized': dof,
                        'dish_count': 0,
                        'total_initial': 0,
                        'total_surviving': 0,
                        'survival_rate': 0,
                        'max_days': 0
                    }
                
                # Update group summary
                summary[group_key]['dish_count'] += 1
                summary[group_key]['total_initial'] += initial_count
                
                # Calculate final surviving count
                final_count = initial_count
                latest_date = ''
                
                for check_time, check in quality_checks.items():
                    if isinstance(check, dict):
                        num_dead = check.get('num_dead', 0)
                        final_count -= num_dead
                        
                        # Track latest check date
                        if ':' in check_time:
                            check_date = check_time[:8]
                        else:
                            check_date = check_time
                            
                        if check_date > latest_date:
                            latest_date = check_date
                
                # Update surviving count
                summary[group_key]['total_surviving'] += max(0, final_count)
                
                # Update max days
                if latest_date:
                    days = self._calculate_days_between(dof, latest_date)
                    summary[group_key]['max_days'] = max(summary[group_key]['max_days'], days)
                
            except Exception as e:
                logger.error(f"Error processing dish {dish.get('dish_id', 'unknown')} for summary: {str(e)}")
        
        # Calculate survival rates and convert to list
        summary_rows = []
        for key, data in summary.items():
            if data['total_initial'] > 0:
                data['survival_rate'] = (data['total_surviving'] / data['total_initial']) * 100
            summary_rows.append(data)
            
        # Sort by cross ID and genotype
        summary_rows.sort(key=lambda x: (x['cross_id'], x['genotype']))
        
        return summary_rows
            

# Create a singleton instance for global access
survivability_exporter = SurvivabilityExporter()