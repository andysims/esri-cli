from arcgis.gis import GIS, User
import logging

log = logging.getLogger(__name__)


def get_user(gis: GIS, username: str) -> User:
    """Fetch a user by username; raise ValueError if not found."""
    user = gis.users.get(username)
    if not user:
        log.warning("Username not found: %s", username)
        raise ValueError(f"Username was not found for {username}")
    log.info("Username found: %s", username)
    return user
