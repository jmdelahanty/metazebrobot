# src/metazebrobot/views/dialogs/update_cross_status_dialog.py

import logging
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QComboBox, QPushButton, QDialogButtonBox
)

# Import the Cross model to get status options
from ...models.cross import Cross

logger = logging.getLogger(__name__)

class UpdateCrossStatusDialog(QDialog):
    """Dialog for updating the status of a Cross."""

    # Get allowed statuses directly from the Cross model's Literal definition
    ALLOWED_STATUSES = ["Requested", "Performed", "Screening", "Completed", "Archived"]

    def __init__(self, current_status: str, parent=None):
        """
        Initialize the dialog.

        Args:
            current_status (str): The current status of the cross.
            parent: Parent widget.
        """
        super().__init__(parent)
        self.setWindowTitle("Update Cross Status")
        self.setMinimumWidth(350)
        self.current_status = current_status
        self.setup_ui()

    def setup_ui(self):
        """Set up the user interface."""
        layout = QVBoxLayout(self)
        form_layout = QFormLayout()

        self.status_combo = QComboBox()
        self.status_combo.addItems(self.ALLOWED_STATUSES)

        # Set the initial selection
        index = self.status_combo.findText(self.current_status)
        if index != -1:
            self.status_combo.setCurrentIndex(index)

        form_layout.addRow("New Status:", self.status_combo)
        layout.addLayout(form_layout)

        # Standard Buttons
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def get_selected_status(self) -> str:
        """Return the selected status from the combobox."""
        return self.status_combo.currentText()