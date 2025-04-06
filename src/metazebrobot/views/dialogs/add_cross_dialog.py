"""
Dialog for adding a new zebrafish cross.
"""

import logging
from datetime import datetime
from typing import Dict, Optional, List, Any

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QGroupBox, QLabel,
    QLineEdit, QComboBox, QSpinBox, QPushButton, QDateEdit, QTextEdit,
    QMessageBox, QScrollArea, QWidget
)
from PySide6.QtCore import Qt, QDate

# Import model definitions for type hints and validation reference
from ...models.cross import CrossType, Parent, TransgenicIndicator, TransgenicDetails

logger = logging.getLogger(__name__)

class AddCrossDialog(QDialog):
    """Dialog to enter details for a new cross."""

    COLOR_OPTIONS = ["", "Green", "Red", "Yellow", "Cyan", "Magenta", "Far-Red", "Other"]
    MOD_TYPE_OPTIONS = ["tg", "mu", "other"] # Corresponds to Literal

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add New Cross")
        self.setMinimumWidth(600)
        self.setMinimumHeight(650) # Adjusted height

        # Main layout
        main_layout = QVBoxLayout(self)

        # Scroll Area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll_widget = QWidget()
        form_container_layout = QVBoxLayout(scroll_widget) # Layout inside scroll widget

        # --- Core Details ---
        core_group = QGroupBox("Core Information")
        core_layout = QFormLayout(core_group)
        core_layout.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)

        self.cross_id = QLineEdit()
        self.cross_id.setPlaceholderText("e.g., 15238 (must be unique)")
        core_layout.addRow("Cross ID:", self.cross_id)

        self.request_date = QDateEdit(QDate.currentDate())
        self.request_date.setCalendarPopup(True)
        self.request_date.setDisplayFormat("yyyy-MM-dd")
        core_layout.addRow("Request Date:", self.request_date)

        self.responsible_requestor = QLineEdit()
        core_layout.addRow("Responsible Requestor:", self.responsible_requestor)

        self.line_strain = QLineEdit()
        self.line_strain.setPlaceholderText("Overall description, e.g., Tg(gfap:GFP); Tg(elavl3:RFP)")
        core_layout.addRow("Line/Strain:", self.line_strain)

        self.requested_groups = QSpinBox()
        self.requested_groups.setMinimum(1)
        self.requested_groups.setValue(1)
        core_layout.addRow("Requested Groups:", self.requested_groups)

        self.cross_type = QComboBox()
        self.cross_type.addItems(["Standard", "Transgenic"])
        self.cross_type.currentTextChanged.connect(self.toggle_transgenic_inputs)
        core_layout.addRow("Cross Type:", self.cross_type)

        self.cross_status = QComboBox()
        self.cross_status.addItems(["Requested", "Performed", "Screening", "Completed", "Archived"])
        core_layout.addRow("Initial Status:", self.cross_status)

        form_container_layout.addWidget(core_group)


        # --- Parents Details ---
        parents_group = QGroupBox("Parents (Exactly 2 Required)")
        parents_layout = QHBoxLayout(parents_group)
        parent1_group = QGroupBox("Parent 1")
        parent1_layout = QFormLayout(parent1_group)
        self.parent1_id = QLineEdit()
        self.parent1_id.setPlaceholderText("e.g., M11:E5 (5187)")
        self.parent1_sex = QComboBox()
        self.parent1_sex.addItems(["unknown", "M", "F"])
        self.parent1_genotype = QLineEdit()
        self.parent1_genotype.setPlaceholderText("(Optional)")
        parent1_layout.addRow("Identifier:", self.parent1_id)
        parent1_layout.addRow("Sex:", self.parent1_sex)
        parent1_layout.addRow("Genotype:", self.parent1_genotype)
        parents_layout.addWidget(parent1_group)
        parent2_group = QGroupBox("Parent 2")
        parent2_layout = QFormLayout(parent2_group)
        self.parent2_id = QLineEdit()
        self.parent2_id.setPlaceholderText("e.g., M18:C9 (4541)")
        self.parent2_sex = QComboBox()
        self.parent2_sex.addItems(["unknown", "M", "F"])
        self.parent2_genotype = QLineEdit()
        self.parent2_genotype.setPlaceholderText("(Optional)")
        parent2_layout.addRow("Identifier:", self.parent2_id)
        parent2_layout.addRow("Sex:", self.parent2_sex)
        parent2_layout.addRow("Genotype:", self.parent2_genotype)
        parents_layout.addWidget(parent2_group)
        form_container_layout.addWidget(parents_group)


        # --- Transgenic Details (Initially Hidden & Modified UI) ---
        self.transgenic_group = QGroupBox("Transgenic Component Details")
        transgenic_outer_layout = QVBoxLayout(self.transgenic_group)

        # --- Indicator 1 Group ---
        indicator1_group = QGroupBox("Component 1 (Required if Transgenic)")
        transgenic_layout1 = QFormLayout(indicator1_group)
        transgenic_layout1.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)

        self.indicator1_mod_type = QComboBox()
        self.indicator1_mod_type.addItems(self.MOD_TYPE_OPTIONS)
        self.indicator1_promoter = QLineEdit() # Changed from name
        self.indicator1_reporter = QLineEdit() # Changed from name
        self.indicator1_expr = QLineEdit()
        self.indicator1_color = QComboBox()
        self.indicator1_color.addItems(self.COLOR_OPTIONS)

        self.indicator1_promoter.setPlaceholderText("(Optional) e.g., gfap, elavl3")
        self.indicator1_reporter.setPlaceholderText("(Required) e.g., TRPV1-T2A-GFP, jRGECO1b") # Required
        self.indicator1_expr.setPlaceholderText("(Optional) e.g., pan-glial")

        transgenic_layout1.addRow("Modification Type:", self.indicator1_mod_type)
        transgenic_layout1.addRow("Promoter/Driver:", self.indicator1_promoter) # Changed label
        transgenic_layout1.addRow("Reporter/Effector:", self.indicator1_reporter) # Changed label
        transgenic_layout1.addRow("Expected Expression:", self.indicator1_expr)
        transgenic_layout1.addRow("Color:", self.indicator1_color)

        transgenic_outer_layout.addWidget(indicator1_group)

        # --- Indicator 2 Group ---
        indicator2_group = QGroupBox("Component 2 (Optional)")
        transgenic_layout2 = QFormLayout(indicator2_group)
        transgenic_layout2.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)

        self.indicator2_mod_type = QComboBox()
        self.indicator2_mod_type.addItems(self.MOD_TYPE_OPTIONS)
        self.indicator2_promoter = QLineEdit() # Changed from name
        self.indicator2_reporter = QLineEdit() # Changed from name
        self.indicator2_expr = QLineEdit()
        self.indicator2_color = QComboBox()
        self.indicator2_color.addItems(self.COLOR_OPTIONS)

        self.indicator2_promoter.setPlaceholderText("(Optional)")
        self.indicator2_reporter.setPlaceholderText("(Required if adding Component 2)") # Required if adding
        self.indicator2_expr.setPlaceholderText("(Optional)")

        transgenic_layout2.addRow("Modification Type:", self.indicator2_mod_type)
        transgenic_layout2.addRow("Promoter/Driver:", self.indicator2_promoter) # Changed label
        transgenic_layout2.addRow("Reporter/Effector:", self.indicator2_reporter) # Changed label
        transgenic_layout2.addRow("Expected Expression:", self.indicator2_expr)
        transgenic_layout2.addRow("Color:", self.indicator2_color)

        transgenic_outer_layout.addWidget(indicator2_group)

        self.transgenic_group.setVisible(False) # Hide initially
        form_container_layout.addWidget(self.transgenic_group)

        # --- Notes ---
        notes_group = QGroupBox("Notes")
        notes_layout = QVBoxLayout(notes_group)
        self.notes = QTextEdit()
        self.notes.setPlaceholderText("Enter any relevant notes about the cross request or setup...")
        self.notes.setAcceptRichText(False)
        self.notes.setFixedHeight(60)
        notes_layout.addWidget(self.notes)
        form_container_layout.addWidget(notes_group)


        # Add form layout to scroll area
        scroll.setWidget(scroll_widget)
        main_layout.addWidget(scroll)


        # --- Dialog Buttons ---
        button_box = QHBoxLayout()
        save_button = QPushButton("Save Cross")
        save_button.clicked.connect(self.accept)
        cancel_button = QPushButton("Cancel")
        cancel_button.clicked.connect(self.reject)

        button_box.addStretch()
        button_box.addWidget(save_button)
        button_box.addWidget(cancel_button)
        main_layout.addLayout(button_box)


    def toggle_transgenic_inputs(self, cross_type_text: str):
        """Show or hide the transgenic details group based on selection."""
        is_transgenic = (cross_type_text == "Transgenic")
        self.transgenic_group.setVisible(is_transgenic)

    def get_cross_data(self) -> Optional[Dict[str, Any]]:
        """
        Collect data from the form fields and structure it
        into a dictionary suitable for the Cross model.
        """
        cross_data = {}

        # --- Basic Validation ---
        required_fields = {
            "Cross ID": self.cross_id.text().strip(),
            "Responsible Requestor": self.responsible_requestor.text().strip(),
            "Line/Strain": self.line_strain.text().strip(),
            "Parent 1 Identifier": self.parent1_id.text().strip(),
            "Parent 2 Identifier": self.parent2_id.text().strip(),
        }
        for name, value in required_fields.items():
            if not value:
                QMessageBox.warning(self, "Input Error", f"'{name}' field cannot be empty.")
                return None

        # --- Collect Core Data ---
        cross_data["cross_id"] = required_fields["Cross ID"]
        cross_data["request_date"] = self.request_date.date().toString("yyyyMMdd")
        cross_data["responsible_requestor"] = required_fields["Responsible Requestor"]
        cross_data["line_strain"] = required_fields["Line/Strain"]
        cross_data["requested_groups"] = self.requested_groups.value()
        cross_data["cross_type"] = self.cross_type.currentText()
        cross_data["cross_status"] = self.cross_status.currentText()
        notes_text = self.notes.toPlainText().strip()
        if notes_text:
             cross_data["notes"] = notes_text

        # --- Collect Parent Data ---
        parents = [
            {
                "identifier": required_fields["Parent 1 Identifier"],
                "sex": self.parent1_sex.currentText(),
                "genotype": self.parent1_genotype.text().strip() or None,
            },
            {
                "identifier": required_fields["Parent 2 Identifier"],
                "sex": self.parent2_sex.currentText(),
                "genotype": self.parent2_genotype.text().strip() or None,
            }
        ]
        cross_data["parents"] = parents

        # --- Collect Transgenic Data (if applicable) ---
        if cross_data["cross_type"] == "Transgenic":
            indicators = []
            # --- Indicator 1 ---
            ind1_reporter = self.indicator1_reporter.text().strip()
            if not ind1_reporter: # Reporter/Effector is required
                 QMessageBox.warning(self, "Input Error", "Component 1: Reporter/Effector is required for Transgenic crosses.")
                 return None

            indicator1_data = {
                "modification_type": self.indicator1_mod_type.currentText(),
                "promoter_driver": self.indicator1_promoter.text().strip() or None,
                "reporter_effector": ind1_reporter,
                "expected_expression": self.indicator1_expr.text().strip() or None,
            }
            ind1_color = self.indicator1_color.currentText()
            if ind1_color and ind1_color != "Other":
                 indicator1_data["color"] = ind1_color
            elif ind1_color == "Other":
                 indicator1_data["color"] = "Other"
            indicators.append(indicator1_data)

            # --- Indicator 2 (Optional) ---
            ind2_reporter = self.indicator2_reporter.text().strip()
            if ind2_reporter: # Only add indicator 2 if reporter is filled
                 indicator2_data = {
                     "modification_type": self.indicator2_mod_type.currentText(),
                     "promoter_driver": self.indicator2_promoter.text().strip() or None,
                     "reporter_effector": ind2_reporter,
                     "expected_expression": self.indicator2_expr.text().strip() or None,
                 }
                 ind2_color = self.indicator2_color.currentText()
                 if ind2_color and ind2_color != "Other":
                      indicator2_data["color"] = ind2_color
                 elif ind2_color == "Other":
                      indicator2_data["color"] = "Other"
                 indicators.append(indicator2_data)
            # Check if other ind2 fields were filled without reporter
            elif self.indicator2_promoter.text().strip() or \
                 self.indicator2_expr.text().strip() or \
                 (self.indicator2_color.currentText() and self.indicator2_color.currentText() != ""):
                 QMessageBox.warning(self, "Input Error", "Component 2: Reporter/Effector is required if adding a second component.")
                 return None

            if not indicators: # Should not happen if type is Transgenic due to check above, but safeguard
                 QMessageBox.warning(self, "Input Error", "At least one component is required for Transgenic crosses.")
                 return None

            cross_data["transgenic_details"] = {"indicators": indicators}
        else:
             cross_data["transgenic_details"] = None


        logger.debug(f"Collected data from AddCrossDialog: {cross_data}")
        return cross_data

