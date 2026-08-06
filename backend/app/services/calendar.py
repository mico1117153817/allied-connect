"""Calendar service: build calendar data from TimeStation shifts and scheduled shifts."""
from datetime import datetime, date, timedelta
from app.config import settings


def build_calendar_data(
    shifts: list[dict],
    scheduled_shifts: list,
    start_date: str,
    end_date: str,
    late_threshold_minutes: int | None = None,
    early_leave_threshold_minutes: int | None = None,
) -> list[dict]:
    """Build calendar data for a date range.

    Returns list of dicts per date with:
        - date, worked, total_hours, shifts
        - is_late, late_minutes (arrived after threshold)
        - is_early_leave, early_leave_minutes (left before scheduled end)
        - is_scheduled, is_missed (scheduled but didn't work, past date)
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
        shift_date_str = in_time_raw[:10]
        shifts_by_date.setdefault(shift_date_str, []).append(shift)

    today = date.today()
    late_threshold = late_threshold_minutes if late_threshold_minutes is not None else settings.LATE_THRESHOLD_MINUTES
    early_threshold = early_leave_threshold_minutes if early_leave_threshold_minutes is not None else late_threshold

    result: list[dict] = []
    current = start
    while current <= end:
        date_str = current.isoformat()
        day_shifts = shifts_by_date.get(date_str, [])
        dow = current.weekday()  # 0=Mon..6=Sun
        scheduled_for_day = schedule_lookup.get(dow, [])

        if day_shifts:
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
                        if delta > late_threshold:
                            is_late = True
                            late_minutes = int(round(delta))

            # Early leave detection: compare last shift's out.time to scheduled end
            is_early_leave = False
            early_leave_minutes = 0
            if scheduled_for_day:
                last_out_raw = (day_shifts_sorted[-1].get("out", {}) or {}).get("time", "")
                if last_out_raw:
                    try:
                        last_out_dt = datetime.fromisoformat(
                            last_out_raw.replace("Z", "+00:00")
                        )
                    except ValueError:
                        last_out_dt = None
                    if last_out_dt is not None:
                        scheduled_end = max(s.end_time for s in scheduled_for_day)
                        from datetime import datetime as _dt
                        sched_end_dt = _dt.combine(current, scheduled_end)
                        last_out_naive = last_out_dt.replace(tzinfo=None) if last_out_dt.tzinfo else last_out_dt
                        end_delta = (sched_end_dt - last_out_naive).total_seconds() / 60.0
                        if end_delta > early_threshold:
                            is_early_leave = True
                            early_leave_minutes = int(round(end_delta))

            result.append({
                "date": date_str,
                "worked": True,
                "total_hours": round(total_minutes / 60.0, 2),
                "shifts": shift_entries,
                "is_late": is_late,
                "late_minutes": late_minutes,
                "is_early_leave": is_early_leave,
                "early_leave_minutes": early_leave_minutes,
                "is_scheduled": bool(scheduled_for_day),
                "is_missed": False,
            })
        else:
            is_scheduled = bool(scheduled_for_day)
            is_missed = is_scheduled and current <= today

            result.append({
                "date": date_str,
                "worked": False,
                "total_hours": 0.0,
                "shifts": [],
                "is_late": False,
                "late_minutes": 0,
                "is_early_leave": False,
                "early_leave_minutes": 0,
                "is_scheduled": is_scheduled,
                "is_missed": is_missed,
            })

        current += timedelta(days=1)

    return result
