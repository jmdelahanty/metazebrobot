"""
PyRAT API worker for non-blocking API calls.

This module provides a QThread worker for fetching tank data from the PyRAT API
without blocking the UI.
"""

import logging
import sys
from pathlib import Path
from typing import Dict, List, Any, Optional

from PySide6.QtCore import QThread, Signal

# Add parent directory to path to import pyrat_query_tool
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
from pyrat_query_tool import get_tanks, add_age_information

logger = logging.getLogger(__name__)


class PyRATWorker(QThread):
    """
    Worker thread for fetching tanks from the PyRAT API.

    Signals:
        finished: Emitted when API call completes successfully.
                  Contains (tanks_list, age_status_counts_dict).
        error: Emitted when an error occurs. Contains error message string.
        progress: Emitted to report progress. Contains progress message string.
    """

    finished = Signal(list, dict)
    error = Signal(str)
    progress = Signal(str)

    def __init__(
        self,
        base_url: str,
        client_token: str,
        user_token: str,
        filters: Optional[Dict[str, Any]] = None,
        parent=None,
    ):
        """
        Initialize the worker.

        Args:
            base_url: PyRAT API base URL.
            client_token: API client token.
            user_token: API user token.
            filters: Optional dictionary of API filter parameters.
            parent: Parent QObject.
        """
        super().__init__(parent)
        self.base_url = base_url
        self.client_token = client_token
        self.user_token = user_token
        self.filters = filters or {}
        self._is_cancelled = False

    def cancel(self):
        """Request cancellation of the worker."""
        self._is_cancelled = True

    def run(self):
        """Execute the API call in a separate thread."""
        try:
            self.progress.emit("Connecting to PyRAT API...")

            if self._is_cancelled:
                return

            # Fetch tanks from the API
            self.progress.emit("Fetching tanks...")
            tanks = get_tanks(
                base_url=self.base_url,
                client_token=self.client_token,
                user_token=self.user_token,
                filters=self.filters,
                limit=10000,
                verify_ssl=False,
                console=None,  # Don't use Rich console in worker thread
            )

            if self._is_cancelled:
                return

            if tanks is None:
                self.error.emit("Failed to fetch tanks from PyRAT API")
                return

            # Add age information
            self.progress.emit(f"Processing {len(tanks)} tanks...")
            tanks_with_age, age_status_counts = add_age_information(tanks)

            if self._is_cancelled:
                return

            self.progress.emit("Done!")
            self.finished.emit(tanks_with_age, age_status_counts)

        except Exception as e:
            logger.error(f"PyRAT worker error: {e}", exc_info=True)
            self.error.emit(str(e))
