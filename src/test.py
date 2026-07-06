from pprint import pprint
import logging
from collections import Counter
from auth import gis_conn, load_config
from .users import *
from .audit import *
from .groups import *
from .content import *

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s: %(asctime)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

log = logging.getLogger(__name__)


if __name__ == "__main__":

    creds = load_config(source="agol")
    gis = gis_conn(creds=creds)

    create_folder(gis, "bob", owner="asims@cityofpasadena.net_pasgis")
    # u = user_provider_breakdown(gis)
    # print(u)

    # u = new_users(gis)
    # i = move_item(
    #    gis,
    #    item="8f64cad4bbc44d668e9785242ccc28f1",
    #    to_folder="test",
    #    owner="asims@cityofpasadena.net_pasgis",
    # )
    # g = new_groups(gis)

    # print(u)
    # print(i)
    # print(g)
    """
    summary = Counter(
        "Never" if u.daysSinceLastLogin is None else "Inactive" for u in ui
    )
    print(summary)
    

    print()
    usr = find_user(gis, username="yomontes")
    pprint(usr)
    """
    """
    if len(usr) > 1:
        for u in usr:
            pprint(u)
    else:
        pprint(usr)

    print()
    """
    # delete_user(gis, username="cboyd-contractor")

    """
    user = gis.users.get("yomontes")
    folders = list(user.folders)
    print(len(folders))
    print(type(folders[0]) if folders else "empty")
    print(vars(folders[0]) if folders else "empty")
    print()
    print(folders)
    for f in folders:
        print(vars(f).keys())
        # print(f["_folder"])
        print(f._fid)
        print(f._name)
        print(f._folder)
        print(f._properties)
    """
