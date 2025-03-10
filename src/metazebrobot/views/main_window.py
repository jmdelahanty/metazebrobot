"""
Main window for the MetaZebrobot application.

This module provides the main application window and coordinates the tabs.
"""

import sys
import logging
from pathlib import Path
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QTabWidget, QMessageBox,
    QSystemTrayIcon, QMenu, QMenuBar, QDialog
)
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QIcon, QPixmap, QPainter, QColor, QAction

from ..data.data_manager import data_manager
from .agarose_tab import AgaroseTab
from .fish_dish_tab import FishDishTab

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
        
        # Create system tray icon
        self.setup_system_tray()
        
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
            
    def setup_system_tray(self):
        """Setup the system tray icon and menu."""
        # Create the system tray icon
        self.tray_icon = QSystemTrayIcon(self)
        
        # Create a simple icon
        icon = self.create_simple_icon()
        self.tray_icon.setIcon(icon)
        
        # Create the menu
        tray_menu = QMenu()
        
        # Add menu items
        show_action = tray_menu.addAction("Show")
        show_action.triggered.connect(self.show)
        
        hide_action = tray_menu.addAction("Hide")
        hide_action.triggered.connect(self.hide)
        
        quit_action = tray_menu.addAction("Quit")
        quit_action.triggered.connect(self.close_application)
        
        # Set the menu for the tray icon
        self.tray_icon.setContextMenu(tray_menu)
        
        # Show a message when the icon is first displayed
        self.tray_icon.showMessage(
            "Lab Inventory",
            "Application is running in the system tray",
            QSystemTrayIcon.Information,
            2000
        )
        
        # Show the icon
        self.tray_icon.show()
        
        # Connect double click to show/hide window
        self.tray_icon.activated.connect(self.tray_icon_activated)
        
    def create_simple_icon(self):
        """Create a colored square icon."""
        # Create a pixmap
        pixmap = QPixmap(32, 32)
        pixmap.fill(Qt.transparent)
        
        # Create a painter
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # Draw a colored square with rounded corners
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(41, 128, 185))  # Nice blue color
        painter.drawRoundedRect(0, 0, 32, 32, 8, 8)
        
        # End painting
        painter.end()
        
        return QIcon(pixmap)
        
    def tray_icon_activated(self, reason):
        """Handle tray icon activation."""
        if reason == QSystemTrayIcon.DoubleClick:
            if self.isVisible():
                self.hide()
            else:
                self.show()
                self.raise_()  # Bring window to front
                self.activateWindow()
                
    def closeEvent(self, event):
        """Override close event to minimize to tray instead of closing."""
        if self.tray_icon.isVisible():
            self.hide()
            self.tray_icon.showMessage(
                "Lab Inventory",
                "Application minimized to tray",
                QSystemTrayIcon.Information,
                2000
            )
            event.ignore()
        else:
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
            <p>Developed for lab researchers to efficiently track materials and dishes.</p>
            <p>Version 1.0.0</p>"""
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
            
            # Placeholder for other tabs - we'll implement these later
            # For now, just add empty widgets with labels
            
            # Fish water tab placeholder
            fish_water_tab = QWidget()
            fish_water_layout = QVBoxLayout(fish_water_tab)
            fish_water_layout.addWidget(QWidget())  # Placeholder
            tabs.addTab(fish_water_tab, "Fish Water")
            
            # Poly-L-Serine tab placeholder
            pls_tab = QWidget()
            pls_layout = QVBoxLayout(pls_tab)
            pls_layout.addWidget(QWidget())  # Placeholder
            tabs.addTab(pls_tab, "Poly-L-Serine")
            
            # Fish dishes tab
            fish_dishes_tab = FishDishTab()
            tabs.addTab(fish_dishes_tab, "Fish Dishes")
            
        except Exception as e:
            logger.error(f"Error creating tabs: {str(e)}")
            QMessageBox.warning(
                self, 
                "Tab Creation Error", 
                f"Error creating tabs: {str(e)}"
            )
            raise