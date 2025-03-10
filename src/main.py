#!/usr/bin/env python3
"""
Main entry point for the MetaZebrobot application.

This script initializes the application, loads configuration, and launches the main window.
"""

import sys
import logging
from pathlib import Path

from PySide6.QtWidgets import QApplication

# Add parent directory to path to allow imports from metazebrobot package
sys.path.append(str(Path(__file__).parent))

from metazebrobot.utils.config import config
from metazebrobot.data.data_manager import data_manager
from metazebrobot.views.main_window import LabInventoryGUI


def setup_logging():
    """Configure application logging."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler('metazebrobot.log')
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
        app = QApplication(sys.argv)
        app.setApplicationName("MetaZebrobot")
        app.setOrganizationName("Zebrafish Lab")
        
        # Create and show main window
        logger.info("Initializing main window...")
        window = LabInventoryGUI()
        window.show()
        
        # Run the application
        logger.info("Application started successfully")
        return app.exec()
        
    except Exception as e:
        logging.error(f"Unhandled exception in main: {str(e)}", exc_info=True)
        return 1


if __name__ == '__main__':
    sys.exit(main())