"""Calendar service: build calendar data from TimeStation shifts and scheduled shifts."""
from datetime import datetime, date, timedelta
from app.config import settings


def build_calendar_data(
    shifts: list[dict],
    scheduled_shifts: list,
    start_date: str,
    end_date: str,
    late_threshold_minutes: int | None = None,
) -> list[dict]:
    """Build calendar data for a date range.

    Args:
        shifts: list of shift dicts from TimeStation, each with:
            - shift_id, total_minutes, in.time (ISO-8601), out.time
        scheduled_shifts: list of ScheduledShift ORM objects, each with:
            - day_of_week (int 0=Mon..6=Sun), start_time (datetime.time), end_time
        start_date: ISO date string 'YYYY-MM-DD'
        end_date: ISO date string 'YYYY-MM-DD'

    Returns:
        list of dicts, one per date in [start_date, end_date], each containing:
            - date (str ISO), worked (bool), total_hours (float),
            - shifts (list of {in, out, minutes}), is_late (bool), late_minutes (int),
            - is_scheduled (bool), is_missed (bool)
    """
    start = date.fromisoformat(start_date)
    end = date.fromisoformat(end_date)

    # Build schedule lookup: day_of_week -> list of scheduled shifts
    schedule_lookup: dict[int, list] = {}
    for sch in scheduled_shifts:
        schedule_lookup.setdefault(sch.day_of_week, []).append(sch)

    # Group shifts by date string
    shifts_by_date: dict[str, list[dict]] = {}
    for shift in shifts:
        in_time_raw = shift.get("in", {}).get("time", "") or ""
        shift_date_str = in_time_raw[:10]  # 'YYYY-MM-DD'
        shifts_by_date.setdefault(shift_date_str, []).append(shift)

    today = date.today()
    threshold = late_threshold_minutes if late_threshold_minutes is not None else settings.LATE_THRESHOLD_MINUTES

    result: list[dict] = []
    current = start
    while current <= end:
        date_str = current.isoformat()
        day_shifts = shifts_by_date.get(date_str, [])
        dow = current.weekday()  # 0=Mon..6=Sun
        scheduled_for_day = schedule_lookup.get(dow, [])

        if day_shifts:
            # Sort by clock-in time
            day_shifts_sorted = sorted(
                day_shifts,
                key=lambda s: (s.get("in", {}) or {}).get("time", ""),
            )
            total_minutes = sum(int(s.get("total_minutes", 0) or 0) for s in day_shifts_sorted)

            shift_entries = []
            for s in day_shifts_sorted:
                in_t = (s.get("in", {}) or {}).get("time", "")
                out_t = (s.get("out", {}) or {}).get("time", "")
                shift_entries.append({
                    "in": in_t,
                    "out": out_t,
                    "minutes": int(s.get("total_minutes", 0) or 0),
                })

            # Late detection: compare first shift's in.time to scheduled start
            is_late = False
            late_minutes = 0
            if scheduled_for_day:
                first_in_raw = (day_shifts_sorted[0].get("in", {}) or {}).get("time", "")
                if first_in_raw:
                    try:
                        first_in_dt = datetime.fromisoformat(
                            first_in_raw.replace("Z", "+00:00")
                        )
                    except ValueError:
                        first_in_dt = None
                    if first_in_dt is not None:
                        scheduled_start = min(s.start_time for s in scheduled_for_day)
                        from datetime import datetime as _dt
                        sched_dt = _dt.combine(current, scheduled_start)
                        first_in_naive = first_in_dt.replace(tzinfo=None) if first_in_dt.tzinfo else first_in_dt
                        delta = (first_in_naive - sched_dt).total_seconds() / 60.0
                        if delta > threshold:
                            is_late = True
                            late_minutes = int(round(delta))

            result.append({
                "date": date_str,
                "worked": True,
                "total_hours": round(total_minutes / 60.0, 2),
                "shifts": shift_entries,
                "is_late": is_late,
                "late_minutes": late_minutes,
                "is_scheduled": bool(scheduled_for_day),
                "is_missed": False,
            })
        else:
            # No shifts worked — check if this was a scheduled day
            is_scheduled = bool(scheduled_for_day)
            # Only flag as missed if the day is in the past (or today) and was scheduled
            is_missed = is_scheduled and current <= today

            result.append({
                "date": date_str,
                "worked": False,
                "total_hours": 0.0,
                "shifts": [],
                "is_late": False,
                "late_minutes": 0,
                "is_scheduled": is_scheduled,
                "is_missed": is_missed,
            })

        current += timedelta(days=1)

    return result
