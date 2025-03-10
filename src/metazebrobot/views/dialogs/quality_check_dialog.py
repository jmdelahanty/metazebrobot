"""
Quality check dialog for fish dishes.

This dialog is used to record quality checks for fish dishes.
"""

import logging
from datetime import datetime
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QLineEdit, QCheckBox, QSpinBox, QPushButton
)
from PySide6.QtCore import Signal, Qt

logger = logging.getLogger(__name__)


class QualityCheckDialog(QDialog):
    """Dialog for entering quality check data."""
    
    # Define a signal for when a check is saved
    check_saved = Signal(dict)
    
    def __init__(self, parent=None):
        """Initialize the dialog."""
        super().__init__(parent)
        self.setWindowTitle("Quality Check Entry")
        # Set a fixed size for the dialog
        self.setMinimumWidth(400)
        self.setMinimumHeight(500)
        self.setup_ui()
    
    def setup_ui(self):
        """Set up the user interface."""
        layout = QVBoxLayout(self)
        form_layout = QFormLayout()
        
        # Set wider spacing
        layout.setSpacing(10)
        form_layout.setSpacing(10)
        
        # Check time (auto-filled with current time)
        self.check_time = QLineEdit()
        current_time = datetime.now().strftime("%Y%m%d%H:%M:%S")
        self.check_time.setText(current_time)
        self.check_time.setPlaceholderText("YYYYMMDDhh:mm:ss")  # Show format
        self.check_time.setReadOnly(False)  # Make it editable
        form_layout.addRow("Check Time:", self.check_time)

        # Add a "Now" button to quickly set current time
        now_button = QPushButton("Set Current Time")
        now_button.clicked.connect(self.set_current_time)
        form_layout.addRow("", now_button)  # Add in new row
        
        # Feeding information
        self.fed = QCheckBox()
        form_layout.addRow("Fed:", self.fed)
        
        self.feed_type = QLineEdit()
        self.feed_type.setEnabled(False)  # Initially disabled
        self.feed_type.setPlaceholderText("e.g., paramecia, dry food")
        form_layout.addRow("Feed Type:", self.feed_type)
        
        # Connect fed checkbox to enable/disable feed type
        self.fed.stateChanged.connect(lambda state: self.feed_type.setEnabled(bool(state)))
        
        # Water change information
        self.water_changed = QCheckBox()
        form_layout.addRow("Water Changed:", self.water_changed)
        
        self.vol_water_changed = QSpinBox()
        self.vol_water_changed.setRange(0, 1000)
        self.vol_water_changed.setSuffix(" mL")
        self.vol_water_changed.setEnabled(False)  # Initially disabled
        form_layout.addRow("Volume Changed:", self.vol_water_changed)
        
        # Connect water changed checkbox to enable/disable volume
        self.water_changed.stateChanged.connect(lambda state: self.vol_water_changed.setEnabled(bool(state)))
        
        # Health information
        self.num_dead = QSpinBox()
        self.num_dead.setRange(0, 100)
        form_layout.addRow("Number Dead:", self.num_dead)
        
        # Notes field
        self.notes = QLineEdit()
        self.notes.setPlaceholderText("Any additional observations...")
        form_layout.addRow("Notes:", self.notes)
        
        # Add form to main layout
        layout.addLayout(form_layout)
        
        # Add buttons
        button_layout = QHBoxLayout()
        save_button = QPushButton("Save")
        save_button.clicked.connect(self.handle_save)  # Custom handler
        
        save_close_button = QPushButton("Save and Close")
        save_close_button.clicked.connect(self.accept)
        
        close_button = QPushButton("Close")
        close_button.clicked.connect(self.reject)
        
        button_layout.addWidget(save_button)
        button_layout.addWidget(save_close_button)
        button_layout.addWidget(close_button)
        layout.addLayout(button_layout)
    
    def set_current_time(self):
        """Set the check time to current time."""
        current_time = datetime.now().strftime("%Y%m%d%H:%M:%S")
        self.check_time.setText(current_time)

    def handle_save(self):
        """Handle save button click without closing the dialog."""
        # Get the data
        check_data = self.get_data()
        
        # Emit the signal with the data
        self.check_saved.emit(check_data)
        
        # Clear fields after saving
        self.clear_fields()
        
    def clear_fields(self):
        """Clear all input fields."""
        self.set_current_time()  # Reset to current time
        self.fed.setChecked(False)
        self.feed_type.clear()
        self.water_changed.setChecked(False)
        self.vol_water_changed.setValue(0)
        self.num_dead.setValue(0)
        self.notes.clear()
    
    def get_data(self):
        """
        Return the quality check data as a dictionary.
        
        Returns:
            Dict containing quality check data
        """
        return {
            "check_time": self.check_time.text(),
            "fed": self.fed.isChecked(),
            "feed_type": self.feed_type.text() if self.fed.isChecked() else None,
            "water_changed": self.water_changed.isChecked(),
            "vol_water_changed": self.vol_water_changed.value() if self.water_changed.isChecked() else None,
            "num_dead": self.num_dead.value(),
            "notes": self.notes.text() if self.notes.text() else None
        }
    
    def accept(self) -> None:
        """Override accept to emit signal before accepting."""
        # Emit signal with data
        self.check_saved.emit(self.get_data())
        
        # Call parent implementation to accept the dialog
        super().accept()