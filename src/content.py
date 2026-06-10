import logging
from typing import Any

from arcgis.gis import GIS, Item

from .utils import esri_timestamp_to_str
from .models import ArcGISItem
from .groups import _resolve_group
from .common import get_user

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


# ======== Lifecycle ========
def update_metadata(
    gis: GIS,
    item: str | Item,
    title: str | None = None,
    description: str | None = None,
    tags: list[str] | None = None,
    snippet: str | None = None,
) -> None:
    """Update one or more metadata fields on an item.

    Pass only the fields to change
    At least one field must be provided.

    title:       Display name of the item.
    description: Long-form description (HTML is accepted by the API).
    tags:        Full replacement tag list. This overwrites existing tags,
                 it doesn't append — pass the complete desired list.
    snippet:     Short summary (max ~250 chars). Shown in search results.
    """
    if not any([title, description, tags is not None, snippet]):
        raise ValueError("Provide at least one of: title, description, tags, snippet.")

    raw_item = _resolve_item(gis, item)

    update_kwargs: dict[str, Any] = {}
    if title is not None:
        update_kwargs["title"] = title
    if description is not None:
        update_kwargs["description"] = description
    if tags is not None:

        update_kwargs["tags"] = ",".join(tags)
    if snippet is not None:
        update_kwargs["snippet"] = snippet

    log.info(
        "Updating metadata for '%s' (ID: %s) — fields: %s",
        raw_item.title,
        raw_item.id,
        list(update_kwargs.keys()),
    )

    try:
        success = raw_item.update(item_properties=update_kwargs)

        if success:
            log.info("Successfully updated metadata for '%s'", raw_item.title)
        else:
            raise RuntimeError(f"Metadata update returned False for item {raw_item.id}")

    except Exception:
        log.exception("Failed to update metadata for item '%s'", raw_item.title)
        raise


def update_thumbnail(
    gis: GIS,
    item: str | Item,
    thumbnail_path: str,
) -> None:
    """Set or replace the thumbnail for an item.

    thumbnail_path: Local filesystem path to the image file.
                    JPEG and PNG are the most reliable formats.
                    Recommended size: 600×400px. The API will reject
                    files over 1MB.
    """
    from pathlib import Path

    raw_item = _resolve_item(gis, item)

    thumb_file = Path(thumbnail_path)
    if not thumb_file.is_file():
        raise FileNotFoundError(f"Thumbnail file not found: {thumbnail_path}")

    log.info(
        "Updating thumbnail for '%s' (ID: %s) — file: %s",
        raw_item.title,
        raw_item.id,
        thumbnail_path,
    )

    try:
        success = raw_item.update(thumbnail=str(thumb_file))

        if success:
            log.info("Successfully updated thumbnail for '%s'", raw_item.title)
        else:
            raise RuntimeError(
                f"Thumbnail update returned False for item {raw_item.id}"
            )

    except Exception:
        log.exception("Failed to update thumbnail for item '%s'", raw_item.title)
        raise


def move_item(
    gis: GIS,
    item: str | Item,
    to_folder: str,
    owner: str | None = None,
) -> None:
    """Move an item to a different folder.

    to_folder: The destination folder name. Use "/" or "" for the root folder.
    owner:     Username of the item owner. Required if the item is not owned
               by the currently authenticated user (i.e. you're an admin
               moving someone else's content).

    The source folder doesn't need to be specified — the API looks up the
    item's current location automatically.
    """
    raw_item = _resolve_item(gis, item)

    # Normalize root folder — the API accepts "/" for root.
    destination = to_folder.strip() or "/"

    log.info(
        "Moving item '%s' (ID: %s) to folder '%s'",
        raw_item.title,
        raw_item.id,
        destination,
    )

    try:
        move_kwargs: dict[str, Any] = {"folder": destination}
        if owner:
            move_kwargs["owner"] = owner

        result = raw_item.move(**move_kwargs)

        if result and result.get("success"):
            log.info(
                "Successfully moved '%s' to folder '%s'", raw_item.title, destination
            )
        else:
            raise RuntimeError(
                f"Move returned unexpected result for item {raw_item.id}: {result}"
            )

    except Exception:
        log.exception("Failed to move item '%s'", raw_item.title)
        raise


# copy item
# delete item
def create_folder(
    gis: GIS,
    folder_name: str,
    owner: str | None = None,
) -> dict:
    """Create a new content folder.

    folder_name: Name of the folder to create.
    owner:       Username to create the folder under. Defaults to the
                 currently authenticated user.

    Returns the raw folder dict from the API (contains 'id', 'title',
    'username', 'created').
    """
    folder_name = folder_name.strip()
    if not folder_name:
        raise ValueError("folder_name cannot be empty")

    target_owner = owner or gis.users.me.username

    log.info("Creating folder '%s' for user %s", folder_name, target_owner)

    try:
        result: dict | None = gis.content.create_folder(
            folder=folder_name,
            owner=target_owner,
        )

        if not result:
            raise RuntimeError(
                f"create_folder returned None for '{folder_name}' (owner: {target_owner}). "
                "Folder may already exist."
            )

        log.info(
            "Successfully created folder '%s' (ID: %s) for %s",
            folder_name,
            result.get("id"),
            target_owner,
        )
        return result

    except Exception:
        log.exception("Failed to create folder '%s' for %s", folder_name, target_owner)
        raise


def delete_folder(
    gis: GIS,
    folder_name: str,
    owner: str | None = None,
    dry_run: bool = False,
) -> None:
    """Delete a folder and all its contents.

    This is destructive — all items inside the folder are permanently deleted
    along with the folder itself. Use dry_run=True to see what would be removed
    before committing.

    folder_name: Name (not ID) of the folder to delete.
    owner:       Username whose folder this is. Defaults to the currently
                 authenticated user.
    """
    folder_name = folder_name.strip()
    if not folder_name:
        raise ValueError("folder_name cannot be empty")

    target_owner = owner or gis.users.me.username

    user = get_user(gis, target_owner)
    matching = [
        f
        for f in user.folders
        if (f._name or f._properties.get("name", "")).lower() == folder_name.lower()
        and getattr(f, "_fid", None) != "Root Folder"
    ]

    if not matching:
        raise ValueError(f"Folder '{folder_name}' not found for user {target_owner}.")

    folder = matching[0]
    folder_id = folder._fid

    if dry_run:
        items_in_folder = list(user.items(folder=folder_name))
        log.info(
            "Dry run: folder '%s' (ID: %s) contains %d item(s) — would be deleted.",
            folder_name,
            folder_id,
            len(items_in_folder),
        )
        return

    log.info(
        "Deleting folder '%s' (ID: %s) for user %s",
        folder_name,
        folder_id,
        target_owner,
    )

    try:
        success = folder.delete()

        if success:
            log.info("Successfully deleted folder '%s'", folder_name)
        else:
            raise RuntimeError(
                f"Folder.delete() returned False for '{folder_name}' (owner: {target_owner})"
            )

    except Exception:
        log.exception(
            "Failed to delete folder '%s' for user %s", folder_name, target_owner
        )
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
