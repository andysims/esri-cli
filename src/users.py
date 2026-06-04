import logging
from dataclasses import dataclass
from typing import NamedTuple
from arcgis.gis import GIS, User

from utils import esri_timestamp_to_str

log = logging.getLogger(__name__)
logging.getLogger("arcgis").setLevel(logging.ERROR)  # will move into main.py


@dataclass
class ArcGISUser:
    firstName: str
    lastName: str
    fullName: str
    username: str
    email: str
    idpUsername: str
    created: str | None
    lastLogin: str | None
    role: str
    userLicenseType: str
    mfaEnabled: str
    access: str
    provider: str
    disabled: bool
    groups: int

    @classmethod
    def from_arcgis(cls, user_obj):
        return cls(
            firstName=user_obj.firstName,
            lastName=user_obj.lastName,
            fullName=user_obj.fullName,
            username=user_obj.username,
            email=user_obj.email,
            idpUsername=user_obj.idpUsername,
            created=esri_timestamp_to_str(user_obj.created),
            lastLogin=esri_timestamp_to_str(user_obj.lastLogin),
            role=user_obj.role,
            userLicenseType=user_obj.userLicenseTypeId,
            mfaEnabled=user_obj.mfaEnabled,
            access=user_obj.access,
            provider=user_obj.provider,
            disabled=user_obj.disabled,
            groups=len(user_obj.groups),
        )

@dataclass
class FolderInfo:
    id: str
    name: str
    created: str | None


# ======== SEARCH ========
def get_user(gis: GIS, username: str) -> User:
    user = gis.users.get(username)
    if not user:
        log.warning("Username not found: %s", username)
        raise ValueError(f"Username was not found for {username}")
    log.info("Username found: %s", username)
    return user


def get_user_details(gis: GIS, username: str) -> ArcGISUser:
    raw_user = get_user(gis, username)
    return ArcGISUser.from_arcgis(raw_user)


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


def find_user(
    gis: GIS,
    username: str | None = None,
    email: str | None = None,
    lastname: str | None = None,
) -> list[ArcGISUser]:
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

        users: list[ArcGISUser] = [
            ArcGISUser.from_arcgis(u) for u in raw_users
        ]

        if not users:
            log.warning("Query returned no results: %s", query_string)
        else:
            log.info("Found %d user(s) for query: %s", len(users), query_string)

        return users

    except Exception:
        log.exception("Error during user search with query: %s", query_string)
        raise


def get_user_folders(gis: GIS, username: str) -> list[FolderInfo]:
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

    except Exception as e:   # 
        log.exception("Error fetching folders for %s", username)
        raise


# ======== Access/Security ========
def set_user_disabled(gis: GIS, username: str, disable: bool) -> bool:
    try:
        user = gis.users.get(username)   
        if not user:
            log.warning("User %s was not found", username)
            return False

        current_state = user.disabled   # or user.get("disabled", False)

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


"""
# ==== Functions to create ====
# Search
- find_user: DONE
- get_user_details: DONE
- get_user_folders: DONE

# Lifecycle
- create_user
- update_user_role
- update_user_type
- delete_user

# Access/Security
- disable_user: DONE
- enable_user: DONE
- reset_password (for non-Enterprise): not focused on this, for now
- update_user_idp: DONE

# Offboarding 
- check_user_dependencies
- reassign_user_content
"""