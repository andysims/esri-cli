import datetime as dt
from datetime import datetime, timedelta, timezone
import logging
from arcgis.gis import GIS, Item
from collections import Counter  # probably throw this into reporting
from typing import Optional, List

from .users import find_user
from .models import ArcGISUser, ArcGISItem, ArcGISGroup, AuditReport

log = logging.getLogger(__name__)
logging.getLogger("arcgis").setLevel(logging.ERROR)


def total_users(gis: GIS) -> int:
    user_counts = gis.users.counts("user_type", as_df=False)
    total_users: int = sum(item["count"] for item in user_counts)
    log.info("There are %d total users.", total_users)

    return total_users

    # def total_items(gis: GIS) -> int:
    """Returns the total number of items owned by the organization."""


#    total_count: int = gis.content.advanced_search(query="*", return_count=True)

#    print(total_count)
#    log.info("There are %d total items in the organization.", total_count)
#    return total_count


# ======== User/Access Audits ========
def inactive_users(gis: GIS, days: int = 90) -> list[ArcGISUser]:
    """Return users who have never logged in or haven't logged in within N days."""

    cutoff_date = dt.datetime.now() - dt.timedelta(days=days)
    cutoff_timestamp_ms = int(cutoff_date.timestamp() * 1000)

    max_users = total_users(gis)

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


def get_users(
    gis: GIS,
    exclude_license_types: Optional[List[str]] = None,
    exclude_providers: Optional[List[str]] = None,
    exclude_roles: Optional[List[str]] = None,
    outside_org: bool = False,
) -> List["ArcGISUser"]:
    """
    Returns a list of ArcGISUser objects.

    By default returns ALL users.
    Pass lists to exclude users matching any of the provided values.
    """
    try:
        max_users = total_users(gis)
    except NameError:
        max_users = 10000  # for safety

    all_users = gis.users.search(max_users=max_users, outside_org=outside_org)

    exclude_license_types = set(exclude_license_types or [])
    exclude_providers = set(exclude_providers or [])
    exclude_roles = set(exclude_roles or [])

    filtered = []
    for u in all_users:
        if (
            exclude_license_types
            and u.get("userLicenseTypeId") in exclude_license_types
        ):
            continue
        if exclude_providers and u.get("provider") in exclude_providers:
            continue
        if exclude_roles and u.get("role") in exclude_roles:
            continue

        filtered.append(ArcGISUser.from_arcgis(u))

    return filtered


def sharing_audit(gis: GIS, username: str | None = "") -> dict[str, int] | None:
    try:
        username = (username or "").strip().lower()

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

        items = gis.content.search(query=search_query, max_items=-1)
        if not items:
            log.warning("%s does not own any items or org is empty", context_name)
            return None

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
    org_id = getattr(gis.properties, "id", None)

    if org_id:
        base_query = f"access:public AND orgid:{org_id} AND NOT owner:esri_*"
    else:
        base_query = "access:public AND NOT owner:esri_*"

    if item_types and isinstance(item_types, list):
        type_clauses = [f'type:"{t}"' for t in item_types]
        type_query = " OR ".join(type_clauses)
        search_query = f"{base_query} AND ({type_query})"
    else:
        search_query = base_query

    log.info("Searching for organization public items with query: %s", search_query)

    public_content = gis.content.search(
        query=search_query, max_items=-1, outside_org=False
    )

    valid_items = []
    for item in public_content:
        try:
            transformed_item = ArcGISItem.from_arcgis(item)
            valid_items.append(transformed_item)
        except ValueError:
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


# ======== Limits/Availability ========
def users_by_role(gis: GIS) -> dict[str, int]:
    """Returns a count of users grouped by their role."""
    users = gis.users.search(max_users=total_users(gis), outside_org=False)
    return dict(Counter(u.get("role", "none") for u in users))


def users_by_license_type(gis: GIS) -> dict[str, int]:
    """Returns a count of users grouped by license type (userLicenseTypeId)."""

    users = gis.users.search(max_users=total_users(gis), outside_org=False)
    return dict(Counter(u.get("userLicenseTypeId", "none") for u in users))


def license_threshold(gis: GIS) -> dict:
    """Returns detailed license usage and availability analytics for the organization."""

    users = gis.users.search(max_users=total_users(gis), outside_org=False)
    active_counts = Counter(u.get("userLicenseTypeId", "none") for u in users)

    portal_licenses = gis.users.license_types

    report = {}
    total_assigned = 0
    total_limit = 0

    for license_meta in portal_licenses:
        license_id = license_meta.get("id")  # e.g., 'viewerUT'
        display_name = license_meta.get("name")  # e.g., 'Viewer'
        max_seats = license_meta.get("maxUsers", 0)  # Total seats allowed

        assigned_count = active_counts.get(license_id, 0)
        available_seats = max_seats - assigned_count

        # Build individual analytics record
        report[license_id] = {
            "name": display_name,
            "assigned": assigned_count,
            "total_purchased": max_seats,
            "available": available_seats,
            "available_pct": (
                str(f"{round((available_seats / max_seats) * 100, 0)}%")
                if max_seats != 0
                else "N/A"
            ),
        }

        # Increment global metrics
        total_assigned += assigned_count
        total_limit += max_seats

    # 3. Add global overview summary metrics
    report["summary"] = {
        "total_assigned": total_assigned,
        "total_purchased_limit": total_limit,
        "total_available_seats": total_limit - total_assigned,
    }

    return report


# ======== Security ========
def user_provider_breakdown(gis: GIS) -> dict[str, int]:
    """Returns counts of 'enterprise' vs 'local' (provider) users."""
    users = gis.users.search(max_users=total_users(gis), outside_org=False)
    return dict(Counter(u.get("provider", "unknown") for u in users))


def disabled_users(gis: GIS) -> list[ArcGISUser]:
    """Returns a list of all disabled using ArcGISUser dataclasses."""
    all_users = gis.users.search(max_users=total_users(gis), outside_org=False)
    return [ArcGISUser.from_arcgis(u) for u in all_users if u.get("disabled") is True]


# ======== Activity ========
def new_items(gis: GIS, days: int = 7) -> list[ArcGISItem]:
    """Returns items created within the last N days."""
    start_date = datetime.now(timezone.utc) - timedelta(days=days)
    # milliseconds
    start_ms = int(start_date.timestamp() * 1000)

    query = (
        f"created:[{start_ms} TO {int(datetime.now(timezone.utc).timestamp() * 1000)}]"
    )

    # avoid max_items=total_items() if you have 50k+ items
    # this will cause significant lag. Use a reasonable limit.
    items = gis.content.search(query=query, max_items=10000)
    valid_items = [item for item in items if isinstance(item, Item)]

    return [ArcGISItem.from_arcgis(item) for item in valid_items]


def new_users(gis: GIS, days: int = 7) -> list[ArcGISUser]:
    """Return users created within the last N days."""
    cutoff_date = dt.datetime.now() - dt.timedelta(days=days)
    cutoff_timestamp_ms = int(cutoff_date.timestamp() * 1000)

    all_users = gis.users.search(max_users=total_users(gis), outside_org=False)

    return [
        ArcGISUser.from_arcgis(u)
        for u in all_users
        if u.get("created", 0) >= cutoff_timestamp_ms
    ]


def new_groups(gis: GIS, days: int = 7) -> list[ArcGISGroup]:
    """Return groups created within the last N days."""
    cutoff_date = dt.datetime.now() - dt.timedelta(days=days)
    query = f"created: [{int(cutoff_date.timestamp() * 1000)} TO {int(dt.datetime.now().timestamp() * 1000)}]"
    groups = gis.groups.search(
        query=query, max_groups=total_users(gis), outside_org=False
    )

    return [ArcGISGroup.from_arcgis(g) for g in groups]


def new_assets_report(gis: GIS, days: int = 7) -> AuditReport:
    """Aggregates new items, users, and groups into a structured report."""
    return {
        "items": new_items(gis, days),
        "users": new_users(gis, days),
        "groups": new_groups(gis, days),
    }
