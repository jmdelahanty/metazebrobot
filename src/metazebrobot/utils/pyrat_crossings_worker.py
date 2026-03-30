"""
PyRAT API worker for non-blocking crossings API calls.

This module provides a QThread worker for fetching crossing data from the PyRAT API
without blocking the UI.
"""

import logging
from typing import Dict, List, Any, Optional
from urllib.parse import urljoin

import requests

from PySide6.QtCore import QThread, Signal

logger = logging.getLogger(__name__)


class PyRATCrossingsWorker(QThread):
    """
    Worker thread for fetching crossings from the PyRAT API.

    Signals:
        finished: Emitted when API call completes successfully.
                  Contains list of crossing dictionaries.
        error: Emitted when an error occurs. Contains error message string.
        progress: Emitted to report progress. Contains progress message string.
    """

    finished = Signal(list)
    error = Signal(str)
    progress = Signal(str)

    # Keys to request for crossings
    CROSSING_KEYS = [
        'crossing_id', 'status', 'date_of_record', 'date_of_set_up', 'date_of_raise',
        'responsible_id', 'responsible_fullname',
        'strain_id', 'strain_name', 'strain_name_with_id',
        'description', 'tanks'
    ]

    # Keys to request for related tanks
    TANK_KEYS = [
        'tank_id', 'tank_label', 'status', 'strain_name',
        'number_of_male', 'number_of_female', 'number_of_unknown',
        'alive_count', 'date_of_birth',
        'location_rack_name', 'location_room_name', 'tank_position'
    ]

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

            # Prepare URL
            if not self.base_url.endswith('/'):
                self.base_url += '/'
            api_base = urljoin(self.base_url, 'api/v3/')
            crossings_url = urljoin(api_base, 'tanks/crossings')

            # Prepare request
            headers = {
                'Accept': 'application/json',
                'Content-Type': 'application/json'
            }
            auth = (self.client_token, self.user_token)

            params = {
                'k': self.CROSSING_KEYS,
                'tk': self.TANK_KEYS,
                'l': 1000,  # Limit
                's': ['date_of_record:desc'],  # Sort by most recent first
            }
            params.update(self.filters)

            # Fetch crossings
            self.progress.emit("Fetching crossings...")

            # Disable SSL warnings
            import urllib3
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

            response = requests.get(
                crossings_url,
                auth=auth,
                headers=headers,
                params=params,
                verify=False
            )

            if self._is_cancelled:
                return

            if response.status_code != 200:
                self.error.emit(f"API error: {response.status_code} - {response.text}")
                return

            crossings = response.json()
            total_count = response.headers.get('X-Total-Count', len(crossings))

            self.progress.emit(f"Processing {len(crossings)} crossings...")

            if self._is_cancelled:
                return

            self.progress.emit("Done!")
            self.finished.emit(crossings)

            logger.info(f"Fetched {len(crossings)} crossings (total: {total_count})")

        except Exception as e:
            logger.error(f"PyRAT crossings worker error: {e}", exc_info=True)
            self.error.emit(str(e))
