import logging
from typing import Any

from arcgis.gis import GIS, Item

from .utils import esri_timestamp_to_str
from .models import ArcGISItem
from .groups import _resolve_group
from .users import get_user

log = logging.getLogger(__name__)


# ======== Helper ========
def _resolve_item(gis: GIS, item: str | Item) -> Item:
    """Internal helper: resolve item ID (str) or Item object to a raw Item."""
    if isinstance(item, str):
        raw_item: Item = gis.content.get(item)
        if not raw_item:
            raise ValueError(f"Item not found: {item}")
        return raw_item
    return item


# ======== Search ========
def find_item(
    gis: GIS,
    item_id: str | None = None,
    title: str | None = None,
    owner: str | None = None,
) -> list[ArcGISItem]:
    """Search for items by any combination of item_id, title, or owner.

    All provided criteria are AND-ed together. Returns an empty list if no
    criteria are given or no results are found.
    """
    query_parts = []
    if item_id:
        query_parts.append(f"id:{item_id}")
    if title:
        query_parts.append(f'title:"{title}"')
    if owner:
        query_parts.append(f"owner:{owner}")

    if not query_parts:
        log.warning("No search criteria provided for find_item")
        return []

    query_string = " AND ".join(query_parts)

    try:
        raw_items = gis.content.search(query=query_string)

        items: list[ArcGISItem] = [ArcGISItem.from_arcgis(i) for i in raw_items]

        if not items:
            log.warning("Query returned no results: %s", query_string)
        else:
            log.info("Found %d item(s) for query: %s", len(items), query_string)

        return items

    except Exception:
        log.exception("Error during item search with query: %s", query_string)
        raise


def item_details(gis: GIS, item: str | Item) -> ArcGISItem:
    """Return detailed ArcGISItem for a given item ID or Item object."""
    if isinstance(item, str):
        raw_item: Item = gis.content.get(item)
        if not raw_item:
            raise ValueError(f"Item not found: {item}")
    else:
        raw_item = item

    return ArcGISItem.from_arcgis(raw_item)


def item_dependencies(
    gis: GIS,
    item_id: str,
) -> dict:
    """Return dependencies for an item (what it depends on).

    Uses item_id to ensure accuracy. Returns a dict with the raw dependency info.
    """
    raw_item: Item = gis.content.get(item_id)
    if not raw_item:
        raise ValueError(f"Item not found: {item_id}")

    log.info("Fetching dependencies for item '%s' (ID: %s)", raw_item.title, item_id)

    try:
        deps = raw_item.dependent_upon()

        log.info(
            "Found %d dependencies for item %s", len(deps.get("list", [])), item_id
        )
        return deps

    except Exception:
        log.exception("Failed to fetch dependencies for item %s", item_id)
        raise


# ======== Sharing and Access ========
def update_item_owner(
    gis: GIS,
    item: str | Item,
    new_owner: str,
) -> None:
    """Reassign ownership of an item to a different user."""
    raw_item = _resolve_item(gis, item)
    target_user = get_user(gis, new_owner)

    if raw_item.owner == target_user.username:
        log.info("Item '%s' is already owned by %s", raw_item.title, new_owner)
        return

    log.info(
        "Transferring ownership of '%s' from %s to %s",
        raw_item.title,
        raw_item.owner,
        new_owner,
    )

    try:
        success = raw_item.reassign_to(target_user)

        if success:
            log.info(
                "Successfully transferred ownership of '%s' to %s",
                raw_item.title,
                new_owner,
            )
        else:
            raise RuntimeError(f"Failed to reassign ownership of item {raw_item.id}")

    except Exception:
        log.exception("Failed to transfer ownership of item '%s'", raw_item.title)
        raise


def share_item(
    gis: GIS,
    item: str | Item,
    groups: list[str] | None = None,
    access: str | None = None,
) -> None:
    """Share an item with specific groups and/or change its access level.

    access can be: 'private', 'org', 'public'
    groups: list of group IDs or titles
    """
    raw_item = _resolve_item(gis, item)

    if access and access not in ("private", "org", "public"):
        raise ValueError("access must be one of: 'private', 'org', 'public'")

    group_ids = []
    if groups:
        for g in groups:
            resolved = _resolve_group(gis, g) if hasattr(g, "_resolve_group") else g
            group_ids.append(resolved.id if hasattr(resolved, "id") else resolved)

    log.info(
        "Sharing item '%s' — access=%s, groups=%s",
        raw_item.title,
        access,
        len(group_ids),
    )

    try:
        result = raw_item.share(groups=group_ids, access=access)

        if result and result.get("success"):
            log.info("Successfully shared item '%s'", raw_item.title)
        else:
            raise RuntimeError(f"Failed to share item (result: {result})")

    except Exception:
        log.exception("Failed to share item '%s'", raw_item.title)
        raise


def unshare_item(
    gis: GIS,
    item: str | Item,
    groups: list[str] | None = None,
    unshare_from_org: bool = False,
) -> None:
    """Unshare an item (remove sharing from groups and/or org/public)."""
    raw_item = _resolve_item(gis, item)

    log.info(
        "Unsharing item '%s' (groups=%s, unshare_from_org=%s)",
        raw_item.title,
        groups,
        unshare_from_org,
    )

    try:
        result = raw_item.unshare(groups=groups or [], everyone=unshare_from_org)

        if result and result.get("success"):
            log.info("Successfully unshared item '%s'", raw_item.title)
        else:
            raise RuntimeError(f"Failed to unshare item")

    except Exception:
        log.exception("Failed to unshare item '%s'", raw_item.title)
        raise
