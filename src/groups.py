from arcgis.gis import GIS, Group, User
import logging

log = logging.getLogger(__name__)


# ======== Search ========
# find_group (by name, owner, tag)
# group_details
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
