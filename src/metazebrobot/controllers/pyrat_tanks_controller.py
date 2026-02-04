"""
Controller for PyRAT tanks operations.

This module contains business logic for managing tank data from the PyRAT API,
including credential management, filtering, sorting, and searching.
"""

import json
import logging
import os
from typing import Dict, List, Optional, Any, Callable, Tuple

import keyring

from ..models.pyrat_tank import PyRATTank, AgeStatus

logger = logging.getLogger(__name__)

# Keyring service name (must match pyrat_query_tool.py)
KEYRING_SERVICE = "pyrat-api"

# Default user mapping file path
USER_MAPPING_FILE = os.path.expanduser("~/.pyrat_user_mapping.json")


class PyRATTanksController:
    """
    Controller for PyRAT tank-related operations.

    Provides methods for credential management, parsing tank data,
    filtering, sorting, and searching tanks.
    """

    # Default responsible username for filtering
    DEFAULT_RESPONSIBLE_USERNAME = "delahantyj"

    def __init__(self):
        """Initialize the controller."""
        self._user_mapping: Optional[Dict[str, int]] = None

    def get_user_mapping(self) -> Dict[str, int]:
        """
        Load and return the username to user ID mapping.

        Returns:
            Dictionary mapping usernames to user IDs.
        """
        if self._user_mapping is None:
            self._user_mapping = {}
            if os.path.exists(USER_MAPPING_FILE):
                try:
                    with open(USER_MAPPING_FILE, "r") as f:
                        self._user_mapping = json.load(f)
                    logger.info(f"Loaded {len(self._user_mapping)} user mappings")
                except Exception as e:
                    logger.error(f"Error loading user mapping: {e}")
        return self._user_mapping

    def get_user_id(self, username: str) -> Optional[int]:
        """
        Get the user ID for a username.

        Args:
            username: The username to look up.

        Returns:
            User ID if found, None otherwise.
        """
        mapping = self.get_user_mapping()
        return mapping.get(username)

    def get_default_responsible_id(self) -> Optional[int]:
        """
        Get the user ID for the default responsible person.

        Returns:
            User ID for the default responsible person, or None if not found.
        """
        return self.get_user_id(self.DEFAULT_RESPONSIBLE_USERNAME)

    def get_credentials(self) -> Optional[Dict[str, str]]:
        """
        Retrieve PyRAT API credentials from the system keyring.

        Returns:
            Dictionary with base_url, client_token, user_token if found,
            None otherwise.
        """
        try:
            base_url = keyring.get_password(KEYRING_SERVICE, "base_url")
            client_token = keyring.get_password(KEYRING_SERVICE, "client_token")
            user_token = keyring.get_password(KEYRING_SERVICE, "user_token")

            if base_url and client_token and user_token:
                return {
                    "base_url": base_url,
                    "client_token": client_token,
                    "user_token": user_token,
                }
            return None
        except Exception as e:
            logger.error(f"Error retrieving credentials from keyring: {e}")
            return None

    def has_credentials(self) -> bool:
        """
        Check if PyRAT API credentials are configured.

        Returns:
            True if all required credentials exist, False otherwise.
        """
        return self.get_credentials() is not None

    def parse_tanks(self, raw_tanks: List[Dict[str, Any]]) -> List[PyRATTank]:
        """
        Parse raw API dictionaries into PyRATTank model objects.

        Args:
            raw_tanks: List of raw tank dictionaries from the API.

        Returns:
            List of validated PyRATTank objects.
        """
        result: List[PyRATTank] = []
        for tank_data in raw_tanks:
            try:
                tank = PyRATTank.from_api_dict(tank_data)
                result.append(tank)
            except Exception as e:
                tank_id = tank_data.get("tank_id", "unknown")
                logger.error(f"Error parsing tank {tank_id}: {e}")
        return result

    def filter_tanks(
        self,
        tanks: List[PyRATTank],
        filter_func: Callable[[PyRATTank], bool],
    ) -> List[PyRATTank]:
        """
        Filter tanks based on a filter function.

        Args:
            tanks: List of PyRATTank objects to filter.
            filter_func: Function that returns True for tanks to keep.

        Returns:
            Filtered list of tanks.
        """
        try:
            return [t for t in tanks if filter_func(t)]
        except Exception as e:
            logger.error(f"Error filtering tanks: {e}")
            return tanks

    def filter_by_rack(
        self, tanks: List[PyRATTank], rack_name: str
    ) -> List[PyRATTank]:
        """Filter tanks by rack name."""
        if not rack_name or rack_name == "All":
            return tanks
        return self.filter_tanks(
            tanks, lambda t: t.location_rack_name == rack_name
        )

    def filter_by_status(
        self, tanks: List[PyRATTank], status: str
    ) -> List[PyRATTank]:
        """Filter tanks by status."""
        if not status or status == "All":
            return tanks
        return self.filter_tanks(tanks, lambda t: t.status == status)

    def filter_by_age_status(
        self, tanks: List[PyRATTank], age_status: str
    ) -> List[PyRATTank]:
        """Filter tanks by age status (URGENT, WARNING, OK, UNKNOWN)."""
        if not age_status or age_status == "All":
            return tanks
        return self.filter_tanks(tanks, lambda t: t.age_status == age_status)

    def filter_by_responsible(
        self, tanks: List[PyRATTank], responsible: str
    ) -> List[PyRATTank]:
        """Filter tanks by responsible person name."""
        if not responsible or responsible == "All":
            return tanks
        return self.filter_tanks(
            tanks, lambda t: t.responsible_fullname == responsible
        )

    def search_tanks(
        self,
        tanks: List[PyRATTank],
        search_text: str,
        case_sensitive: bool = False,
    ) -> List[PyRATTank]:
        """
        Search tanks for text in various fields.

        Args:
            tanks: List of PyRATTank objects to search.
            search_text: Text to search for.
            case_sensitive: Whether to perform case-sensitive search.

        Returns:
            List of tanks matching the search.
        """
        if not search_text:
            return tanks

        result: List[PyRATTank] = []
        search_lower = search_text if case_sensitive else search_text.lower()

        for tank in tanks:
            try:
                # Fields to search within
                fields_to_check = [
                    str(tank.tank_id),
                    tank.tank_label or "",
                    tank.tank_position or "",
                    tank.location_rack_name or "",
                    tank.location_room_name or "",
                    tank.responsible_fullname or "",
                    tank.owner_fullname or "",
                    tank.strain_name_with_id or "",
                    tank.status or "",
                ]

                # Perform search
                for field_value in fields_to_check:
                    check_value = field_value if case_sensitive else field_value.lower()
                    if search_lower in check_value:
                        result.append(tank)
                        break

            except Exception as e:
                logger.error(f"Error searching tank {tank.tank_id}: {e}")

        return result

    def sort_tanks(
        self,
        tanks: List[PyRATTank],
        sort_key: str,
        ascending: bool = True,
    ) -> List[PyRATTank]:
        """
        Sort tanks by a specific key.

        Args:
            tanks: List of PyRATTank objects to sort.
            sort_key: Attribute name to sort by.
            ascending: Sort direction.

        Returns:
            Sorted list of tanks.
        """

        def get_sort_value(tank: PyRATTank, key: str) -> Any:
            """Extract sortable value from tank."""
            if hasattr(tank, key):
                value = getattr(tank, key)
                # Handle None values for proper sorting
                if value is None:
                    # Return a value that sorts appropriately
                    if key in ("age_days", "tank_id", "total_fish"):
                        return -1 if ascending else float("inf")
                    return ""
                return value
            return ""

        try:
            return sorted(
                tanks,
                key=lambda t: get_sort_value(t, sort_key),
                reverse=not ascending,
            )
        except Exception as e:
            logger.error(f"Error sorting tanks by '{sort_key}': {e}")
            return tanks

    def build_api_filters(
        self,
        rack: Optional[str] = None,
        status: Optional[str] = None,
        responsible_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Build API query parameters for filtering.

        Args:
            rack: Rack name to filter by.
            status: Tank status to filter by.
            responsible_id: Responsible person ID to filter by.

        Returns:
            Dictionary of API filter parameters.
        """
        filters: Dict[str, Any] = {}

        if rack and rack != "All":
            filters["location_rack_name"] = rack

        if status and status != "All":
            filters["status"] = status

        if responsible_id:
            filters["responsible_id"] = responsible_id

        return filters

    def get_unique_values(
        self, tanks: List[PyRATTank], field: str
    ) -> List[str]:
        """
        Get unique values for a field from the tank list.

        Args:
            tanks: List of tanks.
            field: Field name to extract unique values from.

        Returns:
            Sorted list of unique non-empty values.
        """
        values = set()
        for tank in tanks:
            value = getattr(tank, field, None)
            if value:
                values.add(str(value))
        return sorted(values)

    def count_by_age_status(
        self, tanks: List[PyRATTank]
    ) -> Dict[str, int]:
        """
        Count tanks by age status.

        Args:
            tanks: List of tanks.

        Returns:
            Dictionary with counts for each age status.
        """
        counts = {"URGENT": 0, "WARNING": 0, "OK": 0, "UNKNOWN": 0}
        for tank in tanks:
            status = tank.age_status
            if status in counts:
                counts[status] += 1
        return counts


# Create singleton instance
pyrat_tanks_controller = PyRATTanksController()
