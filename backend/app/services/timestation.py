import httpx
import time
import logging
from app.config import settings

logger = logging.getLogger(__name__)


class TimeStationClient:
    """Async client for the TimeStation API v1.2 with in-memory TTL caching."""

    def __init__(self):
        self.base_url = settings.TIMESTATION_API_BASE
        self.api_key = settings.TIMESTATION_API_KEY
        self._client = httpx.AsyncClient(
            auth=(self.api_key, ""),
            timeout=30.0,
        )
        self._cache: dict[str, dict] = {}  # key -> {"data": ..., "expires": ts}

    # ── internal helpers ──────────────────────────────────────────

    async def _request_json(self, path: str, params: dict | None = None) -> dict:
        resp = await self._client.get(f"{self.base_url}/{path}", params=params)
        resp.raise_for_status()
        return resp.json()

    async def _request_text(self, path: str, params: dict | None = None) -> str:
        resp = await self._client.get(f"{self.base_url}/{path}", params=params)
        resp.raise_for_status()
        return resp.text

    def _get_cached(self, key: str):
        cached = self._cache.get(key)
        if cached and cached["expires"] > time.time():
            return cached["data"]
        return None

    def _set_cached(self, key: str, data, ttl: int):
        self._cache[key] = {"data": data, "expires": time.time() + ttl}

    # ── public API ─────────────────────────────────────────────────

    async def get_employees(self) -> list[dict]:
        """List all employees. Cached 5 min."""
        cached = self._get_cached("employees")
        if cached is not None:
            return cached
        data = await self._request_json("employees")
        employees = data.get("employees", [])
        self._set_cached("employees", employees, settings.CACHE_TTL_EMPLOYEES)
        return employees

    async def get_employee(self, employee_id: str) -> dict:
        """Get a single employee by TimeStation ID."""
        data = await self._request_json(f"employees/{employee_id}")
        return data.get("employee", {})

    async def get_shifts(
        self, employee_id: str, start_date: str, end_date: str
    ) -> list[dict]:
        """Get shifts for an employee in a date range. Cached 15 min."""
        cache_key = f"shifts:{employee_id}:{start_date}:{end_date}"
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached
        data = await self._request_json(
            "shifts",
            params={
                "employee_id": employee_id,
                "start_date": start_date,
                "end_date": end_date,
            },
        )
        shifts = data.get("shifts", [])
        self._set_cached(cache_key, shifts, settings.CACHE_TTL_SHIFTS)
        return shifts

    async def get_current_status_csv(self) -> str:
        """CurrentEmployeeStatus report (CSV). Cached 2 min."""
        cached = self._get_cached("current_status")
        if cached is not None:
            return cached
        text = await self._request_text("reports/CurrentEmployeeStatus")
        self._set_cached("current_status", text, settings.CACHE_TTL_STATUS)
        return text

    async def get_daily_attendance_csv(self, date_str: str) -> str:
        """DailyAttendanceAbsence report (CSV). Cached 2 min."""
        cache_key = f"daily_attendance:{date_str}"
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached
        text = await self._request_text(
            "reports/DailyAttendanceAbsence", params={"report_daydate": date_str}
        )
        self._set_cached(cache_key, text, settings.CACHE_TTL_STATUS)
        return text

    async def get_employee_daily_summary_csv(
        self, start_date: str, end_date: str
    ) -> str:
        """EmployeeDailySummary report (CSV). Cached 15 min."""
        cache_key = f"daily_summary:{start_date}:{end_date}"
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached
        text = await self._request_text(
            "reports/EmployeeDailySummary",
            params={
                "report_startdate": start_date,
                "report_enddate": end_date,
            },
        )
        self._set_cached(cache_key, text, settings.CACHE_TTL_SHIFTS)
        return text

    async def close(self):
        await self._client.aclose()


# Module-level singleton
timestation = TimeStationClient()
