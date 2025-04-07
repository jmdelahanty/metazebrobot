"""
Export dialog for MetaZebrobot.

This module provides a dialog for exporting data from the application.
It is located in the dialogs package.
"""

import logging
import os
from pathlib import Path
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QLineEdit, QCheckBox, QPushButton,
    QFileDialog, QMessageBox, QGroupBox, QRadioButton
)
from PySide6.QtCore import Qt

from metazebrobot.utils.export_module import (
    export_survivability_report, export_survivability_summary,
    export_lineage_json)

from metazebrobot.data.data_manager import data_manager

logger = logging.getLogger(__name__)


class ExportDialog(QDialog):
    """
    Dialog for exporting data from MetaZebrobot.
    
    This dialog provides options for exporting various types of data.
    """
    
    def __init__(self, parent=None):
        """Initialize the dialog."""
        super().__init__(parent)
        self.setWindowTitle("Export Data")
        self.setMinimumWidth(500)
        self.setMinimumHeight(300)
        self.setup_ui()
        
    def setup_ui(self):
        """Set up the user interface."""
        layout = QVBoxLayout(self)

        # Create export type selection group
        export_type_group = QGroupBox("Export Type")
        export_type_layout = QVBoxLayout(export_type_group)

        # Radio buttons for export type
        self.export_detail = QRadioButton("Detailed Survivability Report (.csv)") # Added format
        self.export_detail.setChecked(True)
        export_type_layout.addWidget(self.export_detail)

        self.export_summary = QRadioButton("Summarized Survivability Report (.csv)") # Added format
        export_type_layout.addWidget(self.export_summary)

        self.export_both = QRadioButton("Both Survivability Reports (.csv)") # Added format
        export_type_layout.addWidget(self.export_both)

        self.export_lineage = QRadioButton("Lineage/Flow Data (.json)") # New radio button
        export_type_layout.addWidget(self.export_lineage)

        layout.addWidget(export_type_group)

        # Create form layout for file paths
        form_layout = QFormLayout()

        # Detailed report file path
        self.detailed_path_label = QLabel("Detailed Report Path:") # Create the label and assign to self
        self.detailed_path = QLineEdit()
        self.detailed_path.setText(os.path.join(os.path.expanduser("~"), "survivability_report.csv"))
        browse_detailed = QPushButton("Browse...")
        browse_detailed.clicked.connect(self.browse_detailed_path)
        detailed_layout = QHBoxLayout()
        detailed_layout.addWidget(self.detailed_path)
        detailed_layout.addWidget(browse_detailed)
        # Use the label variable here in addRow
        form_layout.addRow(self.detailed_path_label, detailed_layout)

        # Summary report file path
        self.summary_path_label = QLabel("Summary Report Path:") # Create the label and assign to self
        self.summary_path = QLineEdit()
        self.summary_path.setText(os.path.join(os.path.expanduser("~"), "survivability_summary.csv"))
        browse_summary = QPushButton("Browse...")
        browse_summary.clicked.connect(self.browse_summary_path)
        summary_layout = QHBoxLayout()
        summary_layout.addWidget(self.summary_path)
        summary_layout.addWidget(browse_summary)
        # Use the label variable here in addRow
        form_layout.addRow(self.summary_path_label, summary_layout)
        
        self.lineage_path_label = QLabel("Lineage JSON Path:")
        self.lineage_path = QLineEdit()
        self.lineage_path.setText(os.path.join(os.path.expanduser("~"), "dish_lineage.json"))
        browse_lineage = QPushButton("Browse...")
        browse_lineage.clicked.connect(self.browse_lineage_path)
        lineage_layout = QHBoxLayout()
        lineage_layout.addWidget(self.lineage_path)
        lineage_layout.addWidget(browse_lineage)
        form_layout.addRow(self.lineage_path_label, lineage_layout) # Use label ref

        # Add form layout to main layout
        layout.addLayout(form_layout)
        
        # Add information label
        info_label = QLabel(
            "This will export survivability data from all fish dishes in the system. "
            "The detailed report includes data for each quality check, while the summary "
            "report provides aggregated data by cross ID and genotype."
        )
        info_label.setWordWrap(True)
        layout.addWidget(info_label)
        
        # Add spacer
        layout.addSpacing(20)
        
        # Add buttons
        button_layout = QHBoxLayout()
        export_button = QPushButton("Export")
        export_button.clicked.connect(self.export_data)
        
        cancel_button = QPushButton("Cancel")
        cancel_button.clicked.connect(self.reject)
        
        button_layout.addWidget(export_button)
        button_layout.addWidget(cancel_button)
        layout.addLayout(button_layout)
        
        # Connect radio buttons to enable/disable file paths
        self.export_detail.toggled.connect(self.update_ui_state)
        self.export_summary.toggled.connect(self.update_ui_state)
        self.export_both.toggled.connect(self.update_ui_state)
        self.export_lineage.toggled.connect(self.update_ui_state)
        
        # Initial UI state update
        self.update_ui_state()
        
    def update_ui_state(self):
        """Update UI state based on selected export type."""
        detailed_enabled = self.export_detail.isChecked() or self.export_both.isChecked()
        summary_enabled = self.export_summary.isChecked() or self.export_both.isChecked()
        lineage_enabled = self.export_lineage.isChecked() # Check if lineage is selected

        # Enable/disable path inputs
        self.detailed_path.setEnabled(detailed_enabled)
        self.summary_path.setEnabled(summary_enabled)
        self.lineage_path.setEnabled(lineage_enabled)

        # Also hide/show the corresponding labels for clarity
        self.detailed_path_label.setVisible(detailed_enabled)
        self.summary_path_label.setVisible(summary_enabled)
        self.lineage_path_label.setVisible(lineage_enabled)
        
    def browse_detailed_path(self):
        """Open file dialog to select detailed report path."""
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Detailed Report",
            self.detailed_path.text(),
            "CSV Files (*.csv);;All Files (*)"
        )
        
        if file_path:
            self.detailed_path.setText(file_path)
            
    def browse_summary_path(self):
        """Open file dialog to select summary report path."""
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Summary Report",
            self.summary_path.text(),
            "CSV Files (*.csv);;All Files (*)"
        )
        
        if file_path:
            self.summary_path.setText(file_path)

    def browse_lineage_path(self):
            """Open file dialog to select lineage JSON path."""
            file_path, _ = QFileDialog.getSaveFileName(
                self,
                "Save Lineage JSON",
                self.lineage_path.text(),
                "JSON Files (*.json);;All Files (*)"
            )
            if file_path:
                self.lineage_path.setText(file_path)
            
    def export_data(self):
        """Export data based on selected options."""
        try:
            # Determine what to export
            export_detailed = self.export_detail.isChecked() or self.export_both.isChecked()
            export_summary = self.export_summary.isChecked() or self.export_both.isChecked()
            export_lineage = self.export_lineage.isChecked() # Check lineage export

            # Get file paths
            detailed_path = self.detailed_path.text()
            summary_path = self.summary_path.text()
            lineage_path = self.lineage_path.text() # Get lineage path

            # Validate paths based on selection
            if export_detailed and not detailed_path:
                QMessageBox.warning(self, "Error", "Please specify a path for the detailed report")
                return
            if export_summary and not summary_path:
                QMessageBox.warning(self, "Error", "Please specify a path for the summary report")
                return
            if export_lineage and not lineage_path: # Validate lineage path
                QMessageBox.warning(self, "Error", "Please specify a path for the lineage JSON file")
                return

            # Export data
            success_detailed = True
            success_summary = True
            success_lineage = True # Success flag for lineage

            if export_detailed:
                if not export_survivability_report(detailed_path):
                    logger.error("Failed to export detailed report")
                    success_detailed = False

            if export_summary:
                if not export_survivability_summary(summary_path):
                    logger.error("Failed to export summary report")
                    success_summary = False

            if export_lineage: # Call lineage export function
                if not export_lineage_json(lineage_path):
                    logger.error("Failed to export lineage JSON")
                    success_lineage = False

            # Determine overall success
            overall_success = True
            if export_detailed: overall_success &= success_detailed
            if export_summary: overall_success &= success_summary
            if export_lineage: overall_success &= success_lineage

            # Show result message
            if overall_success:
                QMessageBox.information(self, "Success", "Export completed successfully")
                self.accept()
            else:
                # Provide more specific feedback if possible
                error_messages = []
                if export_detailed and not success_detailed: error_messages.append("Failed to export detailed survivability report.")
                if export_summary and not success_summary: error_messages.append("Failed to export summary survivability report.")
                if export_lineage and not success_lineage: error_messages.append("Failed to export lineage JSON.")
                QMessageBox.warning(
                    self,
                    "Export Error",
                    "There were errors during export:\n\n" + "\n".join(error_messages) + "\n\nPlease check the log for details."
                )

        except Exception as e:
            logger.error(f"Error exporting data: {str(e)}", exc_info=True)
            QMessageBox.critical(self, "Error", f"An error occurred during export: {str(e)}")