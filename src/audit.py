import datetime as dt
import logging
from dataclasses import dataclass
from arcgis.gis import GIS, User
from collections import Counter  # probably throw this into reporting

from auth import gis_conn, load_config
from utils import esri_timestamp_to_str
from users import find_user, get_user
from models import ArcGISUser

log = logging.getLogger(__name__)
logging.getLogger("arcgis").setLevel(logging.ERROR)


# ==== User/Access Audits ====
def total_users(gis) -> int:
    user_counts = gis.users.counts("user_type", as_df=False)
    total_users: int = sum(item["count"] for item in user_counts)
    log.info("There are %d total users.", total_users)

    return total_users


def inactive_users(gis: GIS, days: int = 90) -> list[ArcGISUser]:
    """Return users who have never logged in or haven't logged in within N days."""
    cutoff_date = dt.datetime.now() - dt.timedelta(days=days)
    cutoff_timestamp_ms = int(cutoff_date.timestamp() * 1000)

    max_users = total_users(gis)
    all_users = gis.users.search(max_users=max_users)

    return [
        ArcGISUser.from_arcgis(u)
        for u in all_users
        if u.get("lastLogin", -1) == -1 or u.get("lastLogin", 0) < cutoff_timestamp_ms
    ]


def user_sharing_audit(gis: GIS, username: str) -> dict[str, int] | None:
    try:
        username = username.strip().lower()
        user = find_user(gis=gis, username=username)

        if not user:
            log.warning("User not found: %s", username)
            return None

        user_items = gis.content.search(query=f"owner:{username}", max_items=-1)

        if not user_items:
            log.warning("%s does not own any items", username)
            return None

        audit_summary = {
            "username": username,
            "total_items": len(user_items),
            "public_count": 0,
            "org_count": 0,
            "private_count": 0,
        }

        for item in user_items:
            if item.access == "public":
                audit_summary["public_count"] += 1
            elif item.access == "org":
                audit_summary["org_count"] += 1
            else:
                audit_summary["private_count"] += 1

        return audit_summary
    except Exception:
        log.exception("Issue with fetching content")
        return None


"""
# ==== Functions to create ====
# User/Access Audits
- admin_count_audit
- inactive_users
- users_sharing_audit
- user_sharing_audit: IP

# Content Exposure
- public_item_audit
- broken_links_audit

# Group Audits
- group_security_audit
- empty_groups_audit

# Limit Auditing
- license_threshold_audit
- role_threshold_audit



==================
# Activity
- get_user_activity (last login, creation date, login frequency)
- get_inactive_users (no login within N days)
- get_login_report

# Inventory
- get_org_user_summary (counts by role, type, provider)
- get_unowned_content (items whose owner no longer exists)
- get_shared_publicly (all publicly shared items)
- get_items_not_accessed (stale content by modified/viewed date)

# Security
- get_users_without_mfa
- get_enterprise_vs_local_breakdown
- get_disabled_users
- get_users_by_role
"""
