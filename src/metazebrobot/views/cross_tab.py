"""
Cross tab UI component for MetaZebrobot.

This module provides the UI for viewing and managing zebrafish crosses.
"""

import logging
from typing import Dict, Optional

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QFormLayout, QGroupBox,
    QLabel, QLineEdit, QComboBox, QSpinBox, QCheckBox, QPushButton,
    QDateEdit, QTableWidget, QTableWidgetItem, QMessageBox, QHeaderView,
    QScrollArea, QTextEdit, QSplitter, QSizePolicy, QDialog # Added QDialog
)
from PySide6.QtCore import Qt, Slot

# Import controller and model
from ..controllers.cross_controller import cross_controller
from ..models.cross import Cross, Parent, TransgenicDetails # Import specific models
from .dialogs.update_cross_status_dialog import UpdateCrossStatusDialog

# Import the new dialog (will be created in the next step)
from .dialogs.add_cross_dialog import AddCrossDialog

logger = logging.getLogger(__name__)

class CrossTab(QWidget):
    """
    Tab for viewing and managing zebrafish crosses.
    """

    def __init__(self, parent=None):
        """
        Initialize the cross tab.

        Args:
            parent: Parent widget
        """
        super().__init__(parent)

        # Initialize state for sorting
        self.cross_sort_column = 0  # Default sort by Cross ID
        self.cross_sort_order = Qt.SortOrder.AscendingOrder

        self.setup_ui()
        self.update_crosses_table() # Initial population

    def setup_ui(self):
        """Set up the user interface."""
        main_layout = QVBoxLayout(self)

        # --- Filter, Refresh, and Add Controls --- # MODIFIED SECTION
        controls_layout = QHBoxLayout() # Renamed for clarity

        controls_layout.addWidget(QLabel("Search:"))
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Search ID, Line, Requestor...")
        self.search_box.textChanged.connect(self.filter_and_refresh_table)
        controls_layout.addWidget(self.search_box)

        controls_layout.addWidget(QLabel("Type:"))
        self.type_filter = QComboBox()
        self.type_filter.addItems(["All", "Standard", "Transgenic"]) # Match CrossType Literal
        self.type_filter.currentTextChanged.connect(self.filter_and_refresh_table)
        controls_layout.addWidget(self.type_filter)

        controls_layout.addWidget(QLabel("Status:"))
        self.status_filter = QComboBox()
        # Add common statuses, potentially load dynamically if needed
        self.status_filter.addItems(["All", "Requested", "Performed", "Screening", "Completed", "Archived"])
        self.status_filter.currentTextChanged.connect(self.filter_and_refresh_table)
        controls_layout.addWidget(self.status_filter)

        refresh_button = QPushButton("Refresh")
        refresh_button.clicked.connect(self.update_crosses_table)
        controls_layout.addWidget(refresh_button)

        # --- NEW: Add Cross Button ---
        add_button = QPushButton("Add New Cross")
        add_button.clicked.connect(self.show_add_cross_dialog) # Connect to new slot
        controls_layout.addWidget(add_button)
        # --- End NEW ---

        main_layout.addLayout(controls_layout) # Add the controls layout

        # --- Main Area (Table and Detail View) using QSplitter ---
        splitter = QSplitter(Qt.Orientation.Vertical, self)

        # --- Crosses Table ---
        self.crosses_table = QTableWidget()
        self.setup_cross_table() # Configure table appearance and signals
        splitter.addWidget(self.crosses_table)

        # --- Detail View Area ---
        detail_group = QGroupBox("Selected Cross Details")
        detail_layout = QVBoxLayout(detail_group)
        self.detail_view = QTextEdit()
        self.detail_view.setReadOnly(True)
        self.detail_view.setPlaceholderText("Select a cross from the table above to see details.")
        detail_layout.addWidget(self.detail_view)
        splitter.addWidget(detail_group)

        # Adjust splitter sizes (optional, can be adjusted by user)
        splitter.setSizes([400, 200]) # Initial sizes for table and detail view

        main_layout.addWidget(splitter)

    def setup_cross_table(self):
        """Setup the cross table with columns, sorting, and selection handling."""
        self.crosses_table.setColumnCount(8)
        self.crosses_table.setHorizontalHeaderLabels([
            "Cross ID", "Request Date", "Requestor", "Line/Strain",
            "Type", "Status", "Req. Groups", "Prod. Groups"
        ])

        # Appearance and behavior
        self.crosses_table.setAlternatingRowColors(True)
        self.crosses_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.crosses_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.crosses_table.verticalHeader().setVisible(False)
        self.crosses_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers) # Read-only table
        self.crosses_table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)


        # Column resizing
        header = self.crosses_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive) # Allow user resize
        header.setStretchLastSection(False) # Don't stretch last section by default
        # Set initial reasonable widths or resize modes
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents) # Cross ID
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents) # Date
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents) # Type
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents) # Status
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents) # Groups
        # Stretch Line/Strain
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)


        # Connect signals
        header.sectionClicked.connect(self.handle_header_click)
        # Use currentItemChanged for updating detail view on single click/selection
        self.crosses_table.currentItemChanged.connect(self.handle_selection_change)
        self.crosses_table.cellDoubleClicked.connect(self.handle_cross_cell_double_click)

    @Slot(int, int)
    def handle_cross_cell_double_click(self, row: int, column: int):
        """Handle double-clicks on the cross table."""
        # Define the index for the status column (check your table setup)
        STATUS_COLUMN_INDEX = 5 # Assuming 'Status' is the 6th column (index 5)

        if column == STATUS_COLUMN_INDEX:
            try:
                cross_id_item = self.crosses_table.item(row, 0) # Get item from Cross ID column
                status_item = self.crosses_table.item(row, STATUS_COLUMN_INDEX) # Get item from Status column

                if not cross_id_item or not status_item:
                    logger.warning("Could not get cross ID or status item for double-clicked row.")
                    return

                cross_id = cross_id_item.data(Qt.ItemDataRole.UserRole) # Get ID from UserRole data
                if not cross_id:
                    cross_id = cross_id_item.text() # Fallback if UserRole wasn't set

                current_status = status_item.text()

                # --- Show the new dialog ---
                dialog = UpdateCrossStatusDialog(current_status=current_status, parent=self)
                if dialog.exec() == QDialog.DialogCode.Accepted:
                    new_status = dialog.get_selected_status()
                    if new_status != current_status:
                        logger.info(f"Attempting to update status for cross {cross_id} from '{current_status}' to '{new_status}'")
                        # Call controller method (to be created in next step)
                        success, message = cross_controller.update_cross_status(cross_id, new_status)

                        if success:
                            QMessageBox.information(self, "Success", f"Cross {cross_id} status updated to '{new_status}'.")
                            self.update_crosses_table() # Refresh table to show change
                        else:
                            QMessageBox.warning(self, "Update Failed", f"Could not update status for cross {cross_id}:\n{message}")
                    else:
                        logger.debug("Status not changed.")

            except Exception as e:
                logger.error(f"Error handling cross table double-click: {e}", exc_info=True)
                QMessageBox.critical(self, "Error", f"An error occurred: {e}")

    @Slot(int)
    def handle_header_click(self, column_index: int):
        """Handle clicks on the table header for sorting."""
        if self.cross_sort_column == column_index:
            # Toggle sort order
            self.cross_sort_order = Qt.SortOrder.DescendingOrder if self.cross_sort_order == Qt.SortOrder.AscendingOrder else Qt.SortOrder.AscendingOrder
        else:
            self.cross_sort_column = column_index
            self.cross_sort_order = Qt.SortOrder.AscendingOrder

        self.update_crosses_table() # Re-sort and refresh table

    @Slot(QTableWidgetItem, QTableWidgetItem)
    def handle_selection_change(self, current: Optional[QTableWidgetItem], previous: Optional[QTableWidgetItem]):
        """Update the detail view when the selected table row changes."""
        if current:
            row = current.row()
            self.update_detail_view(row)
        else:
            self.detail_view.clear() # Clear details if no item is selected

    # --- NEW Slot ---
    @Slot()
    def show_add_cross_dialog(self):
        """Show the dialog to add a new cross."""
        try:
            dialog = AddCrossDialog(self) # Create instance of the new dialog
            if dialog.exec() == QDialog.DialogCode.Accepted:
                # Dialog was accepted (Save clicked)
                cross_data = dialog.get_cross_data()
                if cross_data:
                    logger.info(f"Attempting to create cross with data: {cross_data}")
                    # Call controller to create the cross
                    success, message, new_cross_obj = cross_controller.create_cross(cross_data)

                    if success:
                        QMessageBox.information(self, "Success", f"Cross '{message}' created successfully.")
                        self.update_crosses_table() # Refresh the table
                    else:
                        logger.error(f"Failed to create cross: {message}")
                        QMessageBox.warning(self, "Creation Failed", f"Could not create cross:\n{message}")
                else:
                     logger.warning("AddCrossDialog accepted, but returned no data.")

        except Exception as e:
            logger.error(f"Error showing or processing Add Cross dialog: {e}", exc_info=True)
            QMessageBox.critical(self, "Error", f"An error occurred: {e}")
    # --- End NEW Slot ---


    # --- Data Update and Display ---

    @Slot()
    def filter_and_refresh_table(self):
        """Slot to refresh the table based on current filters."""
        self.update_crosses_table()

    def update_crosses_table(self):
        """Fetch, filter, sort, and display crosses in the table."""
        logger.debug("Updating crosses table...")
        try:
            all_crosses = cross_controller.get_all_crosses()

            # Apply filters
            filtered_crosses = self.apply_filters(all_crosses)

            # Apply sorting
            sorted_crosses = self.apply_sorting(filtered_crosses)

            # Populate table
            self.populate_crosses_table(sorted_crosses)

            # Clear detail view after refresh
            # self.detail_view.clear() # Keep detail view if selection persists? Maybe clear is better.
            current_selection = self.crosses_table.currentRow()
            if current_selection < 0: # No row selected
                 self.detail_view.clear()
            # else: # Keep detail view for selected row if it still exists after refresh
                 # self.update_detail_view(current_selection) # This might cause issues if row index changes drastically

            logger.debug("Crosses table update complete.")

        except Exception as e:
            logger.error(f"Error updating crosses table: {e}", exc_info=True)
            QMessageBox.critical(self, "Error", f"Failed to update crosses table: {e}")

    def apply_filters(self, crosses: Dict[str, Cross]) -> Dict[str, Cross]:
        """Apply current filter settings to the dictionary of crosses."""
        filtered = crosses

        # Type filter
        type_filter_text = self.type_filter.currentText()
        if type_filter_text != "All":
            filtered = cross_controller.filter_crosses(
                filtered, lambda cross: cross.cross_type == type_filter_text
            )

        # Status filter
        status_filter_text = self.status_filter.currentText()
        if status_filter_text != "All":
            filtered = cross_controller.filter_crosses(
                filtered, lambda cross: cross.cross_status == status_filter_text
            )

        # Search filter
        search_text = self.search_box.text().strip()
        if search_text:
            filtered = cross_controller.search_crosses(
                filtered, search_text, case_sensitive=False
            )

        return filtered

    def apply_sorting(self, crosses: Dict[str, Cross]) -> Dict[str, Cross]:
        """Apply current sorting settings to the dictionary of crosses."""
        column_to_key = {
            0: "cross_id",
            1: "request_date",
            2: "responsible_requestor",
            3: "line_strain",
            4: "cross_type",
            5: "cross_status",
            6: "requested_groups",
            7: "groups_produced"
        }
        sort_key = column_to_key.get(self.cross_sort_column, "cross_id") # Default to cross_id
        ascending = (self.cross_sort_order == Qt.SortOrder.AscendingOrder)
        return cross_controller.sort_crosses(crosses, sort_key, ascending)

    def populate_crosses_table(self, crosses: Dict[str, Cross]):
        """Fill the table widget with cross data."""
        current_selection_id = None
        current_row = self.crosses_table.currentRow()
        if current_row >= 0:
             id_item = self.crosses_table.item(current_row, 0)
             if id_item:
                  current_selection_id = id_item.data(Qt.ItemDataRole.UserRole)


        self.crosses_table.setSortingEnabled(False) # Disable sorting during population
        self.crosses_table.setRowCount(0) # Clear table before populating
        self.crosses_table.setRowCount(len(crosses))

        new_selection_row = -1
        for i, (cross_id, cross) in enumerate(crosses.items()):
            self.crosses_table.setItem(i, 0, QTableWidgetItem(cross.cross_id))
            self.crosses_table.setItem(i, 1, QTableWidgetItem(cross.request_date))
            self.crosses_table.setItem(i, 2, QTableWidgetItem(cross.responsible_requestor))
            self.crosses_table.setItem(i, 3, QTableWidgetItem(cross.line_strain))
            self.crosses_table.setItem(i, 4, QTableWidgetItem(cross.cross_type))
            self.crosses_table.setItem(i, 5, QTableWidgetItem(cross.cross_status or 'N/A'))
            self.crosses_table.setItem(i, 6, QTableWidgetItem(str(cross.requested_groups) if cross.requested_groups is not None else "None"))
            self.crosses_table.setItem(i, 7, QTableWidgetItem(str(cross.groups_produced) if cross.groups_produced is not None else "None"))

            # Store cross_id in the first column item for easy retrieval
            self.crosses_table.item(i, 0).setData(Qt.ItemDataRole.UserRole, cross_id)

            # Check if this row corresponds to the previously selected ID
            if cross_id == current_selection_id:
                 new_selection_row = i


        self.crosses_table.setSortingEnabled(True) # Re-enable sorting

        # Restore selection if the item still exists
        if new_selection_row >= 0:
             self.crosses_table.setCurrentCell(new_selection_row, 0) # Select the cell
             # self.update_detail_view(new_selection_row) # Update detail view explicitly if needed


    def update_detail_view(self, row: int):
        """Update the detail view area with info from the selected cross."""
        try:
            cross_id_item = self.crosses_table.item(row, 0)
            if not cross_id_item:
                self.detail_view.clear()
                return

            # Retrieve cross_id stored in the item's UserRole data
            cross_id = cross_id_item.data(Qt.ItemDataRole.UserRole)
            if not cross_id:
                 # Fallback if UserRole wasn't set (shouldn't happen)
                 cross_id = cross_id_item.text()

            # Fetch the full Cross object using the controller
            # This ensures we have the complete, potentially updated data
            cross = cross_controller.get_cross(cross_id)

            if cross:
                # Format details into HTML for nice display in QTextEdit
                details_html = f"""
                <h3>Cross Details: {cross.cross_id}</h3>
                <p><b>Request Date:</b> {cross.request_date}<br>
                   <b>Requestor:</b> {cross.responsible_requestor}<br>
                   <b>Line/Strain:</b> {cross.line_strain}<br>
                   <b>Type:</b> {cross.cross_type}<br>
                   <b>Status:</b> {cross.cross_status or 'N/A'}<br>
                   <b>Requested Groups:</b> {cross.requested_groups}</p>
                <h4>Parents:</h4>
                <ul>
                """
                for parent in cross.parents:
                    details_html += f"<li>{parent.identifier}"
                    if parent.sex != 'unknown':
                        details_html += f" ({parent.sex})"
                    if parent.genotype:
                         details_html += f" - Genotype: {parent.genotype}"
                    details_html += "</li>"
                details_html += "</ul>"

                if cross.transgenic_details:
                    details_html += "<h4>Transgenic Details:</h4><ul>"
                    for indicator in cross.transgenic_details.indicators:
                        details_html += f"<li><b>Indicator:</b> {indicator.standard_notation}<br>" \
                            f"&nbsp;&nbsp;<b>Expected Expression:</b> {indicator.expected_expression or 'N/A'}</li>"
                    details_html += "</ul>"
                    # Add aggregate results if available (optional)
                    if cross.transgenic_details.aggregate_results:
                         agg = cross.transgenic_details.aggregate_results
                         details_html += "<h5>Aggregate Results:</h5>"
                         details_html += f"<p>&nbsp;&nbsp;Total Initial: {agg.total_initially_produced or 'N/A'}<br>" \
                                         f"&nbsp;&nbsp;Total Final Positive: {agg.total_positive_final or 'N/A'}<br>" \
                                         f"&nbsp;&nbsp;Yield: {agg.yield_percentage:.1f}%" if agg.yield_percentage is not None else "N/A" \
                                         f"<br>&nbsp;&nbsp;Date Aggregated: {agg.date_aggregated or 'N/A'}</p>"


                if cross.notes:
                    # Use <pre> tag to preserve formatting in notes
                    details_html += f"<h4>Notes:</h4><pre>{cross.notes}</pre>"

                self.detail_view.setHtml(details_html)
            else:
                self.detail_view.setText(f"Could not load details for cross ID: {cross_id}")

        except Exception as e:
            logger.error(f"Error updating detail view for row {row}: {e}", exc_info=True)
            self.detail_view.setText(f"Error displaying details: {e}")

