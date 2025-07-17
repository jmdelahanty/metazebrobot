"""
Fish Water tab UI component.

This module provides the UI for managing fish water batches and derivatives.
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

from ..controllers.fish_water_controller import fish_water_controller

logger = logging.getLogger(__name__)


class FishWaterTab(QWidget):
    """
    Tab for managing fish water batches and derivatives.
    
    This tab provides functionality to:
    - View and manage fish water batches (sources)
    - Create and track fish water derivatives
    - Monitor water quality and usage
    """
    
    def __init__(self, parent=None):
        """Initialize the fish water tab."""
        super().__init__(parent)
        
        self.batch_sort_column = 0
        self.batch_sort_order = Qt.SortOrder.AscendingOrder
        self.derivative_sort_column = 0
        self.derivative_sort_order = Qt.SortOrder.AscendingOrder
        
        self.setup_ui()
        self.refresh_data()
        
    def setup_ui(self):
        """Set up the user interface."""
        layout = QVBoxLayout(self)
        
        # Create tab widget for batches and derivatives
        tab_widget = QTabWidget()
        
        # Fish Water Batches Tab
        batches_tab = self.create_batches_tab()
        tab_widget.addTab(batches_tab, "Water Batches")
        
        # Fish Water Derivatives Tab
        derivatives_tab = self.create_derivatives_tab()
        tab_widget.addTab(derivatives_tab, "Water Derivatives")
        
        layout.addWidget(tab_widget)
        
    def create_batches_tab(self):
        """Create the fish water batches management tab."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # Add new batch form
        form_group = QGroupBox("Add New Fish Water Batch")
        form_layout = QGridLayout(form_group)
        
        # Batch ID
        form_layout.addWidget(QLabel("Batch ID:"), 0, 0)
        self.batch_id = QLineEdit()
        self.batch_id.setPlaceholderText("e.g., FW_20250117_001")
        form_layout.addWidget(self.batch_id, 0, 1)
        
        # Source
        form_layout.addWidget(QLabel("Source:"), 0, 2)
        self.batch_source = QComboBox()
        self.batch_source.addItems(["Janelia System", "RO Water", "Tap Water", "Distilled Water", "Other"])
        self.batch_source.setEditable(True)
        form_layout.addWidget(self.batch_source, 0, 3)
        
        # Volume (in mL to match existing data)
        form_layout.addWidget(QLabel("Volume (mL):"), 1, 0)
        self.batch_volume = QDoubleSpinBox()
        self.batch_volume.setRange(1.0, 100000.0)
        self.batch_volume.setValue(1000.0)
        self.batch_volume.setSuffix(" mL")
        form_layout.addWidget(self.batch_volume, 1, 1)
        
        # Date prepared (YYYY-MM-DD format to match existing)
        form_layout.addWidget(QLabel("Date Prepared:"), 1, 2)
        self.batch_date = QDateEdit(QDate.currentDate())
        self.batch_date.setCalendarPopup(True)
        self.batch_date.setDisplayFormat("yyyy-MM-dd")
        form_layout.addWidget(self.batch_date, 1, 3)
        
        # Prepared by
        form_layout.addWidget(QLabel("Prepared By:"), 2, 0)
        self.batch_prepared_by = QLineEdit()
        self.batch_prepared_by.setText("Jeremy Delahanty")
        form_layout.addWidget(self.batch_prepared_by, 2, 1, 1, 2)
        
        # Notes
        form_layout.addWidget(QLabel("Notes:"), 3, 0)
        self.batch_notes = QLineEdit()
        self.batch_notes.setPlaceholderText("Optional notes about this batch")
        form_layout.addWidget(self.batch_notes, 3, 1, 1, 3)
        
        # Add button
        add_batch_button = QPushButton("Add Water Batch")
        add_batch_button.clicked.connect(self.add_water_batch)
        form_layout.addWidget(add_batch_button, 4, 0, 1, 2)
        
        # Clear button
        clear_batch_button = QPushButton("Clear Form")
        clear_batch_button.clicked.connect(self.clear_batch_form)
        form_layout.addWidget(clear_batch_button, 4, 2, 1, 2)
        
        layout.addWidget(form_group)
        
        # Filter controls
        filter_layout = QHBoxLayout()
        filter_layout.addWidget(QLabel("Search:"))
        self.batch_search = QLineEdit()
        self.batch_search.setPlaceholderText("Search batches...")
        self.batch_search.textChanged.connect(self.filter_batches)
        filter_layout.addWidget(self.batch_search)
        
        filter_layout.addWidget(QLabel("Source:"))
        self.batch_source_filter = QComboBox()
        self.batch_source_filter.addItems(["All", "Janelia System", "RO Water", "Tap Water", "Distilled Water", "Other"])
        self.batch_source_filter.currentTextChanged.connect(self.filter_batches)
        filter_layout.addWidget(self.batch_source_filter)
        
        refresh_batches_button = QPushButton("Refresh")
        refresh_batches_button.clicked.connect(self.refresh_batches_table)
        filter_layout.addWidget(refresh_batches_button)
        
        filter_layout.addStretch()
        layout.addLayout(filter_layout)
        
        # Batches table
        self.batches_table = QTableWidget()
        self.setup_batches_table()
        layout.addWidget(self.batches_table)
        
        return widget
        
    def create_derivatives_tab(self):
        """Create the fish water derivatives management tab."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # Add new derivative form
        form_group = QGroupBox("Create Fish Water Derivative")
        form_layout = QGridLayout(form_group)
        
        # Base batch selection
        form_layout.addWidget(QLabel("Source Batch:"), 0, 0)
        self.derivative_base_batch = QComboBox()
        self.update_batch_dropdown()
        form_layout.addWidget(self.derivative_base_batch, 0, 1)
        
        # Derivative ID
        form_layout.addWidget(QLabel("Derivative ID:"), 0, 2)
        self.derivative_id = QLineEdit()
        self.derivative_id.setPlaceholderText("e.g., FW_FILTERED_2025_0001")
        form_layout.addWidget(self.derivative_id, 0, 3)
        
        # Type
        form_layout.addWidget(QLabel("Type:"), 1, 0)
        self.derivative_type = QComboBox()
        self.derivative_type.addItems(["filtered", "processed", "treated", "other"])
        self.derivative_type.setEditable(True)
        form_layout.addWidget(self.derivative_type, 1, 1)
        
        # Volume prepared
        form_layout.addWidget(QLabel("Volume (mL):"), 1, 2)
        self.derivative_volume = QDoubleSpinBox()
        self.derivative_volume.setRange(1.0, 10000.0)
        self.derivative_volume.setValue(250.0)
        self.derivative_volume.setSuffix(" mL")
        form_layout.addWidget(self.derivative_volume, 1, 3)
        
        # Storage location
        form_layout.addWidget(QLabel("Storage Location:"), 2, 0)
        self.derivative_storage = QLineEdit()
        self.derivative_storage.setText("2E.260-7-B")
        form_layout.addWidget(self.derivative_storage, 2, 1)
        
        # Prepared by
        form_layout.addWidget(QLabel("Prepared By:"), 2, 2)
        self.derivative_prepared_by = QLineEdit()
        self.derivative_prepared_by.setText("Jeremy Delahanty")
        form_layout.addWidget(self.derivative_prepared_by, 2, 3)
        
        # Date prepared
        form_layout.addWidget(QLabel("Date Prepared:"), 3, 0)
        self.derivative_date = QDateEdit(QDate.currentDate())
        self.derivative_date.setCalendarPopup(True)
        self.derivative_date.setDisplayFormat("yyyy-MM-dd")
        form_layout.addWidget(self.derivative_date, 3, 1)
        
        # Filter type (for filtered derivatives)
        form_layout.addWidget(QLabel("Filter Type:"), 3, 2)
        self.derivative_filter_type = QComboBox()
        self.derivative_filter_type.addItems(["vacuum", "gravity", "pressure", "other"])
        self.derivative_filter_type.setEditable(True)
        form_layout.addWidget(self.derivative_filter_type, 3, 3)
        
        # Filter size
        form_layout.addWidget(QLabel("Filter Size:"), 4, 0)
        self.derivative_filter_size = QComboBox()
        self.derivative_filter_size.addItems(["20um", "10um", "5um", "1um", "0.22um", "other"])
        self.derivative_filter_size.setEditable(True)
        form_layout.addWidget(self.derivative_filter_size, 4, 1)
        
        # Notes
        form_layout.addWidget(QLabel("Notes:"), 4, 2)
        self.derivative_notes = QLineEdit()
        self.derivative_notes.setPlaceholderText("Optional notes")
        form_layout.addWidget(self.derivative_notes, 4, 3)
        
        # Add button
        add_derivative_button = QPushButton("Create Water Derivative")
        add_derivative_button.clicked.connect(self.add_water_derivative)
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
        self.derivative_type_filter.addItems(["All", "filtered", "processed", "treated", "other"])
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
    
    def setup_batches_table(self):
        """Setup the fish water batches table."""
        self.batches_table.setColumnCount(5)
        self.batches_table.setHorizontalHeaderLabels([
            "Batch ID", "Source", "Volume (mL)", "Date Prepared", "Prepared By"
        ])
        
        self.batches_table.setAlternatingRowColors(True)
        self.batches_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.batches_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.batches_table.verticalHeader().setVisible(False)
        self.batches_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        
        header = self.batches_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)  # Batch ID
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)      # Source
        
        self.batches_table.setSortingEnabled(True)
        header.sectionClicked.connect(self.handle_batch_header_click)
        
    def setup_derivatives_table(self):
        """Setup the fish water derivatives table."""
        self.derivatives_table.setColumnCount(6)
        self.derivatives_table.setHorizontalHeaderLabels([
            "Derivative ID", "Source Batch", "Type", "Volume (mL)", "Prepared By", "Date Prepared"
        ])
        
        self.derivatives_table.setAlternatingRowColors(True)
        self.derivatives_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.derivatives_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.derivatives_table.verticalHeader().setVisible(False)
        self.derivatives_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        
        header = self.derivatives_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)  # Derivative ID
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)      # Type
        
        self.derivatives_table.setSortingEnabled(True)
        header.sectionClicked.connect(self.handle_derivative_header_click)
    
    def handle_batch_header_click(self, column):
        """Handle clicks on the batch table header for sorting."""
        if self.batch_sort_column == column:
            self.batch_sort_order = Qt.SortOrder.DescendingOrder if self.batch_sort_order == Qt.SortOrder.AscendingOrder else Qt.SortOrder.AscendingOrder
        else:
            self.batch_sort_column = column
            self.batch_sort_order = Qt.SortOrder.AscendingOrder
        self.refresh_batches_table()
    
    def handle_derivative_header_click(self, column):
        """Handle clicks on the derivative table header for sorting."""
        if self.derivative_sort_column == column:
            self.derivative_sort_order = Qt.SortOrder.DescendingOrder if self.derivative_sort_order == Qt.SortOrder.AscendingOrder else Qt.SortOrder.AscendingOrder
        else:
            self.derivative_sort_column = column
            self.derivative_sort_order = Qt.SortOrder.AscendingOrder
        self.refresh_derivatives_table()
    
    @Slot()
    def add_water_batch(self):
        """Add a new fish water batch."""
        try:
            batch_id = self.batch_id.text().strip()
            if not batch_id:
                QMessageBox.warning(self, "Input Error", "Please enter a Batch ID")
                return
            
            # Collect data to match your existing structure
            batch_data = {
                "source": self.batch_source.currentText(),
                "volume_prepared_mL": self.batch_volume.value(),
                "preparation_date": self.batch_date.date().toString("yyyy-MM-dd"),
                "prepared_by": self.batch_prepared_by.text().strip(),
                "notes": self.batch_notes.text().strip() or None
            }
            
            success, message = fish_water_controller.create_batch(batch_id, batch_data)
            
            if success:
                QMessageBox.information(self, "Success", f"Added fish water batch: {batch_id}")
                self.clear_batch_form()
                self.refresh_batches_table()
                self.update_batch_dropdown()
            else:
                QMessageBox.warning(self, "Error", f"Failed to add batch: {message}")
                
        except Exception as e:
            logger.error(f"Error adding fish water batch: {str(e)}")
            QMessageBox.critical(self, "Error", f"An unexpected error occurred: {str(e)}")
    
    @Slot()
    def add_water_derivative(self):
        """Add a new fish water derivative."""
        try:
            derivative_id = self.derivative_id.text().strip()
            source_batch = self.derivative_base_batch.currentText()
            
            if not derivative_id:
                QMessageBox.warning(self, "Input Error", "Please enter a Derivative ID")
                return
            
            if not source_batch or source_batch == "-- No batches available --":
                QMessageBox.warning(self, "Input Error", "Please select a source batch")
                return
            
            # Collect data to match your existing structure
            derivative_data = {
                "source_batch_id": source_batch,
                "derivative_type": self.derivative_type.currentText(),
                "volume_prepared_mL": self.derivative_volume.value(),
                "storage_location": self.derivative_storage.text().strip(),
                "prepared_by": self.derivative_prepared_by.text().strip(),
                "date_prepared": self.derivative_date.date().toString("yyyyMMdd"),
                "filter_type": self.derivative_filter_type.currentText() if self.derivative_type.currentText() == "filtered" else None,
                "filter_size": self.derivative_filter_size.currentText() if self.derivative_type.currentText() == "filtered" else None,
                "visual_inspection": "clear, no particles",  # Default
                "notes": self.derivative_notes.text().strip() or None
            }
            
            success, message = fish_water_controller.create_derivative(derivative_id, derivative_data)
            
            if success:
                QMessageBox.information(self, "Success", f"Created water derivative: {derivative_id}")
                self.clear_derivative_form()
                self.refresh_derivatives_table()
            else:
                QMessageBox.warning(self, "Error", f"Failed to create derivative: {message}")
                
        except Exception as e:
            logger.error(f"Error adding fish water derivative: {str(e)}")
            QMessageBox.critical(self, "Error", f"An unexpected error occurred: {str(e)}")
    
    def clear_batch_form(self):
        """Clear the batch form fields."""
        self.batch_id.clear()
        self.batch_source.setCurrentIndex(0)
        self.batch_volume.setValue(1000.0)
        self.batch_date.setDate(QDate.currentDate())
        self.batch_prepared_by.setText("Jeremy Delahanty")
        self.batch_notes.clear()
    
    def clear_derivative_form(self):
        """Clear the derivative form fields."""
        self.derivative_id.clear()
        self.derivative_base_batch.setCurrentIndex(0)
        self.derivative_type.setCurrentIndex(0)
        self.derivative_volume.setValue(250.0)
        self.derivative_storage.setText("2E.260-7-B")
        self.derivative_prepared_by.setText("Jeremy Delahanty")
        self.derivative_date.setDate(QDate.currentDate())
        self.derivative_filter_type.setCurrentIndex(0)
        self.derivative_filter_size.setCurrentIndex(0)
        self.derivative_notes.clear()
    
    def update_batch_dropdown(self):
        """Update the base batch dropdown for derivatives."""
        current_selection = self.derivative_base_batch.currentText()
        self.derivative_base_batch.clear()
        
        try:
            batches = fish_water_controller.get_all_batches()
            if batches:
                batch_ids = sorted(batches.keys(), reverse=True)  # Most recent first
                self.derivative_base_batch.addItems(batch_ids)
                
                # Restore selection if it still exists
                index = self.derivative_base_batch.findText(current_selection)
                if index >= 0:
                    self.derivative_base_batch.setCurrentIndex(index)
            else:
                self.derivative_base_batch.addItem("-- No batches available --")
                
        except Exception as e:
            logger.error(f"Error updating batch dropdown: {e}")
            self.derivative_base_batch.addItem("-- Error loading batches --")
    
    def refresh_data(self):
        """Refresh all data."""
        self.refresh_batches_table()
        self.refresh_derivatives_table()
        self.update_batch_dropdown()
    
    def refresh_batches_table(self):
        """Refresh the batches table."""
        try:
            all_batches = fish_water_controller.get_all_batches()
            filtered_batches = self.apply_batch_filters(all_batches)
            sorted_batches = self.apply_batch_sorting(filtered_batches)
            self.populate_batches_table(sorted_batches)
        except Exception as e:
            logger.error(f"Error refreshing batches table: {str(e)}")
            QMessageBox.warning(self, "Error", f"Error refreshing batches: {str(e)}")
    
    def refresh_derivatives_table(self):
        """Refresh the derivatives table."""
        try:
            all_derivatives = fish_water_controller.get_all_derivatives()
            filtered_derivatives = self.apply_derivative_filters(all_derivatives)
            sorted_derivatives = self.apply_derivative_sorting(filtered_derivatives)
            self.populate_derivatives_table(sorted_derivatives)
        except Exception as e:
            logger.error(f"Error refreshing derivatives table: {str(e)}")
            QMessageBox.warning(self, "Error", f"Error refreshing derivatives: {str(e)}")
    
    def apply_batch_filters(self, batches):
        """Apply filters to batches."""
        result = batches
        
        # Search filter
        search_text = self.batch_search.text().strip()
        if search_text:
            result = fish_water_controller.search_batches(result, search_text)
        
        # Source filter
        source_filter = self.batch_source_filter.currentText()
        if source_filter != "All":
            result = fish_water_controller.filter_batches(result, lambda batch: batch.source == source_filter)
        
        return result
    
    def apply_derivative_filters(self, derivatives):
        """Apply filters to derivatives."""
        result = derivatives
        
        # Search filter
        search_text = self.derivative_search.text().strip()
        if search_text:
            result = fish_water_controller.search_derivatives(result, search_text)
        
        # Type filter
        type_filter = self.derivative_type_filter.currentText()
        if type_filter != "All":
            result = fish_water_controller.filter_derivatives(result, lambda deriv: deriv.type == type_filter)
        
        return result
    
    def apply_batch_sorting(self, batches):
        """Apply sorting to batches with correct field mapping."""
        # Table columns: "Batch ID", "Source", "Volume (mL)", "Date Prepared", "Prepared By"
        column_to_key = {
            0: "source",  # Batch ID column - we'll use source as the identifier
            1: "source", 
            2: "volume_prepared_mL",
            3: "preparation_date",
            4: "prepared_by"
        }
        sort_key = column_to_key.get(self.batch_sort_column, "source")
        ascending = (self.batch_sort_order == Qt.SortOrder.AscendingOrder)
        return fish_water_controller.sort_batches(batches, sort_key, ascending)
    
    def apply_derivative_sorting(self, derivatives):
        """Apply sorting to derivatives with correct field mapping."""
        # Table columns: "Derivative ID", "Source Batch", "Type", "Volume (mL)", "Prepared By", "Date Prepared"
        column_to_key = {
            0: "source_batch_id",  # Derivative ID column - use source_batch_id as identifier
            1: "source_batch_id",
            2: "type", 
            3: "volume_prepared_mL",
            4: "prepared_by",
            5: "date_prepared"
        }
        sort_key = column_to_key.get(self.derivative_sort_column, "source_batch_id")
        ascending = (self.derivative_sort_order == Qt.SortOrder.AscendingOrder)
        return fish_water_controller.sort_derivatives(derivatives, sort_key, ascending)
    
    def populate_batches_table(self, batches):
        """Populate the batches table."""
        self.batches_table.setSortingEnabled(False)
        self.batches_table.setRowCount(len(batches))
        
        for i, (batch_id, batch) in enumerate(batches.items()):
            try:
                self.batches_table.setItem(i, 0, QTableWidgetItem(batch_id))
                self.batches_table.setItem(i, 1, QTableWidgetItem(str(batch.source)))
                # Handle volume - might be None for existing data
                volume_text = f"{batch.volume_prepared_mL:.1f}" if batch.volume_prepared_mL else "N/A"
                self.batches_table.setItem(i, 2, QTableWidgetItem(volume_text))
                self.batches_table.setItem(i, 3, QTableWidgetItem(str(batch.preparation_date)))
                # Handle prepared_by - might be None for existing data
                prepared_by_text = str(batch.prepared_by) if batch.prepared_by else "N/A"
                self.batches_table.setItem(i, 4, QTableWidgetItem(prepared_by_text))
                
            except Exception as e:
                logger.error(f"Error populating batch row {i}: {str(e)}")
        
        self.batches_table.setSortingEnabled(True)
    
    def populate_derivatives_table(self, derivatives):
        """Populate the derivatives table."""
        self.derivatives_table.setSortingEnabled(False)
        self.derivatives_table.setRowCount(len(derivatives))
        
        for i, (derivative_id, derivative) in enumerate(derivatives.items()):
            try:
                self.derivatives_table.setItem(i, 0, QTableWidgetItem(derivative_id))
                self.derivatives_table.setItem(i, 1, QTableWidgetItem(str(derivative.source_batch_id)))
                self.derivatives_table.setItem(i, 2, QTableWidgetItem(str(derivative.type)))
                self.derivatives_table.setItem(i, 3, QTableWidgetItem(f"{derivative.volume_prepared_mL:.1f}"))
                self.derivatives_table.setItem(i, 4, QTableWidgetItem(str(derivative.prepared_by)))
                self.derivatives_table.setItem(i, 5, QTableWidgetItem(str(derivative.date_prepared)))
                
            except Exception as e:
                logger.error(f"Error populating derivative row {i}: {str(e)}")
        
        self.derivatives_table.setSortingEnabled(True)
    
    @Slot()
    def filter_batches(self):
        """Filter batches based on current filter settings."""
        self.refresh_batches_table()
    
    @Slot()
    def filter_derivatives(self):
        """Filter derivatives based on current filter settings."""
        self.refresh_derivatives_table()