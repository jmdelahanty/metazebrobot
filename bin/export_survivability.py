#!/usr/bin/env python3
"""
Export fish dish survivability data to CSV.

This script can be run directly to generate a survivability report from fish dish data.
It is designed to be used from the command line, but can also be imported and
used programmatically.

Usage:
    python export_survivability.py --dishes-dir /path/to/dishes --output report.csv
    python export_survivability.py --summary --summary-output summary.csv
    python export_survivability.py --both
"""

import os
import sys
import argparse
import logging
from pathlib import Path

# Add parent directory to path to allow imports
script_dir = Path(__file__).resolve().parent
sys.path.append(str(script_dir.parent))

from metazebrobot.utils.config import config
from metazebrobot.data.data_manager import data_manager
from metazebrobot.utils.export_module import survivability_exporter


def setup_logging():
    """Configure logging for the script."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler('export_survivability.log')
        ]
    )


def parse_arguments():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description='Export fish dish survivability data to CSV')
    
    parser.add_argument(
        '--dishes-dir',
        type=str,
        help='Directory containing fish dish JSON files (overrides config)'
    )
    
    parser.add_argument(
        '--output',
        type=str,
        default='survivability_report.csv',
        help='Output CSV file path (default: survivability_report.csv)'
    )
    
    parser.add_argument(
        '--summary',
        action='store_true',
        help='Generate a summary report instead of detailed report'
    )
    
    parser.add_argument(
        '--summary-output',
        type=str,
        default='survivability_summary.csv',
        help='Output CSV file path for summary (default: survivability_summary.csv)'
    )
    
    parser.add_argument(
        '--both',
        action='store_true',
        help='Generate both detailed and summary reports'
    )
    
    return parser.parse_args()


def main():
    """Main entry point for the script."""
    try:
        # Set up logging
        setup_logging()
        logger = logging.getLogger(__name__)
        
        logger.info("Starting survivability report export")
        
        # Parse arguments
        args = parse_arguments()
        
        # Load configuration
        if not config.load_config():
            logger.warning("Failed to load configuration. Using default paths.")
        
        # Override dish directory if specified
        if args.dishes_dir:
            data_manager.dish_data_dir = Path(args.dishes_dir)
            logger.info(f"Using custom dish directory: {data_manager.dish_data_dir}")
        
        # Initialize data manager
        if not data_manager.is_initialized:
            data_manager.initialize()
        
        # Determine what to export
        generate_detailed = not args.summary or args.both
        generate_summary = args.summary or args.both
        
        # Export detailed report if requested
        if generate_detailed:
            output_path = args.output
            logger.info(f"Exporting detailed survivability report to {output_path}")
            
            if survivability_exporter.export_survivability_report(output_path):
                logger.info(f"Successfully exported detailed report to {output_path}")
                print(f"Successfully exported detailed report to {output_path}")
            else:
                logger.error("Failed to export detailed survivability report")
                print("Failed to export detailed survivability report")
                return 1
        
        # Export summary report if requested
        if generate_summary:
            summary_output = args.summary_output
            logger.info(f"Exporting survivability summary to {summary_output}")
            
            if survivability_exporter.export_survivability_summary(summary_output):
                logger.info(f"Successfully exported summary to {summary_output}")
                print(f"Successfully exported summary to {summary_output}")
            else:
                logger.error("Failed to export survivability summary")
                print("Failed to export survivability summary")
                return 1
        
        return 0
        
    except Exception as e:
        logging.error(f"Unhandled exception in main: {str(e)}", exc_info=True)
        print(f"Error: {str(e)}")
        return 1


if __name__ == '__main__':
    sys.exit(main())