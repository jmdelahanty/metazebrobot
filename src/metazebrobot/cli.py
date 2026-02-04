#!/usr/bin/env python3
"""
Main entry point for the MetaZebrobot application.

This script initializes the application, loads configuration, and launches the main window.
"""

import sys
import logging
from pathlib import Path

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QGuiApplication, QIcon

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
        app.setQuitOnLastWindowClosed(True)
        QGuiApplication.setDesktopFileName("metazebrobot")

        icon_path = None
        config_icon_path = config.get_path("app_icon_path")
        if config_icon_path and config_icon_path.exists():
            icon_path = config_icon_path
        else:
            default_icon_path = Path(__file__).resolve().parent / "config" / "images" / "app_icon.png"
            if default_icon_path.exists():
                icon_path = default_icon_path

        if icon_path:
            app.setWindowIcon(QIcon(str(icon_path)))
        else:
            logger.info("No app icon found. Set app_icon_path in config.json or place app_icon.png in config/images.")
        
        # Create and show main window
        logger.info("Initializing main window...")
        window = LabInventoryGUI()
        window.show()
        
        # Run the application
        logger.info("Application started successfully")
        # Use app.exec() which returns the exit code
        exit_code = app.exec()
        logger.info(f"Application event loop exited with code {exit_code}")
        return exit_code
        
    except Exception as e:
        # Use exc_info=True to log the full traceback
        logging.error(f"Unhandled exception in main: {str(e)}", exc_info=True) 
        return 1


# This block allows running 'python -m metazebrobot.cli' directly if needed,
# but the primary way to run is via the entry point script.
if __name__ == '__main__':
    # Exit with the code returned by app.exec() or the error code
    sys.exit(main())
