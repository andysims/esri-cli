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


def export_to_txt(content: str, filename_prefix: str) -> None:
    """Write a plain-text report string to ~/Downloads/<prefix>_YYYYMMDD.txt.

    content:         The formatted string to write. Should already be stripped
                     of Rich markup (use _strip_markup() in main.py before
                     passing in).
    filename_prefix: Used as the base name, e.g. "sharing_audit" →
                     sharing_audit_20260609.txt
    """
    from pathlib import Path
    from datetime import datetime

    if not content or not content.strip():
        print("No content to export.")
        return

    downloads_path = Path.home() / "Downloads"
    timestamp = datetime.now().strftime("%Y%m%d")
    file_path = downloads_path / f"{filename_prefix}_{timestamp}.txt"

    with open(file_path, mode="w", encoding="utf-8") as f:
        f.write(f"ArcGIS Admin CLI — {filename_prefix.replace('_', ' ').title()}\n")
        f.write(f"Generated: {datetime.now().strftime('%m/%d/%Y %I:%M %p')}\n")
        f.write("=" * 60 + "\n\n")
        f.write(content)

    print(f"Exported to: {file_path}")


def export_whats_new_txt(report: dict, days: int, filename_prefix: str) -> None:
    """Export the new_assets_report dict to a formatted .txt file in ~/Downloads.

    report:          The AuditReport dict with keys 'users', 'groups', 'items'.
                     Each value is a list of ArcGISUser, ArcGISGroup, ArcGISItem.
    days:            The lookback window used — written into the report header.
    filename_prefix: Base name for the file, e.g. "whats_new" →
                     whats_new_20260609.txt
    """
    from pathlib import Path
    from datetime import datetime

    users = report.get("users", [])
    groups = report.get("groups", [])
    items = report.get("items", [])

    downloads_path = Path.home() / "Downloads"
    timestamp = datetime.now().strftime("%Y%m%d")
    file_path = downloads_path / f"{filename_prefix}_{timestamp}.txt"

    def sep(width=70):
        return "-" * width

    lines = []

    # ── File header ───────────────────────────────────────────────────────
    lines += [
        "ArcGIS Admin CLI — What's New Report",
        f"Generated:  {datetime.now().strftime('%m/%d/%Y %I:%M %p')}",
        f"Period:     Last {days} days",
        "=" * 70,
        "",
        f"  New Users:   {len(users)}",
        f"  New Groups:  {len(groups)}",
        f"  New Items:   {len(items)}",
        "",
        "=" * 70,
    ]

    # ── Users section ─────────────────────────────────────────────────────
    lines += ["", f"NEW USERS ({len(users)})", sep()]

    if users:
        # Column widths sized for typical ArcGIS field lengths.
        cw = {"username": 25, "fullName": 28, "role": 20, "license": 18, "created": 20}
        header = (
            f"{'Username':<{cw['username']}} "
            f"{'Full Name':<{cw['fullName']}} "
            f"{'Role':<{cw['role']}} "
            f"{'License':<{cw['license']}} "
            f"{'Created':<{cw['created']}}"
        )
        lines += [header, sep()]
        for u in users:
            lines.append(
                f"{(u.username or ''):<{cw['username']}} "
                f"{(u.fullName or ''):<{cw['fullName']}} "
                f"{(u.role or ''):<{cw['role']}} "
                f"{(u.userLicenseType or ''):<{cw['license']}} "
                f"{(u.created or '—'):<{cw['created']}}"
            )
    else:
        lines.append("  No new users in this period.")

    # ── Groups section ────────────────────────────────────────────────────
    lines += ["", "", f"NEW GROUPS ({len(groups)})", sep()]

    if groups:
        cw = {"title": 35, "owner": 25, "access": 12, "created": 20}
        header = (
            f"{'Title':<{cw['title']}} "
            f"{'Owner':<{cw['owner']}} "
            f"{'Access':<{cw['access']}} "
            f"{'Created':<{cw['created']}}"
        )
        lines += [header, sep()]
        for g in groups:
            lines.append(
                f"{(g.title or ''):<{cw['title']}} "
                f"{(g.owner or ''):<{cw['owner']}} "
                f"{(g.access or ''):<{cw['access']}} "
                f"{(g.created or '—'):<{cw['created']}}"
            )
    else:
        lines.append("  No new groups in this period.")

    # ── Items section ─────────────────────────────────────────────────────
    lines += ["", "", f"NEW ITEMS ({len(items)})", sep()]

    if items:
        cw = {"title": 35, "type": 22, "owner": 22, "access": 10, "created": 20}
        header = (
            f"{'Title':<{cw['title']}} "
            f"{'Type':<{cw['type']}} "
            f"{'Owner':<{cw['owner']}} "
            f"{'Access':<{cw['access']}} "
            f"{'Created':<{cw['created']}}"
        )
        lines += [header, sep()]
        for item in items:
            lines.append(
                f"{(item.title or ''):<{cw['title']}} "
                f"{(item.type or ''):<{cw['type']}} "
                f"{(item.owner or ''):<{cw['owner']}} "
                f"{(item.access or '—'):<{cw['access']}} "
                f"{(item.created or '—'):<{cw['created']}}"
            )
    else:
        lines.append("  No new items in this period.")

    lines += ["", "=" * 70, ""]

    with open(file_path, mode="w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"Exported to: {file_path}")


def export_whats_new_csv(report: "AuditReport") -> None:
    """Export each section of a new_assets_report to its own CSV in ~/Downloads.

    Produces up to three files (skips empty sections):
        new_users_YYYYMMDD.csv
        new_groups_YYYYMMDD.csv
        new_items_YYYYMMDD.csv

    All dataclass fields are included — not just the ones shown on screen.
    Sorting by 'created' descending is handled by the existing export_to_csv().
    """
    users = report.get("users", [])
    groups = report.get("groups", [])
    items = report.get("items", [])

    if users:
        export_to_csv(users, "new_users")
    if groups:
        export_to_csv(groups, "new_groups")
    if items:
        export_to_csv(items, "new_items")

    if not any([users, groups, items]):
        print("Nothing to export — all sections are empty.")
