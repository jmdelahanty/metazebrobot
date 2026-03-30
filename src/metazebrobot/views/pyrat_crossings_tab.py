"""
PyRAT Crossings tab UI component for MetaZebrobot.

This module provides the UI for viewing and filtering crossings from the PyRAT API
with performance tracking.
"""

import logging
from typing import Dict, List, Optional

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QComboBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QMessageBox,
    QHeaderView,
    QTextEdit,
    QSplitter,
    QSizePolicy,
    QGroupBox,
    QProgressBar,
)
from PySide6.QtCore import Qt, Slot, Signal, QSettings
from PySide6.QtGui import QColor, QBrush

from ..controllers.pyrat_tanks_controller import pyrat_tanks_controller
from ..models.pyrat_crossing import PyRATCrossing
from ..utils.pyrat_crossings_worker import PyRATCrossingsWorker
from .dialogs.transgenic_indicator_dialog import TransgenicIndicatorDialog

logger = logging.getLogger(__name__)

# Color constants for crossing status
COLOR_RAISED = QColor(200, 255, 200)  # Light green - completed
COLOR_SETUP = QColor(200, 220, 255)  # Light blue - in progress
COLOR_RECORDED = QColor(255, 255, 200)  # Light yellow - pending
COLOR_DISCARDED = QColor(240, 240, 240)  # Light gray - discarded


class PyRATCrossingsTab(QWidget):
    """
    Tab for viewing and filtering crossings from the PyRAT API.

    Features:
    - Browse crossings with filters (status, strain, search)
    - Performance tracking (requested vs raised)
    - Color-coded rows based on status
    - Detail view panel for selected crossing
    - Filter persistence between sessions
    """

    def __init__(self, parent=None):
        """Initialize the PyRAT crossings tab."""
        super().__init__(parent)

        # Initialize state
        self.crossings: List[PyRATCrossing] = []
        self.filtered_crossings: List[PyRATCrossing] = []
        self.sort_column = 0
        self.sort_order = Qt.SortOrder.DescendingOrder  # Most recent first
        self.worker: Optional[PyRATCrossingsWorker] = None

        # QSettings for filter persistence
        self.settings = QSettings("Ahrens Lab", "MetaZebrobot")

        self.setup_ui()
        self.restore_filter_settings()

    def setup_ui(self):
        """Set up the user interface."""
        main_layout = QVBoxLayout(self)

        # --- Filter Controls ---
        filter_layout = QHBoxLayout()

        # Search box
        filter_layout.addWidget(QLabel("Search:"))
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Search ID, strain, description...")
        self.search_box.textChanged.connect(self.filter_and_refresh_table)
        filter_layout.addWidget(self.search_box)

        # Status filter
        filter_layout.addWidget(QLabel("Status:"))
        self.status_filter = QComboBox()
        self.status_filter.addItems(["All", "recorded", "set-up", "raised", "discarded"])
        self.status_filter.currentTextChanged.connect(self.filter_and_refresh_table)
        filter_layout.addWidget(self.status_filter)

        # Strain filter
        filter_layout.addWidget(QLabel("Strain:"))
        self.strain_filter = QComboBox()
        self.strain_filter.addItem("All")
        self.strain_filter.currentTextChanged.connect(self.filter_and_refresh_table)
        filter_layout.addWidget(self.strain_filter)

        # Refresh button
        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.clicked.connect(self.refresh_crossings)
        filter_layout.addWidget(self.refresh_button)

        # Edit Indicators button
        self.edit_indicators_button = QPushButton("Edit Indicators")
        self.edit_indicators_button.setEnabled(False)
        self.edit_indicators_button.clicked.connect(self.show_indicator_dialog)
        filter_layout.addWidget(self.edit_indicators_button)

        main_layout.addLayout(filter_layout)

        # --- Progress bar (hidden by default) ---
        self.progress_bar = QProgressBar()
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setRange(0, 0)  # Indeterminate
        self.progress_bar.hide()
        main_layout.addWidget(self.progress_bar)

        # --- Main Area (Table and Detail View) using QSplitter ---
        splitter = QSplitter(Qt.Orientation.Vertical, self)

        # Crossings Table
        self.crossings_table = QTableWidget()
        self.setup_crossings_table()
        splitter.addWidget(self.crossings_table)

        # Detail View Area
        detail_group = QGroupBox("Selected Crossing Details")
        detail_layout = QVBoxLayout(detail_group)
        self.detail_view = QTextEdit()
        self.detail_view.setReadOnly(True)
        self.detail_view.setPlaceholderText(
            "Select a crossing from the table above to see details."
        )
        detail_layout.addWidget(self.detail_view)
        splitter.addWidget(detail_group)

        splitter.setSizes([400, 200])
        main_layout.addWidget(splitter)

        # --- Summary Stats Bar ---
        stats_layout = QHBoxLayout()
        self.stats_label = QLabel("No crossings loaded. Click Refresh to load crossings.")
        stats_layout.addWidget(self.stats_label)
        stats_layout.addStretch()
        main_layout.addLayout(stats_layout)

    def setup_crossings_table(self):
        """Configure the crossings table."""
        self.crossings_table.setColumnCount(8)
        self.crossings_table.setHorizontalHeaderLabels(
            [
                "ID",
                "Date",
                "Status",
                "Strain",
                "Requested",
                "Raised",
                "Performance",
                "Description",
            ]
        )

        # Appearance and behavior
        self.crossings_table.setAlternatingRowColors(False)  # Custom colors
        self.crossings_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.crossings_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.crossings_table.verticalHeader().setVisible(False)
        self.crossings_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.crossings_table.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )

        # Column resizing
        header = self.crossings_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)  # ID
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)  # Date
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)  # Status
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)  # Strain
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)  # Requested
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)  # Raised
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents)  # Performance
        header.setSectionResizeMode(7, QHeaderView.ResizeMode.Stretch)  # Description

        # Connect signals
        header.sectionClicked.connect(self.handle_header_click)
        self.crossings_table.currentItemChanged.connect(self.handle_selection_change)

    def restore_filter_settings(self):
        """Restore filter settings from QSettings."""
        self.settings.beginGroup("PyRATCrossingsTab")

        status = self.settings.value("status_filter", "All")
        index = self.status_filter.findText(status)
        if index >= 0:
            self.status_filter.setCurrentIndex(index)

        self.settings.endGroup()

    def save_filter_settings(self):
        """Save filter settings to QSettings."""
        self.settings.beginGroup("PyRATCrossingsTab")
        self.settings.setValue("status_filter", self.status_filter.currentText())
        self.settings.setValue("strain_filter", self.strain_filter.currentText())
        self.settings.endGroup()

    @Slot()
    def refresh_crossings(self):
        """Fetch crossings from the PyRAT API."""
        # Check for credentials
        if not pyrat_tanks_controller.has_credentials():
            QMessageBox.warning(
                self,
                "Credentials Required",
                "PyRAT API credentials are not configured.\n\n"
                "Please run the following command in a terminal to set up credentials:\n\n"
                "  python pyrat_query_tool.py --setup-credentials\n\n"
                "This will securely store your API credentials in the system keyring.",
            )
            return

        # Get credentials
        credentials = pyrat_tanks_controller.get_credentials()
        if not credentials:
            QMessageBox.critical(
                self, "Error", "Failed to retrieve credentials from keyring."
            )
            return

        # Cancel any existing worker
        if self.worker and self.worker.isRunning():
            self.worker.cancel()
            self.worker.wait()

        # Disable refresh button and show progress
        self.refresh_button.setEnabled(False)
        self.progress_bar.show()
        self.progress_bar.setFormat("Connecting to PyRAT API...")

        # Build API filters - filter by responsible person (you)
        api_filters = {}
        responsible_id = pyrat_tanks_controller.get_default_responsible_id()
        if responsible_id:
            api_filters["responsible_id"] = responsible_id
            logger.info(f"Filtering crossings by responsible_id: {responsible_id}")

        # Create and start worker
        self.worker = PyRATCrossingsWorker(
            base_url=credentials["base_url"],
            client_token=credentials["client_token"],
            user_token=credentials["user_token"],
            filters=api_filters,
            parent=self,
        )

        self.worker.finished.connect(self.on_worker_finished)
        self.worker.error.connect(self.on_worker_error)
        self.worker.progress.connect(self.on_worker_progress)
        self.worker.start()

    @Slot(list)
    def on_worker_finished(self, crossings_data: list):
        """Handle successful API response."""
        self.progress_bar.hide()
        self.refresh_button.setEnabled(True)

        # Parse crossings
        self.crossings = pyrat_tanks_controller.parse_crossings(crossings_data)

        # Update filter dropdowns with available values
        self.update_filter_dropdowns()

        # Apply filters and refresh table
        self.filter_and_refresh_table()

        logger.info(f"Loaded {len(self.crossings)} crossings from PyRAT API")

    @Slot(str)
    def on_worker_error(self, error_message: str):
        """Handle API error."""
        self.progress_bar.hide()
        self.refresh_button.setEnabled(True)

        QMessageBox.critical(
            self,
            "API Error",
            f"Failed to fetch crossings from PyRAT:\n\n{error_message}",
        )
        logger.error(f"PyRAT API error: {error_message}")

    @Slot(str)
    def on_worker_progress(self, message: str):
        """Update progress display."""
        self.progress_bar.setFormat(message)

    def update_filter_dropdowns(self):
        """Update filter dropdown options based on loaded crossings."""
        # Save current selection
        current_strain = self.strain_filter.currentText()

        # Update strain dropdown
        strains = pyrat_tanks_controller.get_unique_crossing_values(self.crossings, "strain_name")
        self.strain_filter.blockSignals(True)
        self.strain_filter.clear()
        self.strain_filter.addItem("All")
        self.strain_filter.addItems(strains)
        # Restore selection if still valid
        index = self.strain_filter.findText(current_strain)
        if index >= 0:
            self.strain_filter.setCurrentIndex(index)
        self.strain_filter.blockSignals(False)

    @Slot()
    def filter_and_refresh_table(self):
        """Apply filters and update the table."""
        # Save filter settings
        self.save_filter_settings()

        # Start with all crossings
        filtered = self.crossings

        # Apply status filter
        status = self.status_filter.currentText()
        filtered = pyrat_tanks_controller.filter_crossings_by_status(filtered, status)

        # Apply strain filter
        strain = self.strain_filter.currentText()
        filtered = pyrat_tanks_controller.filter_crossings_by_strain(filtered, strain)

        # Apply search
        search_text = self.search_box.text().strip()
        filtered = pyrat_tanks_controller.search_crossings(filtered, search_text)

        # Apply sorting
        filtered = self.apply_sorting(filtered)

        self.filtered_crossings = filtered
        self.populate_table(filtered)
        self.update_stats_label()

    def apply_sorting(self, crossings: List[PyRATCrossing]) -> List[PyRATCrossing]:
        """Apply current sorting settings."""
        column_to_key = {
            0: "crossing_id",
            1: "date_of_record",
            2: "status",
            3: "strain_name",
            4: "requested_groups",
            5: "raised_count",
            6: "performance",
            7: "description",
        }
        sort_key = column_to_key.get(self.sort_column, "crossing_id")
        ascending = self.sort_order == Qt.SortOrder.AscendingOrder
        return pyrat_tanks_controller.sort_crossings(crossings, sort_key, ascending)

    @Slot(int)
    def handle_header_click(self, column_index: int):
        """Handle clicks on the table header for sorting."""
        if self.sort_column == column_index:
            self.sort_order = (
                Qt.SortOrder.DescendingOrder
                if self.sort_order == Qt.SortOrder.AscendingOrder
                else Qt.SortOrder.AscendingOrder
            )
        else:
            self.sort_column = column_index
            self.sort_order = Qt.SortOrder.AscendingOrder

        self.filter_and_refresh_table()

    @Slot(QTableWidgetItem, QTableWidgetItem)
    def handle_selection_change(
        self, current: Optional[QTableWidgetItem], previous: Optional[QTableWidgetItem]
    ):
        """Update detail view when selection changes."""
        if current:
            self.update_detail_view(current.row())
            self.edit_indicators_button.setEnabled(True)
        else:
            self.detail_view.clear()
            self.edit_indicators_button.setEnabled(False)

    def populate_table(self, crossings: List[PyRATCrossing]):
        """Fill the table with crossing data."""
        self.crossings_table.setSortingEnabled(False)
        self.crossings_table.setRowCount(0)
        self.crossings_table.setRowCount(len(crossings))

        for i, crossing in enumerate(crossings):
            # Create items
            self.crossings_table.setItem(i, 0, QTableWidgetItem(str(crossing.crossing_id)))
            self.crossings_table.setItem(i, 1, QTableWidgetItem(crossing.date_display))
            self.crossings_table.setItem(i, 2, QTableWidgetItem(crossing.status or ""))
            self.crossings_table.setItem(i, 3, QTableWidgetItem(crossing.strain_name or ""))

            # Requested groups
            req_str = str(crossing.requested_groups) if crossing.requested_groups else "?"
            self.crossings_table.setItem(i, 4, QTableWidgetItem(req_str))

            # Raised count
            self.crossings_table.setItem(i, 5, QTableWidgetItem(str(crossing.raised_count)))

            # Performance
            self.crossings_table.setItem(i, 6, QTableWidgetItem(crossing.performance_display))

            # Description (truncated)
            desc = crossing.description or ""
            desc_truncated = desc[:50] + "..." if len(desc) > 50 else desc
            self.crossings_table.setItem(i, 7, QTableWidgetItem(desc_truncated))

            # Store crossing_id in first column for easy retrieval
            self.crossings_table.item(i, 0).setData(Qt.ItemDataRole.UserRole, crossing.crossing_id)

            # Set row background color based on status
            bg_color = self.get_status_color(crossing.status)
            for col in range(self.crossings_table.columnCount()):
                item = self.crossings_table.item(i, col)
                if item:
                    item.setBackground(QBrush(bg_color))

        # Keep sorting disabled - we handle sorting ourselves in handle_header_click
        # Qt's built-in sorting treats numbers as strings

    def get_status_color(self, status: str) -> QColor:
        """Get background color for crossing status."""
        if status == "raised":
            return COLOR_RAISED
        elif status == "set-up":
            return COLOR_SETUP
        elif status == "recorded":
            return COLOR_RECORDED
        else:
            return COLOR_DISCARDED

    def update_detail_view(self, row: int):
        """Update the detail view with selected crossing info."""
        if row < 0 or row >= len(self.filtered_crossings):
            self.detail_view.clear()
            return

        crossing = self.filtered_crossings[row]

        # Format performance with styling
        perf_style = ""
        perf = crossing.performance
        if perf is not None:
            if perf >= 1.0:
                perf_style = "color: green; font-weight: bold;"
            elif perf >= 0.5:
                perf_style = "color: orange;"
            else:
                perf_style = "color: red;"

        # Build parent tanks HTML
        parents_html = ""
        if crossing.parent_tanks:
            for tank in crossing.parent_tanks:
                parents_html += f"""
                <li>{tank.location_display}: {tank.total_fish} fish
                    ({tank.number_of_male}M/{tank.number_of_female}F/{tank.number_of_unknown}U)
                    — {tank.strain_name or 'N/A'}</li>
                """
        else:
            parents_html = "<li>None</li>"

        # Build child tanks HTML
        children_html = ""
        if crossing.child_tanks:
            for tank in crossing.child_tanks:
                children_html += f"""
                <li>{tank.location_display}: {tank.total_fish} fish
                    ({tank.number_of_male}M/{tank.number_of_female}F/{tank.number_of_unknown}U)
                    — Status: {tank.status or 'N/A'}</li>
                """
        else:
            children_html = "<li>None (not yet raised)</li>"

        details_html = f"""
        <h3>Crossing Details: {crossing.crossing_id}</h3>
        <p>
            <b>Status:</b> {crossing.status or 'N/A'}<br>
            <b>Strain:</b> {crossing.strain_name_with_id or crossing.strain_name or 'N/A'}
        </p>

        <h4>Dates</h4>
        <p>
            <b>Recorded:</b> {crossing.date_of_record or 'N/A'}<br>
            <b>Set Up:</b> {crossing.date_of_set_up or 'N/A'}<br>
            <b>Raised:</b> {crossing.date_of_raise or 'N/A'}
        </p>

        <h4>Performance</h4>
        <p>
            <b>Requested Groups:</b> {crossing.requested_groups or '? (could not parse)'}<br>
            <b>Raised Tanks:</b> {crossing.raised_count}<br>
            <b>Performance:</b> <span style="{perf_style}">{crossing.performance_display}</span>
        </p>

        <h4>Description</h4>
        <p>{crossing.description or 'No description'}</p>

        <h4>Parent Tanks ({len(crossing.parent_tanks)})</h4>
        <ul>{parents_html}</ul>

        <h4>Child Tanks ({crossing.raised_count})</h4>
        <ul>{children_html}</ul>

        <h4>Responsible</h4>
        <p>{crossing.responsible_fullname or 'N/A'}</p>
        """

        self.detail_view.setHtml(details_html)

    @Slot()
    def show_indicator_dialog(self):
        """Open the transgenic indicator dialog for the selected crossing."""
        current_row = self.crossings_table.currentRow()
        if current_row < 0 or current_row >= len(self.filtered_crossings):
            QMessageBox.warning(self, "No Selection", "Please select a crossing first.")
            return

        crossing = self.filtered_crossings[current_row]
        dialog = TransgenicIndicatorDialog(
            crossing_id=str(crossing.crossing_id),
            strain_name=crossing.strain_name or "",
            parent=self,
        )
        dialog.exec()

    def update_stats_label(self):
        """Update the summary statistics label."""
        if not self.crossings:
            self.stats_label.setText("No crossings loaded. Click Refresh to load crossings.")
            return

        stats = pyrat_tanks_controller.get_crossing_stats(self.crossings)
        filtered_count = len(self.filtered_crossings)

        # Format status counts
        status_counts = stats["status_counts"]
        avg_perf = stats["avg_performance"]
        avg_perf_str = f"{avg_perf:.0%}" if avg_perf is not None else "N/A"

        stats_text = (
            f"Showing {filtered_count} of {stats['total']} crossings | "
            f"<span style='color: green;'>Raised: {status_counts.get('raised', 0)}</span> | "
            f"<span style='color: blue;'>Set-up: {status_counts.get('set-up', 0)}</span> | "
            f"<span style='color: orange;'>Recorded: {status_counts.get('recorded', 0)}</span> | "
            f"Avg Performance: {avg_perf_str}"
        )

        self.stats_label.setText(stats_text)
        self.stats_label.setTextFormat(Qt.TextFormat.RichText)
