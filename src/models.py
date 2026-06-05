from dataclasses import dataclass
from .utils import esri_timestamp_to_str
import datetime as dt


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
    daysSinceLastLogin: int | None
    role: str
    userLicenseType: str
    mfaEnabled: bool | None
    access: str
    provider: str
    disabled: bool
    groups: int

    @classmethod
    def from_arcgis(cls, user_obj):
        last_login_ms = user_obj.get("lastLogin", -1)
        days_since = None

        if last_login_ms and last_login_ms != -1:
            login_date = dt.datetime.fromtimestamp(last_login_ms / 1000)
            days_since = (dt.datetime.now() - login_date).days

        return cls(
            firstName=user_obj.get("firstName", ""),
            lastName=user_obj.get("lastName", ""),
            fullName=user_obj.get("fullName", ""),
            username=user_obj.get(
                "username", ""
            ),  # Username is mandatory and always present
            email=user_obj.get("email", ""),
            idpUsername=user_obj.get("idpUsername", ""),
            created=esri_timestamp_to_str(user_obj.get("created")),
            lastLogin=esri_timestamp_to_str(user_obj.get("lastLogin")),
            daysSinceLastLogin=days_since,
            role=user_obj.get("role", ""),
            userLicenseType=user_obj.get("userLicenseTypeId", ""),
            mfaEnabled=user_obj.get("mfaEnabled", False),
            access=user_obj.get("access", ""),
            provider=user_obj.get("provider", ""),
            disabled=user_obj.get("disabled", False),
            groups=len(user_obj.get("groups", [])),
        )


@dataclass
class FolderInfo:
    id: str
    name: str
    created: str | None
