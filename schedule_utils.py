"""
Schedule utilities: parse natural-language schedules into UTC cron expressions.
Uses a simple mapping for common patterns + pytz for timezone conversion.
"""

import re
from datetime import datetime

import pytz


# Common natural language → cron patterns
SCHEDULE_PATTERNS = {
    r"every\s+day\s+at\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?": "daily",
    r"every\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\s+at\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?": "weekly",
    r"every\s+(\d+)\s+hours?": "hourly",
    r"every\s+hour": "hourly_1",
    r"every\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)": "weekly_default",
}

DAYS_MAP = {
    "sunday": 0, "monday": 1, "tuesday": 2, "wednesday": 3,
    "thursday": 4, "friday": 5, "saturday": 6,
}


def _parse_time(hour_str: str, minute_str: str | None, ampm: str | None) -> tuple[int, int]:
    """Parse hour/minute/ampm into 24-hour time."""
    hour = int(hour_str)
    minute = int(minute_str) if minute_str else 0

    if ampm:
        ampm = ampm.lower()
        if ampm == "pm" and hour != 12:
            hour += 12
        elif ampm == "am" and hour == 12:
            hour = 0

    return hour, minute


def _convert_to_utc(hour: int, minute: int, timezone: str) -> tuple[int, int]:
    """Convert a local hour:minute to UTC using pytz."""
    tz = pytz.timezone(timezone)
    # Use today's date for the conversion
    today = datetime.now().date()
    local_dt = tz.localize(datetime(today.year, today.month, today.day, hour, minute))
    utc_dt = local_dt.astimezone(pytz.UTC)
    return utc_dt.hour, utc_dt.minute


def natural_to_cron(text: str, timezone: str = "UTC") -> dict:
    """
    Parse a natural-language schedule into a UTC cron expression.

    Returns:
        {
            "cron_utc": "30 2 * * *",
            "display": "8:00 AM IST (2:30 AM UTC)"
        }
    """
    text_lower = text.strip().lower()

    # Try: every day at <time>
    m = re.match(r"every\s+day\s+at\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", text_lower)
    if m:
        hour, minute = _parse_time(m.group(1), m.group(2), m.group(3))
        utc_h, utc_m = _convert_to_utc(hour, minute, timezone)

        tz_abbr = _tz_abbr(timezone)
        local_str = f"{hour % 12 or 12}:{minute:02d} {'AM' if hour < 12 else 'PM'} {tz_abbr}"
        utc_str = f"{utc_h % 12 or 12}:{utc_m:02d} {'AM' if utc_h < 12 else 'PM'} UTC"

        return {
            "cron_utc": f"{utc_m} {utc_h} * * *",
            "display": f"{local_str} ({utc_str})",
        }

    # Try: every <weekday> at <time>
    m = re.match(
        r"every\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\s+at\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?",
        text_lower,
    )
    if m:
        day = DAYS_MAP[m.group(1)]
        hour, minute = _parse_time(m.group(2), m.group(3), m.group(4))
        utc_h, utc_m = _convert_to_utc(hour, minute, timezone)

        tz_abbr = _tz_abbr(timezone)
        local_str = f"{hour % 12 or 12}:{minute:02d} {'AM' if hour < 12 else 'PM'} {tz_abbr}"
        utc_str = f"{utc_h % 12 or 12}:{utc_m:02d} {'AM' if utc_h < 12 else 'PM'} UTC"
        day_name = m.group(1).capitalize()

        return {
            "cron_utc": f"{utc_m} {utc_h} * * {day}",
            "display": f"{day_name} {local_str} ({utc_str})",
        }

    # Try: every <weekday> (default 9am)
    m = re.match(r"every\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)$", text_lower)
    if m:
        day = DAYS_MAP[m.group(1)]
        utc_h, utc_m = _convert_to_utc(9, 0, timezone)
        day_name = m.group(1).capitalize()
        return {
            "cron_utc": f"{utc_m} {utc_h} * * {day}",
            "display": f"{day_name} 9:00 AM ({utc_h}:{utc_m:02d} UTC)",
        }

    # Try: every N hours
    m = re.match(r"every\s+(\d+)\s+hours?", text_lower)
    if m:
        n = int(m.group(1))
        return {
            "cron_utc": f"0 */{n} * * *",
            "display": f"Every {n} hour(s)",
        }

    # Try: every hour
    if re.match(r"every\s+hour$", text_lower):
        return {
            "cron_utc": "0 * * * *",
            "display": "Every hour",
        }

    # Fallback: treat as raw cron if it looks like one (5 fields)
    parts = text.strip().split()
    if len(parts) == 5:
        return {
            "cron_utc": text.strip(),
            "display": f"Custom: {text.strip()} UTC",
        }

    # Unable to parse
    return {
        "cron_utc": "0 0 * * *",
        "display": f"Could not parse '{text}' — defaulting to midnight UTC",
    }


def _tz_abbr(timezone: str) -> str:
    """Get a short timezone abbreviation."""
    try:
        tz = pytz.timezone(timezone)
        now = datetime.now(tz)
        return now.strftime("%Z")
    except Exception:
        return timezone
