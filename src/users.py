import logging
from dataclasses import dataclass
from typing import NamedTuple
from arcgis.gis import GIS, User

from utils import esri_timestamp_to_str

log = logging.getLogger(__name__)
logging.getLogger("arcgis").setLevel(logging.ERROR)  # will move this into main.py


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


class FolderInfo(NamedTuple):
    id: str
    name: str
    created: str | None


# ======== SEARCH ========
def get_user(gis: GIS, username: str) -> User:
    user = gis.users.get(username)

    if user:
        log.info("Username found: %s", username)
        return user
    else:
        log.warning("Username not found: %s", username)
        raise ValueError(f"Username was not found for {username}")


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
) -> ArcGISUser | None:
    query = []
    if username:
        query.append(f"username:{username}")
    if email:
        query.append(f"email:{email}")
    if lastname:
        query.append(f"lastname:{lastname}")

    if not query:
        log.warning("Sufficient info not provided for user search")
        return None

    query_string = " AND ".join(query)
    users = gis.users.search(query=query_string)

    if not users:
        log.warning("Query returned no results: %s", query_string)
        return None

    if len(users) == 1:
        user = users[0]
    else:
        user = select_user(users)

    return ArcGISUser.from_arcgis(user)


def get_user_details(gis: GIS, username: str) -> ArcGISUser:
    user = gis.users.get(username)
    # print(vars(user).keys())

    if user:
        log.info("Username found: %s", username)
        return ArcGISUser.from_arcgis(user)
    else:
        log.warning("Username not found: %s", username)
        raise ValueError(f"Username was not found for {username}")


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
                name=f._name or f._properties["name"],
                created=esri_timestamp_to_str(f._properties["created"]),
            )
            for f in user.folders
            if f._fid != "Root Folder"
        ]
    except Exception:
        log.exception("Error fetching folders for %s", username)
        return []

    if not folders:
        log.warning("No folders found for %s (outside root)", username)
        return []

    log.info("Returning %d folders for %s", len(folders), username)
    return folders


# ======== Access/Security ========
def disable_user(gis: GIS, username: str) -> bool:
    try:
        search_results: list[User] = gis.users.search(query=f"username:{username}")

        if not search_results:
            log.warning("Failed to disable user: User %s was not found", username)
            return False

        user: User = search_results[0]

        is_disabled: bool = user.get("disabled", False)

        if is_disabled:
            log.info("User %s is already disabled", username)
            return False

        success: bool = user.disable()
        if success:
            log.info("Successfully disabled user: %s", username)
            return True
        else:
            log.error("Failed to disable user")
            return False

    except Exception:
        log.exception(
            "Unexpected error occurred while attempting to disable %s", username
        )
        return False


def enable_user(gis: GIS, username: str) -> bool:
    try:
        search_results: list[User] = gis.users.search(query=f"username:{username}")

        if not search_results:
            log.warning("Failed to enable user: User %s was not found", username)
            return False

        user: User = search_results[0]

        is_disabled: bool = user.get("disabled", False)

        if not is_disabled:
            log.info("User %s is already enabled", username)
            return False

        success: bool = user.enable()
        if success:
            log.info("Successfully enabled user: %s", username)
            return True
        else:
            log.error("Failed to enable user")
            return False

    except Exception:
        log.exception(
            "Unexpected error occurred while attempting to enable %s", username
        )
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
