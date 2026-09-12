import calendar
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from dateutil import parser as dateutil_parser
import structlog

logger = structlog.get_logger(__name__)

RELATIVE_PATTERN = re.compile(
    r"(\d+)\s*(second|minute|hour|day|week)s?\s*ago", re.IGNORECASE
)


def parse_to_utc(raw_date: Any, reference_now: Optional[datetime] = None) -> Optional[datetime]:
    now = reference_now or datetime.now(timezone.utc)

    if raw_date is None:
        return None

    # Unix epoch timestamps (seconds or JavaScript milliseconds)
    if isinstance(raw_date, (int, float)):
        try:
            ts = float(raw_date)
            if ts > 1e11:  # JavaScript timestamp in milliseconds
                ts /= 1000.0
            return datetime.fromtimestamp(ts, tz=timezone.utc)
        except (ValueError, OSError, OverflowError) as e:
            logger.warning("date_parse_epoch_failed", raw=raw_date, error=str(e))
            return None

    # feedparser struct_time objects
    if hasattr(raw_date, "tm_year"):
        try:
            return datetime.fromtimestamp(calendar.timegm(raw_date), tz=timezone.utc)
        except Exception as e:
            logger.warning("date_parse_struct_time_failed", error=str(e))
            return None

    if isinstance(raw_date, str):
        raw_str = raw_date.strip()
        if not raw_str:
            return None

        match = RELATIVE_PATTERN.search(raw_str)
        if match:
            amount, unit = int(match.group(1)), match.group(2).lower()
            delta_map = {
                "second": timedelta(seconds=amount),
                "minute": timedelta(minutes=amount),
                "hour": timedelta(hours=amount),
                "day": timedelta(days=amount),
                "week": timedelta(weeks=amount),
            }
            return now - delta_map[unit]

        try:
            parsed = dateutil_parser.parse(raw_str)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc)
        except (ValueError, OverflowError) as e:
            logger.warning("date_parse_failed", raw=raw_str, error=str(e))
            return None

    return None


def is_within_freshness_window(parsed_date: Optional[datetime], hours: int = 24) -> bool:
    if parsed_date is None:
        return False
    if parsed_date.tzinfo is None:
        parsed_date = parsed_date.replace(tzinfo=timezone.utc)

    now = datetime.now(timezone.utc)
    delta = now - parsed_date
    return -timedelta(minutes=15) <= delta <= timedelta(hours=hours)
