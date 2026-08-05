import pytest
from unittest.mock import AsyncMock, patch
from app.services.timestation import TimeStationClient


@pytest.mark.asyncio
async def test_get_employees_returns_list():
    client = TimeStationClient()
    mock_data = {
        "employees": [
            {"employee_id": "emp_1", "name": "Test User", "pin": "1234", "status": "in"}
        ]
    }
    with patch.object(client, "_request_json", new_callable=AsyncMock) as mock_req:
        mock_req.return_value = mock_data
        result = await client.get_employees()
        assert len(result) == 1
        assert result[0]["name"] == "Test User"
        mock_req.assert_called_once_with("employees")


@pytest.mark.asyncio
async def test_cache_avoids_duplicate_api_call():
    client = TimeStationClient()
    call_count = 0
    mock_data = {"employees": [{"employee_id": "emp_1", "name": "Cached User"}]}

    async def mock_request(path, params=None):
        nonlocal call_count
        call_count += 1
        return mock_data

    with patch.object(client, "_request_json", side_effect=mock_request):
        result1 = await client.get_employees()
        result2 = await client.get_employees()
        assert call_count == 1  # Only first call hits the API
        assert result1 == result2
        assert result1[0]["name"] == "Cached User"


@pytest.mark.asyncio
async def test_get_shifts_caches_per_employee_date_range():
    client = TimeStationClient()
    mock_data = {"shifts": [{"shift_id": "s1", "total_minutes": "480"}]}

    with patch.object(client, "_request_json", new_callable=AsyncMock) as mock_req:
        mock_req.return_value = mock_data
        result = await client.get_shifts("emp_1", "2025-07-01", "2025-07-31")
        assert len(result) == 1
        assert result[0]["total_minutes"] == "480"

        # Second call should use cache
        await client.get_shifts("emp_1", "2025-07-01", "2025-07-31")
        assert mock_req.call_count == 1

        # Different date range = new API call
        await client.get_shifts("emp_1", "2025-08-01", "2025-08-31")
        assert mock_req.call_count == 2


@pytest.mark.asyncio
async def test_get_current_status_csv():
    client = TimeStationClient()
    mock_csv = '"Name","Status"\n"Test","In"'
    with patch.object(client, "_request_text", new_callable=AsyncMock) as mock_text:
        mock_text.return_value = mock_csv
        result = await client.get_current_status_csv()
        assert result == mock_csv
        # Second call should use cache
        await client.get_current_status_csv()
        assert mock_text.call_count == 1
