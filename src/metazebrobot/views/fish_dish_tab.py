# src/metazebrobot/views/fish_dish_tab.py

import logging
from datetime import datetime
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QFormLayout, QGroupBox,
    QLabel, QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QCheckBox,
    QPushButton, QDateEdit, QTableWidget, QTableWidgetItem, QMessageBox,
    QHeaderView, QScrollArea, QDialog
)
from PySide6.QtCore import Qt, QDate, Signal, Slot

from ..controllers.fish_dish_controller import fish_dish_controller
from ..controllers.cross_controller import cross_controller
from ..models.fish_dish import FishDish
from .dialogs.quality_check_dialog import QualityCheckDialog
from .dialogs.termination_dialog import TerminationDialog
from .dialogs.screening_dialog import ScreeningDialog

logger = logging.getLogger(__name__)


class FishDishTab(QWidget):
    """
    Tab for managing fish dishes. Includes functionality to pre-fill
    dish info based on selected cross and displays dish lineage.
    """
    # Define a placeholder text for the combobox
    CROSS_PLACEHOLDER = "-- Select Cross --"

    def __init__(self, parent=None):
        """
        Initialize the fish dish tab.
        """
        super().__init__(parent)

        self.dish_sort_column = 0 # Default sort by Dish ID
        self.dish_sort_order = Qt.SortOrder.AscendingOrder
        self._last_selected_cross_id = self.CROSS_PLACEHOLDER

        self.setup_ui()
        self.update_cross_id_dropdown() # Populate dropdown initially
        self.update_dishes_table() # Populate table initially

    @Slot(str)
    def handle_cross_selection_change(self, selected_cross_id: str):
        """Auto-populate form fields when a cross ID is selected."""
        logger.debug(f"Cross selection changed to: {selected_cross_id}")
        if selected_cross_id != self._last_selected_cross_id:
            self.dish_number.setValue(1)
            self._last_selected_cross_id = selected_cross_id
        if selected_cross_id == self.CROSS_PLACEHOLDER or not selected_cross_id:
            # Clear auto-filled fields if placeholder is selected
            self.genotype.clear()
            self.parents.clear()
            self.responsible.clear()
            return

        try:
            cross = cross_controller.get_cross(selected_cross_id)
            if cross:
                self.genotype.setText(cross.line_strain or "") # Use line_strain for genotype
                parent_str = ", ".join([p.identifier for p in cross.parents]) if cross.parents else ""
                self.parents.setText(parent_str)
                self.responsible.setText(cross.responsible_requestor or "")
            else:
                # Cross not found (might happen if list is stale), clear fields
                logger.warning(f"Selected cross ID '{selected_cross_id}' not found by controller.")
                self.genotype.clear()
                self.parents.clear()
                self.responsible.clear()
        except Exception as e:
             logger.error(f"Error fetching details for cross {selected_cross_id}: {e}", exc_info=True)
             # Clear fields on error
             self.genotype.clear()
             self.parents.clear()
             self.responsible.clear()

    def setup_ui(self):
        """Set up the user interface."""
        layout = QVBoxLayout(self)

        # --- Create scroll area for the form ---
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll_widget = QWidget()
        scroll_layout = QVBoxLayout(scroll_widget)

        # --- Form section ---
        form_group = QGroupBox("New Primary Dish Information") # Clarified title
        form_layout = QGridLayout()
        form_layout.setColumnStretch(1, 1)
        form_layout.setColumnStretch(3, 1)
        form_layout.setHorizontalSpacing(10)
        form_layout.setVerticalSpacing(5)

        row = 0

        # --- Cross ID ComboBox ---
        form_layout.addWidget(QLabel("Cross ID:"), row, 0)
        self.cross_id = QComboBox()
        self.cross_id.setEditable(False)
        self.cross_id.setMinimumContentsLength(10)
        self.cross_id.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        # Connect signal to auto-populate fields
        self.cross_id.currentTextChanged.connect(self.handle_cross_selection_change)
        form_layout.addWidget(self.cross_id, row, 1)

        form_layout.addWidget(QLabel("Genotype:"), row, 2)
        self.genotype = QLineEdit()
        self.genotype.setPlaceholderText("(auto-filled from cross)")
        form_layout.addWidget(self.genotype, row, 3)

        row += 1
        form_layout.addWidget(QLabel("Dish Number:"), row, 0)
        self.dish_number = QSpinBox()
        self.dish_number.setMinimum(1)
        form_layout.addWidget(self.dish_number, row, 1)
        form_layout.addWidget(QLabel("Sex:"), row, 2)
        self.sex = QComboBox()
        self.sex.addItems(["unknown", "M", "F"])
        form_layout.addWidget(self.sex, row, 3)

        row += 1
        form_layout.addWidget(QLabel("Source Group ID:"), row, 0)
        self.source_group_id = QLineEdit()
        self.source_group_id.setPlaceholderText("e.g., 15178-G1 (from aquatics)")
        form_layout.addWidget(self.source_group_id, row, 1)
        form_layout.addWidget(QLabel("Initial Fish Count:"), row, 2) # Changed Label
        self.fish_count = QSpinBox()
        self.fish_count.setRange(0, 1000)
        self.fish_count.setValue(1)
        self.fish_count.setToolTip("Initial estimate for this primary dish.") # Added tooltip
        form_layout.addWidget(self.fish_count, row, 3)

        row += 1
        form_layout.addWidget(QLabel("Date of Fertilization:"), row, 0)
        self.dof = QDateEdit()
        self.dof.setDate(QDate.currentDate())
        self.dof.setCalendarPopup(True)
        self.dof.setDisplayFormat("yyyy-MM-dd")
        form_layout.addWidget(self.dof, row, 1)
        form_layout.addWidget(QLabel("Species:"), row, 2)
        self.species = QLineEdit()
        self.species.setText("Danio rerio")
        form_layout.addWidget(self.species, row, 3)

        row += 1
        form_layout.addWidget(QLabel("Responsible:"), row, 0)
        self.responsible = QLineEdit()
        self.responsible.setPlaceholderText("(auto-filled from cross)")
        form_layout.addWidget(self.responsible, row, 1)
        form_layout.addWidget(QLabel("Parents:"), row, 2)
        self.parents = QLineEdit()
        self.parents.setPlaceholderText("(auto-filled from cross)")
        form_layout.addWidget(self.parents, row, 3)

        row += 1
        form_layout.addWidget(QLabel("Temperature (°C):"), row, 0)
        self.temperature = QDoubleSpinBox()
        self.temperature.setRange(18, 30)
        self.temperature.setValue(28.5)
        self.temperature.setSingleStep(0.5)
        form_layout.addWidget(self.temperature, row, 1)
        form_layout.addWidget(QLabel("Room:"), row, 2)
        self.room = QLineEdit()
        self.room.setText("2E.282")
        form_layout.addWidget(self.room, row, 3)

        row += 1
        form_layout.addWidget(QLabel("Light Duration:"), row, 0)
        self.light_duration = QLineEdit()
        self.light_duration.setText("14:10")
        form_layout.addWidget(self.light_duration, row, 1)
        form_layout.addWidget(QLabel("Dawn/Dusk Time:"), row, 2)
        self.dawn_dusk = QLineEdit()
        self.dawn_dusk.setText("8:00")
        form_layout.addWidget(self.dawn_dusk, row, 3)

        row += 1
        form_layout.addWidget(QLabel("In a beaker?"), row, 0)
        self.beaker_housing = QCheckBox()
        self.beaker_housing.setChecked(False)
        form_layout.addWidget(self.beaker_housing, row, 1)
        form_layout.addWidget(QLabel("Volume Water Total (mL):"), row, 2) # Moved Label
        self.vol_water_total = QLineEdit()
        self.vol_water_total.setPlaceholderText("e.g., 80")
        form_layout.addWidget(self.vol_water_total, row, 3) # Moved Field


        row += 1
        form_layout.addWidget(QLabel("Dish Notes:"), row, 0)
        self.notes = QLineEdit()
        self.notes.setPlaceholderText("(Optional) General notes for this dish")
        form_layout.addWidget(self.notes, row, 1, 1, 3) # Span notes across columns
        # --- End Form Fields ---

        form_group.setLayout(form_layout)
        scroll_layout.addWidget(form_group)

        # --- Add/Clear Buttons for Form ---
        button_layout = QHBoxLayout()
        add_button = QPushButton("Add New Primary Dish") # Clarified button text
        add_button.clicked.connect(self.add_fish_dish)
        button_layout.addWidget(add_button)
        clear_button = QPushButton("Clear Form")
        clear_button.clicked.connect(self.clear_fish_dish_form)
        button_layout.addWidget(clear_button)
        scroll_layout.addLayout(button_layout)

        scroll.setWidget(scroll_widget)
        scroll.setMaximumHeight(450) # Adjusted height potentially
        layout.addWidget(scroll)

        # --- Filter/Action Controls ---
        filter_layout = QHBoxLayout()
        filter_layout.addWidget(QLabel("Search:"))
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Enter search text...")
        self.search_box.textChanged.connect(self.filter_dishes)
        filter_layout.addWidget(self.search_box)
        filter_layout.addWidget(QLabel("Status:"))
        self.status_filter = QComboBox()
        self.status_filter.addItems(["All", "Active Only", "Inactive Only"])
        self.status_filter.currentTextChanged.connect(self.filter_dishes)
        filter_layout.addWidget(self.status_filter)
        # --- ADDED Filter ---
        filter_layout.addWidget(QLabel("Population Type:"))
        self.pop_type_filter = QComboBox()
        self.pop_type_filter.addItems(["All", "primary", "negative_screened", "positive_screened", "other"]) # Match model
        self.pop_type_filter.currentTextChanged.connect(self.filter_dishes)
        filter_layout.addWidget(self.pop_type_filter)
        # -------------------
        refresh_button = QPushButton("Refresh Table")
        refresh_button.clicked.connect(self.refresh_all) # Connects to refresh_all
        filter_layout.addWidget(refresh_button)
        self.manage_screening_button = QPushButton("Manage Screening")
        self.manage_screening_button.setEnabled(False)
        self.manage_screening_button.clicked.connect(self.show_screening_dialog)
        filter_layout.addWidget(self.manage_screening_button)
        self.terminate_dish_button = QPushButton("Terminate Dish")
        self.terminate_dish_button.setEnabled(False)
        self.terminate_dish_button.clicked.connect(self.show_termination_dialog_for_selected)
        filter_layout.addWidget(self.terminate_dish_button)
        filter_layout.addStretch()
        layout.addLayout(filter_layout)

        # --- Dishes table ---
        self.dishes_table = QTableWidget()
        layout.addWidget(self.dishes_table)
        self.setup_dish_table() # Call setup method


    def update_cross_id_dropdown(self):
        """Fetches crosses and populates the Cross ID dropdown."""
        logger.debug("Updating Cross ID dropdown...")
        try:
            current_selection = self.cross_id.currentText()
            self.cross_id.blockSignals(True)
            self.cross_id.clear()
            self.cross_id.addItem(self.CROSS_PLACEHOLDER)

            all_crosses = cross_controller.get_all_crosses()
            # Sort by request date descending, then cross ID as tie-breaker
            active_crosses = [
                c for c in all_crosses.values()
                if (c.cross_status or "").lower() != "archived"
            ]
            sorted_crosses = sorted(
                active_crosses,
                key=lambda c: (c.request_date or '00000000', c.cross_id),
                reverse=True
            )

            for cross in sorted_crosses:
                self.cross_id.addItem(cross.cross_id)

            index = self.cross_id.findText(current_selection)
            if index != -1:
                self.cross_id.setCurrentIndex(index)
            else:
                self.cross_id.setCurrentIndex(0)

            self.cross_id.blockSignals(False)
            # Manually trigger handler for initial load or if selection was restored
            if self.cross_id.currentIndex() >= 0:
                 self.handle_cross_selection_change(self.cross_id.currentText())
            else:
                 self.handle_cross_selection_change(self.CROSS_PLACEHOLDER)

        except Exception as e:
            logger.error(f"Error updating cross ID dropdown: {e}", exc_info=True)
            QMessageBox.warning(self, "Error", "Could not update Cross ID list.")
            self.cross_id.blockSignals(False)

    @Slot()
    def refresh_all(self):
        """Refreshes both the table and the cross dropdown."""
        logger.info("Refreshing Fish Dish Tab data...")
        self.update_cross_id_dropdown()
        self.update_dishes_table()

    # --- METHOD UPDATED ---
    def setup_dish_table(self):
        """Setup the dish table with lineage columns."""
        self.dishes_table.setColumnCount(9) # Increased column count
        self.dishes_table.setHorizontalHeaderLabels([
            "Dish ID", "Date Created", "Genotype", "Responsible",
            "Status", "Location", "Fish Count", "Pop. Type", "Parent Dish" # Added new headers
        ])
        self.dishes_table.setAlternatingRowColors(True)
        self.dishes_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.dishes_table.setSelectionMode(QTableWidget.SelectionMode.ExtendedSelection)
        self.dishes_table.verticalHeader().setVisible(False)
        self.dishes_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        header = self.dishes_table.horizontalHeader()

        # Adjust resize modes
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents) # Default to contents
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive) # Allow Dish ID resize
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch) # Stretch Genotype
        header.setSectionResizeMode(8, QHeaderView.ResizeMode.Interactive) # Allow Parent Dish resize

        self.dishes_table.setSortingEnabled(True) # Enable sorting
        header.sectionClicked.connect(self.handle_header_click)
        self.dishes_table.cellDoubleClicked.connect(self.handle_dish_cell_double_click)
        self.dishes_table.itemSelectionChanged.connect(self.handle_table_selection_change)
    # --- END METHOD UPDATE ---


    @Slot()
    def handle_table_selection_change(self):
        """Enable/disable action buttons based on table selection."""
        selected_rows = self.dishes_table.selectionModel().selectedRows()
        num_selected = len(selected_rows)
        has_selection = num_selected > 0

        # Screening only works for single selection
        self.manage_screening_button.setEnabled(num_selected == 1)
        self.terminate_dish_button.setEnabled(has_selection)

        # Update button text to reflect selection count
        if num_selected > 1:
            self.terminate_dish_button.setText(f"Terminate {num_selected} Dishes")
        else:
            self.terminate_dish_button.setText("Terminate Dish")

    def handle_header_click(self, column):
        """Handle clicks on the table header for sorting."""
        if self.dish_sort_column == column:
            self.dish_sort_order = Qt.SortOrder.DescendingOrder if self.dish_sort_order == Qt.SortOrder.AscendingOrder else Qt.SortOrder.AscendingOrder
        else:
            self.dish_sort_column = column
            self.dish_sort_order = Qt.SortOrder.AscendingOrder
        self.update_dishes_table()

    def handle_dish_cell_double_click(self, row, column):
        """Handle double-click: Open Termination for status, Quality Check otherwise."""
        try:
            dish_id_item = self.dishes_table.item(row, 0)
            if not dish_id_item: return
            dish_id = dish_id_item.text()

            STATUS_COLUMN_INDEX = 4 # Define status column index

            if column == STATUS_COLUMN_INDEX:
                self.show_termination_dialog(dish_id)
            else:
                self.show_quality_check_dialog(dish_id)
        except Exception as e:
            logger.error(f"Error handling cell double-click: {str(e)}", exc_info=True)
            QMessageBox.critical(self, "Error", f"Error processing double-click: {str(e)}")

    def show_termination_dialog(self, dish_id):
        """Show dialog to update dish status."""
        try:
            dish = fish_dish_controller.get_dish(dish_id)
            if not dish:
                QMessageBox.warning(self, "Error", f"Could not load dish {dish_id}")
                return

            dialog = TerminationDialog(self)
            dialog.set_data(dish.status, dish.termination_date, dish.termination_reason)

            if dialog.exec() == QDialog.DialogCode.Accepted:
                update_data = dialog.get_data()
                success, message = fish_dish_controller.update_dish_status(
                    dish_id=dish_id, **update_data
                )
                if success:
                    self.update_dishes_table()
                    QMessageBox.information(self, "Success", "Dish status updated successfully")
                else:
                    QMessageBox.warning(self, "Error", f"Failed to update dish status: {message}")
        except Exception as e:
            logger.error(f"Error showing/updating termination dialog: {str(e)}", exc_info=True)
            QMessageBox.critical(self, "Error", f"Error updating dish status: {str(e)}")

    @Slot()
    def show_termination_dialog_for_selected(self):
        """Show termination dialog for the currently selected dish(es)."""
        selected_rows = self.dishes_table.selectionModel().selectedRows()
        if not selected_rows:
            QMessageBox.warning(self, "No Selection", "Please select a dish from the table first.")
            return

        try:
            # Collect all selected dish IDs
            dish_ids = []
            for index in selected_rows:
                dish_id_item = self.dishes_table.item(index.row(), 0)
                if dish_id_item:
                    dish_ids.append(dish_id_item.text())

            if not dish_ids:
                QMessageBox.critical(self, "Error", "Could not determine Dish IDs for the selected rows.")
                return

            # Single dish: use existing dialog with pre-filled data
            if len(dish_ids) == 1:
                self.show_termination_dialog(dish_ids[0])
                return

            # Batch: show dialog in batch mode
            dialog = TerminationDialog(self, batch_dish_ids=dish_ids)

            if dialog.exec() == QDialog.DialogCode.Accepted:
                update_data = dialog.get_data()
                successes = []
                failures = []

                for dish_id in dish_ids:
                    success, message = fish_dish_controller.update_dish_status(
                        dish_id=dish_id, **update_data
                    )
                    if success:
                        successes.append(dish_id)
                    else:
                        failures.append(f"{dish_id}: {message}")

                self.update_dishes_table()

                if failures:
                    QMessageBox.warning(
                        self, "Partial Success",
                        f"Updated {len(successes)} of {len(dish_ids)} dishes.\n\n"
                        f"Failures:\n" + "\n".join(failures)
                    )
                else:
                    QMessageBox.information(
                        self, "Success",
                        f"Successfully updated {len(successes)} dishes."
                    )

        except Exception as e:
            logger.error(f"Error showing termination dialog for selected: {e}", exc_info=True)
            QMessageBox.critical(self, "Error", f"Could not open termination dialog: {e}")

    def show_quality_check_dialog(self, dish_id):
        """Show the quality check dialog for a dish."""
        try:
            if not fish_dish_controller.get_dish(dish_id):
                 QMessageBox.warning(self, "Error", f"Could not load dish {dish_id} to add quality check.")
                 return

            dialog = QualityCheckDialog(self)
            # Connect signals to slots
            dialog.check_saved.connect(lambda check_data: self.save_quality_check(dish_id, check_data))
            dialog.batch_checks_saved.connect(lambda check_list: self.save_batch_quality_checks(dish_id, check_list))
            dialog.exec()
        except Exception as e:
            logger.error(f"Error showing quality check dialog: {str(e)}", exc_info=True)
            QMessageBox.critical(self, "Error", f"Error showing quality check dialog: {str(e)}")

    @Slot()
    def show_screening_dialog(self):
        """Shows the screening management dialog for the selected dish."""
        selected_rows = self.dishes_table.selectionModel().selectedRows()
        if not selected_rows:
            QMessageBox.warning(self, "No Selection", "Please select a dish from the table first.")
            return

        try:
            selected_row = selected_rows[0].row()
            dish_id_item = self.dishes_table.item(selected_row, 0)
            if not dish_id_item:
                QMessageBox.critical(self, "Error", "Could not determine Dish ID for the selected row.")
                return
            dish_id = dish_id_item.text()

            dish = fish_dish_controller.get_dish(dish_id)
            if not dish:
                 QMessageBox.warning(self, "Not Found", f"Dish {dish_id} could not be loaded.")
                 return

            dialog = ScreeningDialog(dish_id=dish_id, parent=self)
            dialog.exec()
            # Refresh table after screening dialog closes in case status changed or dishes were derived
            self.update_dishes_table()

        except Exception as e:
            logger.error(f"Error showing screening dialog: {e}", exc_info=True)
            QMessageBox.critical(self, "Error", f"Could not open screening dialog: {e}")

    def save_quality_check(self, dish_id, check_data):
        """Save a quality check for a dish."""
        try:
            success, message = fish_dish_controller.add_quality_check(dish_id=dish_id, **check_data)
            if success:
                logger.info(f"Quality check saved for dish {dish_id}")
                # Consider if table needs refresh here (unlikely needed just for QC)
            else:
                QMessageBox.warning(self, "Error", f"Failed to save quality check: {message}")
        except Exception as e:
            logger.error(f"Error saving quality check: {str(e)}", exc_info=True)
            QMessageBox.critical(self, "Error", f"Error saving quality check: {str(e)}")

    def save_batch_quality_checks(self, dish_id, check_list):
        """Save multiple quality checks for a dish."""
        try:
            success_count = 0
            error_messages = []
            total_checks = len(check_list)

            for check_data in check_list:
                success, message = fish_dish_controller.add_quality_check(dish_id=dish_id, **check_data)
                if success:
                    success_count += 1
                else:
                    time_str = check_data.get('check_time', 'N/A')
                    error_messages.append(f"Entry {time_str}: {message}")

            log_msg = f"Batch QC Save for {dish_id}: Saved {success_count}/{total_checks}."
            if error_messages:
                log_msg += f" Errors: {'; '.join(error_messages)}"
            logger.info(log_msg)

            if success_count == total_checks:
                # Maybe skip popup if all successful? Optional.
                QMessageBox.information(self, "Success", f"All {success_count} quality checks saved successfully")
            elif success_count > 0:
                QMessageBox.warning(self, "Partial Success",
                                    f"Saved {success_count} of {total_checks} quality checks.\n\nErrors:\n" + "\n".join(error_messages))
            else:
                QMessageBox.critical(self, "Error",
                                     f"Failed to save any quality checks.\n\nErrors:\n" + "\n".join(error_messages))
        except Exception as e:
            logger.error(f"Error saving batch quality checks: {str(e)}", exc_info=True)
            QMessageBox.critical(self, "Error", f"Error saving batch quality checks: {str(e)}")

    def update_dishes_table(self):
        """Update the fish dishes table."""
        logger.debug("Updating dishes table...")
        try:
            all_dishes = fish_dish_controller.get_all_dishes(include_inactive=True)
            filtered_dishes = self.apply_filters(all_dishes)
            sorted_dishes = self.apply_sorting(filtered_dishes)
            self.populate_dishes_table(sorted_dishes)
            self.handle_table_selection_change() # Update button state
            logger.debug("Dishes table update complete.")
        except Exception as e:
            logger.error(f"Error updating dishes table: {str(e)}", exc_info=True)
            QMessageBox.critical(self, "Error", f"Error updating dishes table: {str(e)}")


    def apply_filters(self, dishes):
        """Apply filters to the dishes."""
        result = dishes
        # Status Filter
        status_filter = self.status_filter.currentText()
        if status_filter == "Active Only":
            result = fish_dish_controller.filter_dishes(result, lambda dish: dish.status == "active")
        elif status_filter == "Inactive Only":
            result = fish_dish_controller.filter_dishes(result, lambda dish: dish.status == "inactive")

        # Population Type Filter
        pop_type_filter = self.pop_type_filter.currentText()
        if pop_type_filter != "All":
             result = fish_dish_controller.filter_dishes(result, lambda dish: dish.dish_population_type == pop_type_filter)

        # Search Filter
        search_text = self.search_box.text().strip()
        if search_text:
            result = fish_dish_controller.search_dishes(result, search_text, case_sensitive=False)

        return result

    # --- METHOD UPDATED ---
    def apply_sorting(self, dishes):
        """Apply sorting to the dishes, including new columns."""
        column_to_key = {
            0: "dish_id",
            1: "date_created",
            2: "genotype",
            3: "responsible",
            4: "status",
            5: "enclosure.room", # Example nested sort
            6: "fish_count",
            7: "dish_population_type", # Added sort key
            8: "parent_dish_id" # Added sort key
        }
        sort_key = column_to_key.get(self.dish_sort_column, "dish_id") # Default to dish_id
        ascending = (self.dish_sort_order == Qt.SortOrder.AscendingOrder)
        logger.debug(f"Sorting dishes by '{sort_key}', Ascending: {ascending}")
        return fish_dish_controller.sort_dishes(dishes, sort_key, ascending=ascending)
    # --- END METHOD UPDATE ---

    # --- METHOD UPDATED ---
    def populate_dishes_table(self, dishes):
        """Populate the dishes table, including new columns."""
        selected_dish_id = None
        current_selection = self.dishes_table.selectionModel().selectedRows()
        if current_selection:
            row_index = current_selection[0].row()
            # Ensure row index is valid before accessing item
            if 0 <= row_index < self.dishes_table.rowCount():
                 id_item = self.dishes_table.item(row_index, 0)
                 if id_item:
                     selected_dish_id = id_item.text()

        self.dishes_table.setSortingEnabled(False) # Disable sorting during population
        self.dishes_table.setRowCount(0)
        self.dishes_table.setRowCount(len(dishes))
        new_selection_row = -1

        for i, (dish_id, dish) in enumerate(dishes.items()):
            try:
                # Existing columns
                col = 0
                self.dishes_table.setItem(i, col, QTableWidgetItem(dish_id)); col+=1
                self.dishes_table.setItem(i, col, QTableWidgetItem(dish.date_created)); col+=1
                self.dishes_table.setItem(i, col, QTableWidgetItem(dish.genotype)); col+=1
                self.dishes_table.setItem(i, col, QTableWidgetItem(dish.responsible)); col+=1
                self.dishes_table.setItem(i, col, QTableWidgetItem(dish.status)); col+=1
                room = dish.enclosure.room if dish.enclosure else "N/A"
                self.dishes_table.setItem(i, col, QTableWidgetItem(room)); col+=1
                self.dishes_table.setItem(i, col, QTableWidgetItem(str(dish.fish_count))); col+=1

                # New columns
                pop_type = getattr(dish, 'dish_population_type', 'N/A') # Use getattr for safety
                self.dishes_table.setItem(i, col, QTableWidgetItem(str(pop_type))); col+=1
                parent_id = getattr(dish, 'parent_dish_id', None) # Use getattr for safety
                self.dishes_table.setItem(i, col, QTableWidgetItem(str(parent_id) if parent_id else "")); col+=1

                # Restore selection if needed
                if dish_id == selected_dish_id:
                    new_selection_row = i

                # Apply styling for inactive dishes
                if dish.status == "inactive":
                    for c in range(self.dishes_table.columnCount()):
                        item = self.dishes_table.item(i, c)
                        if item:
                            item.setBackground(Qt.GlobalColor.lightGray)

            except Exception as e:
                logger.error(f"Error setting dish table row {i} for dish {dish_id}: {str(e)}", exc_info=True)
                # Add placeholder for error row
                self.dishes_table.setItem(i, 0, QTableWidgetItem(dish_id))
                self.dishes_table.setItem(i, 2, QTableWidgetItem("Error Loading Data"))
                # Set background color for error row
                for c in range(self.dishes_table.columnCount()):
                     error_item = QTableWidgetItem("Error")
                     error_item.setBackground(Qt.GlobalColor.red)
                     self.dishes_table.setItem(i, c, error_item)


        self.dishes_table.setSortingEnabled(True) # Re-enable sorting

        # Restore selection if the item still exists
        if new_selection_row != -1:
             self.dishes_table.selectRow(new_selection_row)
    # --- END METHOD UPDATE ---

    def filter_dishes(self):
        """Filter dishes based on current filter settings."""
        self.update_dishes_table()

    def clear_fish_dish_form(self):
        """Clear all inputs in the fish dish form."""
        self.cross_id.setCurrentIndex(0) # This should trigger handle_cross_selection_change to clear fields
        # Explicitly clear fields not cleared by cross selection change
        self.dish_number.setValue(1)
        self.dof.setDate(QDate.currentDate())
        self.sex.setCurrentText("unknown")
        self.species.setText("Danio rerio")
        self.temperature.setValue(28.5)
        self.room.setText("2E.282")
        self.light_duration.setText("14:10")
        self.dawn_dusk.setText("8:00")
        self.beaker_housing.setChecked(False)
        self.fish_count.setValue(0)
        self.vol_water_total.clear()
        self.source_group_id.clear()
        self.notes.clear()

    def add_fish_dish(self):
        """Add a new *primary* fish dish."""
        try:
            cross_id = self.cross_id.currentText()
            if cross_id == self.CROSS_PLACEHOLDER:
                 QMessageBox.warning(self, "Input Error", "Please select a Cross ID.")
                 return

            dish_number = self.dish_number.value()
            genotype = self.genotype.text().strip()
            responsible = self.responsible.text().strip()
            source_group_id_text = self.source_group_id.text().strip() or None
            notes = self.notes.text().strip() or None

            if not genotype: return self.show_input_error("Genotype (auto-filled from cross, but currently empty)")
            if not responsible: return self.show_input_error("Responsible person (auto-filled from cross, but currently empty)")

            dof = self.dof.date().toString("yyyyMMdd")
            parents_text = self.parents.text().strip()
            parents = [p.strip() for p in parents_text.split(",") if p.strip()] if parents_text else []

            vol_water_total_str = self.vol_water_total.text().strip()
            vol_water_total_val = None
            if vol_water_total_str:
                try:
                    vol_water_total_val = int(vol_water_total_str)
                except ValueError:
                    QMessageBox.warning(self, "Input Error", "Volume Water Total must be a valid number.")
                    return

            # Call the controller method specifically for primary dishes
            success, message, dish = fish_dish_controller.create_dish(
                cross_id=cross_id,
                dish_number=dish_number,
                genotype=genotype,
                responsible=responsible,
                source_group_id=source_group_id_text,
                dof=dof,
                sex=self.sex.currentText(),
                species=self.species.text().strip(),
                fish_count=self.fish_count.value(), # Initial estimate
                parents=parents,
                temperature=self.temperature.value(),
                light_duration=self.light_duration.text().strip(),
                dawn_dusk=self.dawn_dusk.text().strip(),
                room=self.room.text().strip(),
                in_beaker=self.beaker_housing.isChecked(),
                vol_water_total=vol_water_total_val,
                notes=notes
            )

            if success:
                self.update_dishes_table()
                # Optionally increment dish number for next entry?
                self.dish_number.setValue(self.dish_number.value() + 1)
                # Don't clear cross-related fields
                self.fish_count.setValue(0)
                self.vol_water_total.clear()
                self.source_group_id.clear()
                self.notes.clear()
                QMessageBox.information(self, "Success", f"Added new primary dish: {message}")
            else:
                QMessageBox.warning(self, "Error", f"Failed to add dish: {message}")

        except Exception as e:
            logger.error(f"Error adding fish dish: {str(e)}", exc_info=True)
            QMessageBox.critical(self, "Error", f"An unexpected error occurred while adding the dish: {str(e)}")

    def show_input_error(self, field_name):
        """Helper to show a standardized input error message."""
        QMessageBox.warning(self, "Input Error", f"Please enter or select a value for {field_name}")
