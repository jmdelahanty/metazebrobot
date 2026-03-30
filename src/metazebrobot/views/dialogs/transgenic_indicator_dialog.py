"""
Dialog for reviewing and editing transgenic indicators for a PyRAT crossing.

Pre-seeds indicator rows by parsing the strain_name string, then lets the
user review, correct, and fill in color/expected_expression before saving.
"""

import logging
from typing import List, Dict, Optional

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QGroupBox,
    QLabel, QLineEdit, QComboBox, QPushButton, QScrollArea, QWidget,
    QMessageBox
)
from PySide6.QtCore import Qt

from ...utils.strain_parser import parse_strain_name
from ...data.data_manager import data_manager

logger = logging.getLogger(__name__)

COLOR_OPTIONS = ["", "Green", "Red", "Yellow", "Cyan", "Magenta", "Far-Red", "Other"]
MOD_TYPE_OPTIONS = ["tg", "mu", "other"]


class IndicatorRow:
    """Holds the widgets for a single indicator row."""

    def __init__(self):
        self.group = QGroupBox()
        layout = QFormLayout(self.group)
        layout.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)

        self.mod_type = QComboBox()
        self.mod_type.addItems(MOD_TYPE_OPTIONS)
        layout.addRow("Modification Type:", self.mod_type)

        self.promoter = QLineEdit()
        self.promoter.setPlaceholderText("e.g., gfap, elavl3")
        layout.addRow("Promoter/Driver:", self.promoter)

        self.reporter = QLineEdit()
        self.reporter.setPlaceholderText("e.g., TRPV1-T2A-GFP, jRGECO1b")
        layout.addRow("Reporter/Effector:", self.reporter)

        self.color = QComboBox()
        self.color.addItems(COLOR_OPTIONS)
        layout.addRow("Color:", self.color)

        self.expression = QLineEdit()
        self.expression.setPlaceholderText("e.g., pan-glial, pan-neuronal")
        layout.addRow("Expected Expression:", self.expression)

    def set_data(self, data: Dict[str, Optional[str]]):
        """Populate fields from a dict."""
        mod = data.get("modification_type")
        if mod and mod in MOD_TYPE_OPTIONS:
            self.mod_type.setCurrentText(mod)

        self.promoter.setText(data.get("promoter_driver") or "")
        self.reporter.setText(data.get("reporter_effector") or "")

        color = data.get("color") or ""
        if color in COLOR_OPTIONS:
            self.color.setCurrentText(color)

        self.expression.setText(data.get("expected_expression") or "")

    def get_data(self) -> Optional[Dict[str, Optional[str]]]:
        """Collect data from fields. Returns None if reporter is empty."""
        reporter = self.reporter.text().strip()
        if not reporter:
            return None

        return {
            "modification_type": self.mod_type.currentText(),
            "promoter_driver": self.promoter.text().strip() or None,
            "reporter_effector": reporter,
            "color": self.color.currentText() or None,
            "expected_expression": self.expression.text().strip() or None,
        }

    def update_title(self, index: int):
        self.group.setTitle(f"Indicator {index + 1}")


class TransgenicIndicatorDialog(QDialog):
    """Dialog for reviewing/editing transgenic indicators for a crossing."""

    def __init__(self, crossing_id: str, strain_name: str, parent=None):
        super().__init__(parent)
        self.crossing_id = crossing_id
        self.strain_name = strain_name
        self.indicator_rows: List[IndicatorRow] = []

        self.setWindowTitle(f"Transgenic Indicators — Crossing {crossing_id}")
        self.setMinimumWidth(550)
        self.setMinimumHeight(400)
        self.setup_ui()
        self.load_or_seed_indicators()

    def setup_ui(self):
        main_layout = QVBoxLayout(self)

        # Strain reference
        strain_label = QLabel(f"Strain: {self.strain_name}")
        strain_label.setWordWrap(True)
        strain_label.setStyleSheet("font-weight: bold; margin-bottom: 8px;")
        main_layout.addWidget(strain_label)

        # Scroll area for indicator rows
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll_widget = QWidget()
        self.rows_layout = QVBoxLayout(self.scroll_widget)
        self.rows_layout.addStretch()
        self.scroll.setWidget(self.scroll_widget)
        main_layout.addWidget(self.scroll)

        # Add/Remove buttons
        row_buttons = QHBoxLayout()
        add_btn = QPushButton("Add Indicator")
        add_btn.clicked.connect(self.add_empty_row)
        row_buttons.addWidget(add_btn)
        remove_btn = QPushButton("Remove Last")
        remove_btn.clicked.connect(self.remove_last_row)
        row_buttons.addWidget(remove_btn)
        row_buttons.addStretch()
        main_layout.addLayout(row_buttons)

        # Save/Cancel
        button_layout = QHBoxLayout()
        save_btn = QPushButton("Save")
        save_btn.clicked.connect(self.save_and_accept)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        button_layout.addStretch()
        button_layout.addWidget(save_btn)
        button_layout.addWidget(cancel_btn)
        main_layout.addLayout(button_layout)

    def load_or_seed_indicators(self):
        """Load existing indicators from DB, or seed from strain_name parser."""
        existing = data_manager.get_crossing_indicators(self.crossing_id)

        if existing:
            for ind_data in existing:
                self.add_row(ind_data)
        else:
            parsed = parse_strain_name(self.strain_name)
            if parsed:
                for ind_data in parsed:
                    self.add_row(ind_data)
            else:
                # Non-transgenic strain, add one empty row
                self.add_empty_row()

    def add_row(self, data: Optional[Dict[str, Optional[str]]] = None):
        """Add an indicator row, optionally pre-filled."""
        row = IndicatorRow()
        if data:
            row.set_data(data)
        row.update_title(len(self.indicator_rows))
        self.indicator_rows.append(row)
        # Insert before the stretch
        self.rows_layout.insertWidget(self.rows_layout.count() - 1, row.group)

    def add_empty_row(self):
        self.add_row()

    def remove_last_row(self):
        if not self.indicator_rows:
            return
        row = self.indicator_rows.pop()
        self.rows_layout.removeWidget(row.group)
        row.group.deleteLater()
        # Re-number remaining rows
        for i, r in enumerate(self.indicator_rows):
            r.update_title(i)

    def save_and_accept(self):
        """Collect data from all rows and save to DB."""
        indicators = []
        for i, row in enumerate(self.indicator_rows):
            data = row.get_data()
            if data:
                indicators.append(data)
            elif row.reporter.text().strip() == "" and (
                row.promoter.text().strip() or row.expression.text().strip()
            ):
                QMessageBox.warning(
                    self, "Input Error",
                    f"Indicator {i + 1}: Reporter/Effector is required if other fields are filled."
                )
                return

        if data_manager.save_crossing_indicators(self.crossing_id, indicators):
            logger.info(f"Saved {len(indicators)} indicators for crossing {self.crossing_id}")
            self.accept()
        else:
            QMessageBox.critical(self, "Error", "Failed to save indicators.")
