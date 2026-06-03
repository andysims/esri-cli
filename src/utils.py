# src/utils.py
from datetime import datetime, timezone
import logging

log = logging.getLogger(__name__)


def esri_timestamp_to_str(esri_time: int | float) -> str | None:
    """Convert an ESRI timestamp (epoch in ms) to a 12-hour AM/PM string format.

    Returns 'MM-DD-YYYY hh:mm:ss AM/PM' or None if an error occurs.
    """
    try:
        # Convert milliseconds to seconds and create a timezone-aware UTC datetime
        dt_utc = datetime.fromtimestamp(esri_time / 1000.0, tz=timezone.utc)

        # Format to: 2026-06-02 04:56:12 PM (%I is 12-hour, %p is AM/PM)
        return dt_utc.strftime("%m-%d-%Y %I:%M %p")

    except (TypeError, ValueError, OverflowError) as e:
        log.error(f"Failed to convert ESRI timestamp '{esri_time}': {e}")
        return None


def get_output_file_timestamp() -> str:
    """Returns the current date formatted as 'YYYYMMDD' for naming files."""
    # Uses local time by default
    return datetime.now().strftime("%Y%m%d")
