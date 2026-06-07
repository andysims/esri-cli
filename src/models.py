from dataclasses import dataclass, field
from .utils import esri_timestamp_to_str
import datetime as dt
from typing import Dict, Any, List, Optional


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
    def from_arcgis(cls, group_obj: Any) -> "ArcGISGroup":
        """Create from arcgis.gis.Group object or dict. Very defensive."""
        if group_obj is None:
            raise ValueError("Received None instead of a Group object")

        # Handle both dict and arcgis.gis.Group object
        if isinstance(group_obj, dict):
            props = group_obj
        else:
            props = getattr(group_obj, "properties", None)
            if props is None:
                props = group_obj  # fallback if no .properties

        if props is None:
            raise ValueError("Could not extract properties from group object")

        # Members
        try:
            raw_members = (
                group_obj.get_members() if hasattr(group_obj, "get_members") else {}
            )
        except Exception:
            raw_members = {}

        all_users: List[str] = []
        if raw_members.get("owner"):
            all_users.append(raw_members["owner"])
        all_users.extend(raw_members.get("admins", []))
        all_users.extend(raw_members.get("members", []))

        member_count = len(set(all_users))

        # Item count (can be expensive + flaky)
        try:
            if hasattr(group_obj, "content"):
                group_items = group_obj.content(max_items=10000)
                item_count = len(group_items)
            else:
                item_count = 0
        except Exception:
            item_count = 0

        return cls(
            id=props.get("id", ""),
            title=props.get("title", ""),
            owner=props.get("owner", ""),
            description=props.get("description"),
            created=esri_timestamp_to_str(props.get("created")),
            modified=esri_timestamp_to_str(props.get("modified")),
            access=props.get("access", "private"),
            isInvitationOnly=bool(props.get("isInvitationOnly", False)),
            isReadOnly=bool(props.get("isReadOnly", False)),
            isViewOnly=bool(props.get("isViewOnly", False)),
            protected=bool(props.get("protected", False)),
            item_count=item_count,
            members=raw_members,
            member_count=member_count,
        )


@dataclass
class ArcGISGroupItem:
    id: str
    title: str
    type: str
    owner: str
    access: str
    created: Optional[str]
    modified: Optional[str]
    size_bytes: int
    numViews: int
    protected: bool
    tags: List[str]
    url: Optional[str] = None
    description: Optional[str] = None

    @property
    def size_mb(self) -> float:
        """Helper to read item in MB."""
        return round(self.size_bytes / (1024 * 1024), 2)

    @classmethod
    def from_arcgis_item(cls, item) -> "ArcGISGroupItem":
        """Instantiates from an ArcGIS API for Python Item object."""
        props = getattr(item, "properties", {}) if hasattr(item, "properties") else item

        raw_size = props.get("size", 0)
        size_int = int(raw_size) if raw_size is not None else 0

        return cls(
            id=props.get("id", ""),
            title=props.get("title", ""),
            type=props.get("type", ""),
            owner=props.get("owner", ""),
            access=props.get("access", "private"),
            created=esri_timestamp_to_str(props.get("created")),
            modified=esri_timestamp_to_str(props.get("modified")),
            size_bytes=size_int,
            numViews=int(props.get("numViews", 0)),
            protected=bool(props.get("protected", False)),
            tags=props.get("tags", []),
            url=props.get("url"),
            description=props.get("description"),
        )


@dataclass
class ArcGISItem:
    id: str
    title: str
    type: str
    owner: str
    access: str
    created: str | None
    modified: str | None
    description: str | None
    tags: list[str] | None
    url: str | None

    @classmethod
    def from_arcgis(cls, item_obj: Any) -> "ArcGISItem":
        """Create ArcGISItem from an arcgis.gis.Item object."""

        props = (
            getattr(item_obj, "properties", {})
            if hasattr(item_obj, "properties")
            else item_obj
        )

        return cls(
            id=props.get("id"),
            title=props.get("title", "Untitled"),
            type=props.get("type", "Unknown"),
            owner=props.get("owner"),
            access=props.get("access", "private"),
            created=esri_timestamp_to_str(props.get("created")),
            modified=esri_timestamp_to_str(props.get("modified")),
            description=props.get("description"),
            tags=props.get("tags", []),
            url=props.get("url"),
        )
