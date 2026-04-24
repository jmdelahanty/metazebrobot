"""
Termination dialog for fish dishes.

This dialog is used to update the status of a fish dish, particularly for terminating it.
Supports both single-dish and batch termination modes.
"""

import logging
from datetime import datetime
from typing import List, Optional
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QComboBox, QDateEdit, QPushButton
)
from PySide6.QtCore import QDate, Qt

from ...models.fish_dish import (
    TERMINATION_REASON_OPTIONS,
    normalize_termination_reason,
)

logger = logging.getLogger(__name__)


class TerminationDialog(QDialog):
    """Dialog for updating fish dish status."""

    def __init__(self, parent=None, batch_dish_ids: Optional[List[str]] = None):
        """Initialize the dialog.

        Args:
            parent: Parent widget.
            batch_dish_ids: If provided, enables batch mode for these dish IDs.
        """
        super().__init__(parent)
        self.batch_dish_ids = batch_dish_ids
        if batch_dish_ids and len(batch_dish_ids) > 1:
            self.setWindowTitle(f"Terminate {len(batch_dish_ids)} Dishes")
        else:
            self.setWindowTitle("Update Dish Status")
        self.setMinimumWidth(400)
        self.setup_ui()

    def setup_ui(self):
        """Set up the user interface."""
        layout = QVBoxLayout(self)

        # Batch mode header showing affected dishes
        if self.batch_dish_ids and len(self.batch_dish_ids) > 1:
            header = QLabel(f"The following {len(self.batch_dish_ids)} dishes will be updated:")
            header.setStyleSheet("font-weight: bold; margin-bottom: 4px;")
            layout.addWidget(header)
            dishes_label = QLabel(", ".join(self.batch_dish_ids))
            dishes_label.setWordWrap(True)
            dishes_label.setStyleSheet("color: #555; margin-bottom: 8px;")
            layout.addWidget(dishes_label)

        form_layout = QFormLayout()

        # Status selection
        self.status = QComboBox()
        self.status.addItems(["active", "inactive"])
        form_layout.addRow("Status:", self.status)

        # Termination date (only enabled if status is inactive)
        self.termination_date = QDateEdit()
        self.termination_date.setDate(QDate.currentDate())
        self.termination_date.setCalendarPopup(True)
        self.termination_date.setEnabled(False)
        form_layout.addRow("Termination Date:", self.termination_date)

        # Termination reason (only enabled if status is inactive)
        self.termination_reason = QComboBox()
        for reason in TERMINATION_REASON_OPTIONS:
            self.termination_reason.addItem(reason["label"], reason["value"])
        self.termination_reason.setEnabled(False)
        form_layout.addRow("Termination Reason:", self.termination_reason)

        # Connect status change to enable/disable termination fields
        self.status.currentTextChanged.connect(self.handle_status_change)

        layout.addLayout(form_layout)

        # Buttons
        button_box = QHBoxLayout()
        save_button = QPushButton("Save")
        save_button.clicked.connect(self.accept)
        cancel_button = QPushButton("Cancel")
        cancel_button.clicked.connect(self.reject)

        button_box.addWidget(save_button)
        button_box.addWidget(cancel_button)
        layout.addLayout(button_box)

        # Default to "inactive" in batch mode
        if self.batch_dish_ids and len(self.batch_dish_ids) > 1:
            self.status.setCurrentText("inactive")

    def handle_status_change(self, status):
        """
        Enable or disable termination fields based on status.
        
        Args:
            status: Current status value
        """
        is_inactive = status == "inactive"
        self.termination_date.setEnabled(is_inactive)
        self.termination_reason.setEnabled(is_inactive)

    def get_data(self):
        """
        Return the dialog data.
        
        Returns:
            Dict with status, termination_date, and termination_reason
        """
        status = self.status.currentText()
        return {
            "status": status,
            "termination_date": self.termination_date.date().toString("yyyyMMdd") if status == "inactive" else None,
            "termination_reason": self.termination_reason.currentData() if status == "inactive" else None
        }
        
    def set_data(self, status, termination_date=None, termination_reason=None):
        """
        Set the dialog data.
        
        Args:
            status: Current dish status
            termination_date: Termination date (YYYYMMDD)
            termination_reason: Reason for termination
        """
        self.status.setCurrentText(status)
        
        if termination_date:
            try:
                # Convert YYYYMMDD to QDate
                year = int(termination_date[0:4])
                month = int(termination_date[4:6])
                day = int(termination_date[6:8])
                self.termination_date.setDate(QDate(year, month, day))
            except (ValueError, IndexError):
                # If the date format is invalid, use current date
                self.termination_date.setDate(QDate.currentDate())
        else:
            self.termination_date.setDate(QDate.currentDate())
            
        canonical_reason = normalize_termination_reason(termination_reason)
        if canonical_reason:
            index = self.termination_reason.findData(canonical_reason)
            self.termination_reason.setCurrentIndex(index if index >= 0 else 0)
        else:
            self.termination_reason.setCurrentIndex(0)
            
        # Update UI state
        self.handle_status_change(status)
