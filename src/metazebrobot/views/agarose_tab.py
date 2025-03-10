"""
Agarose tab UI component.

This module provides the UI for managing agarose solutions.
"""

import logging
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QDoubleSpinBox, QSpinBox, QComboBox, QPushButton,
    QTableWidget, QTableWidgetItem, QMessageBox
)
from PySide6.QtCore import Qt

from ..controllers.agarose_controller import agarose_controller
from ..data.data_manager import data_manager

logger = logging.getLogger(__name__)


class AgaroseTab(QWidget):
    """
    Tab for managing agarose solutions.
    
    This tab provides UI for creating and viewing agarose solutions.
    """
    
    def __init__(self, parent=None):
        """
        Initialize the agarose tab.
        
        Args:
            parent: Parent widget
        """
        super().__init__(parent)
        self.setup_ui()
        
    def setup_ui(self):
        """Set up the user interface."""
        layout = QVBoxLayout(self)
        
        # Add new solution section
        form_layout = QHBoxLayout()
        
        # Bottle ID input
        bottle_layout = QVBoxLayout()
        bottle_layout.addWidget(QLabel("Agarose Bottle ID:"))
        self.agarose_bottle_id = QLineEdit()
        bottle_layout.addWidget(self.agarose_bottle_id)
        form_layout.addLayout(bottle_layout)
        
        # Concentration input
        conc_layout = QVBoxLayout()
        conc_layout.addWidget(QLabel("Concentration:"))
        self.concentration = QDoubleSpinBox()
        self.concentration.setRange(0, 1)
        self.concentration.setSingleStep(0.01)
        self.concentration.setValue(0.02)
        conc_layout.addWidget(self.concentration)
        form_layout.addLayout(conc_layout)
        
        # Volume input
        volume_layout = QVBoxLayout()
        volume_layout.addWidget(QLabel("Volume (mL):"))
        self.volume = QSpinBox()
        self.volume.setRange(0, 1000)
        self.volume.setValue(100)
        volume_layout.addWidget(self.volume)
        form_layout.addLayout(volume_layout)
        
        # Fish water batch selection
        fw_layout = QVBoxLayout()
        fw_layout.addWidget(QLabel("Fish Water Batch:"))
        self.fw_batch = QComboBox()
        self.update_fw_batches()
        fw_layout.addWidget(self.fw_batch)
        form_layout.addLayout(fw_layout)
        
        # Add solution button
        add_button = QPushButton("Add New Solution")
        add_button.clicked.connect(self.add_agarose_solution)
        form_layout.addWidget(add_button)
        
        layout.addLayout(form_layout)
        
        # Solutions table
        self.solutions_table = QTableWidget()
        self.solutions_table.setColumnCount(7)
        self.solutions_table.setHorizontalHeaderLabels([
            "Solution ID", "Date Prepared", "Concentration", "Volume (mL)",
            "Fish Water Batch", "Storage Location", "Expiration"
        ])
        layout.addWidget(self.solutions_table)
        
        # Set up table properties
        self.solutions_table.setAlternatingRowColors(True)
        self.solutions_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.solutions_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.solutions_table.horizontalHeader().setStretchLastSection(True)
        
        # Initial update of the table
        self.update_solutions_table()
        
    def update_fw_batches(self):
        """Update fish water batch dropdown."""
        self.fw_batch.clear()
        
        # Get fish water batches from data manager
        batches = data_manager.get_fish_water_batches()
        
        for batch_id in batches:
            self.fw_batch.addItem(batch_id)
            
    def update_solutions_table(self):
        """Update the agarose solutions table."""
        # Get all solutions
        solutions = data_manager.get_agarose_solutions()
        
        # Set row count
        self.solutions_table.setRowCount(len(solutions))
        
        # Populate table
        for i, (sol_id, sol_data) in enumerate(solutions.items()):
            self.solutions_table.setItem(i, 0, QTableWidgetItem(sol_id))
            self.solutions_table.setItem(i, 1, QTableWidgetItem(str(sol_data.get('date_prepared', ''))))
            self.solutions_table.setItem(i, 2, QTableWidgetItem(str(sol_data.get('concentration', ''))))
            self.solutions_table.setItem(i, 3, QTableWidgetItem(str(sol_data.get('volume_prepared_mL', ''))))
            self.solutions_table.setItem(i, 4, QTableWidgetItem(str(sol_data.get('fish_water_batch_id', ''))))
            
            # Storage location and expiration may be nested
            storage = sol_data.get('storage', {})
            self.solutions_table.setItem(i, 5, QTableWidgetItem(str(storage.get('location', ''))))
            self.solutions_table.setItem(i, 6, QTableWidgetItem(str(storage.get('expiration', ''))))
            
    def add_agarose_solution(self):
        """Add a new agarose solution."""
        try:
            # Get input values
            bottle_id = self.agarose_bottle_id.text().strip()
            concentration = self.concentration.value()
            volume = self.volume.value()
            
            # Validate inputs
            if not bottle_id:
                QMessageBox.warning(self, "Input Error", "Please enter an agarose bottle ID")
                return
                
            if volume <= 0:
                QMessageBox.warning(self, "Input Error", "Volume must be greater than 0")
                return
                
            # Get selected fish water batch
            fish_water_batch = self.fw_batch.currentText()
            if not fish_water_batch:
                QMessageBox.warning(self, "Input Error", "Please select a fish water batch")
                return
            
            # Create solution using controller
            success, solution_id, solution = agarose_controller.create_solution(
                concentration=concentration,
                agarose_bottle_id=bottle_id,
                fish_water_batch_id=fish_water_batch,
                volume_prepared_mL=volume
            )
            
            if success:
                # Update the table
                self.update_solutions_table()
                
                # Clear inputs
                self.agarose_bottle_id.clear()
                self.volume.setValue(100)
                self.concentration.setValue(0.02)
                
                QMessageBox.information(
                    self, 
                    "Success", 
                    f"Added new solution: {solution_id}"
                )
            else:
                QMessageBox.warning(
                    self, 
                    "Error", 
                    "Failed to add solution. Check the inputs and try again."
                )
                
        except Exception as e:
            logger.error(f"Error adding agarose solution: {str(e)}")
            QMessageBox.critical(
                self, 
                "Error", 
                f"An unexpected error occurred: {str(e)}"
            )