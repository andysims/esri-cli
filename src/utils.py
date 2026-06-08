# src/utils.py
from datetime import datetime, timezone
import logging
import csv
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import List, Any, Union

log = logging.getLogger(__name__)


# ======== Datetime Utils ========
def esri_timestamp_to_str(esri_time: int | float) -> str | None:
    """Convert an ESRI timestamp (epoch in ms) to a 12-hour AM/PM string format.

    Returns 'MM-DD-YYYY hh:mm:ss AM/PM' or None if an error occurs.
    """
    if esri_time in (-1, 0, None):
        return None

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


# ======== Export Utils ========
def export_to_csv(data: Union[Any, List[Any]], filename_prefix: str):
    """
    Exports a single model or list of models to a CSV in the user's
    Downloads folder. Automatically sorts by 'created' date descending
    if the field exists.
    """
    if not data:
        print("No data to export.")
        return

    # Normalize
    if not isinstance(data, list):
        data = [data]

    def get_sort_key(item):
        val = getattr(item, "created", None)
        if not val or not isinstance(val, str):
            return datetime.min
        try:
            # Handles: MM/DD/YYYY HH:MM AM/PM
            return datetime.strptime(val, "%m/%d/%Y %I:%M %p")
        except ValueError:
            return datetime.min

    data.sort(key=get_sort_key, reverse=True)

    downloads_path = Path.home() / "Downloads"
    timestamp = datetime.now().strftime("%Y%m%d")
    file_path = downloads_path / f"{filename_prefix}_{timestamp}.csv"

    dict_data = [asdict(item) if is_dataclass(item) else item for item in data]

    with open(file_path, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=dict_data[0].keys())
        writer.writeheader()
        writer.writerows(dict_data)

    print(f"Successfully exported {len(data)} record(s) to: {file_path}")
