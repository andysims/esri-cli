import logging
from typing import Any

from arcgis.gis import GIS, Item

from .utils import esri_timestamp_to_str
from .models import ArcGISItem

log = logging.GetLogger(__name__)

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

        items: list[ArcGISItem] = [
            ArcGISItem.from_arcgis(i) for i in raw_items
        ]

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

        log.info("Found %d dependencies for item %s", len(deps.get("list", [])), item_id)
        return deps

    except Exception:
        log.exception("Failed to fetch dependencies for item %s", item_id)
        raise
