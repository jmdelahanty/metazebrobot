"""
Controller for PyRAT tanks operations.

This module contains business logic for managing tank data from the PyRAT API,
including credential management, filtering, sorting, and searching.
"""

import json
import logging
import os
from typing import Dict, List, Optional, Any, Callable, Tuple

from ..models.pyrat_tank import PyRATTank, AgeStatus
from ..models.pyrat_crossing import PyRATCrossing
from ..utils.pyrat_credentials import (
    get_pyrat_api_credentials,
    get_pyrat_frontend_credentials,
)

logger = logging.getLogger(__name__)

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
        self._cached_crossings: List[PyRATCrossing] = []

    @property
    def cached_crossings(self) -> List[PyRATCrossing]:
        """Return cached crossings from the last API fetch."""
        return self._cached_crossings

    @cached_crossings.setter
    def cached_crossings(self, crossings: List[PyRATCrossing]):
        self._cached_crossings = crossings

    def get_crossing_by_id(self, crossing_id: str) -> Optional[PyRATCrossing]:
        """Look up a crossing by ID from the cache."""
        for c in self._cached_crossings:
            if str(c.crossing_id) == str(crossing_id):
                return c
        return None

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
        Retrieve PyRAT API credentials from CLI/env/keyring helpers.

        Returns:
            Dictionary with base_url, client_token, user_token if found,
            None otherwise.
        """
        return get_pyrat_api_credentials()

    def has_credentials(self) -> bool:
        """
        Check if PyRAT API credentials are configured.

        Returns:
            True if all required credentials exist, False otherwise.
        """
        return self.get_credentials() is not None

    def get_frontend_credentials(self) -> Optional[Dict[str, str]]:
        """Retrieve optional PyRAT frontend credentials for backend/v1 access."""
        api_credentials = self.get_credentials()
        default_base_url = api_credentials["base_url"] if api_credentials else None
        return get_pyrat_frontend_credentials(default_base_url=default_base_url)

    def has_frontend_credentials(self) -> bool:
        """Check if PyRAT frontend credentials are configured."""
        return self.get_frontend_credentials() is not None

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

    # =========================================================================
    # Crossing-related methods
    # =========================================================================

    def parse_crossings(self, raw_crossings: List[Dict[str, Any]]) -> List[PyRATCrossing]:
        """
        Parse raw API dictionaries into PyRATCrossing model objects.

        Args:
            raw_crossings: List of raw crossing dictionaries from the API.

        Returns:
            List of validated PyRATCrossing objects.
        """
        result: List[PyRATCrossing] = []
        for crossing_data in raw_crossings:
            try:
                crossing = PyRATCrossing.from_api_dict(crossing_data)
                result.append(crossing)
            except Exception as e:
                crossing_id = crossing_data.get("crossing_id", "unknown")
                logger.error(f"Error parsing crossing {crossing_id}: {e}")
        return result

    def filter_crossings(
        self,
        crossings: List[PyRATCrossing],
        filter_func: Callable[[PyRATCrossing], bool],
    ) -> List[PyRATCrossing]:
        """
        Filter crossings based on a filter function.

        Args:
            crossings: List of PyRATCrossing objects to filter.
            filter_func: Function that returns True for crossings to keep.

        Returns:
            Filtered list of crossings.
        """
        try:
            return [c for c in crossings if filter_func(c)]
        except Exception as e:
            logger.error(f"Error filtering crossings: {e}")
            return crossings

    def filter_crossings_by_status(
        self, crossings: List[PyRATCrossing], status: str
    ) -> List[PyRATCrossing]:
        """Filter crossings by status (recorded, set-up, raised, discarded)."""
        if not status or status == "All":
            return crossings
        return self.filter_crossings(crossings, lambda c: c.status == status)

    def filter_crossings_by_strain(
        self, crossings: List[PyRATCrossing], strain: str
    ) -> List[PyRATCrossing]:
        """Filter crossings by strain name."""
        if not strain or strain == "All":
            return crossings
        return self.filter_crossings(
            crossings, lambda c: c.strain_name == strain or c.strain_name_with_id == strain
        )

    def search_crossings(
        self,
        crossings: List[PyRATCrossing],
        search_text: str,
        case_sensitive: bool = False,
    ) -> List[PyRATCrossing]:
        """
        Search crossings for text in various fields.

        Args:
            crossings: List of PyRATCrossing objects to search.
            search_text: Text to search for.
            case_sensitive: Whether to perform case-sensitive search.

        Returns:
            List of crossings matching the search.
        """
        if not search_text:
            return crossings

        result: List[PyRATCrossing] = []
        search_lower = search_text if case_sensitive else search_text.lower()

        for crossing in crossings:
            try:
                # Fields to search within
                fields_to_check = [
                    str(crossing.crossing_id),
                    crossing.strain_name or "",
                    crossing.strain_name_with_id or "",
                    crossing.description or "",
                    crossing.responsible_fullname or "",
                    crossing.status or "",
                ]

                # Perform search
                for field_value in fields_to_check:
                    check_value = field_value if case_sensitive else field_value.lower()
                    if search_lower in check_value:
                        result.append(crossing)
                        break

            except Exception as e:
                logger.error(f"Error searching crossing {crossing.crossing_id}: {e}")

        return result

    def sort_crossings(
        self,
        crossings: List[PyRATCrossing],
        sort_key: str,
        ascending: bool = True,
    ) -> List[PyRATCrossing]:
        """
        Sort crossings by a specific key.

        Args:
            crossings: List of PyRATCrossing objects to sort.
            sort_key: Attribute name to sort by.
            ascending: Sort direction.

        Returns:
            Sorted list of crossings.
        """

        def get_sort_value(crossing: PyRATCrossing, key: str) -> Any:
            """Extract sortable value from crossing."""
            if hasattr(crossing, key):
                value = getattr(crossing, key)
                if value is None:
                    if key in ("crossing_id", "raised_count", "requested_groups", "performance_target_count"):
                        return -1 if ascending else float("inf")
                    return ""
                return value
            return ""

        try:
            return sorted(
                crossings,
                key=lambda c: get_sort_value(c, sort_key),
                reverse=not ascending,
            )
        except Exception as e:
            logger.error(f"Error sorting crossings by '{sort_key}': {e}")
            return crossings

    def get_unique_crossing_values(
        self, crossings: List[PyRATCrossing], field: str
    ) -> List[str]:
        """
        Get unique values for a field from the crossing list.

        Args:
            crossings: List of crossings.
            field: Field name to extract unique values from.

        Returns:
            Sorted list of unique non-empty values.
        """
        values = set()
        for crossing in crossings:
            value = getattr(crossing, field, None)
            if value:
                values.add(str(value))
        return sorted(values)

    def count_crossings_by_status(
        self, crossings: List[PyRATCrossing]
    ) -> Dict[str, int]:
        """
        Count crossings by status.

        Args:
            crossings: List of crossings.

        Returns:
            Dictionary with counts for each status.
        """
        counts = {"recorded": 0, "set-up": 0, "raised": 0, "discarded": 0}
        for crossing in crossings:
            status = crossing.status
            if status in counts:
                counts[status] += 1
        return counts

    def get_crossing_stats(
        self, crossings: List[PyRATCrossing]
    ) -> Dict[str, Any]:
        """
        Get summary statistics for crossings.

        Args:
            crossings: List of crossings.

        Returns:
            Dictionary with various statistics.
        """
        total = len(crossings)
        status_counts = self.count_crossings_by_status(crossings)

        # Calculate performance stats for crossings with valid data
        performances = [c.performance for c in crossings if c.performance is not None]
        avg_performance = sum(performances) / len(performances) if performances else None

        total_requested = sum(c.performance_target_count or 0 for c in crossings)
        total_raised = sum(c.raised_count for c in crossings)

        return {
            "total": total,
            "status_counts": status_counts,
            "total_requested": total_requested,
            "total_raised": total_raised,
            "avg_performance": avg_performance,
            "crossings_with_performance": len(performances),
        }


# Create singleton instance
pyrat_tanks_controller = PyRATTanksController()
