from arcgis.gis import GIS, Group, User
import logging

log = logging.getLogger(__name__)

# ======== Helper Func ========
def _resolve_group(gis: GIS, group: str):
    """Internal helper: resolve group ID or title to raw Group object."""
    if not isinstance(group, str):
        raise TypeError("group must be a string (ID or title)")

    # Try ID first
    raw_group = gis.groups.get(group)
    if raw_group:
        return raw_group

    # Fallback to title search
    results = gis.groups.search(f"title:{group}")
    if len(results) == 0:
        raise ValueError(f"Group not found: {group}")
    if len(results) > 1:
        raise ValueError(f"Multiple groups found with title '{group}'. Use group ID instead.")

    return results[0]


# ======== Search ========
def find_group(
    gis: GIS,
    group_id: str | None = None,
    title: str | None = None,
    owner: str | None = None,
) -> list[ArcGISGroup]:
    """Search for groups by any combination of group_id, title, or owner.

    All provided criteria are AND-ed together. Returns an empty list if no
    criteria are given or no results are found.
    """
    query_parts = []
    if group_id:
        query_parts.append(f"id:{group_id}")
    if title:
        query_parts.append(f"title:{title}")
    if owner:
        query_parts.append(f"owner:{owner}")

    if not query_parts:
        log.warning("No search criteria provided for find_group")
        return []

    query_string = " AND ".join(query_parts)

    try:
        raw_groups: list = gis.groups.search(query=query_string)

        groups: list[ArcGISGroup] = [
            ArcGISGroup.from_arcgis(g) for g in raw_groups
        ]

        if not groups:
            log.warning("Query returned no results: %s", query_string)
        else:
            log.info("Found %d group(s) for query: %s", len(groups), query_string)

        return groups

    except Exception:
        log.exception("Error during group search with query: %s", query_string)
        raise


def group_details(
    gis: GIS, 
    group: str | ArcGISGroup | None = None
) -> ArcGISGroup:
    """Return an ArcGISGroup dataclass for the given group ID or title.
    
    Accepts either:
      - str: treated as group ID first, then falls back to title search
      - ArcGISGroup: just converts it (noop basically)
    """
    if isinstance(group, ArcGISGroup):
        return group

    if not isinstance(group, str):
        raise TypeError("group must be a str (ID or title) or ArcGISGroup")

    if not group:
        raise ValueError("Group ID or title cannot be empty")

    # Try exact ID lookup first (most common + efficient)
    raw_group = gis.groups.get(group)
    
    if not raw_group:
        # Fallback: search by title
        results = gis.groups.search(query=f"title:{group}")
        if len(results) == 0:
            raise ValueError(f"No group found with ID or title: {group}")
        elif len(results) > 1:
            raise ValueError(
                f"Multiple groups found with title '{group}'. "
                f"Use the group ID instead for unambiguous lookup."
            )
        raw_group = results[0]

    return ArcGISGroup.from_arcgis(raw_group)


# ======== Membership ========
def add_group_member(
    gis: GIS,
    group: str,
    username: str,
) -> None:
    """Add a user as a member to a group.
    
    group: Group ID or title (resolved via group_details)
    username: Username to add
    """
    raw_group = group_details(gis, group)  # This returns ArcGISGroup, but we need raw for methods
    # resolving to raw Group object
    if isinstance(group, str):
        raw_group_obj = gis.groups.get(group) or _get_group_by_title(gis, group)
    else:
        raw_group_obj = group

    if not raw_group_obj:
        raise ValueError(f"Group not found: {group}")

    user = get_user(gis, username)

    log.info("Adding user %s to group '%s'", username, raw_group_obj.title)

    try:
        result = raw_group_obj.add_users([username])
        if result and not result.get("notAdded"):
            log.info("Successfully added %s to group '%s'", username, raw_group_obj.title)
        else:
            raise RuntimeError(f"Failed to add {username} to group (API result: {result})")
    except Exception:
        log.exception("Failed to add user %s to group '%s'", username, raw_group_obj.title)
        raise


def remove_group_member(
    gis: GIS,
    group: str,
    username: str,
) -> None:
    """Remove a user from a group."""
    raw_group_obj = _resolve_group(gis, group)

    log.info("Removing user %s from group '%s'", username, raw_group_obj.title)

    try:
        result = raw_group_obj.remove_users([username])
        if result and not result.get("notRemoved"):
            log.info("Successfully removed %s from group '%s'", username, raw_group_obj.title)
        else:
            raise RuntimeError(f"Failed to remove {username} from group")
    except Exception:
        log.exception("Failed to remove user %s from group '%s'", username, raw_group_obj.title)
        raise


def update_member_role(
    gis: GIS,
    group: str,
    username: str,
    role: str,  # "member", "admin", or "owner"
) -> None:
    """Update a member's role in the group.
    
    role must be one of: 'member', 'admin', 'owner'
    """
    if role not in ("member", "admin", "owner"):
        raise ValueError("role must be 'member', 'admin', or 'owner'")

    raw_group_obj = _resolve_group(gis, group)
    user = get_user(gis, username)

    log.info("Updating role of %s in group '%s' to %s", username, raw_group_obj.title, role)

    try:
        success = raw_group_obj.update_member(username=username, role=role)
        if success:
            log.info("Successfully updated %s role to '%s' in group '%s'", 
                     username, role, raw_group_obj.title)
        else:
            raise RuntimeError(f"Failed to update role for {username}")
    except Exception:
        log.exception("Failed to update role for %s in group '%s'", username, raw_group_obj.title)
        raise


def transfer_group_ownership(
    gis: GIS,
    group_id: str,
    new_owner_username: str,
) -> None:
    """Reassign ownership of a single group to a new user.

    Raises if the group doesn't exist or the operation fails.
    """
    group = gis.groups.get(group_id)
    if not group:
        raise ValueError(f"Group with id {group_id} not found")

    log.info(
        "Transferring ownership of group '%s' to %s", group.title, new_owner_username
    )

    try:
        group.reassign_to(new_owner_username)
        log.info("Successfully transferred ownership of group '%s'", group.title)
    except Exception:
        log.exception("Failed to transfer ownership of group %s", group_id)
        raise


def transfer_user_groups(
    gis: GIS,
    from_user: User,
    to_user: User,
) -> None:
    # Transfer all group ownerships and memberships from one user to another
    for group_dict in from_user.groups:
        group = gis.groups.get(group_dict["id"])
        if not group:
            continue

        if group.owner == from_user.username:
            group.reassign_to(to_user.username)
        else:
            # Member only → remove old, add new
            group.remove_users(from_user.username)
            group.add_users(to_user.username)


# ==== Lifecycle ========
def create_group(
    gis: GIS,
    title: str,
    description: str | None = None,
    access: str = "org",
    tags: list[str] | None = None,
    isInvitationOnly: bool = False,
    isViewOnly: bool = False,
    protected: bool = False,
) -> ArcGISGroup:
    """Create a new group and return the ArcGISGroup dataclass."""
    if not title:
        raise ValueError("title is required")

    if access not in ("private", "org", "public"):
        raise ValueError("access must be one of: 'private', 'org', 'public'")

    if tags is None:
        tags = []

    log.info("Creating new group: '%s' (access=%s)", title, access)

    try:
        new_group = gis.groups.create(
            title=title,
            description=description,
            access=access,
            tags=",".join(tags) if tags else None,
            isInvitationOnly=isInvitationOnly,
            isViewOnly=isViewOnly,
            protected=protected,
        )

        if not new_group:
            raise RuntimeError("Group creation failed — API returned None")

        arcgis_group = ArcGISGroup.from_arcgis(new_group)

        log.info("Successfully created group '%s' (ID: %s)", 
                arcgis_group.title, arcgis_group.id)

        return arcgis_group

    except Exception:
        log.exception("Failed to create group '%s'", title)
        raise


def delete_group(
    gis: GIS,
    group: str,
    dry_run: bool = False,
) -> None:
    """Delete a group.
    
    group: Group ID or title (resolved automatically)
    Use dry_run=True to test without actually deleting.
    """
    raw_group = _resolve_group(gis, group)

    if dry_run:
        log.info("Dry run: Group '%s' (ID: %s) would be deleted.", 
                raw_group.title, raw_group.id)
        # safety check
        if raw_group.protected:
            raise ValueError(f"Group '{raw_group.title}' is protected and cannot be deleted.")
        return

    log.info("Deleting group '%s' (ID: %s)", raw_group.title, raw_group.id)

    try:
        success = raw_group.delete()

        if success:
            log.info("Successfully deleted group '%s'", raw_group.title)
        else:
            raise RuntimeError(f"Failed to delete group '{raw_group.title}' (API returned False)")

    except Exception:
        log.exception("Failed to delete group '%s' (ID: %s)", raw_group.title, raw_group.id)
        raise


def update_group(
    gis: GIS,
    group: str,
    title: str | None = None,
    description: str | None = None,
    access: str | None = None,
) -> None:
    """Update properties of a group (title, description, and/or access).
    
    group: Group ID or title (resolved via _resolve_group)
    At least one of title, description, or access must be provided.
    """
    if not any([title, description, access]):
        raise ValueError("At least one of title, description, or access must be provided")

    raw_group = _resolve_group(gis, group)

    log.info(
        "Updating group '%s' (ID: %s) — title=%s, access=%s",
        raw_group.title, raw_group.id, title, access
    )

    try:
        # Build update payload
        update_data = {}
        if title is not None:
            update_data["title"] = title
        if description is not None:
            update_data["description"] = description
        if access is not None:
            if access not in ("private", "org", "public"):
                raise ValueError("access must be one of: 'private', 'org', 'public'")
            update_data["access"] = access

        success = raw_group.update(**update_data)

        if success:
            log.info("Successfully updated group '%s'", raw_group.title)
        else:
            raise RuntimeError(f"Group update returned False for group {raw_group.id}")

    except Exception:
        log.exception("Failed to update group '%s' (ID: %s)", raw_group.title, raw_group.id)
        raise

# ======== Content ========
def group_content(
    gis: GIS,
    group: str,
) -> list[ArcGISGroupItem]:
    """Return all items (content) belonging to a group.
    
    Accepts either a group ID or group title (name).
    Returns an empty list if the group has no content.
    """

    raw_group = _resolve_group(gis, group)

    log.info("Fetching content for group '%s' (ID: %s)", raw_group.title, raw_group.id)

    try:
        # Get all items in the group
        raw_items = raw_group.content()

        items: list[ArcGISGroupItem] = [
            ArcGISGroupItem.from_arcgis_item(item) for item in raw_items
        ]

        if not items:
            log.warning("Group '%s' contains no items", raw_group.title)
        else:
            log.info("Found %d item(s) in group '%s'", len(items), raw_group.title)

        return items

    except Exception:
        log.exception("Error fetching content for group '%s'", raw_group.title)
        raise

def add_item(
    gis: GIS,
    group: str,
    item: str | Item,
) -> None:
    """Share an item with a group (add item to group).
    
    group: Group ID or title (resolved automatically)
    item: Item ID (str) or Item object
    """
    raw_group = _resolve_group(gis, group)

    # Resolve item
    if isinstance(item, str):
        raw_item: Item = gis.content.get(item)
        if not raw_item:
            raise ValueError(f"Item not found: {item}")
    else:
        raw_item = item

    log.info("Adding item '%s' to group '%s'", raw_item.title, raw_group.title)

    try:
        result = raw_item.share(groups=[raw_group.id])

        if result and result.get("success"):
            log.info("Successfully added item '%s' to group '%s'", 
                     raw_item.title, raw_group.title)
        else:
            raise RuntimeError(f"Failed to share item with group (result: {result})")

    except Exception:
        log.exception("Failed to add item '%s' to group '%s'", 
                     raw_item.title, raw_group.title)
        raise


def remove_item(
    gis: GIS,
    group: str,
    item: str | Item,
) -> None:
    """Remove an item from a group (unshare from the group)."""
    raw_group = _resolve_group(gis, group)

    # Resolve item
    if isinstance(item, str):
        raw_item: Item = gis.content.get(item)
        if not raw_item:
            raise ValueError(f"Item not found: {item}")
    else:
        raw_item = item

    log.info("Removing item '%s' from group '%s'", raw_item.title, raw_group.title)

    try:
        # Unshare from specific group
        result = raw_item.share(groups=[], clear_groups=False)

        if result and result.get("success"):
            log.info("Successfully removed item '%s' from group '%s'", 
                     raw_item.title, raw_group.title)
        else:
            raise RuntimeError(f"Failed to remove item from group")

    except Exception:
        log.exception("Failed to remove item '%s' from group '%s'", 
                     raw_item.title, raw_group.title)
        raise


"""
# Search
- find_group (by name, owner, id): DONE
- group_details: DONE

# Lifecycle
- create_group: DONE
- delete_group: DONE
- update_group: DONE

# Membership
- add_group_member: DONE
- remove_group_member: DONE
- update_member_role (owner, admin, member): DONE
- transfer_group_ownership: DONE (changes ownership of user's groups)
- transfer_user_groups: DONE (transfers groups from one user to another)

# Content
- group_content: DONE
- add_item_to_group: DONE
- remove_item_from_group: DONE
"""
