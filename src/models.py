from dataclasses import dataclass
from .utils import esri_timestamp_to_str
import datetime as dt
from typing import Dict, Any


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


@dataclass
class ArcGISGroup:
    id: str
    title: str
    owner: str
    description: str | None
    created: str | None
    modified: str | None
    access: str
    isInvitationOnly: bool
    isReadOnly: bool
    isViewOnly: bool
    protected: bool
    item_count: int

    @classmethod
    def from_arcgis(cls, group_obj) -> "ArcGISGroup":
        """Create ArcGISGroup from arcgis.gis.Group object."""
        # Safely get item_count
        try:
            item_count = len(group_obj.content()) if hasattr(group_obj, "content") else 0
        except Exception:
            item_count = 0

        return cls(
            id=getattr(group_obj, "id", ""),
            title=getattr(group_obj, "title", ""),
            owner=getattr(group_obj, "owner", ""),
            description=getattr(group_obj, "description", None),
            created=esri_timestamp_to_str(getattr(group_obj, "created", None)),
            modified=esri_timestamp_to_str(getattr(group_obj, "modified", None)),
            access=getattr(group_obj, "access", "private"),
            isInvitationOnly=getattr(group_obj, "isInvitationOnly", False),
            isReadOnly=getattr(group_obj, "isReadOnly", False),
            isViewOnly=getattr(group_obj, "isViewOnly", False),
            protected=getattr(group_obj, "protected", False),
            item_count=item_count,
        )
