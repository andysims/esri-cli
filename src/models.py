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
    members: Dict[str, List[str]] = field(default_factory=dict)
    member_count: int = 0

    @classmethod
    def from_arcgis(cls, group_obj) -> "ArcGISGroup":
        """Create ArcGISGroup from arcgis.gis.Group object."""
        # getting members
        raw_members = group_obj.get_members()
        all_users = (
            [raw_members.get("owner")] if raw_members.get("owner") else []
        ) + raw_members.get("admins", []) + raw_members.get("members", [])
        member_count = len(set(all_users))
        
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
            members=raw_members,
            member_count=member_count
        )


@dataclass
class ArcGISGroupItem:
    id: str
    title: str
    type: str
    owner: str
    access: str
    created: str | None
    modified: str | None
    size_bytes: int
    numViews: int
    protected: bool
    tags: List[str]
    url: Optional[str] = None
    description: Optional[str] = None

    @property
    def size_mb(self) -> float:
        """Helper property to quickly read the item size in Megabytes."""
        return round(self.size_bytes / (1024 * 1024), 2)

    @classmethod
    def from_arcgis_item(cls, item: Item) -> "ArcGISGroupItem":
        """Instantiates from an ArcGIS API for Python Item object."""
        return cls(
            id=getattr(item, "id", ""),
            title=getattr(item, "title", ""),
            type=getattr(item, "type", ""),
            owner=getattr(item, "owner", ""),
            access=getattr(item, "access", "private"),
            created=esri_timestamp_to_str(getattr(item, "created", None)),
            modified=esri_timestamp_to_str(getattr(item, "modified", None)),
            size_bytes=getattr(item, "size", 0),
            numViews=getattr(item, "numViews", 0),
            protected=getattr(item, "protected", False),
            tags=getattr(item, "tags", []),
            url=getattr(item, "url", None),
            description=getattr(item, "description", None),
        )
