"""Small read-only client for the PyRAT api/v3 endpoints used for heritage.

Shared by scripts/refresh_cross_cache.py and the tank-origin resolver so the
crossing field lists, paging (PyRAT's ``o`` offset + ``X-Total-Count``), and
request pacing live in one place.
"""

from __future__ import annotations

import time
from datetime import date
from typing import Any, Dict, List, Optional, Sequence

import requests
import urllib3

from .pyrat_credentials import get_pyrat_api_credentials

BATCH_SIZE = 50
PAGE_SIZE = 200


class PyratApiClient:
    def __init__(
        self,
        crossing_fields: Sequence[str],
        crossing_tank_fields: Sequence[str],
        pause: float = 0.5,
        credentials: Optional[Dict[str, str]] = None,
    ):
        credentials = credentials or get_pyrat_api_credentials()
        if not credentials:
            raise RuntimeError("PyRAT API credentials are not configured.")
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        self.base_url = f"{credentials['base_url']}api/v3/"
        self.auth = (credentials["client_token"], credentials["user_token"])
        self.crossing_fields = list(crossing_fields)
        self.crossing_tank_fields = list(crossing_tank_fields)
        self.pause = pause
        self.requests = 0

    def _get(self, path: str, params: Optional[Dict[str, Any]] = None) -> requests.Response:
        if self.requests:
            time.sleep(self.pause)
        self.requests += 1
        response = requests.get(
            self.base_url + path,
            auth=self.auth,
            headers={"Accept": "application/json"},
            params=params or {},
            verify=False,
            timeout=60,
        )
        response.raise_for_status()
        return response

    def _crossings(self, params: Dict[str, Any]) -> requests.Response:
        return self._get("tanks/crossings", {
            "k": self.crossing_fields,
            "tk": self.crossing_tank_fields,
            **params,
        })

    def crossings_by_ids(self, crossing_ids: Sequence[int]) -> List[Dict[str, Any]]:
        crossings: List[Dict[str, Any]] = []
        for start in range(0, len(crossing_ids), BATCH_SIZE):
            batch = list(crossing_ids[start:start + BATCH_SIZE])
            crossings.extend(self._crossings({"crossing_id": batch, "l": len(batch)}).json())
        return crossings

    def crossings_recorded(self, since: date, until: Optional[date] = None) -> List[Dict[str, Any]]:
        """All owners' crossings recorded in [since, until], paged."""
        crossings: List[Dict[str, Any]] = []
        offset = 0
        while True:
            params: Dict[str, Any] = {
                "date_of_record_from": since.isoformat(),
                "s": ["crossing_id:asc"],
                "l": PAGE_SIZE,
                "o": offset,
            }
            if until:
                params["date_of_record_to"] = until.isoformat()
            response = self._crossings(params)
            page = response.json()
            crossings.extend(page)
            total = int(response.headers.get("X-Total-Count") or 0)
            offset += len(page)
            if not page or offset >= total:
                return crossings

    def tank_history(self, tank_id: Any) -> List[Dict[str, Any]]:
        return self._get(f"tanks/{tank_id}/history").json()
