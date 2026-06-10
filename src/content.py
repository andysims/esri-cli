import logging
from typing import Any
from collections import Counter

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
        raw_items = gis.content.search(query=query_string, max_items=-1)

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


def content_ownership_report(
    gis: GIS,
    top_n: int = 25,
    exclude_users: list[str] | None = None,
    item_types: list[str] | None = None,
    outside_org: bool = False,
) -> list[dict]:
    """Return the top N users ranked by content item count, descending.

    Each entry in the returned list is a dict with:
        rank        — 1-based position in the sorted results
        username    — the owner string as it appears on items
        item_count  — number of items owned (after filters applied)

    top_n:         How many users to return. Pass -1 for all owners found.
    exclude_users: Usernames to exclude from the results. Case-insensitive.
                   Anything beginning with 'esri_' is always excluded
                   regardless of this list.
    item_types:    If provided, only count items whose type exactly matches
                   one of the strings in this list (case-insensitive).
                   e.g. ["Web Map", "Feature Service"]
                   If None, all item types are counted.
    outside_org:   Include items outside the org. Almost always False.
    """
    log.info(
        "Fetching org items for ownership report (top_n=%d, item_types=%s)",
        top_n,
        item_types,
    )

    # if item_types are specified, construct an OR
    if item_types:
        type_clauses = " OR ".join(f'type:"{t}"' for t in item_types)
        query = f"({type_clauses})"
    else:
        query = "*"

    try:
        all_items = gis.content.search(
            query=query,
            max_items=-1,
            outside_org=outside_org,
        )
    except Exception:
        log.exception("Failed to fetch items for ownership report")
        raise

    if not all_items:
        log.warning("No items returned — org may be empty or query was restricted.")
        return []

    # esri_ accounts are always excluded
    excluded = {u.lower() for u in (exclude_users or [])}

    def _should_exclude(owner: str) -> bool:
        o = (owner or "").lower()
        return o.startswith("esri_") or o in excluded

    counts: Counter = Counter(
        owner
        for item in all_items
        if not _should_exclude(
            owner := (getattr(item, "owner", None) or item.get("owner", "unknown"))
        )
    )

    log.info(
        "Report: %d unique owners after exclusions (%d total items scanned)",
        len(counts),
        len(all_items),
    )

    sorted_owners = counts.most_common(top_n if top_n > 0 else None)

    return [
        {"rank": i + 1, "username": username, "item_count": count}
        for i, (username, count) in enumerate(sorted_owners)
    ]


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
        "Moving item '%s' (ID: %s) to folder '%s' (owner context: %s)",
        raw_item.title,
        raw_item.id,
        destination,
        owner or "current user",
    )

    try:
        # Scenario A: Moving content owned by another user (Admin context)
        if owner and owner != gis.users.me.username:
            reassign_kwargs = {}
            if destination != "/":
                reassign_kwargs["target_folder"] = destination

            # reassign_to handles cross-user/admin structural moves
            success = raw_item.reassign_to(owner, **reassign_kwargs)
            if not success:
                raise RuntimeError(
                    f"Reassign/move returned False for item {raw_item.id} to owner {owner}"
                )
            log.info(
                "Successfully reassigned/moved '%s' to folder '%s' under owner %s",
                raw_item.title,
                destination,
                owner,
            )

        # Scenario B: Moving content within the authenticated user's own account
        else:
            move_result = raw_item.move(folder=destination)
            if not move_result or not move_result.get("success"):
                raise RuntimeError(
                    f"Move returned unexpected result for item {raw_item.id}: {move_result}"
                )
            log.info(
                "Successfully moved '%s' to folder '%s'", raw_item.title, destination
            )

    except Exception:
        log.exception("Failed to move item '%s'", raw_item.title)
        raise


def copy_item(
    gis: GIS,
    item: str | Item,
    title: str | None = None,
    folder: str | None = None,
    owner: str | None = None,
) -> ArcGISItem:
    """Copy an item, optionally specifying a new title, folder, or owner.

    title:  Title for the copy. Defaults to "Copy of <original title>".
    folder: Destination folder name for the copy. Defaults to the root folder.
    owner:  Username of the target folder owner. Required if moving into a folder
            owned by a different user.

    Returns the ArcGISItem dataclass for the newly created copy.
    """
    raw_item = _resolve_item(gis, item)

    copy_title = title or f"Copy of {raw_item.title}"

    log.info(
        "Copying item '%s' (ID: %s) → title: '%s', folder: '%s', owner: '%s'",
        raw_item.title,
        raw_item.id,
        copy_title,
        folder or "root",
        owner or "current user",
    )

    try:
        # Step 1: Copy the item into the active user's root context
        new_item: Item | None = raw_item.copy(title=copy_title)

        if not new_item:
            raise RuntimeError(f"Copy returned None for item {raw_item.id}")

        destination = (folder or "").strip() or "/"

        # Step 2: Handle Relocation / Ownership Reassignment
        if owner and owner != gis.users.me.username:
            log.info(
                "Reassigning ownership of item %s to %s (folder: '%s')",
                new_item.id,
                owner,
                destination,
            )

            # Form signature cleanly: reassign_to(target_username, target_folder=None)
            reassign_kwargs = {}
            if destination != "/":
                reassign_kwargs["target_folder"] = destination

            success = new_item.reassign_to(owner, **reassign_kwargs)
            if not success:
                raise RuntimeError(
                    f"Failed to reassign copied item {new_item.id} to user '{owner}'"
                )

        elif destination != "/":
            log.info("Moving copied item %s to folder '%s'", new_item.id, destination)
            # Safe local structural shift
            move_result = new_item.move(folder=destination)
            if not move_result or not move_result.get("success"):
                raise RuntimeError(
                    f"Failed to move copied item {new_item.id} to folder '{destination}': {move_result}"
                )

        log.info(
            "Successfully copied '%s' → new item ID: %s", raw_item.title, new_item.id
        )
        return ArcGISItem.from_arcgis(new_item)

    except Exception:
        log.exception("Failed to copy item '%s'", raw_item.title)
        raise


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
        # returns an arcgis.content.Folder
        folder_obj = gis.content.folders.create(
            folder=folder_name,
            owner=target_owner,
        )

        if not folder_obj:
            raise RuntimeError(
                f"create_folder returned None for '{folder_name}' (owner: {target_owner})."
            )

        # Access props directly; avoid AttributeErrors
        props = folder_obj._properties
        folder_id = props.get("id")

        log.info(
            "Successfully created folder '%s' (ID: %s) for %s",
            folder_name,
            folder_id,
            target_owner,
        )

        return dict(props)

    except Exception as e:
        # handles existing folder cases without breaking
        if "not available" in str(e) or "already exists" in str(e).lower():
            log.warning(
                "Folder '%s' already exists for user %s. Retrieving existing folder.",
                folder_name,
                target_owner,
            )
            user = gis.users.get(target_owner)
            for f in user.folders:
                if (
                    f._name or f._properties.get("name", "")
                ).lower() == folder_name.lower():
                    return dict(f._properties)

        log.exception("Failed to create folder '%s' for %s", folder_name, target_owner)
        raise


def delete_item(
    gis: GIS,
    item: str | Item,
    dry_run: bool = False,
) -> None:
    """Permanently delete an item by its instance or unique Item ID string.

    This cannot be undone. Use dry_run=True to verify the item exists and
    is resolvable before committing.

    item:    The Item object or the 32-character alphanumeric item ID string.
    dry_run: If True, logs intended action without executing the deletion.
    """
    raw_item = _resolve_item(gis, item)

    if dry_run:
        log.info(
            "Dry run: item '%s' (ID: %s, owner: %s) would be deleted.",
            raw_item.title,
            raw_item.id,
            raw_item.owner,
        )
        return

    log.info(
        "Deleting item '%s' (ID: %s, owner: %s)",
        raw_item.title,
        raw_item.id,
        raw_item.owner,
    )

    try:
        success = raw_item.delete()

        if success:
            log.info("Successfully deleted item '%s'", raw_item.title)
        else:
            raise RuntimeError(f"Delete returned False for item {raw_item.id}")

    except Exception:
        log.exception("Failed to delete item '%s'", raw_item.title)
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
