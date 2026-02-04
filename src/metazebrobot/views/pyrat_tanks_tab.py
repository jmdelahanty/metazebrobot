"""
PyRAT Tanks tab UI component for MetaZebrobot.

This module provides the UI for viewing and filtering tanks from the PyRAT API
with age monitoring alerts.
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
from ..models.pyrat_tank import PyRATTank
from ..utils.pyrat_worker import PyRATWorker

logger = logging.getLogger(__name__)

# Color constants for age status
COLOR_URGENT = QColor(255, 200, 200)  # Light red
COLOR_WARNING = QColor(255, 255, 200)  # Light yellow
COLOR_OK = QColor(200, 255, 200)  # Light green
COLOR_UNKNOWN = QColor(240, 240, 240)  # Light gray


class PyRATTanksTab(QWidget):
    """
    Tab for viewing and filtering tanks from the PyRAT API.

    Features:
    - Browse tanks with filters (rack, status, age status, responsible, search)
    - Color-coded rows based on age status
    - Detail view panel for selected tank
    - Filter persistence between sessions
    """

    # Signal emitted when urgent count changes (for tab badge)
    urgent_count_changed = Signal(int)

    def __init__(self, parent=None):
        """Initialize the PyRAT tanks tab."""
        super().__init__(parent)

        # Initialize state
        self.tanks: List[PyRATTank] = []
        self.filtered_tanks: List[PyRATTank] = []
        self.age_status_counts: Dict[str, int] = {}
        self.sort_column = 0
        self.sort_order = Qt.SortOrder.AscendingOrder
        self.worker: Optional[PyRATWorker] = None

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
        self.search_box.setPlaceholderText("Search ID, label, strain, person...")
        self.search_box.textChanged.connect(self.filter_and_refresh_table)
        filter_layout.addWidget(self.search_box)

        # Rack filter
        filter_layout.addWidget(QLabel("Rack:"))
        self.rack_filter = QComboBox()
        self.rack_filter.addItem("All")
        self.rack_filter.currentTextChanged.connect(self.filter_and_refresh_table)
        filter_layout.addWidget(self.rack_filter)

        # Status filter
        filter_layout.addWidget(QLabel("Status:"))
        self.status_filter = QComboBox()
        self.status_filter.addItems(["All", "open", "closed", "exported", "joined"])
        self.status_filter.currentTextChanged.connect(self.filter_and_refresh_table)
        filter_layout.addWidget(self.status_filter)

        # Age status filter
        filter_layout.addWidget(QLabel("Age Status:"))
        self.age_status_filter = QComboBox()
        self.age_status_filter.addItems(["All", "URGENT", "WARNING", "OK", "UNKNOWN"])
        self.age_status_filter.currentTextChanged.connect(self.filter_and_refresh_table)
        filter_layout.addWidget(self.age_status_filter)

        # Responsible filter
        filter_layout.addWidget(QLabel("Responsible:"))
        self.responsible_filter = QComboBox()
        self.responsible_filter.addItem("All")
        self.responsible_filter.currentTextChanged.connect(self.filter_and_refresh_table)
        filter_layout.addWidget(self.responsible_filter)

        # Refresh button
        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.clicked.connect(self.refresh_tanks)
        filter_layout.addWidget(self.refresh_button)

        main_layout.addLayout(filter_layout)

        # --- Progress bar (hidden by default) ---
        self.progress_bar = QProgressBar()
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setRange(0, 0)  # Indeterminate
        self.progress_bar.hide()
        main_layout.addWidget(self.progress_bar)

        # --- Main Area (Table and Detail View) using QSplitter ---
        splitter = QSplitter(Qt.Orientation.Vertical, self)

        # Tanks Table
        self.tanks_table = QTableWidget()
        self.setup_tanks_table()
        splitter.addWidget(self.tanks_table)

        # Detail View Area
        detail_group = QGroupBox("Selected Tank Details")
        detail_layout = QVBoxLayout(detail_group)
        self.detail_view = QTextEdit()
        self.detail_view.setReadOnly(True)
        self.detail_view.setPlaceholderText(
            "Select a tank from the table above to see details."
        )
        detail_layout.addWidget(self.detail_view)
        splitter.addWidget(detail_group)

        splitter.setSizes([400, 200])
        main_layout.addWidget(splitter)

        # --- Summary Stats Bar ---
        stats_layout = QHBoxLayout()
        self.stats_label = QLabel("No tanks loaded. Click Refresh to load tanks.")
        stats_layout.addWidget(self.stats_label)
        stats_layout.addStretch()
        main_layout.addLayout(stats_layout)

    def setup_tanks_table(self):
        """Configure the tanks table."""
        self.tanks_table.setColumnCount(9)
        self.tanks_table.setHorizontalHeaderLabels(
            [
                "Tank ID",
                "Label",
                "Rack",
                "Position",
                "Status",
                "Strain",
                "Fish",
                "Responsible",
                "Age (days)",
            ]
        )

        # Appearance and behavior
        self.tanks_table.setAlternatingRowColors(False)  # We use custom row colors
        self.tanks_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.tanks_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.tanks_table.verticalHeader().setVisible(False)
        self.tanks_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tanks_table.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )

        # Column resizing
        header = self.tanks_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)  # ID
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)  # Label
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)  # Rack
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)  # Position
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)  # Status
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)  # Strain
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents)  # Fish
        header.setSectionResizeMode(7, QHeaderView.ResizeMode.ResizeToContents)  # Responsible
        header.setSectionResizeMode(8, QHeaderView.ResizeMode.ResizeToContents)  # Age

        # Connect signals
        header.sectionClicked.connect(self.handle_header_click)
        self.tanks_table.currentItemChanged.connect(self.handle_selection_change)

    def restore_filter_settings(self):
        """Restore filter settings from QSettings."""
        self.settings.beginGroup("PyRATTanksTab")

        # Restore status filter
        status = self.settings.value("status_filter", "All")
        index = self.status_filter.findText(status)
        if index >= 0:
            self.status_filter.setCurrentIndex(index)

        # Restore age status filter
        age_status = self.settings.value("age_status_filter", "All")
        index = self.age_status_filter.findText(age_status)
        if index >= 0:
            self.age_status_filter.setCurrentIndex(index)

        self.settings.endGroup()

    def save_filter_settings(self):
        """Save filter settings to QSettings."""
        self.settings.beginGroup("PyRATTanksTab")
        self.settings.setValue("status_filter", self.status_filter.currentText())
        self.settings.setValue("age_status_filter", self.age_status_filter.currentText())
        self.settings.setValue("rack_filter", self.rack_filter.currentText())
        self.settings.setValue("responsible_filter", self.responsible_filter.currentText())
        self.settings.endGroup()

    @Slot()
    def refresh_tanks(self):
        """Fetch tanks from the PyRAT API."""
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

        # Build API filters - filter by responsible person
        api_filters = {}
        responsible_id = pyrat_tanks_controller.get_default_responsible_id()
        if responsible_id:
            api_filters["responsible_id"] = responsible_id
            logger.info(f"Filtering tanks by responsible_id: {responsible_id}")

        # Create and start worker
        self.worker = PyRATWorker(
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

    @Slot(list, dict)
    def on_worker_finished(self, tanks_data: list, age_counts: dict):
        """Handle successful API response."""
        self.progress_bar.hide()
        self.refresh_button.setEnabled(True)

        # Parse tanks
        self.tanks = pyrat_tanks_controller.parse_tanks(tanks_data)
        self.age_status_counts = age_counts

        # Update filter dropdowns with available values
        self.update_filter_dropdowns()

        # Apply filters and refresh table
        self.filter_and_refresh_table()

        # Emit urgent count for tab badge
        urgent_count = age_counts.get("URGENT", 0)
        self.urgent_count_changed.emit(urgent_count)

        logger.info(f"Loaded {len(self.tanks)} tanks from PyRAT API")

    @Slot(str)
    def on_worker_error(self, error_message: str):
        """Handle API error."""
        self.progress_bar.hide()
        self.refresh_button.setEnabled(True)

        QMessageBox.critical(
            self,
            "API Error",
            f"Failed to fetch tanks from PyRAT:\n\n{error_message}",
        )
        logger.error(f"PyRAT API error: {error_message}")

    @Slot(str)
    def on_worker_progress(self, message: str):
        """Update progress display."""
        self.progress_bar.setFormat(message)

    def update_filter_dropdowns(self):
        """Update filter dropdown options based on loaded tanks."""
        # Save current selections
        current_rack = self.rack_filter.currentText()
        current_responsible = self.responsible_filter.currentText()

        # Update rack dropdown
        racks = pyrat_tanks_controller.get_unique_values(self.tanks, "location_rack_name")
        self.rack_filter.blockSignals(True)
        self.rack_filter.clear()
        self.rack_filter.addItem("All")
        self.rack_filter.addItems(racks)
        # Restore selection if still valid
        index = self.rack_filter.findText(current_rack)
        if index >= 0:
            self.rack_filter.setCurrentIndex(index)
        self.rack_filter.blockSignals(False)

        # Update responsible dropdown
        responsible_names = pyrat_tanks_controller.get_unique_values(
            self.tanks, "responsible_fullname"
        )
        self.responsible_filter.blockSignals(True)
        self.responsible_filter.clear()
        self.responsible_filter.addItem("All")
        self.responsible_filter.addItems(responsible_names)
        # Restore selection if still valid
        index = self.responsible_filter.findText(current_responsible)
        if index >= 0:
            self.responsible_filter.setCurrentIndex(index)
        self.responsible_filter.blockSignals(False)

    @Slot()
    def filter_and_refresh_table(self):
        """Apply filters and update the table."""
        # Save filter settings
        self.save_filter_settings()

        # Start with all tanks
        filtered = self.tanks

        # Apply rack filter
        rack = self.rack_filter.currentText()
        filtered = pyrat_tanks_controller.filter_by_rack(filtered, rack)

        # Apply status filter
        status = self.status_filter.currentText()
        filtered = pyrat_tanks_controller.filter_by_status(filtered, status)

        # Apply age status filter
        age_status = self.age_status_filter.currentText()
        filtered = pyrat_tanks_controller.filter_by_age_status(filtered, age_status)

        # Apply responsible filter
        responsible = self.responsible_filter.currentText()
        filtered = pyrat_tanks_controller.filter_by_responsible(filtered, responsible)

        # Apply search
        search_text = self.search_box.text().strip()
        filtered = pyrat_tanks_controller.search_tanks(filtered, search_text)

        # Apply sorting
        filtered = self.apply_sorting(filtered)

        self.filtered_tanks = filtered
        self.populate_table(filtered)
        self.update_stats_label()

    def apply_sorting(self, tanks: List[PyRATTank]) -> List[PyRATTank]:
        """Apply current sorting settings."""
        column_to_key = {
            0: "tank_id",
            1: "tank_label",
            2: "location_rack_name",
            3: "tank_position",
            4: "status",
            5: "strain_name_with_id",
            6: "total_fish",
            7: "responsible_fullname",
            8: "age_days",
        }
        sort_key = column_to_key.get(self.sort_column, "tank_id")
        ascending = self.sort_order == Qt.SortOrder.AscendingOrder
        return pyrat_tanks_controller.sort_tanks(tanks, sort_key, ascending)

    @Slot(int)
    def handle_header_click(self, column_index: int):
        """Handle clicks on the table header for sorting."""
        if self.sort_column == column_index:
            # Toggle sort order
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
        else:
            self.detail_view.clear()

    def populate_table(self, tanks: List[PyRATTank]):
        """Fill the table with tank data."""
        self.tanks_table.setSortingEnabled(False)
        self.tanks_table.setRowCount(0)
        self.tanks_table.setRowCount(len(tanks))

        for i, tank in enumerate(tanks):
            # Create items
            self.tanks_table.setItem(i, 0, QTableWidgetItem(str(tank.tank_id)))
            self.tanks_table.setItem(i, 1, QTableWidgetItem(tank.tank_label or ""))
            self.tanks_table.setItem(
                i, 2, QTableWidgetItem(tank.location_rack_name or "")
            )
            self.tanks_table.setItem(i, 3, QTableWidgetItem(tank.tank_position or ""))
            self.tanks_table.setItem(i, 4, QTableWidgetItem(tank.status or ""))
            self.tanks_table.setItem(
                i, 5, QTableWidgetItem(tank.strain_name_with_id or "")
            )
            self.tanks_table.setItem(i, 6, QTableWidgetItem(str(tank.total_fish)))
            self.tanks_table.setItem(
                i, 7, QTableWidgetItem(tank.responsible_fullname or "")
            )
            age_str = str(tank.age_days) if tank.age_days is not None else "N/A"
            self.tanks_table.setItem(i, 8, QTableWidgetItem(age_str))

            # Store tank_id in first column for easy retrieval
            self.tanks_table.item(i, 0).setData(Qt.ItemDataRole.UserRole, tank.tank_id)

            # Set row background color based on age status
            bg_color = self.get_age_status_color(tank.age_status)
            for col in range(self.tanks_table.columnCount()):
                item = self.tanks_table.item(i, col)
                if item:
                    item.setBackground(QBrush(bg_color))

        self.tanks_table.setSortingEnabled(True)

    def get_age_status_color(self, age_status: str) -> QColor:
        """Get background color for age status."""
        if age_status == "URGENT":
            return COLOR_URGENT
        elif age_status == "WARNING":
            return COLOR_WARNING
        elif age_status == "OK":
            return COLOR_OK
        else:
            return COLOR_UNKNOWN

    def update_detail_view(self, row: int):
        """Update the detail view with selected tank info."""
        if row < 0 or row >= len(self.filtered_tanks):
            self.detail_view.clear()
            return

        tank = self.filtered_tanks[row]

        # Format age status with appropriate styling
        age_status_style = ""
        if tank.age_status == "URGENT":
            age_status_style = "color: red; font-weight: bold;"
        elif tank.age_status == "WARNING":
            age_status_style = "color: orange; font-weight: bold;"
        elif tank.age_status == "OK":
            age_status_style = "color: green;"

        age_display = (
            f"{tank.age_days} days ({tank.age_weeks} weeks)"
            if tank.age_days is not None
            else "Unknown"
        )

        details_html = f"""
        <h3>Tank Details: {tank.tank_id}</h3>
        <p>
            <b>Label:</b> {tank.tank_label or 'N/A'}<br>
            <b>Status:</b> {tank.status or 'N/A'}
        </p>

        <h4>Location</h4>
        <p>
            <b>Building:</b> {tank.location_building_name or 'N/A'}<br>
            <b>Room:</b> {tank.location_room_name or 'N/A'}<br>
            <b>Area:</b> {tank.location_area_name or 'N/A'}<br>
            <b>Rack:</b> {tank.location_rack_name or 'N/A'}<br>
            <b>Position:</b> {tank.tank_position or 'N/A'}
        </p>

        <h4>Fish Information</h4>
        <p>
            <b>Strain:</b> {tank.strain_name_with_id or 'N/A'}<br>
            <b>Total Fish:</b> {tank.total_fish}<br>
            <b>Males:</b> {tank.number_of_male} | <b>Females:</b> {tank.number_of_female} | <b>Unknown:</b> {tank.number_of_unknown}<br>
            <b>Age Level:</b> {tank.age_level or 'N/A'}
        </p>

        <h4>Age Monitoring</h4>
        <p>
            <b>Date of Birth:</b> {tank.date_of_birth or 'N/A'}<br>
            <b>Age:</b> {age_display}<br>
            <b>Status:</b> <span style="{age_status_style}">{tank.age_status}</span>
        </p>

        <h4>Responsibility</h4>
        <p>
            <b>Responsible:</b> {tank.responsible_fullname or 'N/A'}<br>
            <b>Owner:</b> {tank.owner_fullname or 'N/A'}
        </p>

        <h4>Dates</h4>
        <p>
            <b>Release Date:</b> {tank.date_of_release or 'N/A'}<br>
            <b>Export Date:</b> {tank.export_date or 'N/A'}<br>
            <b>Close Date:</b> {tank.close_date or 'N/A'}
        </p>
        """

        self.detail_view.setHtml(details_html)

    def update_stats_label(self):
        """Update the summary statistics label."""
        if not self.tanks:
            self.stats_label.setText("No tanks loaded. Click Refresh to load tanks.")
            return

        total = len(self.tanks)
        filtered = len(self.filtered_tanks)
        urgent = self.age_status_counts.get("URGENT", 0)
        warning = self.age_status_counts.get("WARNING", 0)
        ok = self.age_status_counts.get("OK", 0)

        stats_text = (
            f"Showing {filtered} of {total} tanks | "
            f"<span style='color: red;'><b>URGENT: {urgent}</b></span> | "
            f"<span style='color: orange;'><b>WARNING: {warning}</b></span> | "
            f"<span style='color: green;'>OK: {ok}</span>"
        )

        self.stats_label.setText(stats_text)
        self.stats_label.setTextFormat(Qt.TextFormat.RichText)

    def get_urgent_count(self) -> int:
        """Get the count of urgent tanks."""
        return self.age_status_counts.get("URGENT", 0)
