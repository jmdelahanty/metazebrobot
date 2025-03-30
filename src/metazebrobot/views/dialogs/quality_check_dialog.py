"""
Quality check dialog for fish dishes.

This dialog is used to record quality checks for fish dishes.
"""

import logging
from datetime import datetime, timedelta
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QLineEdit, QCheckBox, QSpinBox, QPushButton,
    QDateEdit, QTimeEdit, QGroupBox
)
from PySide6.QtCore import Signal, Qt, QDate, QTime

logger = logging.getLogger(__name__)


class QualityCheckDialog(QDialog):
    """Dialog for entering quality check data."""
    
    # Define signals
    check_saved = Signal(dict)
    batch_checks_saved = Signal(list)  # New signal for batch entries
    
    def __init__(self, parent=None):
        """Initialize the dialog."""
        super().__init__(parent)
        self.setWindowTitle("Quality Check Entry")
        # Set a fixed size for the dialog
        self.setMinimumWidth(450)
        self.setMinimumHeight(550)
        self.setup_ui()
    
    def setup_ui(self):
        """Set up the user interface."""
        layout = QVBoxLayout(self)
        form_layout = QFormLayout()
        
        # Set wider spacing
        layout.setSpacing(10)
        form_layout.setSpacing(10)
        
        # Date and Time section
        date_group = QGroupBox("Date and Time")
        date_layout = QVBoxLayout(date_group)
        
        # Single date/time controls
        single_date_layout = QHBoxLayout()
        
        # Date field
        self.check_date = QDateEdit()
        self.check_date.setCalendarPopup(True)
        self.check_date.setDisplayFormat("yyyy-MM-dd")  # Display format (not storage format)
        single_date_layout.addWidget(QLabel("Start Date:"))
        single_date_layout.addWidget(self.check_date)
        
        # Time field
        self.check_time = QTimeEdit()
        self.check_time.setDisplayFormat("HH:mm:ss")  # Display format (not storage format)
        single_date_layout.addWidget(QLabel("Time:"))
        single_date_layout.addWidget(self.check_time)
        
        date_layout.addLayout(single_date_layout)
        
        # Batch mode checkbox
        batch_layout = QHBoxLayout()
        self.batch_mode = QCheckBox("Use Date Range")
        self.batch_mode.stateChanged.connect(self.toggle_batch_mode)
        batch_layout.addWidget(self.batch_mode)
        
        # End date (initially hidden)
        self.end_date = QDateEdit()
        self.end_date.setCalendarPopup(True)
        self.end_date.setDisplayFormat("yyyy-MM-dd")
        self.end_date.setEnabled(False)
        batch_layout.addWidget(QLabel("End Date:"))
        batch_layout.addWidget(self.end_date)
        batch_layout.addStretch()
        
        date_layout.addLayout(batch_layout)
        
        # Set current date and time
        self.set_current_time()
        
        # Add a "Now" button to quickly set current time
        now_button = QPushButton("Set Current Date/Time")
        now_button.clicked.connect(self.set_current_time)
        date_layout.addWidget(now_button)
        
        layout.addWidget(date_group)
        
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
    
    def toggle_batch_mode(self, state):
        """Enable or disable batch mode."""
        self.end_date.setEnabled(bool(state))
        # Set end date to start date if it's before
        if self.end_date.date() < self.check_date.date():
            self.end_date.setDate(self.check_date.date())
    
    def set_current_time(self):
        """Set the check date and time to current date and time."""
        now = datetime.now()
        date = QDate(now.year, now.month, now.day)
        self.check_date.setDate(date)
        self.check_time.setTime(QTime(now.hour, now.minute, now.second))
        self.end_date.setDate(date)  # Set end date to current date by default

    def handle_save(self):
        """Handle save button click without closing the dialog."""
        if self.batch_mode.isChecked():
            # Get multiple entries for date range
            entries = self.get_batch_data()
            
            # Emit the batch signal
            self.batch_checks_saved.emit(entries)
            
            # Display feedback
            num_entries = len(entries)
            logger.info(f"Created {num_entries} quality check entries")
        else:
            # Get single entry
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
    
    def get_data(self, custom_date=None):
        """
        Return the quality check data as a dictionary.
        
        Args:
            custom_date: Optional custom date to use instead of UI date
            
        Returns:
            Dict containing quality check data
        """
        # Format date and time in ISO 8601 format (YYYYMMDDTHH:MM:SS)
        date = custom_date if custom_date else self.check_date.date()
        date_str = date.toString("yyyyMMdd")
        time_str = self.check_time.time().toString("hh:mm:ss")
        iso_datetime = f"{date_str}T{time_str}"
        
        return {
            "check_time": iso_datetime,
            "fed": self.fed.isChecked(),
            "feed_type": self.feed_type.text() if self.fed.isChecked() else None,
            "water_changed": self.water_changed.isChecked(),
            "vol_water_changed": self.vol_water_changed.value() if self.water_changed.isChecked() else None,
            "num_dead": self.num_dead.value(),
            "notes": self.notes.text() if self.notes.text() else None
        }
    
    def get_batch_data(self):
        """
        Return multiple quality check entries for a date range.
        
        Returns:
            List of dictionaries containing quality check data
        """
        entries = []
        
        # Get date range
        start_date = self.check_date.date()
        end_date = self.end_date.date()
        
        # Ensure end date is not before start date
        if end_date < start_date:
            end_date = start_date
        
        # Create an entry for each date in the range
        current_date = QDate(start_date)
        while current_date <= end_date:
            entries.append(self.get_data(custom_date=current_date))
            current_date = current_date.addDays(1)
        
        return entries
    
    def accept(self) -> None:
        """Override accept to emit signal before accepting."""
        # For single entry
        if not self.batch_mode.isChecked():
            self.check_saved.emit(self.get_data())
        else:
            # For batch entries
            entries = self.get_batch_data()
            self.batch_checks_saved.emit(entries)
        
        # Call parent implementation to accept the dialog
        super().accept()