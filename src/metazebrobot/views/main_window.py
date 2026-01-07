"""
Main window for the MetaZebrobot application.

This module provides the main application window and coordinates the tabs.
"""

import logging
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QTabWidget, QMessageBox
)
from PySide6.QtGui import QAction

from ..data.data_manager import data_manager
from .agarose_tab import AgaroseTab
from .fish_dish_tab import FishDishTab
from .fish_water_tab import FishWaterTab
from .poly_l_serine_tab import PolyLSerineTab 
from .dialogs.export_dialog import ExportDialog
from .cross_tab import CrossTab

logger = logging.getLogger(__name__)


class LabInventoryGUI(QMainWindow):
    """
    Main application window for MetaZebrobot.
    
    This class initializes the application UI and manages data loading and saving.
    """
    
    def __init__(self):
        """Initialize the main window."""
        super().__init__()
        
        # Log initialization
        logger.info("Initializing main window")
        
        # Load data first
        self.load_data()

        # Initialize UI
        self.init_ui()
        
    def load_data(self):
        """Load all data."""
        logger.info("Loading data")
        try:
            if not data_manager.load_all_data():
                logger.warning("Some data could not be loaded, using empty datasets")
                
            # Validate and fix data structure
            data_manager.validate_data_structure()
            
        except Exception as e:
            logger.error(f"Error loading data: {str(e)}")
            QMessageBox.warning(
                self,
                "Data Loading Error",
                f"There was an error loading data: {str(e)}\n\nStarting with empty datasets."
            )
            
    def closeEvent(self, event):
        """Override close event to quit the application."""
        self.close_application()
        event.accept()
            
    def close_application(self):
        """Close the application properly."""
        logger.info("Closing application")
        # Save data before closing
        if not data_manager.save_all_data():
            logger.warning("Some data could not be saved")
            
        # Actually quit the application
        from PySide6.QtCore import QCoreApplication
        QCoreApplication.quit()
        
    def setup_menu_bar(self):
        """Set up the menu bar."""
        menu_bar = self.menuBar()
        
        # File menu
        file_menu = menu_bar.addMenu("File")
        
        # Save action
        save_action = QAction("Save All Data", self)
        save_action.setShortcut("Ctrl+S")
        save_action.triggered.connect(self.save_data)
        file_menu.addAction(save_action)
        
        # Export submenu
        export_menu = file_menu.addMenu("Export")
        
        # Export survivability report action
        export_action = QAction("Survivability Reports...", self)
        export_action.triggered.connect(self.show_export_dialog)
        export_menu.addAction(export_action)
        
        file_menu.addSeparator()
        
        # Exit action
        exit_action = QAction("Exit", self)
        exit_action.setShortcut("Ctrl+Q")
        exit_action.triggered.connect(self.close_application)
        file_menu.addAction(exit_action)
        
        # Help menu
        help_menu = menu_bar.addMenu("Help")
        
        # About action
        about_action = QAction("About", self)
        about_action.triggered.connect(self.show_about_dialog)
        help_menu.addAction(about_action)
        
    def save_data(self):
        """Save all data."""
        logger.info("Saving data")
        if data_manager.save_all_data():
            QMessageBox.information(self, "Success", "All data saved successfully")
        else:
            QMessageBox.warning(self, "Warning", "Some data could not be saved")
            
    def show_about_dialog(self):
        """Show the about dialog."""
        QMessageBox.about(
            self,
            "About MetaZebrobot",
            """<h2>MetaZebrobot</h2>
            <p>A comprehensive system for managing laboratory materials and samples.</p>
            <p>Developed for Ahrens' lab researchers to efficiently track materials and dishes.</p>
            <p>Version 1.0.0</p>"""
        )

    def show_export_dialog(self):
        """Show the export dialog."""
        try:
            # Create and show the export dialog
            dialog = ExportDialog(self)
            dialog.exec()
        except Exception as e:
            logger.error(f"Error showing export dialog: {str(e)}")
            QMessageBox.warning(
                self, 
                "Export Error", 
                f"Error showing export dialog: {str(e)}"
            )        

    def init_ui(self):
        """Initialize the user interface."""
        logger.info("Setting up UI")
        
        # Set window properties
        self.setWindowTitle("MetaZebrobot - Lab Inventory Management")
        self.setGeometry(100, 100, 1200, 800)
        
        # Setup menu bar
        self.setup_menu_bar()
        
        # Create main widget and layout
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        layout = QVBoxLayout(main_widget)
        
        # Create tab widget
        tabs = QTabWidget()
        layout.addWidget(tabs)
        
        # Add tabs for different sections
        try:
            # Agarose tab
            agarose_tab = AgaroseTab()
            tabs.addTab(agarose_tab, "Agarose Solutions")
            
            # Fish water tab
            fish_water_tab = FishWaterTab()
            tabs.addTab(fish_water_tab, "Fish Water")
            # Poly-L-Serine tab
            pls_tab = PolyLSerineTab()
            tabs.addTab(pls_tab, "Poly-L-Serine")
            
            # Fish dishes tab
            fish_dishes_tab = FishDishTab()
            tabs.addTab(fish_dishes_tab, "Fish Dishes")

            # Crosses tab
            cross_tab = CrossTab()
            tabs.addTab(cross_tab, "Crosses")
            
        except Exception as e:
            logger.error(f"Error creating tabs: {str(e)}")
            QMessageBox.warning(
                self, 
                "Tab Creation Error", 
                f"Error creating tabs: {str(e)}"
            )
            raise
