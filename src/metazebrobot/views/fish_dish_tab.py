"""
Fish dish tab UI component.

This module provides the UI for managing fish dishes.
"""

import logging
from datetime import datetime
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QFormLayout, QGroupBox,
    QLabel, QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QCheckBox,
    QPushButton, QDateEdit, QTableWidget, QTableWidgetItem, QMessageBox,
    QHeaderView, QScrollArea, QDialog
)
from PySide6.QtCore import Qt, QDate, Signal, Slot

from ..controllers.fish_dish_controller import fish_dish_controller
from ..models.fish_dish import FishDish
from .dialogs.quality_check_dialog import QualityCheckDialog
from .dialogs.termination_dialog import TerminationDialog

logger = logging.getLogger(__name__)


class FishDishTab(QWidget):
    """
    Tab for managing fish dishes.
    
    This tab provides UI for creating and viewing fish dishes.
    """
    
    def __init__(self, parent=None):
        """
        Initialize the fish dish tab.
        
        Args:
            parent: Parent widget
        """
        super().__init__(parent)
        
        # Initialize state
        self.dish_sort_column = 0  # Default sort by dish ID
        self.dish_sort_order = Qt.AscendingOrder  # Default to ascending order

        self.setup_ui()
        
    def setup_ui(self):
        """Set up the user interface."""
        layout = QVBoxLayout(self)
        
        # Create scroll area for the form
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll_widget = QWidget()
        scroll_layout = QVBoxLayout(scroll_widget)
        
        # Form section
        form_group = QGroupBox("New Dish Information")
        form_layout = QGridLayout()
        form_layout.setColumnStretch(1, 1)  # Make the input columns stretch
        form_layout.setColumnStretch(3, 1)
        form_layout.setHorizontalSpacing(10)  # Add spacing between columns
        form_layout.setVerticalSpacing(5)     # Reduce vertical spacing
        
        # Basic information section
        row = 0
        
        # Cross ID
        form_layout.addWidget(QLabel("Cross ID:"), row, 0)
        self.cross_id = QLineEdit()
        form_layout.addWidget(self.cross_id, row, 1)
        
        # Genotype
        form_layout.addWidget(QLabel("Genotype:"), row, 2)
        self.genotype = QLineEdit()
        form_layout.addWidget(self.genotype, row, 3)
        
        row += 1
        
        # Dish number
        form_layout.addWidget(QLabel("Dish Number:"), row, 0)
        self.dish_number = QSpinBox()
        self.dish_number.setMinimum(1)
        form_layout.addWidget(self.dish_number, row, 1)
        
        # Sex
        form_layout.addWidget(QLabel("Sex:"), row, 2)
        self.sex = QComboBox()
        self.sex.addItems(["unknown", "M", "F"])
        form_layout.addWidget(self.sex, row, 3)
        
        row += 1
        
        # Date of fertilization
        form_layout.addWidget(QLabel("Date of Fertilization:"), row, 0)
        self.dof = QDateEdit()
        self.dof.setDate(QDate.currentDate())
        self.dof.setCalendarPopup(True)
        form_layout.addWidget(self.dof, row, 1)
        
        # Species
        form_layout.addWidget(QLabel("Species:"), row, 2)
        self.species = QLineEdit()
        self.species.setText("Danio rerio")  # Default value
        form_layout.addWidget(self.species, row, 3)
        
        row += 1
        
        # Responsible person
        form_layout.addWidget(QLabel("Responsible:"), row, 0)
        self.responsible = QLineEdit()
        self.responsible.setText("Lab Staff")
        form_layout.addWidget(self.responsible, row, 1)
        
        # Parents
        form_layout.addWidget(QLabel("Parents:"), row, 2)
        self.parents = QLineEdit()
        self.parents.setPlaceholderText("Comma-separated list")
        form_layout.addWidget(self.parents, row, 3)
        
        row += 1
        
        # Incubator Properties section
        form_layout.addWidget(QLabel("Temperature (°C):"), row, 0)
        self.temperature = QDoubleSpinBox()
        self.temperature.setRange(18, 30)
        self.temperature.setValue(28.5)
        self.temperature.setSingleStep(0.5)
        form_layout.addWidget(self.temperature, row, 1)
        
        # Room
        form_layout.addWidget(QLabel("Room:"), row, 2)
        self.room = QLineEdit()
        self.room.setText("2E.282")  # Default value
        form_layout.addWidget(self.room, row, 3)
        
        row += 1
        
        # Light cycle
        form_layout.addWidget(QLabel("Light Duration:"), row, 0)
        self.light_duration = QLineEdit()
        self.light_duration.setText("14:10")  # Default value
        form_layout.addWidget(self.light_duration, row, 1)
        
        form_layout.addWidget(QLabel("Dawn/Dusk Time:"), row, 2)
        self.dawn_dusk = QLineEdit()
        self.dawn_dusk.setText("8:00")
        form_layout.addWidget(self.dawn_dusk, row, 3)
        
        row += 1
        
        # Whether a dish is in a beaker
        form_layout.addWidget(QLabel("In a beaker?"), row, 0)
        self.beaker_housing = QCheckBox()
        self.beaker_housing.setChecked(False)
        form_layout.addWidget(self.beaker_housing, row, 1)
        
        # Number of fish
        form_layout.addWidget(QLabel("Number of Fish:"), row, 2)
        self.fish_count = QSpinBox()
        self.fish_count.setRange(0, 1000)  # Set reasonable range
        self.fish_count.setValue(1)  # Default value
        form_layout.addWidget(self.fish_count, row, 3)
        
        # Add form to group box
        form_group.setLayout(form_layout)
        scroll_layout.addWidget(form_group)
        
        # Add buttons
        button_layout = QHBoxLayout()
        add_button = QPushButton("Add New Dish")
        add_button.clicked.connect(self.add_fish_dish)
        button_layout.addWidget(add_button)
        
        clear_button = QPushButton("Clear Form")
        clear_button.clicked.connect(self.clear_fish_dish_form)
        button_layout.addWidget(clear_button)
        
        scroll_layout.addLayout(button_layout)
        
        # Add scroll area to main layout
        scroll.setWidget(scroll_widget)
        layout.addWidget(scroll)
        
        # Add search and filter controls
        filter_layout = QHBoxLayout()
        
        # Search box
        filter_layout.addWidget(QLabel("Search:"))
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Enter search text...")
        self.search_box.textChanged.connect(self.filter_dishes)
        filter_layout.addWidget(self.search_box)
        
        # Status filter
        filter_layout.addWidget(QLabel("Status:"))
        self.status_filter = QComboBox()
        self.status_filter.addItems(["All", "Active Only", "Inactive Only"])
        self.status_filter.currentTextChanged.connect(self.filter_dishes)
        filter_layout.addWidget(self.status_filter)
        
        # Refresh button
        refresh_button = QPushButton("Refresh")
        refresh_button.clicked.connect(self.update_dishes_table)
        filter_layout.addWidget(refresh_button)
        
        layout.addLayout(filter_layout)
        
        # Dishes table
        self.dishes_table = QTableWidget()
        layout.addWidget(self.dishes_table)

        # Setup the table with sorting functionality
        self.setup_dish_table()
        
        # Initial update of the table
        self.update_dishes_table()
        
    def setup_dish_table(self):
        """Setup the dish table with sorting and double-click handling."""
        # Set up table columns
        self.dishes_table.setColumnCount(7)
        self.dishes_table.setHorizontalHeaderLabels([
            "Dish ID", "Date Created", "Genotype", "Responsible", 
            "Status", "Location", "Fish Count"
        ])
        
        # Customize table appearance and behavior
        self.dishes_table.setAlternatingRowColors(True)
        self.dishes_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.dishes_table.setSelectionMode(QTableWidget.SingleSelection)
        self.dishes_table.verticalHeader().setVisible(False)
        self.dishes_table.setEditTriggers(QTableWidget.NoEditTriggers)
        
        # Make columns resize properly
        header = self.dishes_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Stretch)
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)  # Dish ID
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)  # Date
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents)  # Status
        header.setSectionResizeMode(5, QHeaderView.ResizeToContents)  # Location
        header.setSectionResizeMode(6, QHeaderView.ResizeToContents)  # Fish Count
        
        # Connect signals
        self.dishes_table.horizontalHeader().sectionClicked.connect(self.handle_header_click)
        self.dishes_table.cellDoubleClicked.connect(self.handle_dish_cell_double_click)
        
    def handle_header_click(self, column):
        """
        Handle clicks on the table header for sorting.
        
        Args:
            column: Column index that was clicked
        """
        # Toggle sort order if clicking the same column
        if self.dish_sort_column == column:
            self.dish_sort_order = Qt.DescendingOrder if self.dish_sort_order == Qt.AscendingOrder else Qt.AscendingOrder
        else:
            self.dish_sort_column = column
            self.dish_sort_order = Qt.AscendingOrder
        
        # Update the table with the new sorting
        self.update_dishes_table()
        
    def handle_dish_cell_double_click(self, row, column):
        """
        Handle double-click on a cell in the dishes table.
        
        Args:
            row: Row index
            column: Column index
        """
        try:
            # Get dish ID from the first column
            dish_id = self.dishes_table.item(row, 0).text()
            
            # If clicking the status column
            if column == 4:  # Status column
                self.show_termination_dialog(dish_id)
            else:
                # Handle other columns (quality check dialog)
                self.show_quality_check_dialog(dish_id)
                
        except Exception as e:
            logger.error(f"Error handling cell click: {str(e)}")
            QMessageBox.critical(self, "Error", f"Error: {str(e)}")
            
    def show_termination_dialog(self, dish_id):
        """
        Show dialog to update dish status.
        
        Args:
            dish_id: ID of the dish to update
        """
        try:
            # Get the dish
            dish = fish_dish_controller.get_dish(dish_id)
            if not dish:
                QMessageBox.warning(self, "Error", f"Could not load dish {dish_id}")
                return

            # Create and show dialog
            dialog = TerminationDialog(self)
            
            # Set current values
            dialog.set_data(
                dish.status,
                dish.termination_date,
                dish.termination_reason
            )

            if dialog.exec() == QDialog.Accepted:
                # Get updated data
                update_data = dialog.get_data()
                
                # Update dish status
                success, message = fish_dish_controller.update_dish_status(
                    dish_id=dish_id,
                    status=update_data["status"],
                    termination_date=update_data["termination_date"],
                    termination_reason=update_data["termination_reason"]
                )
                
                if success:
                    self.update_dishes_table()
                    QMessageBox.information(self, "Success", "Dish status updated successfully")
                else:
                    QMessageBox.warning(self, "Error", f"Failed to update dish status: {message}")

        except Exception as e:
            logger.error(f"Error updating dish status: {str(e)}")
            QMessageBox.critical(self, "Error", f"Error updating dish status: {str(e)}")
            
    def show_quality_check_dialog(self, dish_id):
        """
        Show dialog to add a quality check.
        
        Args:
            dish_id: ID of the dish to update
        """
        try:
            # Get the dish
            dish = fish_dish_controller.get_dish(dish_id)
            if not dish:
                QMessageBox.warning(self, "Error", f"Could not load dish {dish_id}")
                return
            
            # Create dialog
            dialog = QualityCheckDialog(self)
            
            # Connect signal to save quality check
            dialog.check_saved.connect(lambda check_data: self.save_quality_check(dish_id, check_data))
            
            # Show dialog (non-modal to allow multiple checks)
            dialog.setWindowTitle(f"Quality Check - Dish {dish_id}")
            dialog.show()
            
        except Exception as e:
            logger.error(f"Error showing quality check dialog: {str(e)}")
            QMessageBox.critical(self, "Error", f"Error: {str(e)}")
            
    def save_quality_check(self, dish_id, check_data):
        """
        Save a quality check for a dish.
        
        Args:
            dish_id: ID of the dish
            check_data: Quality check data
        """
        try:
            # Add quality check
            success, message = fish_dish_controller.add_quality_check(
                dish_id=dish_id,
                **check_data
            )
            
            if success:
                QMessageBox.information(self, "Success", "Quality check saved successfully")
            else:
                QMessageBox.warning(self, "Error", f"Failed to save quality check: {message}")
                
        except Exception as e:
            logger.error(f"Error saving quality check: {str(e)}")
            QMessageBox.critical(self, "Error", f"Error saving quality check: {str(e)}")
            
    def update_dishes_table(self):
        """Update the fish dishes table with sorted and filtered entries."""
        try:
            # Get all dishes
            all_dishes = fish_dish_controller.get_all_dishes(include_inactive=True)
            
            # Apply filters
            filtered_dishes = self.apply_filters(all_dishes)
            
            # Apply sorting
            sorted_dishes = self.apply_sorting(filtered_dishes)
            
            # Update table
            self.populate_dishes_table(sorted_dishes)
            
        except Exception as e:
            logger.error(f"Error updating dishes table: {str(e)}")
            QMessageBox.critical(self, "Error", f"Error updating dishes table: {str(e)}")
            
    def apply_filters(self, dishes):
        """
        Apply filters to the dishes.
        
        Args:
            dishes: Dictionary of dishes to filter
            
        Returns:
            Filtered dictionary of dishes
        """
        result = dishes
        
        # Apply status filter
        status_filter = self.status_filter.currentText()
        if status_filter == "Active Only":
            result = fish_dish_controller.filter_dishes(
                result, 
                lambda dish: dish.status == "active"
            )
        elif status_filter == "Inactive Only":
            result = fish_dish_controller.filter_dishes(
                result, 
                lambda dish: dish.status == "inactive"
            )
            
        # Apply search filter
        search_text = self.search_box.text().strip()
        if search_text:
            result = fish_dish_controller.search_dishes(
                result,
                search_text,
                case_sensitive=False
            )
            
        return result
        
    def apply_sorting(self, dishes):
        """
        Apply sorting to the dishes.
        
        Args:
            dishes: Dictionary of dishes to sort
            
        Returns:
            Sorted dictionary of dishes
        """
        # Map column index to sort key
        column_to_key = {
            0: "dish_id",
            1: "date_created",
            2: "genotype",
            3: "responsible",
            4: "status",
            5: "room",
            6: "fish_count"
        }
        
        # Get sort key from column index
        sort_key = column_to_key.get(self.dish_sort_column, "dish_id")
        
        # Sort dishes
        return fish_dish_controller.sort_dishes(
            dishes,
            sort_key,
            ascending=(self.dish_sort_order == Qt.AscendingOrder)
        )
        
    def populate_dishes_table(self, dishes):
        """
        Populate the dishes table with the provided dishes.
        
        Args:
            dishes: Dictionary of dishes to display
        """
        self.dishes_table.setRowCount(len(dishes))
        
        for i, (dish_id, dish) in enumerate(dishes.items()):
            try:
                self.dishes_table.setItem(i, 0, QTableWidgetItem(dish_id))
                self.dishes_table.setItem(i, 1, QTableWidgetItem(dish.date_created))
                self.dishes_table.setItem(i, 2, QTableWidgetItem(dish.genotype))  # Updated
                self.dishes_table.setItem(i, 3, QTableWidgetItem(dish.responsible))  # Updated
                self.dishes_table.setItem(i, 4, QTableWidgetItem(dish.status))
                self.dishes_table.setItem(i, 5, QTableWidgetItem(dish.enclosure.room))  # Updated
                self.dishes_table.setItem(i, 6, QTableWidgetItem(str(dish.fish_count)))  # Updated
                
                # Color inactive rows with light gray background
                if dish.status == "inactive":
                    for col in range(self.dishes_table.columnCount()):
                        item = self.dishes_table.item(i, col)
                        if item:
                            item.setBackground(Qt.lightGray)
            except Exception as e:
                logger.error(f"Error setting dish table row {i}: {str(e)}")

                
    def filter_dishes(self):
        """Filter dishes based on current filter settings."""
        self.update_dishes_table()
        
    def clear_fish_dish_form(self):
        """Clear all inputs in the fish dish form."""
        self.cross_id.clear()
        self.dish_number.setValue(1)
        self.dof.setDate(QDate.currentDate())
        self.genotype.clear()
        self.sex.setCurrentText("unknown")
        self.species.setText("Danio rerio")
        self.responsible.setText("Lab Staff")
        self.parents.clear()
        self.temperature.setValue(28.5)
        self.room.setText("2E.282")
        self.light_duration.setText("14:10")
        self.dawn_dusk.setText("8:00")
        self.beaker_housing.setChecked(False)
        self.fish_count.setValue(1)
        
    def add_fish_dish(self):
        """Add a new fish dish."""
        try:
            # Get input values
            cross_id = self.cross_id.text().strip()
            dish_number = self.dish_number.value()
            genotype = self.genotype.text().strip()
            responsible = self.responsible.text().strip()
            
            # Validate inputs
            if not cross_id:
                QMessageBox.warning(self, "Input Error", "Please enter a cross ID")
                return
                
            if not genotype:
                QMessageBox.warning(self, "Input Error", "Please enter a genotype")
                return
                
            if not responsible:
                QMessageBox.warning(self, "Input Error", "Please enter a responsible person")
                return
                
            # Format date
            dof = self.dof.date().toString("yyyyMMdd")
            
            # Get parents as list
            parents_text = self.parents.text().strip()
            parents = [p.strip() for p in parents_text.split(",")] if parents_text else []
            
            # Create dish
            success, message, dish = fish_dish_controller.create_dish(
                cross_id=cross_id,
                dish_number=dish_number,
                genotype=genotype,
                responsible=responsible,
                dof=dof,
                sex=self.sex.currentText(),
                species=self.species.text().strip(),
                fish_count=self.fish_count.value(),
                parents=parents,
                temperature=self.temperature.value(),
                light_duration=self.light_duration.text().strip(),
                dawn_dusk=self.dawn_dusk.text().strip(),
                room=self.room.text().strip(),
                in_beaker=self.beaker_housing.isChecked()
            )
            
            if success:
                # Update table
                self.update_dishes_table()
                
                # Clear form
                self.clear_fish_dish_form()
                
                QMessageBox.information(self, "Success", f"Added new dish: {message}")
            else:
                QMessageBox.warning(self, "Error", f"Failed to add dish: {message}")
                
        except Exception as e:
            logger.error(f"Error adding fish dish: {str(e)}")
            QMessageBox.critical(self, "Error", f"Error adding fish dish: {str(e)}")