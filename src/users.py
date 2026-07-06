import logging
from arcgis.gis import GIS, User
from typing import List, Union

from .utils import esri_timestamp_to_str
from .groups import transfer_user_groups
from .models import ArcGISUser, FolderInfo, ArcGISGroupSummary, ArcGISGroup
from .common import get_user

log = logging.getLogger(__name__)
logging.getLogger("arcgis").setLevel(logging.ERROR)  # will move into main.py


# ======== SEARCH ========
def user_details(gis: GIS, user: str | User) -> ArcGISUser:
    """Return an ArcGISUser dataclass for the given username or User object."""
    if isinstance(user, str):
        raw_user = gis.users.get(user)
    else:
        raw_user = user

    return ArcGISUser.from_arcgis(raw_user)


def user_groups(gis: GIS, user: Union[str, User]) -> List[ArcGISGroupSummary]:
    """Fetches all groups a user belongs to, mapped to ArcGISGroupSummary and sorted by title."""
    if isinstance(user, str):
        user_obj = gis.users.get(user)
        if not user_obj:
            raise ValueError(f"User '{user}' not found in the target GIS portal.")
    else:
        user_obj = user

    raw_groups = user_obj.groups
    mapped_groups = []

    for grp in raw_groups:
        try:
            mapped_groups.append(ArcGISGroupSummary.from_arcgis(grp, gis=gis))
        except Exception:
            continue

    mapped_groups.sort(key=lambda g: g.title.lower() if g.title else "")
    return mapped_groups


"""
# move this to CLI; has interactivity
def select_user(user_list: list[User]) -> User:
    print("Multiple users found:")
    for i, user in enumerate(user_list, start=1):
        print(f"{i} - {user.username} | {user.fullName} | {user.email}")

    while True:
        try:
            selection = int(input("\nEnter # of user you want additional info: "))
            if 1 <= selection <= len(user_list):
                selected_user = user_list[selection - 1]
                return selected_user
            else:
                print("Invalid selection. Try again.")
        except ValueError:
            print("Please enter a valid integer")
"""


def find_user(
    gis: GIS,
    username: str | None = None,
    email: str | None = None,
    lastname: str | None = None,
) -> list[ArcGISUser]:
    """Search for users by any combination of username, email, or last name.

    All provided criteria are AND-ed together. Returns an empty list if no
    criteria are given or no results are found.
    """
    query_parts = []
    if username:
        query_parts.append(f"username:{username}")
    if email:
        query_parts.append(f"email:{email}")
    if lastname:
        query_parts.append(f"lastname:{lastname}")

    if not query_parts:
        log.warning("No search criteria provided for find_user")
        return []

    query_string = " AND ".join(query_parts)

    try:
        raw_users: list[User] = gis.users.search(query=query_string)

        users: list[ArcGISUser] = [ArcGISUser.from_arcgis(u) for u in raw_users]

        if not users:
            log.warning("Query returned no results: %s", query_string)
        else:
            log.info("Found %d user(s) for query: %s", len(users), query_string)

        return users

    except Exception:
        log.exception("Error during user search with query: %s", query_string)
        raise


def user_folders(gis: GIS, username: str) -> list[FolderInfo]:
    """Return all non-root folders owned by the user.

    Returns an empty list if the user does not exist or has no folders.
    """
    username = username.strip()

    user = gis.users.get(username)
    if not user:
        log.warning("Username not found: %s; returning empty list", username)
        return []

    try:
        folders: list[FolderInfo] = [
            FolderInfo(
                id=f._fid,
                name=f._name or f._properties.get("name"),
                created=esri_timestamp_to_str(f._properties.get("created")),
            )
            for f in user.folders
            if f._fid != "Root Folder"
        ]

        if not folders:
            log.warning("No folders found for %s (outside root)", username)
        else:
            log.info("Returning %d folders for %s", len(folders), username)

        return folders

    except Exception:
        log.exception("Error fetching folders for %s", username)
        raise


# ======== Lifecycle ========
def create_user(
    gis: GIS,
    username: str,
    first_name: str,
    last_name: str,
    email: str,
    idp_username: str | None = None,
    password: str | None = None,
    user_type: str = "viewerUT",
    role: str = "org_viewer",
) -> User | None:
    """Create a local or enterprise user.

    For enterprise (IdP-backed) users, pass idp_username and omit password.
    For local users, pass password and omit idp_username.

    Common user_type values: 'creatorUT', 'viewerUT', 'editorUT', 'fieldWorkerUT'
    Common role values: 'org_admin', 'org_publisher', 'org_user', 'org_editor', 'org_viewer'
    """
    enterprise = idp_username is not None

    if not enterprise and not password:
        raise ValueError("password is required for local users")

    try:
        if gis.users.get(username) is not None:
            log.warning("User %s already exists — skipping creation", username)
            return None

        user: User | None = gis.users.create(
            username=username,
            password=None if enterprise else password,
            firstname=first_name,
            lastname=last_name,
            email=email,
            role=role,
            user_type=user_type,
            provider="enterprise" if enterprise else "arcgis",
            idp_username=idp_username,
        )

        if user is None:
            log.error("Failed to create user %s — API returned None", username)
            return None

        provider_label = "enterprise" if enterprise else "local"
        log.info(
            "Created %s user %s (%s %s, %s) with role '%s' and type '%s'",
            provider_label,
            username,
            first_name,
            last_name,
            email,
            role,
            user_type,
        )
        return user

    except Exception:
        log.exception("Unexpected error creating user %s", username)
        return None


def delete_user(
    gis: GIS,
    username: str,
    reassign_to: str | None = None,
    dry_run: bool = False,
) -> None:
    """Delete a user.

    If the user owns content or groups and no `reassign_to` is provided,
    the operation will fail with a clear message.

    Use dry_run=True to safely check whether deletion would succeed.
    """
    user: User = get_user(gis, username)

    if user.username == gis.users.me.username:
        raise ValueError("Cannot delete the currently logged-in user")

    log.info(
        "Preparing to delete user: %s (dry_run=%s, reassign_to=%s)",
        username,
        dry_run,
        reassign_to,
    )

    # --- Dry-run mode ---
    if dry_run:
        # Check for owned content (user.items() is a generator)
        has_content = False
        for _ in user.items():
            has_content = True
            break

        has_groups = len(user.groups) > 0

        if has_content or has_groups:
            raise ValueError(
                f"User '{username}' owns content or groups. "
                f"Provide reassign_to='targetuser' to transfer ownership first."
            )

        log.info("Dry run successful — user %s can be safely deleted.", username)
        return

    # --- Actual deletion ---
    try:
        delete_kwargs = {}
        if reassign_to is not None:
            delete_kwargs["reassign_to"] = reassign_to

        success = user.delete(**delete_kwargs)

        if success:
            log.info("Successfully deleted user: %s", username)
        else:
            raise RuntimeError(f"Failed to delete user {username}")

    except Exception as e:
        error_str = str(e).lower()
        if any(
            phrase in error_str for phrase in ["owns items", "owns groups", "reassign"]
        ):
            raise ValueError(
                f"User '{username}' owns content or groups. "
                f"Provide reassign_to='target_username' to transfer ownership first."
            ) from e

        log.exception("Failed to delete user %s", username)
        raise


def update_user_role(gis: GIS, username: str, new_role: str) -> bool:
    """Update a user's role.

    Accepts built-in role names ('org_admin', 'org_publisher', 'org_user',
    'org_editor', 'iAAViewer') or a custom role ID/name string.
    """
    try:
        user: User | None = gis.users.get(username)
        if user is None:
            log.warning("Failed to update role: User %s was not found", username)
            return False

        current_role = getattr(user, "role", None)
        if current_role == new_role:
            log.info("User %s already has role '%s'", username, new_role)
            return True

        user.update_role(new_role)
        log.info(
            "Updated role for %s from '%s' to '%s'", username, current_role, new_role
        )
        return True

    except Exception:
        log.exception("Unexpected error updating role for %s", username)
        return False


def update_user_type(gis: GIS, username: str, new_user_type: str) -> bool:
    """Update a user's license type (userLicenseTypeId).

    Common values: 'creatorUT', 'editorUT', 'viewerUT', 'fieldWorkerUT',
    'GISProfessionalAdvUT', 'GISProfessionalStdUT', 'GISProfessionalBasicUT'.
    """
    try:
        user: User | None = gis.users.get(username)
        if user is None:
            log.warning("Failed to update user type: User %s was not found", username)
            return False

        current_type = getattr(user, "userLicenseTypeId", None)
        if current_type == new_user_type:
            log.info("User %s already has user type '%s'", username, new_user_type)
            return True

        success = user.update_license_type(user_type=new_user_type)

        if success:
            log.info(
                "Updated user type for %s from '%s' to '%s'",
                username,
                current_type,
                new_user_type,
            )
            return True
        else:
            log.error(
                "Failed to update user type for %s — API returned falsy", username
            )
            return False

    except Exception:
        log.exception("Unexpected error updating user type for %s", username)
        return False


def reset_password(gis: GIS, username: str, new_password: str) -> bool:
    """Reset the password for a local (non-enterprise) user."""
    try:
        user: User | None = gis.users.get(username)
        if user is None:
            log.warning("Failed to reset password: User %s was not found", username)
            return False

        if getattr(user, "provider", "arcgis") != "arcgis":
            log.warning(
                "User %s is an enterprise account — password reset not applicable",
                username,
            )
            return False

        success = user.update(new_password)

        if success:
            log.info("Successfully reset password for user %s", username)
            return True
        else:
            log.error("Failed to reset password for %s — API returned falsy", username)
            return False

    except Exception:
        log.exception("Unexpected error resetting password for %s", username)
        return False


# ======== Access/Security ========
def set_user_disabled(gis: GIS, username: str, disable: bool) -> bool:
    """Enable or disable a user account.

    Pass disable=True to disable, disable=False to re-enable. Returns False
    if the user is not found or is already in the requested state.
    """
    try:
        user = gis.users.get(username)
        if not user:
            log.warning("User %s was not found", username)
            return False

        current_state = user.disabled  # or user.get("disabled", False)

        if current_state == disable:
            action = "disabled" if disable else "enabled"
            log.info("User %s is already %s", username, action)
            return False

        if disable:
            success = user.disable()
        else:
            success = user.enable()

        if success:
            action = "disabled" if disable else "enabled"
            log.info("Successfully %s user: %s", action, username)
            return True
        else:
            log.error("Failed to %s user", "disable" if disable else "enable")
            return False

    except Exception:
        action = "disable" if disable else "enable"
        log.exception("Unexpected error while attempting to %s %s", action, username)
        return False


def update_user_idp(gis: GIS, username: str, new_idp_username: str) -> bool:
    """Update the IdP username for an enterprise-linked account.

    No-ops if the value is unchanged. Returns False for built-in (arcgis)
    accounts, which cannot have an IdP username set.
    """
    try:
        user: User | None = gis.users.get(username)
        if user is None:
            log.warning("Failed to update IdP: User %s was not found", username)
            return False

        if getattr(user, "idpUsername", None) == new_idp_username:
            log.info("User %s already has idpUsername '%s'", username, new_idp_username)
            return True

        if getattr(user, "provider", "arcgis") == "arcgis":
            log.warning(
                "User %s is a built-in account. Cannot set an IdP username.", username
            )
            return False

        is_enterprise = not getattr(gis.properties, "isPortal", False) is False
        if is_enterprise:
            admin_url = f"{gis.url}/portaladmin/security/users/updateEnterpriseUser"
        else:
            portal_id = gis.properties.id
            admin_url = (
                f"{gis.url}/sharing/rest/portals/{portal_id}/enterpriseUsers/update"
            )

        response: dict = gis._con.post(
            admin_url,
            {
                "username": username,
                "idpUsername": new_idp_username,
                "f": "json",
            },
        )

        if response and response.get("status") == "success":
            log.info("Updated idpUsername for %s to '%s'", username, new_idp_username)
            return True

        log.error(
            "Failed to update idpUsername for %s. Response: %s", username, response
        )
        return False

    except Exception:
        log.exception("Unexpected error updating IdP for %s", username)
        return False


# ======== Offboarding ========
def check_user_dependencies(gis: GIS, username: str) -> dict:
    """Check what a user owns before deletion or offboarding.

    Returns a summary of owned items, folders, and groups. Use this
    before delete_user or transfer_user_content to understand what
    needs to be reassigned first.
    """
    user: User = get_user(gis, username)

    items = list(user.items())
    folders = [f for f in user.folders if getattr(f, "_fid", None) != "Root Folder"]
    groups = user.groups

    owned_groups = [g for g in groups if g.owner == username]
    member_groups = [g for g in groups if g.owner != username]

    summary = {
        "username": username,
        "items": len(items),
        "folders": len(folders),
        "owned_groups": len(owned_groups),
        "member_groups": len(member_groups),
        "safe_to_delete": len(items) == 0 and len(owned_groups) == 0,
    }

    log.info(
        "Dependencies for %s — items: %d, folders: %d, owned_groups: %d, member_groups: %d",
        username,
        summary["items"],
        summary["folders"],
        summary["owned_groups"],
        summary["member_groups"],
    )

    return summary


def transfer_user_content(
    gis: GIS,
    from_username: str,
    to_username: str,
    transfer_groups: bool = True,
) -> None:
    """Transfer all content and optionally groups from one user to another.

    Handles both root and folder-level items. Raises on failure — nothing
    is silently swallowed here since partial transfers can leave things in
    a bad state.
    """
    source_user: User = get_user(gis, from_username)
    target_user: User = get_user(gis, to_username)

    if source_user.username == target_user.username:
        log.info("Source and target users are the same. Nothing to do.")
        return

    log.info("Starting content transfer from %s to %s", from_username, to_username)

    try:
        # Root conten
        root_items = source_user.items()
        for item in root_items:
            item.reassign_to(target_user)

        # Folder content
        for folder in source_user.folders:
            if getattr(folder, "_fid", None) == "Root Folder":
                continue

            folder_title = folder._name or folder._properties.get("name")
            if not folder_title:
                log.warning("Skipping folder with no name for user %s", from_username)
                continue

            # Create folder on target (ignore if it already exists)
            try:
                gis.content.create_folder(folder_title, target_user.username)
            except Exception:
                pass

            folder_items = source_user.items(folder=folder_title)
            for item in folder_items:
                item.reassign_to(target_user, target_folder=folder_title)

        if transfer_groups:
            transfer_user_groups(gis, source_user, target_user)

        log.info(
            "Successfully transferred content from %s to %s", from_username, to_username
        )

    except Exception:
        log.exception(
            "Failed to transfer content from %s to %s", from_username, to_username
        )
        raise


"""
# ==== Functions created ====
# Search
- find_user: DONE
- user_details: DONE
- user_folders: DONE

# Lifecycle)
- create_user: DONE
- update_user_role: DONE
- update_user_type: DONE
- delete_user: DONE

# Access/Security
- disable_user: DONE
- enable_user: DONE
- reset_password (for non-Enterprise): DONE
- update_user_idp: DONE

# Offboarding 
- check_user_dependencies: DONE
- reassign_user_content: DONE
"""
