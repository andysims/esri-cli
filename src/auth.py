import logging
from typing import TypedDict
from pathlib import Path
from dotenv import dotenv_values
from arcgis.gis import GIS

log = logging.getLogger(__name__)


class GISCredentials(TypedDict):
    url: str
    username: str
    password: str


def load_config(source: str) -> GISCredentials:
    source = source.strip().lower()
    env_file = Path(__file__).resolve().parent.parent / ".env"

    if not env_file.is_file():
        error_msg = f"Configuration file not found at: {env_file}"
        log.error(error_msg)
        raise FileNotFoundError(error_msg)

    try:
        config = dotenv_values(env_file)
        
        url_key = f"{source}_url"
        user_key = f"{source}_username"
        password_key = f"{source}_password"

        url = config.get(url_key)
        user = config.get(user_key)
        password = config.get(password_key)
        
        extracted = {url_key: url, user_key: user, password_key: password}
        
        missing_keys = [key for key, val in extracted.items() if not val]

        if missing_keys:
            error_msg = f"Configuration validation failed. Missing or empty keys: {', '.join(missing_keys)}"
            log.error(error_msg)
            raise ValueError(error_msg)

        return {"url": url, "username": user, "password": password}
        
    except Exception as e:
        # Avoid double-logging if it's our own ValueError
        if not isinstance(e, ValueError):
            log.exception("Issue loading config configuration structure.")
        raise


def gis_conn(creds: GISCredentials) -> GIS:
    try:
        gis = GIS(
            url=creds.get("url"),
            username=creds.get("username"),
            password=creds.get("password"),
        )
        return gis
    except Exception:
        log.exception("Issue with GIS connection")
        raise


if __name__ == "__main__":
    lc = load_config(source="agol")
    gis = gis_conn(lc)

    print(f"Hello, {gis.properties.user.username}!")
