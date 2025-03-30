#!/usr/bin/env python3
"""
Main entry point for the MetaZebrobot application.

This script initializes the application, loads configuration, and launches the main window.
"""

import sys
import logging

from PySide6.QtWidgets import QApplication

from metazebrobot.utils.config import config
from metazebrobot.data.data_manager import data_manager
from metazebrobot.views.main_window import LabInventoryGUI


def setup_logging():
    """Configure application logging."""
    # Ensure log file path is handled correctly, maybe relative to project root or user dir
    log_file_path = 'metazebrobot.log' 
    # Consider making the log file path configurable or placing it in a standard location
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(log_file_path) 
        ]
    )


def main():
    """Application entry point."""
    try:
        # Set up logging
        setup_logging()
        logger = logging.getLogger(__name__)
        
        logger.info("Starting MetaZebrobot application...")
        
        # Load configuration
        if not config.load_config():
            logger.error("Failed to load configuration. Using default paths.")
        
        # Initialize data manager with loaded configuration
        if not data_manager.initialize():
            logger.error("Failed to initialize data manager.")
            return 1
        
        # Initialize Qt application
        # Pass sys.argv so Qt can process command-line arguments if needed
        app = QApplication(sys.argv) 
        app.setApplicationName("MetaZebrobot")
        app.setOrganizationName("Zebrafish Lab")
        
        # Create and show main window
        logger.info("Initializing main window...")
        window = LabInventoryGUI()
        window.show()
        
        # Run the application
        logger.info("Application started successfully")
        # Use app.exec() which returns the exit code
        return app.exec() 
        
    except Exception as e:
        # Use exc_info=True to log the full traceback
        logging.error(f"Unhandled exception in main: {str(e)}", exc_info=True) 
        return 1


# This block allows running 'python -m metazebrobot.cli' directly if needed,
# but the primary way to run is via the entry point script.
if __name__ == '__main__':
    # Exit with the code returned by app.exec() or the error code
    sys.exit(main())