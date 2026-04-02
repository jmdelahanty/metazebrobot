# src/metazebrobot/views/dialogs/screening_dialog.py

import logging
from datetime import datetime
from typing import Optional, List, Dict, Any
import os
from pathlib import Path # Import Path

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QGroupBox, QLabel,
    QLineEdit, QSpinBox, QPushButton, QDateEdit, QTextEdit, QTableWidget,
    QTableWidgetItem, QMessageBox, QHeaderView, QAbstractItemView, QDialogButtonBox,
    QCheckBox, QTimeEdit, QSizePolicy, QComboBox, QScrollArea, QWidget
)
from PySide6.QtCore import Qt, QDate, Slot, QTime
from PySide6.QtGui import QPixmap, QFont

# Import controller, models, and data_manager
from ...controllers.fish_dish_controller import fish_dish_controller
# Import the specific models required
from ...models.fish_dish import FishDish, ScreeningStep # Import ScreeningStep
from ...data.data_manager import data_manager

logger = logging.getLogger(__name__)

class ScreeningDialog(QDialog):
    """Dialog for viewing and managing screening steps for a fish dish."""

    # Define constants for image size constraints
    MAX_IMAGE_WIDTH = 1024
    MAX_IMAGE_HEIGHT = 1024

    def __init__(self, dish_id: str, parent=None):
        """
        Initialize the screening dialog.

        Args:
            dish_id (str): The ID of the dish to manage screening for.
            parent: Parent widget.
        """
        super().__init__(parent)
        self.dish_id = dish_id
        self.dish: Optional[FishDish] = None
        self.dish_dof_str: Optional[str] = None
        self.current_protocol: Optional[Dict[str, Any]] = None
        self.indicator_images: Dict[str, str] = {}
        # Store the base path for config files relative to this script's location
        self.config_base_path = Path(__file__).parent.parent.parent / 'config'


        self.setWindowTitle(f"Screening Details - Dish: {self.dish_id}")

        # --- Set font size for the entire dialog ---
        dialog_font = self.font()
        dialog_font.setPointSize(11) # Set desired point size (e.g., 11)
        self.setFont(dialog_font)
        # --------------------------------------------

        self.setup_ui()
        self.load_dish_data()

    def setup_ui(self):
        """Set up the user interface."""
        main_layout = QVBoxLayout(self)

        # --- Create scroll area for main content ---
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        # Container widget for scrollable content
        scroll_content = QWidget()
        content_layout = QVBoxLayout(scroll_content)

        # --- Top Area: Protocol Text and Image Side-by-Side ---
        top_area_layout = QHBoxLayout()

        # Protocol Display Area
        self.protocol_group = QGroupBox("Recommended Screening Protocol")
        protocol_layout = QVBoxLayout(self.protocol_group)
        self.protocol_display = QTextEdit()
        self.protocol_display.setReadOnly(True)
        self.protocol_display.setPlaceholderText("Loading protocol based on dish genotype...")
        self.protocol_display.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)

        protocol_layout.addWidget(self.protocol_display)

        # --- Reference Image Area (Layout Adjusted) ---
        self.image_group = QGroupBox("Reference Image")
        image_layout = QVBoxLayout(self.image_group) # Vertical layout for this group

        # Label to display the image
        self.reference_image_label = QLabel("No reference image available.")
        self.reference_image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.reference_image_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.reference_image_label.setMinimumSize(500, 600)
        self.reference_image_label.setMaximumSize(self.MAX_IMAGE_WIDTH, self.MAX_IMAGE_HEIGHT)

        # ComboBox to select indicator image
        self.indicator_image_selector = QComboBox()
        self.indicator_image_selector.setToolTip("Select indicator to view reference image")
        self.indicator_image_selector.setEnabled(False) # Disabled initially
        self.indicator_image_selector.currentTextChanged.connect(self.on_indicator_selected)

        # Add widgets to the vertical layout
        image_layout.addWidget(self.reference_image_label) # Image label first
        image_layout.addWidget(self.indicator_image_selector) # ComboBox below label
        image_layout.addStretch(1) # Add stretch *after* widgets to push them up

        # Let the group box expand to fill available space
        self.image_group.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        # Add both widgets to the layout with their respective stretch factors
        top_area_layout.addWidget(self.protocol_group, 1)  # Protocol gets 1 part
        top_area_layout.addWidget(self.image_group, 2)     # Image gets 2 parts (more space)

        content_layout.addLayout(top_area_layout)
        content_layout.setStretchFactor(top_area_layout, 3)  # Give top area higher priority

        # --- Existing Steps Table ---
        existing_group = QGroupBox("Existing Screening Steps")
        existing_layout = QVBoxLayout(existing_group)
        self.steps_table = QTableWidget()
        self.setup_steps_table()
        self.steps_table.setMaximumHeight(200)
        existing_layout.addWidget(self.steps_table)
        content_layout.addWidget(existing_group)

        # --- Add New Step Form ---
        add_step_group = QGroupBox("Add New Screening Step")
        add_step_layout = QFormLayout(add_step_group)
        add_step_layout.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)

        # Date and Time Input
        datetime_layout = QHBoxLayout()
        self.step_date = QDateEdit(QDate.currentDate())
        self.step_date.setCalendarPopup(True)
        self.step_date.setDisplayFormat("yyyy-MM-dd")
        self.step_date.dateChanged.connect(self.update_dpf)
        datetime_layout.addWidget(QLabel("Date:"))
        datetime_layout.addWidget(self.step_date)
        datetime_layout.addSpacing(10)
        self.step_time = QTimeEdit(QTime.currentTime())
        self.step_time.setDisplayFormat("HH:mm:ss")
        datetime_layout.addWidget(QLabel("Time:"))
        datetime_layout.addWidget(self.step_time)
        now_button = QPushButton("Now")
        now_button.clicked.connect(self.set_current_datetime)
        datetime_layout.addWidget(now_button)
        datetime_layout.addStretch()
        add_step_layout.addRow("Screening DateTime:", datetime_layout)

        self.step_dpf = QSpinBox()
        self.step_dpf.setRange(-100, 3650)
        self.step_dpf.setReadOnly(True)
        self.step_dpf.setToolTip("Calculated automatically from Screening Date and Dish DOF")
        self.step_dpf.setEnabled(False)
        add_step_layout.addRow("DPF Screened:", self.step_dpf)

        self.step_indicators = QLineEdit()
        self.step_indicators.setPlaceholderText("Comma-separated, e.g. GFP, jRGECO (leave empty for pigment-only)")
        add_step_layout.addRow("Indicators Screened:", self.step_indicators)

        self.step_pigment_screened = QCheckBox()
        self.step_pigment_screened.setToolTip("Check if pigmentation was assessed this step")
        add_step_layout.addRow("Pigment Screened?", self.step_pigment_screened)

        self.step_criteria = QLineEdit()
        self.step_criteria.setPlaceholderText("e.g. fluorescence, brightest")
        add_step_layout.addRow("Criteria:", self.step_criteria)

        self.step_count_screened = QSpinBox()
        self.step_count_screened.setRange(0, 1000)
        self.step_count_screened.setToolTip("Enter the total number of fish actually screened in this step.")
        add_step_layout.addRow("Total Screened This Step:", self.step_count_screened)

        self.step_number_kept = QSpinBox()
        self.step_number_kept.setRange(0, 1000)
        self.step_number_kept.setToolTip("Enter the number of fish kept (passed all criteria) in this step.")
        add_step_layout.addRow("Number Kept:", self.step_number_kept)

        # --- REMOVAL TRACKING FIELDS ---
        self.step_removed_pigmented = QSpinBox()
        self.step_removed_pigmented.setRange(0, 1000)
        self.step_removed_pigmented.setToolTip("Number of fish removed due to pigmentation.")
        add_step_layout.addRow("Removed (Pigmented):", self.step_removed_pigmented)

        self.step_removed_negative = QSpinBox()
        self.step_removed_negative.setRange(0, 1000)
        self.step_removed_negative.setToolTip("Number of fish removed for being negative for the indicator.")
        add_step_layout.addRow("Removed (Negative):", self.step_removed_negative)

        self.step_removed_other = QSpinBox()
        self.step_removed_other.setRange(0, 1000)
        self.step_removed_other.setToolTip("Number of fish removed for other reasons.")
        add_step_layout.addRow("Removed (Other):", self.step_removed_other)
        # --------------------------------

        self.step_tricaine_used = QCheckBox()
        self.step_tricaine_used.setToolTip("Check if tricaine was used for this screening step")
        add_step_layout.addRow("Tricaine Used?", self.step_tricaine_used)

        self.step_notes = QLineEdit()
        self.step_notes.setPlaceholderText("(Optional) Suggested by protocol or other notes")
        add_step_layout.addRow("Step Notes:", self.step_notes)

        add_step_button = QPushButton("Add Step")
        add_step_button.clicked.connect(self.add_screening_step)
        add_step_layout.addRow(add_step_button)

        content_layout.addWidget(add_step_group)

        # --- Finalize Screening ---
        finalize_group = QGroupBox("Finalize Screening (Optional)")
        finalize_layout = QFormLayout(finalize_group)
        finalize_layout.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        self.final_count = QSpinBox(); self.final_count.setRange(0, 1000); self.final_count.setEnabled(False)
        finalize_layout.addRow("Final Positive Count:", self.final_count)
        self.final_date = QDateEdit(); self.final_date.setCalendarPopup(True); self.final_date.setDisplayFormat("yyyy-MM-dd"); self.final_date.setEnabled(False)
        finalize_layout.addRow("Date Finalized:", self.final_date)
        finalize_button = QPushButton("Save Final Results"); finalize_button.clicked.connect(self.finalize_screening)
        finalize_layout.addRow(finalize_button)
        content_layout.addWidget(finalize_group)

        # --- Create Derived Dish ---
        derive_group = QGroupBox("Create Derived Dish")
        derive_layout = QFormLayout(derive_group)
        derive_layout.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)

        self.derive_fish_count = QSpinBox()
        self.derive_fish_count.setRange(1, 1000)
        self.derive_fish_count.setToolTip("Number of fish going into the new dish")
        derive_layout.addRow("Fish Count:", self.derive_fish_count)

        self.derive_container_type = QComboBox()
        self.derive_container_type.addItems(["(same as parent)", "petri_dish", "beaker", "well_plate", "tank"])
        derive_layout.addRow("Container Type:", self.derive_container_type)

        self.derive_population_type = QComboBox()
        self.derive_population_type.addItems(["positive_screened", "negative_screened", "other"])
        derive_layout.addRow("Population Type:", self.derive_population_type)

        self.derive_notes = QLineEdit()
        self.derive_notes.setPlaceholderText("(optional)")
        derive_layout.addRow("Notes:", self.derive_notes)

        derive_button = QPushButton("Create Derived Dish")
        derive_button.clicked.connect(self.create_derived_dish)
        derive_layout.addRow(derive_button)
        content_layout.addWidget(derive_group)

        # Set the scroll area's widget
        scroll_area.setWidget(scroll_content)
        main_layout.addWidget(scroll_area, 1)  # Give scroll area stretch priority

        # --- Dialog Buttons (outside scroll area) ---
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        button_box.rejected.connect(self.reject)
        main_layout.addWidget(button_box)

    @Slot()
    def set_current_datetime(self):
        """Sets the date and time edits to the current time."""
        self.step_date.setDate(QDate.currentDate())
        self.step_time.setTime(QTime.currentTime())

    def setup_steps_table(self):
        """Configure the appearance and columns of the steps table."""
        self.steps_table.setColumnCount(12)
        self.steps_table.setHorizontalHeaderLabels([
            "DateTime", "DPF", "Indicators", "Pigment?", "Criteria", "Screened", "Kept",
            "Rm Pigment", "Rm Neg", "Rm Other", "Tricaine?", "Notes"
        ])
        # -----------------------------------------
        self.steps_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.steps_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.steps_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.steps_table.setAlternatingRowColors(True)
        self.steps_table.verticalHeader().setVisible(False)

        header = self.steps_table.horizontalHeader()
        # Adjust resize modes for new column layout
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents) # Resize most cols to contents initially
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive) # Allow resizing DateTime
        self.steps_table.setColumnWidth(0, 160) # Give DateTime more space
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch) # Stretch Criteria
        header.setSectionResizeMode(10, QHeaderView.ResizeMode.Stretch) # Stretch Notes (now column 10)


    def load_dish_data(self):
        """Load the dish data, protocols, image map and populate the dialog."""
        logger.info(f"Loading screening data, protocol, and images for dish: {self.dish_id}")
        self.dish = fish_dish_controller.get_dish(self.dish_id)
        self.current_protocol = None
        self.protocol_display.clear()
        self.reference_image_label.setText("Loading...")
        self.reference_image_label.setPixmap(QPixmap()) # Clear pixmap
        self.indicator_image_selector.clear()
        self.indicator_image_selector.setEnabled(False)
        self.indicator_images = data_manager.get_indicator_images() # Load the map

        if not self.dish:
            QMessageBox.critical(self, "Error", f"Could not load data for dish {self.dish_id}.")
            self.setEnabled(False)
            self.dish_dof_str = None
            self.protocol_group.setTitle("Recommended Screening Protocol (Dish not loaded)")
            self.reference_image_label.setText("Dish not loaded.")
            return

        self.dish_dof_str = self.dish.dof
        self.protocol_group.setTitle(f"Recommended Protocol for: {self.dish.genotype}")

        # Load Protocol
        all_protocols = data_manager.get_screening_protocols()
        dish_genotype = self.dish.genotype
        protocol_data = None
        if dish_genotype in all_protocols: protocol_data = all_protocols[dish_genotype]
        else:
            normalized_genotype = dish_genotype.replace("; ", ";") # Handle potential variations
            if normalized_genotype in all_protocols: protocol_data = all_protocols[normalized_genotype]

        if not protocol_data and "_default" in all_protocols:
             protocol_data = all_protocols["_default"]; logger.warning(f"Using default protocol for {dish_genotype}")

        # Process found protocol data
        if protocol_data and isinstance(protocol_data, dict):
            self.current_protocol = protocol_data
            self.display_protocol()
        else:
            logger.warning(f"No protocol found or protocol invalid for genotype: {dish_genotype}")
            self.protocol_display.setPlainText("No screening protocol defined.")
            self.reference_image_label.setText("No protocol found.")

        self.populate_steps_table()
        self.populate_finalize_section()
        self.update_dpf() # Initial calculation, suggestion application, and image load trigger
        self.setEnabled(True)

    def display_protocol(self):
        """Formats and displays the loaded protocol steps."""
        if not self.current_protocol or 'steps' not in self.current_protocol:
            self.protocol_display.setPlainText("No protocol steps loaded or defined.")
            return

        protocol_text = "Recommended Steps:\n"
        protocol_text += "--------------------\n"
        steps = self.current_protocol.get('steps', [])
        if not steps:
             protocol_text += "(No specific steps defined in protocol)\n"

        for step in steps:
            dpf_range = step.get('dpf_range', ['N/A', 'N/A'])
            indicators = ", ".join(step.get('indicators', []))
            criteria = step.get('criteria_suggestion', 'N/A')
            notes = step.get('notes_suggestion', 'N/A')
            protocol_text += f"DPF {dpf_range[0]}-{dpf_range[1]}:\n"
            protocol_text += f"  Indicators: {indicators}\n"
            protocol_text += f"  Criteria: {criteria}\n"
            protocol_text += f"  Notes: {notes}\n"
            protocol_text += "--------------------\n"

        self.protocol_display.setPlainText(protocol_text)

    def display_image(self, relative_image_path: Optional[str]):
        """Loads and displays the image specified by the relative path."""
        self.reference_image_label.setPixmap(QPixmap()) # Clear previous pixmap first
        self.reference_image_label.setText("Loading image...") # Set loading text

        if not relative_image_path:
            self.reference_image_label.setText("No image specified/selected.")
            logger.debug("No relative_image_path provided to display_image.")
            return

        absolute_image_path = self.config_base_path / relative_image_path
        logger.info(f"Attempting to load reference image: {absolute_image_path}")

        pixmap = QPixmap(str(absolute_image_path))

        if pixmap.isNull():
            logger.warning(f"Failed to load image: {absolute_image_path}")
            self.reference_image_label.setText(
                f"Image not found:\n{relative_image_path}\n(relative to metazebrobot/config/)"
            )
            self.reference_image_label.setWordWrap(True)
        else:
            # Scale pixmap to fit the label's size
            scaled_pixmap = pixmap.scaled(
                self.reference_image_label.size(), # Scale to the current size of the label widget
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            self.reference_image_label.setPixmap(scaled_pixmap)
            self.reference_image_label.setText("") # Clear loading/error text
            logger.debug(f"Successfully loaded and displayed image: {absolute_image_path}")


    def populate_steps_table(self):
        """Fill the steps table with data from the loaded dish."""
        self.steps_table.setRowCount(0)
        if not self.dish or not self.dish.screening_results or not self.dish.screening_results.screenings:
            logger.debug(f"No screening steps found for dish {self.dish_id}")
            return

        steps = self.dish.screening_results.screenings
        try:
             # Ensure sorting uses the correct datetime attribute name
             steps.sort(key=lambda x: getattr(x, 'screening_datetime', '19000101T00:00:00'))
        except Exception as e:
             logger.error(f"Error sorting screening steps for dish {self.dish_id}: {e}")

        self.steps_table.setRowCount(len(steps))

        for i, step in enumerate(steps):
            # Handle potential missing attributes gracefully
            datetime_str = getattr(step, 'screening_datetime', 'N/A')
            display_datetime = datetime_str
            if datetime_str != 'N/A':
                try:
                     dt_obj = datetime.strptime(datetime_str, "%Y%m%dT%H:%M:%S")
                     display_datetime = dt_obj.strftime("%Y-%m-%d %H:%M:%S")
                except ValueError:
                     logger.warning(f"Could not parse screening datetime for display: {datetime_str}")
                     display_datetime = datetime_str + " (Invalid Format)"

            self.steps_table.setItem(i, 0, QTableWidgetItem(display_datetime))
            self.steps_table.setItem(i, 1, QTableWidgetItem(str(getattr(step, 'dpf_screened', 'N/A'))))
            indicators = getattr(step, 'indicators_screened', [])
            self.steps_table.setItem(i, 2, QTableWidgetItem(", ".join(indicators) if indicators else "-"))
            pigment = getattr(step, 'pigment_screened', False)
            self.steps_table.setItem(i, 3, QTableWidgetItem("Yes" if pigment else "No"))
            self.steps_table.setItem(i, 4, QTableWidgetItem(getattr(step, 'criteria', '') or "-"))
            self.steps_table.setItem(i, 5, QTableWidgetItem(str(getattr(step, 'count_screened_this_step', 0))))
            self.steps_table.setItem(i, 6, QTableWidgetItem(str(getattr(step, 'number_kept', 0))))
            rm_pigment = getattr(step, 'number_removed_pigmented', None)
            self.steps_table.setItem(i, 7, QTableWidgetItem(str(rm_pigment) if rm_pigment is not None else "-"))
            rm_neg = getattr(step, 'number_removed_negative', None)
            self.steps_table.setItem(i, 8, QTableWidgetItem(str(rm_neg) if rm_neg is not None else "-"))
            rm_other = getattr(step, 'number_removed_other', None)
            self.steps_table.setItem(i, 9, QTableWidgetItem(str(rm_other) if rm_other is not None else "-"))
            tricaine_text = "Yes" if getattr(step, 'tricaine_used', False) else "No"
            self.steps_table.setItem(i, 10, QTableWidgetItem(tricaine_text))
            self.steps_table.setItem(i, 11, QTableWidgetItem(getattr(step, 'notes', "") or ""))

        logger.debug(f"Populated table with {len(steps)} screening steps for dish {self.dish_id}")


    def populate_finalize_section(self):
        """Fill the finalize section with data from the loaded dish."""
        if not self.dish or not self.dish.screening_results:
            self.final_count.setEnabled(True); self.final_date.setEnabled(True)
            self.final_date.setDate(QDate.currentDate()); self.final_count.setValue(0)
            return
        results = self.dish.screening_results
        self.final_count.setEnabled(True); self.final_date.setEnabled(True)
        if results.final_positive_count is not None: self.final_count.setValue(results.final_positive_count)
        else: self.final_count.setValue(0)
        if results.date_finalized:
            try:
                dt_obj = datetime.strptime(results.date_finalized, "%Y%m%d")
                self.final_date.setDate(QDate(dt_obj.year, dt_obj.month, dt_obj.day))
            except ValueError: self.final_date.setDate(QDate.currentDate())
        else: self.final_date.setDate(QDate.currentDate())


    @Slot()
    def update_dpf(self):
        """Calculates DPF based on the screening date and applies protocol suggestions."""
        dpf = None
        if not self.dish_dof_str:
            self.step_dpf.setValue(0)
            self.step_dpf.setEnabled(False)
            logger.warning("DOF string not available for DPF calculation.")
            self.apply_protocol_suggestions(None)
            return

        try:
            dof_date = datetime.strptime(self.dish_dof_str, "%Y%m%d").date()
            screening_qdate = self.step_date.date()
            screening_date = screening_qdate.toPython()
            delta = screening_date - dof_date
            dpf = delta.days

            self.step_dpf.setEnabled(True)
            self.step_dpf.setValue(dpf)
            logger.debug(f"Calculated DPF: {dpf} (Screening: {screening_date}, DOF: {dof_date})")

        except ValueError:
            logger.error(f"Could not parse DOF '{self.dish_dof_str}' or screening date for DPF calculation.")
            self.step_dpf.setValue(0)
            self.step_dpf.setEnabled(False)
            dpf = None
        except Exception as e:
            logger.error(f"Unexpected error calculating DPF: {e}", exc_info=True)
            self.step_dpf.setValue(0)
            self.step_dpf.setEnabled(False)
            dpf = None

        self.apply_protocol_suggestions(dpf)


    def apply_protocol_suggestions(self, current_dpf: Optional[int]):
        """Applies suggestions and populates indicator selector based on DPF."""
        # Reset placeholders if fields are empty
        if not self.step_indicator.text(): self.step_indicator.setPlaceholderText("e.g., GFP, Pigment")
        if not self.step_criteria.text(): self.step_criteria.setPlaceholderText("Brief description of criteria")
        if not self.step_notes.text(): self.step_notes.setPlaceholderText("(Optional) Notes for this step")

        # Reset image and selector
        self.indicator_image_selector.blockSignals(True)
        self.indicator_image_selector.clear()
        self.indicator_image_selector.setEnabled(False)
        self.indicator_image_selector.addItem("-- Select Indicator --") # Add placeholder first
        self.indicator_image_selector.blockSignals(False)
        self.display_image(None) # Clear the image

        matching_step = None
        suggested_indicators = []

        # Find matching protocol step based on DPF
        if current_dpf is not None and self.current_protocol and 'steps' in self.current_protocol:
            protocol_steps = self.current_protocol.get('steps', [])
            for step in protocol_steps:
                dpf_range = step.get('dpf_range')
                if isinstance(dpf_range, list) and len(dpf_range) == 2:
                    try:
                        min_dpf, max_dpf = int(dpf_range[0]), int(dpf_range[1])
                        if min_dpf <= current_dpf <= max_dpf:
                            matching_step = step
                            suggested_indicators = matching_step.get('indicators', [])
                            break # Found the relevant step for this DPF
                    except (ValueError, TypeError):
                        logger.warning(f"Invalid dpf_range found in protocol step: {step}. Skipping.")
                        continue

        # Apply suggestions from the matching step if found
        if matching_step:
            logger.debug(f"Applying protocol suggestions for DPF {current_dpf}")
            # Only apply suggestion if the corresponding field is currently empty
            if suggested_indicators and not self.step_indicator.text():
                self.step_indicator.setText(", ".join(suggested_indicators))
            criteria = matching_step.get('criteria_suggestion')
            if criteria and not self.step_criteria.text():
                self.step_criteria.setText(criteria)
            notes = matching_step.get('notes_suggestion')
            if notes and not self.step_notes.text():
                 self.step_notes.setText(notes)

        # Determine which indicators to add to the selector
        # Prioritize suggested indicators, otherwise use all known indicators
        indicators_to_add = suggested_indicators if suggested_indicators else list(self.indicator_images.keys())

        # Populate the selector
        if indicators_to_add:
            self.indicator_image_selector.blockSignals(True)
            # Items are added after the "-- Select Indicator --" placeholder
            self.indicator_image_selector.addItems(indicators_to_add)
            self.indicator_image_selector.setEnabled(True)
            self.indicator_image_selector.setCurrentIndex(0) # Ensure placeholder is selected
            self.indicator_image_selector.blockSignals(False)
            # Trigger image update based on the default selection (placeholder -> no image)
            self.on_indicator_selected(self.indicator_image_selector.currentText())
        else:
             logger.debug("No suggested or known indicators found to populate selector.")
             # Keep selector disabled and image clear


    @Slot(str)
    def on_indicator_selected(self, selected_indicator: str):
        """Loads the reference image for the selected indicator."""
        if not selected_indicator or selected_indicator == "-- Select Indicator --":
            self.display_image(None) # Clear image if placeholder selected
            return

        logger.debug(f"Indicator selected: {selected_indicator}")
        relative_image_path = self.indicator_images.get(selected_indicator)

        if relative_image_path:
            self.display_image(relative_image_path)
        else:
            logger.warning(f"No image path found in map for indicator: {selected_indicator}")
            self.display_image(None) # Clear image if path not found

    @Slot()
    def add_screening_step(self):
        """Collect data from the 'Add Step' fields, save it, and prompt for splitting."""
        if not self.dish:
            QMessageBox.warning(self, "Error", "Dish data not loaded.")
            return

        indicators_text = self.step_indicators.text().strip()
        indicators_list = [ind.strip() for ind in indicators_text.split(",") if ind.strip()]
        pigment_screened = self.step_pigment_screened.isChecked()
        criteria = self.step_criteria.text().strip()
        count_screened = self.step_count_screened.value()
        number_kept = self.step_number_kept.value()

        # Validation
        if not indicators_list and not pigment_screened:
             QMessageBox.warning(self, "Input Error", "Enter at least one indicator or check 'Pigment Screened'.")
             return
        if count_screened <= 0:
             QMessageBox.warning(self, "Input Error", "Total Screened This Step must be greater than zero.")
             return
        if number_kept > count_screened:
             QMessageBox.warning(self, "Input Error", "Number Kept cannot be greater than Total Screened This Step.")
             return


        date_str = self.step_date.date().toString("yyyyMMdd")
        time_str = self.step_time.time().toString("HH:mm:ss")
        screening_datetime_str = f"{date_str}T{time_str}"

        # Calculate DPF again right before saving
        current_dpf_value = None
        if self.step_dpf.isEnabled():
            current_dpf_value = self.step_dpf.value()
        else:
            self.update_dpf() # Try recalculating
            if self.step_dpf.isEnabled():
                 current_dpf_value = self.step_dpf.value()
            else:
                 QMessageBox.warning(self, "Calculation Error", "Could not calculate DPF. Please check the dish DOF and screening date.")
                 return

        # Prepare data for controller
        # Get removal tracking values (0 means not entered, None if not applicable)
        removed_pigmented = self.step_removed_pigmented.value() or None
        removed_negative = self.step_removed_negative.value() or None
        removed_other = self.step_removed_other.value() or None

        step_data = {
            "screening_datetime": screening_datetime_str,
            "dpf_screened": current_dpf_value,
            "indicators_screened": indicators_list,
            "pigment_screened": pigment_screened,
            "criteria": criteria or None,
            "count_screened_this_step": count_screened,
            "number_kept": number_kept,
            "number_removed_pigmented": removed_pigmented,
            "number_removed_negative": removed_negative,
            "number_removed_other": removed_other,
            "tricaine_used": self.step_tricaine_used.isChecked(),
            "notes": self.step_notes.text().strip() or None
        }

        # Call controller to add the step
        success, message, validated_step_obj = fish_dish_controller.add_screening_step(self.dish_id, step_data)

        if success:
            QMessageBox.information(self, "Success", "Screening step added successfully.")
            self.load_dish_data()
            self.clear_add_step_fields()
        else:
            QMessageBox.critical(self, "Error", f"Failed to add screening step:\n{message}")

    def clear_add_step_fields(self):
        """Clear the input fields for adding a new step."""
        self.set_current_datetime()
        self.step_indicators.clear(); self.step_indicators.setPlaceholderText("e.g. GFP, jRGECO")
        self.step_pigment_screened.setChecked(False)
        self.step_criteria.clear(); self.step_criteria.setPlaceholderText("e.g. fluorescence, brightest")
        self.step_notes.clear(); self.step_notes.setPlaceholderText("(Optional) Notes for this step")
        self.step_count_screened.setValue(0)
        self.step_number_kept.setValue(0)
        self.step_removed_pigmented.setValue(0)
        self.step_removed_negative.setValue(0)
        self.step_removed_other.setValue(0)
        self.step_tricaine_used.setChecked(False)
        # Trigger DPF update and suggestions based on current date/time
        self.update_dpf()

    @Slot()
    def create_derived_dish(self):
        """Create a derived dish from the current dish."""
        if not self.dish:
            QMessageBox.warning(self, "Error", "Dish data not loaded.")
            return

        fish_count = self.derive_fish_count.value()
        population_type = self.derive_population_type.currentText()
        container_text = self.derive_container_type.currentText()
        container_type = None if container_text == "(same as parent)" else container_text
        notes = self.derive_notes.text().strip() or None

        success, message, new_dish = fish_dish_controller.create_derived_dish(
            parent_dish_id=self.dish_id,
            population_type=population_type,
            fish_count=fish_count,
            container_type=container_type,
            notes=notes,
        )

        if success:
            QMessageBox.information(self, "Success", f"Created derived dish: {message}")
            self.derive_fish_count.setValue(1)
            self.derive_container_type.setCurrentIndex(0)
            self.derive_population_type.setCurrentIndex(0)
            self.derive_notes.clear()
        else:
            QMessageBox.critical(self, "Error", f"Failed to create derived dish:\n{message}")

    @Slot()
    def finalize_screening(self):
        """Collect data from the 'Finalize' fields and save it."""
        if not self.dish: QMessageBox.warning(self, "Error", "Dish data not loaded."); return
        final_count = self.final_count.value()
        final_date_str = self.final_date.date().toString("yyyyMMdd")
        success, message = fish_dish_controller.finalize_screening(self.dish_id, final_count=final_count, date_finalized=final_date_str)
        if success: QMessageBox.information(self, "Success", "Screening finalized successfully."); self.load_dish_data() # Reload to reflect finalized status
        else: QMessageBox.critical(self, "Error", f"Failed to finalize screening:\n{message}")
