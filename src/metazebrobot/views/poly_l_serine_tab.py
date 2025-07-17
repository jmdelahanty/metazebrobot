"""
Poly-L-Serine tab UI component (simplified to match actual data structure).

This module provides the UI for managing poly-L-serine bottles and derivatives.
"""

import logging
from datetime import datetime
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QFormLayout, QGroupBox,
    QLabel, QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QPushButton,
    QDateEdit, QTableWidget, QTableWidgetItem, QMessageBox, QHeaderView,
    QTabWidget, QTextEdit, QCheckBox
)
from PySide6.QtCore import Qt, QDate, Slot

from ..controllers.poly_l_serine_controller import poly_l_serine_controller

logger = logging.getLogger(__name__)


class PolyLSerineTab(QWidget):
    """
    Tab for managing poly-L-serine bottles and derivatives.
    
    This tab provides functionality to:
    - View and manage poly-L-serine bottles (inventory)
    - Create and track poly-L-serine derivatives (aliquots, solutions)
    """
    
    def __init__(self, parent=None):
        """Initialize the poly-L-serine tab."""
        super().__init__(parent)
        
        self.bottle_sort_column = 0
        self.bottle_sort_order = Qt.SortOrder.AscendingOrder
        self.derivative_sort_column = 0
        self.derivative_sort_order = Qt.SortOrder.AscendingOrder
        
        self.setup_ui()
        self.refresh_data()
        
    def setup_ui(self):
        """Set up the user interface."""
        layout = QVBoxLayout(self)
        
        # Create tab widget for bottles and derivatives
        tab_widget = QTabWidget()
        
        # Poly-L-Serine Bottles Tab
        bottles_tab = self.create_bottles_tab()
        tab_widget.addTab(bottles_tab, "Poly-L-Serine Bottles")
        
        # Poly-L-Serine Derivatives Tab
        derivatives_tab = self.create_derivatives_tab()
        tab_widget.addTab(derivatives_tab, "Poly-L-Serine Derivatives")
        
        layout.addWidget(tab_widget)
        
    def create_bottles_tab(self):
        """Create the poly-L-serine bottles management tab."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # Add new bottle form
        form_group = QGroupBox("Add New Poly-L-Serine Bottle")
        form_layout = QGridLayout(form_group)
        
        # Bottle ID
        form_layout.addWidget(QLabel("Bottle ID:"), 0, 0)
        self.bottle_id = QLineEdit()
        self.bottle_id.setPlaceholderText("e.g., RNBM8479")
        form_layout.addWidget(self.bottle_id, 0, 1)
        
        # Manufacturer
        form_layout.addWidget(QLabel("Manufacturer:"), 0, 2)
        self.bottle_manufacturer = QComboBox()
        self.bottle_manufacturer.addItems(["Sigma Aldrich", "Thermo Fisher", "Merck", "Other"])
        self.bottle_manufacturer.setEditable(True)
        form_layout.addWidget(self.bottle_manufacturer, 0, 3)
        
        # Storage Location
        form_layout.addWidget(QLabel("Storage Location:"), 1, 0)
        self.bottle_storage = QLineEdit()
        self.bottle_storage.setText("2E.254")
        form_layout.addWidget(self.bottle_storage, 1, 1)
        
        # Expiration Date
        form_layout.addWidget(QLabel("Expiration Date:"), 1, 2)
        self.bottle_expiration_date = QDateEdit()
        self.bottle_expiration_date.setCalendarPopup(True)
        self.bottle_expiration_date.setDisplayFormat("yyyy-MM-dd")
        # Set default to 1 year from now
        future_date = QDate.currentDate().addYears(1)
        self.bottle_expiration_date.setDate(future_date)
        form_layout.addWidget(self.bottle_expiration_date, 1, 3)
        
        # Date Received (optional)
        form_layout.addWidget(QLabel("Date Received:"), 2, 0)
        self.bottle_received_date = QDateEdit()
        self.bottle_received_date.setCalendarPopup(True)
        self.bottle_received_date.setDisplayFormat("yyyy-MM-dd")
        self.bottle_received_date.setSpecialValueText("Not specified")
        self.bottle_received_date.setDate(QDate.currentDate())
        received_checkbox = QCheckBox("Specify received date")
        received_checkbox.stateChanged.connect(lambda state: self.bottle_received_date.setEnabled(bool(state)))
        self.bottle_received_date.setEnabled(False)
        form_layout.addWidget(received_checkbox, 2, 1)
        form_layout.addWidget(self.bottle_received_date, 2, 2)
        
        # Notes
        form_layout.addWidget(QLabel("Notes:"), 3, 0)
        self.bottle_notes = QLineEdit()
        self.bottle_notes.setPlaceholderText("Optional notes about this bottle")
        form_layout.addWidget(self.bottle_notes, 3, 1, 1, 3)
        
        # Add button
        add_bottle_button = QPushButton("Add Bottle")
        add_bottle_button.clicked.connect(self.add_bottle)
        form_layout.addWidget(add_bottle_button, 4, 0, 1, 2)
        
        # Clear button
        clear_bottle_button = QPushButton("Clear Form")
        clear_bottle_button.clicked.connect(self.clear_bottle_form)
        form_layout.addWidget(clear_bottle_button, 4, 2, 1, 2)
        
        layout.addWidget(form_group)
        
        # Filter controls
        filter_layout = QHBoxLayout()
        filter_layout.addWidget(QLabel("Search:"))
        self.bottle_search = QLineEdit()
        self.bottle_search.setPlaceholderText("Search bottles...")
        self.bottle_search.textChanged.connect(self.filter_bottles)
        filter_layout.addWidget(self.bottle_search)
        
        refresh_bottles_button = QPushButton("Refresh")
        refresh_bottles_button.clicked.connect(self.refresh_bottles_table)
        filter_layout.addWidget(refresh_bottles_button)
        
        filter_layout.addStretch()
        layout.addLayout(filter_layout)
        
        # Bottles table
        self.bottles_table = QTableWidget()
        self.setup_bottles_table()
        layout.addWidget(self.bottles_table)
        
        return widget
        
    def create_derivatives_tab(self):
        """Create the poly-L-serine derivatives management tab."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # Add new derivative form
        form_group = QGroupBox("Create New Poly-L-Serine Derivative")
        form_layout = QGridLayout(form_group)
        
        # Source bottle selection
        form_layout.addWidget(QLabel("Source Bottle:"), 0, 0)
        self.derivative_source_bottle = QComboBox()
        self.update_bottle_dropdown()
        form_layout.addWidget(self.derivative_source_bottle, 0, 1)
        
        # Derivative ID
        form_layout.addWidget(QLabel("Derivative ID:"), 0, 2)
        self.derivative_id = QLineEdit()
        self.derivative_id.setPlaceholderText("e.g., PLS_ALIQUOT_0002")
        form_layout.addWidget(self.derivative_id, 0, 3)
        
        # Type
        form_layout.addWidget(QLabel("Type:"), 1, 0)
        self.derivative_type = QComboBox()
        self.derivative_type.addItems(["aliquot", "solution", "dilution", "other"])
        form_layout.addWidget(self.derivative_type, 1, 1)
        
        # Volume prepared
        form_layout.addWidget(QLabel("Volume (mL):"), 1, 2)
        self.derivative_volume = QDoubleSpinBox()
        self.derivative_volume.setRange(1.0, 1000.0)
        self.derivative_volume.setValue(50.0)
        self.derivative_volume.setSuffix(" mL")
        form_layout.addWidget(self.derivative_volume, 1, 3)
        
        # Prepared by
        form_layout.addWidget(QLabel("Prepared By:"), 2, 0)
        self.derivative_prepared_by = QLineEdit()
        self.derivative_prepared_by.setText("Jeremy Delahanty")
        form_layout.addWidget(self.derivative_prepared_by, 2, 1)
        
        # Storage location
        form_layout.addWidget(QLabel("Storage Location:"), 2, 2)
        self.derivative_storage_location = QLineEdit()
        self.derivative_storage_location.setText("2E.254")
        form_layout.addWidget(self.derivative_storage_location, 2, 3)
        
        # Storage container
        form_layout.addWidget(QLabel("Storage Container:"), 3, 0)
        self.derivative_storage_container = QComboBox()
        self.derivative_storage_container.addItems(["50mL tube", "15mL tube", "1.5mL tube", "other"])
        self.derivative_storage_container.setEditable(True)
        form_layout.addWidget(self.derivative_storage_container, 3, 1)
        
        # Storage expiration
        form_layout.addWidget(QLabel("Storage Expiration:"), 3, 2)
        self.derivative_storage_expiration = QDateEdit()
        self.derivative_storage_expiration.setCalendarPopup(True)
        self.derivative_storage_expiration.setDisplayFormat("yyyy-MM-dd")
        self.derivative_storage_expiration.setSpecialValueText("Same as bottle")
        # Default to 1 year from now
        future_date = QDate.currentDate().addYears(1)
        self.derivative_storage_expiration.setDate(future_date)
        form_layout.addWidget(self.derivative_storage_expiration, 3, 3)
        
        # Notes
        form_layout.addWidget(QLabel("Notes:"), 4, 0)
        self.derivative_notes = QLineEdit()
        self.derivative_notes.setPlaceholderText("Optional notes")
        form_layout.addWidget(self.derivative_notes, 4, 1, 1, 3)
        
        # Add button
        add_derivative_button = QPushButton("Create Derivative")
        add_derivative_button.clicked.connect(self.add_derivative)
        form_layout.addWidget(add_derivative_button, 5, 0, 1, 2)
        
        # Clear button
        clear_derivative_button = QPushButton("Clear Form")
        clear_derivative_button.clicked.connect(self.clear_derivative_form)
        form_layout.addWidget(clear_derivative_button, 5, 2, 1, 2)
        
        layout.addWidget(form_group)
        
        # Filter controls for derivatives
        derivative_filter_layout = QHBoxLayout()
        derivative_filter_layout.addWidget(QLabel("Search:"))
        self.derivative_search = QLineEdit()
        self.derivative_search.setPlaceholderText("Search derivatives...")
        self.derivative_search.textChanged.connect(self.filter_derivatives)
        derivative_filter_layout.addWidget(self.derivative_search)
        
        derivative_filter_layout.addWidget(QLabel("Type:"))
        self.derivative_type_filter = QComboBox()
        self.derivative_type_filter.addItems(["All", "aliquot", "solution", "dilution", "other"])
        self.derivative_type_filter.currentTextChanged.connect(self.filter_derivatives)
        derivative_filter_layout.addWidget(self.derivative_type_filter)
        
        refresh_derivatives_button = QPushButton("Refresh")
        refresh_derivatives_button.clicked.connect(self.refresh_derivatives_table)
        derivative_filter_layout.addWidget(refresh_derivatives_button)
        
        derivative_filter_layout.addStretch()
        layout.addLayout(derivative_filter_layout)
        
        # Derivatives table
        self.derivatives_table = QTableWidget()
        self.setup_derivatives_table()
        layout.addWidget(self.derivatives_table)
        
        return widget
    
    def setup_bottles_table(self):
        """Setup the poly-L-serine bottles table."""
        self.bottles_table.setColumnCount(5)
        self.bottles_table.setHorizontalHeaderLabels([
            "Bottle ID", "Manufacturer", "Storage Location", "Expiration Date", "Date Received"
        ])
        
        self.bottles_table.setAlternatingRowColors(True)
        self.bottles_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.bottles_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.bottles_table.verticalHeader().setVisible(False)
        self.bottles_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        
        header = self.bottles_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)  # Manufacturer
        
        self.bottles_table.setSortingEnabled(True)
        header.sectionClicked.connect(self.handle_bottle_header_click)
        
    def setup_derivatives_table(self):
        """Setup the poly-L-serine derivatives table."""
        self.derivatives_table.setColumnCount(7)
        self.derivatives_table.setHorizontalHeaderLabels([
            "Derivative ID", "Source Bottle", "Type", "Volume (mL)", "Storage Location", "Container", "Date Prepared"
        ])
        
        self.derivatives_table.setAlternatingRowColors(True)
        self.derivatives_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.derivatives_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.derivatives_table.verticalHeader().setVisible(False)
        self.derivatives_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        
        header = self.derivatives_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)  # Derivative ID
        
        self.derivatives_table.setSortingEnabled(True)
        header.sectionClicked.connect(self.handle_derivative_header_click)
    
    def handle_bottle_header_click(self, column):
        """Handle clicks on the bottle table header for sorting."""
        if self.bottle_sort_column == column:
            self.bottle_sort_order = Qt.SortOrder.DescendingOrder if self.bottle_sort_order == Qt.SortOrder.AscendingOrder else Qt.SortOrder.AscendingOrder
        else:
            self.bottle_sort_column = column
            self.bottle_sort_order = Qt.SortOrder.AscendingOrder
        self.refresh_bottles_table()
    
    def handle_derivative_header_click(self, column):
        """Handle clicks on the derivative table header for sorting."""
        if self.derivative_sort_column == column:
            self.derivative_sort_order = Qt.SortOrder.DescendingOrder if self.derivative_sort_order == Qt.SortOrder.AscendingOrder else Qt.SortOrder.AscendingOrder
        else:
            self.derivative_sort_column = column
            self.derivative_sort_order = Qt.SortOrder.AscendingOrder
        self.refresh_derivatives_table()
    
    @Slot()
    def add_bottle(self):
        """Add a new poly-L-serine bottle."""
        try:
            bottle_id = self.bottle_id.text().strip()
            if not bottle_id:
                QMessageBox.warning(self, "Input Error", "Please enter a Bottle ID")
                return
            
            # Get date_received if checkbox is checked
            date_received = None
            if self.bottle_received_date.isEnabled():
                date_received = self.bottle_received_date.date().toString("yyyyMMdd")
            
            bottle_data = {
                "manufacturer": self.bottle_manufacturer.currentText(),
                "storage_location": self.bottle_storage.text().strip(),
                "expiration_date": self.bottle_expiration_date.date().toString("yyyyMMdd"),
                "date_received": date_received,
                "notes": self.bottle_notes.text().strip() or None
            }
            
            success, message = poly_l_serine_controller.create_bottle(bottle_id, bottle_data)
            
            if success:
                QMessageBox.information(self, "Success", f"Added poly-L-serine bottle: {bottle_id}")
                self.clear_bottle_form()
                self.refresh_bottles_table()
                self.update_bottle_dropdown()
            else:
                QMessageBox.warning(self, "Error", f"Failed to add bottle: {message}")
                
        except Exception as e:
            logger.error(f"Error adding poly-L-serine bottle: {str(e)}")
            QMessageBox.critical(self, "Error", f"An unexpected error occurred: {str(e)}")
    
    @Slot()
    def add_derivative(self):
        """Add a new poly-L-serine derivative."""
        try:
            derivative_id = self.derivative_id.text().strip()
            source_bottle = self.derivative_source_bottle.currentText()
            
            if not derivative_id:
                QMessageBox.warning(self, "Input Error", "Please enter a Derivative ID")
                return
            
            if not source_bottle or source_bottle == "-- No bottles available --":
                QMessageBox.warning(self, "Input Error", "Please select a source bottle")
                return
            
            derivative_data = {
                "source_bottle_id": source_bottle,
                "derivative_type": self.derivative_type.currentText(),
                "volume_prepared": self.derivative_volume.value(),
                "prepared_by": self.derivative_prepared_by.text().strip(),
                "storage_location": self.derivative_storage_location.text().strip(),
                "storage_container": self.derivative_storage_container.currentText(),
                "storage_expiration_date": self.derivative_storage_expiration.date().toString("yyyyMMdd"),
                "notes": self.derivative_notes.text().strip() or None
            }
            
            success, message = poly_l_serine_controller.create_derivative(derivative_id, derivative_data)
            
            if success:
                QMessageBox.information(self, "Success", f"Created poly-L-serine derivative: {derivative_id}")
                self.clear_derivative_form()
                self.refresh_derivatives_table()
            else:
                QMessageBox.warning(self, "Error", f"Failed to create derivative: {message}")
                
        except Exception as e:
            logger.error(f"Error adding poly-L-serine derivative: {str(e)}")
            QMessageBox.critical(self, "Error", f"An unexpected error occurred: {str(e)}")
    
    def clear_bottle_form(self):
        """Clear the bottle form fields."""
        self.bottle_id.clear()
        self.bottle_manufacturer.setCurrentIndex(0)
        self.bottle_storage.setText("2E.254")
        future_date = QDate.currentDate().addYears(1)
        self.bottle_expiration_date.setDate(future_date)
        self.bottle_received_date.setDate(QDate.currentDate())
        self.bottle_notes.clear()
    
    def clear_derivative_form(self):
        """Clear the derivative form fields."""
        self.derivative_id.clear()
        self.derivative_source_bottle.setCurrentIndex(0)
        self.derivative_type.setCurrentIndex(0)
        self.derivative_volume.setValue(50.0)
        self.derivative_prepared_by.setText("Jeremy Delahanty")
        self.derivative_storage_location.setText("2E.254")
        self.derivative_storage_container.setCurrentIndex(0)
        future_date = QDate.currentDate().addYears(1)
        self.derivative_storage_expiration.setDate(future_date)
        self.derivative_notes.clear()
    
    def update_bottle_dropdown(self):
        """Update the source bottle dropdown for derivatives."""
        current_selection = self.derivative_source_bottle.currentText()
        self.derivative_source_bottle.clear()
        
        try:
            bottles = poly_l_serine_controller.get_all_bottles()
            if bottles:
                bottle_ids = sorted(bottles.keys(), reverse=True)  # Most recent first
                self.derivative_source_bottle.addItems(bottle_ids)
                
                # Restore selection if it still exists
                index = self.derivative_source_bottle.findText(current_selection)
                if index >= 0:
                    self.derivative_source_bottle.setCurrentIndex(index)
            else:
                self.derivative_source_bottle.addItem("-- No bottles available --")
                
        except Exception as e:
            logger.error(f"Error updating bottle dropdown: {e}")
            self.derivative_source_bottle.addItem("-- Error loading bottles --")
    
    def refresh_data(self):
        """Refresh all data."""
        self.refresh_bottles_table()
        self.refresh_derivatives_table()
        self.update_bottle_dropdown()
    
    def refresh_bottles_table(self):
        """Refresh the bottles table."""
        try:
            all_bottles = poly_l_serine_controller.get_all_bottles()
            filtered_bottles = self.apply_bottle_filters(all_bottles)
            sorted_bottles = self.apply_bottle_sorting(filtered_bottles)
            self.populate_bottles_table(sorted_bottles)
        except Exception as e:
            logger.error(f"Error refreshing bottles table: {str(e)}")
            QMessageBox.warning(self, "Error", f"Error refreshing bottles: {str(e)}")
    
    def refresh_derivatives_table(self):
        """Refresh the derivatives table."""
        try:
            all_derivatives = poly_l_serine_controller.get_all_derivatives()
            filtered_derivatives = self.apply_derivative_filters(all_derivatives)
            sorted_derivatives = self.apply_derivative_sorting(filtered_derivatives)
            self.populate_derivatives_table(sorted_derivatives)
        except Exception as e:
            logger.error(f"Error refreshing derivatives table: {str(e)}")
            QMessageBox.warning(self, "Error", f"Error refreshing derivatives: {str(e)}")
    
    def apply_bottle_filters(self, bottles):
        """Apply filters to bottles."""
        result = bottles
        
        # Search filter
        search_text = self.bottle_search.text().strip()
        if search_text:
            result = poly_l_serine_controller.search_bottles(result, search_text)
        
        return result
    
    def apply_derivative_filters(self, derivatives):
        """Apply filters to derivatives."""
        result = derivatives
        
        # Search filter
        search_text = self.derivative_search.text().strip()
        if search_text:
            result = poly_l_serine_controller.search_derivatives(result, search_text)
        
        # Type filter
        type_filter = self.derivative_type_filter.currentText()
        if type_filter != "All":
            result = poly_l_serine_controller.filter_derivatives(result, lambda deriv: deriv.type == type_filter)
        
        return result
    
    def apply_bottle_sorting(self, bottles):
        """Apply sorting to bottles."""
        column_to_key = {
            0: "manufacturer",  # Bottle ID column -> use manufacturer as identifier
            1: "manufacturer", 
            2: "storage_location",
            3: "expiration_date",
            4: "date_received"
        }
        sort_key = column_to_key.get(self.bottle_sort_column, "manufacturer")
        ascending = (self.bottle_sort_order == Qt.SortOrder.AscendingOrder)
        return poly_l_serine_controller.sort_bottles(bottles, sort_key, ascending)
    
    def apply_derivative_sorting(self, derivatives):
        """Apply sorting to derivatives."""
        column_to_key = {
            0: "source_bottle_id",  # Derivative ID column -> use source_bottle_id as identifier
            1: "source_bottle_id",
            2: "type", 
            3: "volume_prepared",
            4: "storage_location",
            5: "storage_container",
            6: "date_prepared"
        }
        sort_key = column_to_key.get(self.derivative_sort_column, "source_bottle_id")
        ascending = (self.derivative_sort_order == Qt.SortOrder.AscendingOrder)
        return poly_l_serine_controller.sort_derivatives(derivatives, sort_key, ascending)
    
    def populate_bottles_table(self, bottles):
        """Populate the bottles table."""
        self.bottles_table.setSortingEnabled(False)
        self.bottles_table.setRowCount(len(bottles))
        
        for i, (bottle_id, bottle) in enumerate(bottles.items()):
            try:
                self.bottles_table.setItem(i, 0, QTableWidgetItem(bottle_id))
                self.bottles_table.setItem(i, 1, QTableWidgetItem(str(bottle.manufacturer)))
                self.bottles_table.setItem(i, 2, QTableWidgetItem(str(bottle.storage_location)))
                self.bottles_table.setItem(i, 3, QTableWidgetItem(str(bottle.expiration_date)))
                date_received_text = str(bottle.date_received) if bottle.date_received else "N/A"
                self.bottles_table.setItem(i, 4, QTableWidgetItem(date_received_text))
                
            except Exception as e:
                logger.error(f"Error populating bottle row {i}: {str(e)}")
        
        self.bottles_table.setSortingEnabled(True)
    
    def populate_derivatives_table(self, derivatives):
        """Populate the derivatives table."""
        self.derivatives_table.setSortingEnabled(False)
        self.derivatives_table.setRowCount(len(derivatives))
        
        for i, (derivative_id, derivative) in enumerate(derivatives.items()):
            try:
                self.derivatives_table.setItem(i, 0, QTableWidgetItem(derivative_id))
                self.derivatives_table.setItem(i, 1, QTableWidgetItem(str(derivative.source_bottle_id)))
                self.derivatives_table.setItem(i, 2, QTableWidgetItem(str(derivative.type)))
                self.derivatives_table.setItem(i, 3, QTableWidgetItem(f"{derivative.volume_prepared:.1f}"))
                self.derivatives_table.setItem(i, 4, QTableWidgetItem(str(derivative.storage_location)))
                container_text = str(derivative.storage_container) if derivative.storage_container else "N/A"
                self.derivatives_table.setItem(i, 5, QTableWidgetItem(container_text))
                self.derivatives_table.setItem(i, 6, QTableWidgetItem(str(derivative.date_prepared)))
                
            except Exception as e:
                logger.error(f"Error populating derivative row {i}: {str(e)}")
        
        self.derivatives_table.setSortingEnabled(True)
    
    @Slot()
    def filter_bottles(self):
        """Filter bottles based on current filter settings."""
        self.refresh_bottles_table()
    
    @Slot()
    def filter_derivatives(self):
        """Filter derivatives based on current filter settings."""
        self.refresh_derivatives_table()