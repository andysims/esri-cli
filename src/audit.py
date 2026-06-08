import datetime as dt
import logging
from dataclasses import dataclass
from arcgis.gis import GIS, User
from collections import Counter  # probably throw this into reporting

from .auth import gis_conn, load_config
from .utils import esri_timestamp_to_str
from .users import find_user
from .common import get_user
from .models import ArcGISUser, ArcGISItem

log = logging.getLogger(__name__)
logging.getLogger("arcgis").setLevel(logging.ERROR)


# ======== User/Access Audits ========
def total_users(gis) -> int:
    user_counts = gis.users.counts("user_type", as_df=False)
    total_users: int = sum(item["count"] for item in user_counts)
    log.info("There are %d total users.", total_users)

    return total_users


def inactive_users(gis: GIS, days: int = 90) -> list[ArcGISUser]:
    """Return users who have never logged in or haven't logged in within N days."""

    # 1. Establish millisecond cutoff timestamp matching Esri's database format
    cutoff_date = dt.datetime.now() - dt.timedelta(days=days)
    cutoff_timestamp_ms = int(cutoff_date.timestamp() * 1000)

    # 2. Grab your exact total user count dynamically
    max_users = total_users(gis)

    # 3. Pull the precise list using standard search
    all_users = gis.users.search(max_users=max_users)

    inactive_list = []

    for u in all_users:
        last_login = getattr(u, "lastLogin", -1)

        # User has never logged in
        if last_login is None or last_login == -1:
            inactive_list.append(ArcGISUser.from_arcgis(u))

        # User logged in, but the stamp is older than cutoff
        elif last_login < cutoff_timestamp_ms:
            inactive_list.append(ArcGISUser.from_arcgis(u))

    return inactive_list


def sharing_audit(gis: GIS, username: str | None = "") -> dict[str, int] | None:
    try:
        # 1. Standardize the input
        username = (username or "").strip().lower()

        # 2. Determine search query and log context
        if username:
            user = find_user(gis=gis, username=username)
            if not user:
                log.warning("User not found: %s", username)
                return None
            search_query = f"owner:{username}"
            context_name = username
        else:
            search_query = "*"  # Searches all items in the org
            context_name = "Entire Org"

        # 3. Fetch items
        items = gis.content.search(query=search_query, max_items=-1)
        if not items:
            log.warning("%s does not own any items or org is empty", context_name)
            return None

        # 4. Compile audit
        audit_summary = {
            "scope": context_name,
            "total_items": len(items),
            "public_count": 0,
            "org_count": 0,
            "private_count": 0,
        }

        for item in items:
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


# ======== Content Exposure ========
def public_items(gis: GIS, item_types: list[str] | None = None) -> list[ArcGISItem]:
    """Return all public items belonging strictly to this organization,
    excluding internal Esri system accounts and ghost index stubs.
    """
    # 1. Fetch your specific organization's internal ID
    org_id = getattr(gis.properties, "id", None)

    # 2. Build the base query locked to your org and excluding esri_ owners
    if org_id:
        base_query = f"access:public AND orgid:{org_id} AND NOT owner:esri_*"
    else:
        # Fallback for ArcGIS Enterprise / Local Portal configurations
        base_query = "access:public AND NOT owner:esri_*"

    # 3. Append optional specific item type filters
    if item_types and isinstance(item_types, list):
        type_clauses = [f'type:"{t}"' for t in item_types]
        type_query = " OR ".join(type_clauses)
        search_query = f"{base_query} AND ({type_query})"
    else:
        search_query = base_query

    log.info("Searching for organization public items with query: %s", search_query)

    # 4. Execute the search strictly within the organization's firewall
    public_content = gis.content.search(
        query=search_query, max_items=-1, outside_org=False
    )

    # 5. Process entries one by one to safely drop stubs missing an item ID
    valid_items = []
    for item in public_content:
        try:
            # Try to build the ArcGISItem model
            transformed_item = ArcGISItem.from_arcgis(item)
            valid_items.append(transformed_item)
        except ValueError:
            # Catch the ValueError raised by your model when an ID is missing or empty
            log.debug("Skipped an orphaned index entry because it lacks an item ID.")
            continue

    return valid_items


def broken_dependencies(gis: GIS) -> list[ArcGISItem]:
    """Scan the organization for items with broken layer dependencies,
    deleted data sources, or invalid service URLs, strictly within your org.
    """
    # Fetch org ID
    org_id = getattr(gis.properties, "id", None)

    if org_id:
        search_query = f"orgid:{org_id} AND NOT owner:esri_*"
    else:
        search_query = "NOT owner:esri_*"

    log.info("Scanning organization content with query: %s", search_query)

    all_items = gis.content.search(query=search_query, max_items=-1, outside_org=False)

    broken_list = []

    for item in all_items:
        is_broken = False

        if not getattr(item, "id", None):
            continue

        if getattr(item, "homepage", None) == "broken":
            is_broken = True

        elif item.type == "Web Map":
            try:
                map_data = item.get_data()
                if map_data and "operationalLayers" in map_data:
                    for layer in map_data.get("operationalLayers", []):
                        if "url" in layer and not layer["url"]:
                            is_broken = True
                            break
            except Exception:
                log.debug("Could not read JSON data payload for Web Map: %s", item.id)
                is_broken = True

        if is_broken:
            try:
                transformed_item = ArcGISItem.from_arcgis(item)
                broken_list.append(transformed_item)
            except ValueError:
                continue

    log.info("Found %d items with broken dependencies.", len(broken_list))
    return broken_list


"""
# ==== Functions to create ====
# User/Access Audits
- admin_count_audit
- inactive_users: DONE
- sharing_audit: DONE
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
