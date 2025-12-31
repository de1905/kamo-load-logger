"""KAMO Power API client."""

import logging
from typing import List, Optional
from datetime import datetime

import httpx

from app.config import get_settings
from app.models import (
    KAMOCooperative,
    KAMOAreaGridResponse,
    KAMOAreaLoadTableResponse,
)

logger = logging.getLogger(__name__)


class KAMOClient:
    """Client for KAMO Power API."""

    def __init__(self, base_url: Optional[str] = None, timeout: float = 30.0):
        settings = get_settings()
        self.base_url = base_url or settings.kamo_base_url
        self.timeout = timeout

    async def _get(self, endpoint: str) -> dict:
        """Make GET request to KAMO API."""
        url = f"{self.base_url}{endpoint}"
        logger.debug(f"Fetching: {url}")

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(url)
            response.raise_for_status()
            return response.json()

    async def check_connectivity(self) -> bool:
        """Check if KAMO API is reachable."""
        try:
            await self._get("/area")
            return True
        except Exception as e:
            logger.warning(f"KAMO API connectivity check failed: {e}")
            return False

    async def check_internet(self) -> bool:
        """Check if internet is available (test known reliable endpoint)."""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get("https://www.google.com/generate_204")
                return response.status_code == 204
        except Exception:
            try:
                async with httpx.AsyncClient(timeout=5.0) as client:
                    response = await client.get("https://www.apple.com/library/test/success.html")
                    return response.status_code == 200
            except Exception:
                return False

    async def get_cooperatives(self) -> List[KAMOCooperative]:
        """Fetch list of cooperatives."""
        data = await self._get("/area")
        return [KAMOCooperative(**item) for item in data]

    async def get_area_grid(self, area_id: int) -> KAMOAreaGridResponse:
        """Fetch chart data for an area (includes actual and forecast data)."""
        data = await self._get(f"/areagrid/{area_id}")
        return KAMOAreaGridResponse(**data)

    async def get_area_substations(self, area_id: int) -> KAMOAreaLoadTableResponse:
        """Fetch current substation data for an area."""
        data = await self._get(f"/arealoadtable/{area_id}")
        return KAMOAreaLoadTableResponse(**data)

    def parse_timestamp(self, label: str) -> Optional[datetime]:
        """Parse KAMO timestamp label format: 'MM/DD/YYYY H:00'."""
        try:
            return datetime.strptime(label, "%m/%d/%Y %H:%M")
        except ValueError:
            try:
                # Try alternate format without leading zeros
                return datetime.strptime(label, "%m/%d/%Y %H:%M")
            except ValueError:
                logger.warning(f"Failed to parse timestamp: {label}")
                return None

    def extract_actual_data(
        self, response: KAMOAreaGridResponse
    ) -> List[tuple[datetime, float]]:
        """
        Extract actual (non-forecast) load data from area grid response.

        Returns list of (timestamp, load_kw) tuples.
        """
        # Find the "Actual" series
        actual_series = None
        for series in response.chartLineData:
            if series.label.lower() == "actual":
                actual_series = series
                break

        if not actual_series:
            logger.warning(f"No 'Actual' series found for area {response.Id}")
            return []

        results = []
        for i, value in enumerate(actual_series.data):
            if value is not None and i < len(response.lineChartLabels):
                timestamp = self.parse_timestamp(response.lineChartLabels[i])
                if timestamp:
                    results.append((timestamp, value))

        return results
