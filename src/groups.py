from arcgis.gis import GIS, Group, User
import logging

log = logging.getLogger(__name__)


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

# group_members

# ======== Membership ========
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


"""
# Search
- find_group (by name, owner, tag)
- group_details
- group_members

# Lifecycle
- create_group
- delete_group
- update_group (title, description, access)

# Membership
- add_group_member
- remove_group_member
- update_member_role (owner, admin, member)
- transfer_group_ownership: DONE > this changes ownership of user's groups
- transfer_user_groups: DONE > this transfers groups from one user to another

# Content
- group_content
- add_item_to_group
- remove_item_from_group
"""
