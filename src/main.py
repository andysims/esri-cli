"""
main.py — ArcGIS Admin CLI
--------------------------
Entry point for the CLI. Using Typer to build a multi-command app broken
into sub-apps per domain (users, groups, content, etc.). Rich handles all
terminal output so we get tables, colors, and panels instead of raw print().

Run with:
    esri-cli --help
    esri-cli user find --email jdoe@example.com
    esri-cli group find --title "My Team"
    esri-cli group add-member <group_id> <username>

Auth note: every command takes --env (e.g. "agol" or "portal") to pick which
set of credentials to load from .env. Defaults to "agol". This hits
load_config() + gis_conn() from auth.py.
"""

import logging
import sys
from typing import Optional, List
from collections import Counter
import urllib3

import typer
from arcgis.gis import GIS
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from .auth import load_config, gis_conn
from . import users as user_ops
from . import groups as group_ops
from . import audit as audit_ops
from . import utils as utils_ops
from . import content as content_ops

# ---------------------------------------------------------------------------
# Logging — INFO goes to file, WARNING+ to stderr so Rich owns stdout cleanly.
# ---------------------------------------------------------------------------
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    handlers=[
        logging.FileHandler("arcgis_cli.log"),
        logging.StreamHandler(sys.stderr),
    ],
)
logging.getLogger("arcgis").setLevel(logging.ERROR)
log = logging.getLogger(__name__)

console = Console()

# ---------------------------------------------------------------------------
# Root app — one sub-app per domain, mounted by name.
# Adding a new domain (content, audit, etc.) is just:
#   1. Create foo_app = typer.Typer(...)
#   2. Add commands to it with @foo_app.command(...)
#   3. app.add_typer(foo_app, name="foo")
# ---------------------------------------------------------------------------
app = typer.Typer(
    name="arcgis-admin",
    help="ArcGIS Online / Portal administration CLI.",
    no_args_is_help=True,
)

user_app = typer.Typer(help="User management commands.", no_args_is_help=True)
group_app = typer.Typer(help="Group management commands.", no_args_is_help=True)
audit_app = typer.Typer(help="Audit commands", no_args_is_help=True)

app.add_typer(user_app, name="user")
app.add_typer(group_app, name="group")
app.add_typer(audit_app, name="audit")

content_app = typer.Typer(help="Content management commands.", no_args_is_help=True)
app.add_typer(content_app, name="content")


# ---------------------------------------------------------------------------
# Shared auth helper
# ---------------------------------------------------------------------------
def _connect(env: str) -> GIS:
    """Resolve credentials for `env` and return an authenticated GIS object."""
    try:
        creds = load_config(env)
        gis = gis_conn(creds)
        console.print(
            f"[dim]Connected to [bold]{gis.url}[/bold] as {gis.users.me.username}[/dim]"
        )
        return gis
    except FileNotFoundError:
        console.print(
            "[red bold]Error:[/red bold] .env file not found. Check your project root."
        )
        raise typer.Exit(1)
    except ValueError as e:
        console.print(f"[red bold]Config error:[/red bold] {e}")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red bold]Connection failed:[/red bold] {e}")
        raise typer.Exit(1)


# ===========================================================================
# USER commands
# ===========================================================================


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------
@user_app.command("find")
def cmd_find_user(
    username: Optional[str] = typer.Option(
        None, "--username", "-u", help="ArcGIS username."
    ),
    email: Optional[str] = typer.Option(None, "--email", "-e", help="Email address."),
    lastname: Optional[str] = typer.Option(None, "--lastname", "-l", help="Last name."),
    env: str = typer.Option(
        "agol", "--env", help="Environment key in .env (e.g. agol, portal)."
    ),
):
    """Search for users by username, email, and/or last name.

    All provided filters are AND-ed together. At least one is required.

    Examples:
        esri-cli user find --email jdoe@example.com
        esri-cli user find --lastname Smith --env portal
    """
    if not any([username, email, lastname]):
        console.print(
            "[yellow]Provide at least one of --username, --email, --lastname.[/yellow]"
        )
        raise typer.Exit(1)

    gis = _connect(env)
    results = user_ops.find_user(gis, username=username, email=email, lastname=lastname)

    if not results:
        console.print("[yellow]No users found matching those criteria.[/yellow]")
        return

    table = Table(title=f"Users ({len(results)} found)", show_lines=True)
    table.add_column("Username", style="cyan", no_wrap=True)
    table.add_column("Full Name")
    table.add_column("Email")
    table.add_column("Role")
    table.add_column("User Type")
    table.add_column("Created")

    for u in results:
        table.add_row(
            u.username, u.fullName, u.email, u.role, u.userLicenseType, u.created or "—"
        )

    console.print(table)


@user_app.command("details")
def cmd_user_details(
    username: str = typer.Argument(..., help="Username to look up."),
    env: str = typer.Option("agol", "--env", help="Environment key in .env."),
):
    """Show full profile details for a single user.

    Example:
        esri-cli user details jdoe
    """
    gis = _connect(env)

    try:
        u = user_ops.user_details(gis, username)
    except ValueError as e:
        console.print(f"[red]Not found:[/red] {e}")
        raise typer.Exit(1)

    detail_lines = [
        f"[bold]Username:[/bold]     {u.username}",
        f"[bold]Full Name:[/bold]    {u.fullName}",
        f"[bold]Email:[/bold]        {u.email}",
        f"[bold]idpUsername:[/bold]  {u.idpUsername or '—'}",
        f"[bold]Role:[/bold]         {u.role}",
        f"[bold]User Type:[/bold]    {u.userLicenseType}",
        f"[bold]Created:[/bold]      {u.created or '—'}",
        f"[bold]Last Login:[/bold]   {u.lastLogin or '—'}",
        f"[bold]Disabled:[/bold]     {'Yes' if u.disabled else 'No'}",
        f"[bold]Provider:[/bold]     {u.provider}",
        f"[bold]Groups:[/bold]       {u.groups or '—'}",
    ]
    console.print(
        Panel("\n".join(detail_lines), title=f"[cyan]{username}[/cyan]", expand=False)
    )


@user_app.command("folders")
def cmd_user_folders(
    username: str = typer.Argument(..., help="Username whose folders to list."),
    env: str = typer.Option("agol", "--env", help="Environment key in .env."),
):
    """List all content folders owned by a user (root folder excluded).

    Example:
        esri-cli user folders jdoe
    """
    gis = _connect(env)
    folders = user_ops.user_folders(gis, username)

    if not folders:
        console.print(f"[yellow]No folders found for {username}.[/yellow]")
        return

    table = Table(title=f"Folders for {username}")
    table.add_column("ID", style="dim")
    table.add_column("Name", style="cyan")
    table.add_column("Created")

    for f in folders:
        table.add_row(f.id, f.name, f.created or "—")

    console.print(table)


@user_app.command("groups")
def cmd_user_groups(
    username: str = typer.Argument(..., help="Username to look up groups for."),
    env: str = typer.Option("agol", "--env", help="Environment key in .env."),
):
    """List all groups a user belongs to, sorted alphabetically by group title.

    Example:
        esri-cli user groups bsmith
    """
    gis = _connect(env)

    with console.status(
        f"[bold green]Fetching groups for {username}...", spinner="dots"
    ):
        try:
            groups = user_ops.user_groups(gis, username)
        except ValueError as e:
            console.print(f"[red]Error:[/red] {e}")
            raise typer.Exit(1)

    if not groups:
        console.print(f"[yellow]{username} is not a member of any groups.[/yellow]")
        return

    table = Table(title=f"Groups for {username} ({len(groups)} total)", show_lines=True)

    table.add_column("Group ID", style="dim")
    table.add_column("Group Title", style="cyan")
    table.add_column("Created", justify="center")
    table.add_column("Owner")
    table.add_column("Members", justify="right")

    for g in groups:
        is_owner = username.lower() == g.owner.lower()
        owner_display = f"[bold]{g.owner}[/bold]" if is_owner else g.owner

        table.add_row(
            g.id,
            g.title,
            g.created or "—",
            owner_display,
            str(g.member_count),
        )

    console.print(table)


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------
@user_app.command("create")
def cmd_create_user(
    username: str = typer.Option(..., "--username", "-u", help="New account username."),
    first_name: str = typer.Option(..., "--first-name", "-f", help="First name."),
    last_name: str = typer.Option(..., "--last-name", "-l", help="Last name."),
    email: str = typer.Option(..., "--email", "-e", help="Email address."),
    password: Optional[str] = typer.Option(
        None, help="Password (local accounts only)."
    ),
    idp_username: Optional[str] = typer.Option(
        None, "--idp", help="IdP username (enterprise accounts only)."
    ),
    user_type: str = typer.Option(
        "viewerUT", help="License type (e.g. creatorUT, viewerUT)."
    ),
    role: str = typer.Option(
        "org_viewer", help="Role (e.g. org_publisher, org_admin)."
    ),
    env: str = typer.Option("agol", "--env", help="Environment key in .env."),
):
    """Create a new local or enterprise user.

    For local users, provide --password.
    For enterprise (IdP-backed) users, provide --idp and omit --password.

    Examples:
        esri-cli user create -u jdoe -f Jane -l Doe -e jdoe@co.com --password Secret1!
        esri-cli user create -u jdoe -f Jane -l Doe -e jdoe@co.com --idp jdoe@corp.ad
    """
    gis = _connect(env)

    with console.status(f"Creating user [cyan]{username}[/cyan]..."):
        try:
            result = user_ops.create_user(
                gis,
                username=username,
                first_name=first_name,
                last_name=last_name,
                email=email,
                password=password,
                idp_username=idp_username,
                user_type=user_type,
                role=role,
            )
        except ValueError as e:
            console.print(f"[red bold]Error:[/red bold] {e}")
            raise typer.Exit(1)

    if result is None:
        console.print(
            f"[yellow]User '{username}' already exists — nothing was created.[/yellow]"
        )
    else:
        console.print(
            f"[green]✓[/green] Created user [cyan]{username}[/cyan] ({first_name} {last_name})."
        )


@user_app.command("delete")
def cmd_delete_user(
    username: str = typer.Argument(..., help="Username to delete."),
    reassign_to: Optional[str] = typer.Option(
        None,
        "--reassign-to",
        "-r",
        help="Transfer content/groups to this user before deleting.",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Check whether deletion is safe without actually deleting.",
    ),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt."),
    env: str = typer.Option("agol", "--env", help="Environment key in .env."),
):
    """Delete a user account.

    Use --dry-run first to check whether it's safe. Pass --reassign-to if the
    user owns content or groups that need to be moved before deletion.

    Examples:
        esri-cli user delete jdoe --dry-run
        esri-cli user delete jdoe --reassign-to admin_user --yes
    """
    gis = _connect(env)

    if dry_run:
        try:
            user_ops.delete_user(gis, username, dry_run=True)
            console.print(
                f"[green]✓ Dry run passed.[/green] User '{username}' can be safely deleted."
            )
        except ValueError as e:
            console.print(f"[yellow]Dry run failed:[/yellow] {e}")
        return

    if not yes:
        confirmed = typer.confirm(
            f"Really delete user '{username}'? This cannot be undone."
        )
        if not confirmed:
            console.print("[dim]Aborted.[/dim]")
            raise typer.Exit(0)

    try:
        user_ops.delete_user(gis, username, reassign_to=reassign_to)
        console.print(f"[green]✓[/green] Deleted user [cyan]{username}[/cyan].")
    except ValueError as e:
        console.print(f"[red bold]Error:[/red bold] {e}")
        raise typer.Exit(1)


@user_app.command("set-role")
def cmd_update_role(
    username: str = typer.Argument(..., help="Target username."),
    role: str = typer.Argument(..., help="New role (e.g. org_publisher, org_admin)."),
    env: str = typer.Option("agol", "--env", help="Environment key in .env."),
):
    """Update a user's role.

    Example:
        esri-cli user set-role jdoe org_publisher

    Reference: Standard ArcGIS System Role IDs
        Viewer: iAAAAAAAAAAAAAAA
        Data Editor: iBBBBBBBBBBBBBBB
        Facilitator: iCCCCCCCCCCCCCCC
        User: org_user
        Publisher: org_publisher
        Administrator: org_admin
    """
    gis = _connect(env)
    ok = user_ops.update_user_role(gis, username, role)
    if ok:
        console.print(
            f"[green]✓[/green] Role for [cyan]{username}[/cyan] set to [bold]{role}[/bold]."
        )
    else:
        console.print(f"[red]Failed to update role for {username}.[/red]")
        raise typer.Exit(1)


@user_app.command("set-type")
def cmd_update_type(
    username: str = typer.Argument(..., help="Target username."),
    user_type: str = typer.Argument(
        ..., help="New license type (e.g. creatorUT, viewerUT)."
    ),
    env: str = typer.Option("agol", "--env", help="Environment key in .env."),
):
    """Update a user's license type.

    Example:
        esri-cli user set-type jdoe creatorUT
    """
    gis = _connect(env)
    ok = user_ops.update_user_type(gis, username, user_type)
    if ok:
        console.print(
            f"[green]✓[/green] User type for [cyan]{username}[/cyan] set to [bold]{user_type}[/bold]."
        )
    else:
        console.print(f"[red]Failed to update user type for {username}.[/red]")
        raise typer.Exit(1)


# ---------------------------------------------------------------------------
# Access / Security
# ---------------------------------------------------------------------------


@user_app.command("disable")
def cmd_disable_user(
    username: str = typer.Argument(..., help="Username to disable."),
    env: str = typer.Option("agol", "--env", help="Environment key in .env."),
):
    """Disable a user account (they can no longer sign in).

    Example:
        esri-cli user disable jdoe
    """
    gis = _connect(env)
    ok = user_ops.set_user_disabled(gis, username, disable=True)
    if ok:
        console.print(
            f"[green]✓[/green] Account [cyan]{username}[/cyan] has been [bold]disabled[/bold]."
        )
    else:
        console.print(
            f"[yellow]No change — user may already be disabled or not found.[/yellow]"
        )


@user_app.command("enable")
def cmd_enable_user(
    username: str = typer.Argument(..., help="Username to re-enable."),
    env: str = typer.Option("agol", "--env", help="Environment key in .env."),
):
    """Re-enable a previously disabled user account.

    Example:
        esri-cli user enable jdoe
    """
    gis = _connect(env)
    ok = user_ops.set_user_disabled(gis, username, disable=False)
    if ok:
        console.print(
            f"[green]✓[/green] Account [cyan]{username}[/cyan] has been [bold]re-enabled[/bold]."
        )
    else:
        console.print(
            f"[yellow]No change — user may already be active or not found.[/yellow]"
        )


@user_app.command("reset-password")
def cmd_reset_password(
    username: str = typer.Argument(..., help="Username (local accounts only)."),
    new_password: str = typer.Option(..., "--password", "-p", help="New password."),
    env: str = typer.Option("agol", "--env", help="Environment key in .env."),
):
    """Reset the password for a local (non-enterprise) ArcGIS user.

    Won't work on enterprise/IdP-backed accounts — those passwords live in
    the identity provider, not ArcGIS.

    Example:
        esri-cli user reset-password jdoe --password NewSecret1!
    """
    gis = _connect(env)
    ok = user_ops.reset_password(gis, username, new_password)
    if ok:
        console.print(f"[green]✓[/green] Password reset for [cyan]{username}[/cyan].")
    else:
        console.print(
            f"[red]Failed — user not found, already enterprise, or API error.[/red]"
        )
        raise typer.Exit(1)


@user_app.command("set-idp")
def cmd_update_idp(
    username: str = typer.Argument(..., help="ArcGIS username."),
    idp_username: str = typer.Argument(..., help="New IdP/SAML username to link."),
    env: str = typer.Option("agol", "--env", help="Environment key in .env."),
):
    """Update the IdP (SAML/enterprise) username linked to an account.

    Only applies to enterprise-provider accounts. Built-in 'arcgis' accounts
    cannot have an IdP username.

    Example:
        esri-cli user set-idp jdoe jdoe@corp.onmicrosoft.com
    """
    gis = _connect(env)
    ok = user_ops.update_user_idp(gis, username, idp_username)
    if ok:
        console.print(
            f"[green]✓[/green] IdP username for [cyan]{username}[/cyan] updated to [bold]{idp_username}[/bold]."
        )
    else:
        console.print(f"[red]Update failed — check logs for details.[/red]")
        raise typer.Exit(1)


# ---------------------------------------------------------------------------
# Offboarding
# ---------------------------------------------------------------------------


@user_app.command("check-deps")
def cmd_check_dependencies(
    username: str = typer.Argument(..., help="Username to inspect."),
    env: str = typer.Option("agol", "--env", help="Environment key in .env."),
):
    """Check what a user owns before deletion or offboarding.

    Shows item count, folders, owned groups, and group memberships so you
    know what needs reassigning before the account can be deleted.

    Example:
        esri-cli user check-deps jdoe
    """
    gis = _connect(env)

    try:
        summary = user_ops.check_user_dependencies(gis, username)
    except ValueError as e:
        console.print(f"[red]Not found:[/red] {e}")
        raise typer.Exit(1)

    safe = summary["safe_to_delete"]
    status_color = "green" if safe else "yellow"
    status_label = "Safe to delete" if safe else "Needs reassignment first"

    lines = [
        f"[bold]Items:[/bold]         {summary['items']}",
        f"[bold]Folders:[/bold]       {summary['folders']}",
        f"[bold]Owned groups:[/bold]  {summary['owned_groups']}",
        f"[bold]Member groups:[/bold] {summary['member_groups']}",
        "",
        f"[{status_color}][bold]Status:[/bold] {status_label}[/{status_color}]",
    ]
    console.print(
        Panel(
            "\n".join(lines),
            title=f"[cyan]Dependencies: {username}[/cyan]",
            expand=False,
        )
    )


@user_app.command("transfer")
def cmd_transfer_content(
    from_username: str = typer.Option(
        ..., "--from", "-f", help="User to transfer content FROM."
    ),
    to_username: str = typer.Option(
        ..., "--to", "-t", help="User to transfer content TO."
    ),
    transfer_groups: bool = typer.Option(
        True, "--groups/--no-groups", help="Also transfer group ownership."
    ),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt."),
    env: str = typer.Option("agol", "--env", help="Environment key in .env."),
):
    """Transfer all content (and optionally groups) from one user to another.

    Run this before deleting an offboarded employee's account. Moves both
    root-level and folder items, recreating folders on the target as needed.

    Examples:
        esri-cli user transfer --from jdoe --to admin_user
        esri-cli user transfer --from jdoe --to admin_user --no-groups --yes
    """
    gis = _connect(env)

    if not yes:
        confirmed = typer.confirm(
            f"Transfer all content from '{from_username}' to '{to_username}'?"
            + (" (including groups)" if transfer_groups else " (content only)")
        )
        if not confirmed:
            console.print("[dim]Aborted.[/dim]")
            raise typer.Exit(0)

    with console.status(
        f"Transferring content from [cyan]{from_username}[/cyan] to [cyan]{to_username}[/cyan]..."
    ):
        try:
            user_ops.transfer_user_content(
                gis,
                from_username=from_username,
                to_username=to_username,
                transfer_groups=transfer_groups,
            )
        except ValueError as e:
            console.print(f"[red bold]Error:[/red bold] {e}")
            raise typer.Exit(1)
        except Exception as e:
            console.print(f"[red bold]Transfer failed:[/red bold] {e}")
            raise typer.Exit(1)

    console.print(
        f"[green]✓[/green] Content transferred from [cyan]{from_username}[/cyan] to [cyan]{to_username}[/cyan]."
    )


# ===========================================================================
# GROUP commands
# ===========================================================================

# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------


@group_app.command("find")
def cmd_find_group(
    group_id: Optional[str] = typer.Option(
        None, "--id", "-i", help="Group ID (exact match)."
    ),
    title: Optional[str] = typer.Option(
        None, "--title", "-t", help="Group title (partial match)."
    ),
    owner: Optional[str] = typer.Option(None, "--owner", "-o", help="Owner username."),
    env: str = typer.Option("agol", "--env", help="Environment key in .env."),
):
    """Search for groups by ID, title, and/or owner.

    All filters are AND-ed. At least one is required.

    Examples:
        esri-cli group find --title "GIS Team"
        esri-cli group find --owner jdoe
        esri-cli group find --id abc123def456
    """
    if not any([group_id, title, owner]):
        console.print(
            "[yellow]Provide at least one of --id, --title, --owner.[/yellow]"
        )
        raise typer.Exit(1)

    gis = _connect(env)
    results = group_ops.find_group(gis, group_id=group_id, title=title, owner=owner)

    if not results:
        console.print("[yellow]No groups found matching those criteria.[/yellow]")
        return

    table = Table(title=f"Groups ({len(results)} found)", show_lines=True)
    table.add_column("ID", style="dim", no_wrap=True)
    table.add_column("Title", style="cyan")
    table.add_column("Owner")
    table.add_column("Access")
    table.add_column("Members", justify="right")
    table.add_column("Items", justify="right")

    for g in results:
        table.add_row(
            g.id,
            g.title,
            g.owner,
            g.access,
            str(g.member_count) if hasattr(g, "member_count") else "—",
            str(g.item_count) if hasattr(g, "item_count") else "—",
        )

    console.print(table)


@group_app.command("details")
def cmd_group_details(
    group: str = typer.Argument(..., help="Group ID or title."),
    env: str = typer.Option("agol", "--env", help="Environment key in .env."),
):
    """Show full details for a single group.

    Accepts either a group ID (preferred) or title. If the title matches
    multiple groups, you'll be asked to use the ID instead.

    Example:
        esri-cli group details abc123def456
        esri-cli group details "GIS Team"
    """
    gis = _connect(env)

    try:
        g = group_ops.group_details(gis, group)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    lines = [
        f"[bold]ID:[/bold]          {g.id}",
        f"[bold]Title:[/bold]       {g.title}",
        f"[bold]Owner:[/bold]       {g.owner}",
        f"[bold]Created:[/bold]     {g.created}",
        f"[bold]Access:[/bold]      {g.access}",
        f"[bold]Members:[/bold]     {g.member_count}",
        f"[bold]Items:[/bold]       {g.item_count}",
        f"[bold]Description:[/bold] {g.description or '—'}",
        f"[bold]Protected:[/bold]   {'Yes' if g.protected else 'No'}",
        f"[bold]View Only:[/bold]   {'Yes' if g.isViewOnly else 'No'}",
        f"[bold]Invite Only:[/bold] {'Yes' if g.isInvitationOnly else 'No'}",
    ]
    console.print(
        Panel("\n".join(lines), title=f"[cyan]{g.title}[/cyan]", expand=False)
    )


@group_app.command("members")
def cmd_group_members(
    group: str = typer.Argument(..., help="Group ID or title."),
    env: str = typer.Option("agol", "--env", help="Environment key in .env."),
    export_csv: Optional[str] = typer.Option(
        None, "--export-csv", help="Filename to export results to CSV"
    ),
):
    """Show full members list for a single group."""
    gis = _connect(env)

    try:
        g = group_ops._resolve_group(gis, group)
        members = group_ops.get_group_members(gis, g.id)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    lines = [
        f"[bold]ID:[/bold] {g.id}",
        f"[bold]Owner:[/bold] {g.owner}",
        f"[bold]Protected:[/bold] {'Yes' if getattr(g, 'protected', False) else 'No'}",
        f"[bold]Invite Only:[/bold] {'Yes' if getattr(g, 'isInvitationOnly', False) else 'No'}",
    ]
    console.print(
        Panel("\n".join(lines), title=f"[cyan]Group: {g.title}[/cyan]", expand=False)
    )
    console.print()

    # Create a structured table to show the member list cleanly
    table = Table(title="Group Members Directory", title_justify="left")
    table.add_column("Username", style="dim")
    table.add_column("Full Name", style="bold white")
    table.add_column("Email", style="blue")
    table.add_column("Group Role", style="green")

    # Populate rows from your dataclass fields
    for m in members:
        table.add_row(m.username, m.fullName, m.email or "—", m.group_role.upper())

    console.print(table)

    if export_csv:
        utils_ops.export_to_csv(members, export_csv)
        typer.echo(f"Data exported to {export_csv}")


# ---------------------------------------------------------------------------
# Membership
# ---------------------------------------------------------------------------


@group_app.command("add-member")
def cmd_add_member(
    group: str = typer.Argument(..., help="Group ID or title."),
    username: str = typer.Argument(..., help="Username to add."),
    env: str = typer.Option("agol", "--env", help="Environment key in .env."),
):
    """Add a user to a group.

    Example:
        esri-cli group add-member abc123def456 jdoe
        esri-cli group add-member "GIS Team" jdoe
    """
    gis = _connect(env)

    try:
        group_ops.add_group_member(gis, group=group, username=username)
        console.print(
            f"[green]✓[/green] Added [cyan]{username}[/cyan] to group [bold]{group}[/bold]."
        )
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)


@group_app.command("remove-member")
def cmd_remove_member(
    group: str = typer.Argument(..., help="Group ID or title."),
    username: str = typer.Argument(..., help="Username to remove."),
    env: str = typer.Option("agol", "--env", help="Environment key in .env."),
):
    """Remove a user from a group.

    Example:
        esri-cli group remove-member abc123def456 jdoe
    """
    gis = _connect(env)

    try:
        group_ops.remove_group_member(gis, group=group, username=username)
        console.print(
            f"[green]✓[/green] Removed [cyan]{username}[/cyan] from group [bold]{group}[/bold]."
        )
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)


@group_app.command("set-member-role")
def cmd_update_member_role(
    group: str = typer.Argument(..., help="Group ID or title."),
    username: str = typer.Argument(..., help="Username to update."),
    role: str = typer.Argument(..., help="New role: member, admin, or owner."),
    env: str = typer.Option("agol", "--env", help="Environment key in .env."),
):
    """Update a member's role within a group.

    Valid roles: member, admin, owner.

    Example:
        esri-cli group set-member-role abc123def456 jdoe admin
    """
    gis = _connect(env)

    try:
        group_ops.update_member_role(gis, group=group, username=username, role=role)
        console.print(
            f"[green]✓[/green] Role for [cyan]{username}[/cyan] in group "
            f"[bold]{group}[/bold] set to [bold]{role}[/bold]."
        )
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)


@group_app.command("transfer-ownership")
def cmd_transfer_group_ownership(
    group_id: str = typer.Argument(
        ..., help="Group ID (not title — ownership transfers need an exact ID)."
    ),
    new_owner: str = typer.Argument(..., help="Username of the new owner."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt."),
    env: str = typer.Option("agol", "--env", help="Environment key in .env."),
):
    """Transfer ownership of a group to another user.

    Uses group ID rather than title to avoid any ambiguity — run
    'esri-cli group find --title ...' first if you need to look it up.

    Example:
        esri-cli group transfer-ownership abc123def456 new_owner_username
    """
    gis = _connect(env)

    if not yes:
        confirmed = typer.confirm(
            f"Transfer ownership of group '{group_id}' to '{new_owner}'?"
        )
        if not confirmed:
            console.print("[dim]Aborted.[/dim]")
            raise typer.Exit(0)

    try:
        group_ops.transfer_group_ownership(
            gis, group_id=group_id, new_owner_username=new_owner
        )
        console.print(
            f"[green]✓[/green] Ownership of group [bold]{group_id}[/bold] transferred to [cyan]{new_owner}[/cyan]."
        )
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------


@group_app.command("create")
def cmd_create_group(
    title: str = typer.Option(..., "--title", "-t", help="Group title."),
    description: Optional[str] = typer.Option(
        None, "--description", "-d", help="Group description."
    ),
    access: str = typer.Option(
        "org", "--access", "-a", help="Access level: private, org, or public."
    ),
    tags: Optional[str] = typer.Option(
        None, "--tags", help="Comma-separated tags (e.g. 'gis,maps,team')."
    ),
    invite_only: bool = typer.Option(
        False, "--invite-only", help="Require invitation to join."
    ),
    view_only: bool = typer.Option(
        False, "--view-only", help="Members can only view, not contribute."
    ),
    protected: bool = typer.Option(
        False, "--protected", help="Protect from accidental deletion."
    ),
    env: str = typer.Option("agol", "--env", help="Environment key in .env."),
):
    """Create a new group.

    Examples:
        esri-cli group create --title "GIS Team" --access org
        esri-cli group create --title "Public Maps" --access public --tags "maps,public" --protected
    """
    gis = _connect(env)

    # Split the comma-separated tags string into a list, or pass empty.
    tag_list = [t.strip() for t in tags.split(",")] if tags else []

    try:
        g = group_ops.create_group(
            gis,
            title=title,
            description=description,
            access=access,
            tags=tag_list,
            isInvitationOnly=invite_only,
            isViewOnly=view_only,
            protected=protected,
        )
        console.print(
            f"[green]✓[/green] Created group [cyan]{g.title}[/cyan] (ID: [dim]{g.id}[/dim])."
        )
    except ValueError as e:
        console.print(f"[red bold]Error:[/red bold] {e}")
        raise typer.Exit(1)


@group_app.command("update")
def cmd_update_group(
    group: str = typer.Argument(..., help="Group ID or title."),
    title: Optional[str] = typer.Option(None, "--title", "-t", help="New title."),
    description: Optional[str] = typer.Option(
        None, "--description", "-d", help="New description."
    ),
    access: Optional[str] = typer.Option(
        None, "--access", "-a", help="New access level: private, org, or public."
    ),
    env: str = typer.Option("agol", "--env", help="Environment key in .env."),
):
    """Update a group's title, description, and/or access level.

    At least one of --title, --description, or --access is required.

    Examples:
        esri-cli group update abc123 --title "New Name"
        esri-cli group update "GIS Team" --access public
    """
    if not any([title, description, access]):
        console.print(
            "[yellow]Provide at least one of --title, --description, --access.[/yellow]"
        )
        raise typer.Exit(1)

    gis = _connect(env)

    try:
        group_ops.update_group(
            gis, group=group, title=title, description=description, access=access
        )
        console.print(f"[green]✓[/green] Group [bold]{group}[/bold] updated.")
    except ValueError as e:
        console.print(f"[red bold]Error:[/red bold] {e}")
        raise typer.Exit(1)


@group_app.command("delete")
def cmd_delete_group(
    group: str = typer.Argument(..., help="Group ID or title."),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Check whether deletion is safe without actually deleting.",
    ),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt."),
    env: str = typer.Option("agol", "--env", help="Environment key in .env."),
):
    """Delete a group.

    Protected groups will be rejected even without --dry-run. Use --dry-run
    to verify first.

    Examples:
        esri-cli group delete abc123def456 --dry-run
        esri-cli group delete abc123def456 --yes
    """
    gis = _connect(env)

    if dry_run:
        try:
            group_ops.delete_group(gis, group, dry_run=True)
            console.print(
                f"[green]✓ Dry run passed.[/green] Group '{group}' can be deleted."
            )
        except ValueError as e:
            console.print(f"[yellow]Dry run failed:[/yellow] {e}")
        return

    if not yes:
        confirmed = typer.confirm(
            f"Really delete group '{group}'? This cannot be undone."
        )
        if not confirmed:
            console.print("[dim]Aborted.[/dim]")
            raise typer.Exit(0)

    try:
        group_ops.delete_group(gis, group)
        console.print(f"[green]✓[/green] Deleted group [bold]{group}[/bold].")
    except ValueError as e:
        console.print(f"[red bold]Error:[/red bold] {e}")
        raise typer.Exit(1)


# ---------------------------------------------------------------------------
# Content
# ---------------------------------------------------------------------------
@group_app.command("content")
def cmd_group_content(
    group: str = typer.Argument(..., help="Group ID or title."),
    env: str = typer.Option("agol", "--env", help="Environment key in .env."),
):
    """List all items shared with a group.

    Example:
        esri-cli group content abc123def456
        esri-cli group content "GIS Team"
    """
    gis = _connect(env)

    try:
        items = group_ops.group_content(gis, group)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    if not items:
        console.print(f"[yellow]No items found in group '{group}'.[/yellow]")
        return

    table = Table(title=f"Content in '{group}' ({len(items)} items)", show_lines=True)
    table.add_column("ID", style="dim", no_wrap=True)
    table.add_column("Title", style="cyan")
    table.add_column("Type")
    table.add_column("Owner")
    table.add_column("Created")

    for item in items:
        table.add_row(
            item.id,
            item.title,
            item.type,
            item.owner,
            item.created,
        )

    console.print(table)


@group_app.command("add-item")
def cmd_add_item(
    group: str = typer.Argument(..., help="Group ID or title."),
    item_id: str = typer.Argument(..., help="Item ID to share with the group."),
    env: str = typer.Option("agol", "--env", help="Environment key in .env."),
):
    """Share an item with a group.

    Example:
        esri-cli group add-item abc123def456 item_id_here
    """
    gis = _connect(env)

    try:
        group_ops.add_item(gis, group=group, item=item_id)
        console.print(
            f"[green]✓[/green] Item [dim]{item_id}[/dim] shared with group [bold]{group}[/bold]."
        )
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)


@group_app.command("remove-item")
def cmd_remove_item(
    group: str = typer.Argument(..., help="Group ID or title."),
    item_id: str = typer.Argument(..., help="Item ID to unshare from the group."),
    env: str = typer.Option("agol", "--env", help="Environment key in .env."),
):
    """Unshare an item from a group.

    Note: this calls item.share() with the group removed. If the item is
    shared with other groups, those are left untouched.

    Example:
        esri-cli group remove-item abc123def456 item_id_here
    """
    gis = _connect(env)

    try:
        group_ops.remove_item(gis, group=group, item=item_id)
        console.print(
            f"[green]✓[/green] Item [dim]{item_id}[/dim] removed from group [bold]{group}[/bold]."
        )
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)


# ===========================================================================
# AUDIT commands
# ===========================================================================
# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------
@audit_app.command("inactive")
def cmd_inactive_users(
    days: int = typer.Option(90, "--days", "-d", help="Days inactive"),
    env: str = typer.Option("agol", "--env", help="Environment key in .env."),
    export_csv: Optional[str] = typer.Option(
        None, "--export-csv", help="Export to CSV"
    ),
):
    """Audits environment for users that have not logged in X amount of days."""
    gis = _connect(env)
    try:
        total_org_users = audit_ops.total_users(gis)
        users = audit_ops.inactive_users(gis, days)
        total_count = len(users)
        never_logged_in_count = sum(
            1 for u in users if getattr(u, "daysSinceLastLogin") is None
        )

        inactive_count = total_count - never_logged_in_count

        never_logged_in_pct = round((never_logged_in_count / total_count) * 100, 1)
        inactive_days_pct = round((inactive_count / total_org_users) * 100, 1)

        console.print(
            f"\n[green]✓[/green] Audit complete for environment: [bold]{env}[/bold]"
        )
        console.print(
            f" • Total inactive users:       [bold yellow]{total_count}[/bold yellow]"
        )
        console.print(
            f" • Never logged in:            [bold cyan]{never_logged_in_count} ({never_logged_in_pct}%)[/bold cyan]"
        )
        console.print(
            f" • Inactive for {days}+ days:    [bold magenta]{inactive_count} ({inactive_days_pct}%)[/bold magenta]\n"
        )

        if export_csv:
            utils_ops.export_to_csv(users, export_csv)
            typer.echo(f"Data exported to {export_csv}")

    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)


def _parse_cli_list(values: Optional[List[str]]) -> Optional[List[str]]:
    """Helper to flatten multi-flag inputs and split on commas.

    Turns ['arcgis, enterprise', 'saml'] into ['arcgis', 'enterprise', 'saml']
    """
    if not values:
        return None

    parsed_items = []
    for item in values:
        # Split on commas and strip leading/trailing whitespace
        split_items = [val.strip() for val in item.split(",") if val.strip()]
        parsed_items.extend(split_items)

    return parsed_items if parsed_items else None


@audit_app.command("list-users")
def cmd_list_users(
    exclude_license: Optional[List[str]] = typer.Option(
        None,
        "--exclude-license",
        "-xl",
        help="License type(s) to filter out. Comma-separated or multiple flags.",
    ),
    exclude_provider: Optional[List[str]] = typer.Option(
        None,
        "--exclude-provider",
        "-xp",
        help="Provider(s) to filter out. Comma-separated or multiple flags.",
    ),
    exclude_role: Optional[List[str]] = typer.Option(
        None,
        "--exclude-role",
        "-xr",
        help="Role(s) to filter out. Comma-separated or multiple flags.",
    ),
    outside_org: bool = typer.Option(
        False, "--outside-org", help="Include users from outside the org."
    ),
    env: str = typer.Option("agol", "--env", help="Environment key in .env."),
    export_csv: Optional[str] = typer.Option(
        None, "--export-csv", help="Path to export matching users as CSV."
    ),
):
    """Fetches organization users with optional exclusion filters and displays counts."""
    gis = _connect(env)

    # Process and clean up the comma-separated or multi-flag arguments
    parsed_licenses = _parse_cli_list(exclude_license)
    parsed_providers = _parse_cli_list(exclude_provider)
    parsed_roles = _parse_cli_list(exclude_role)

    try:
        with console.status("[bold green]Fetching and filtering users..."):
            users = audit_ops.get_users(
                gis=gis,
                exclude_license_types=parsed_licenses,
                exclude_providers=parsed_providers,
                exclude_roles=parsed_roles,
                outside_org=outside_org,
            )

        total_count = len(users)

        console.print(
            f"\n[green]✓[/green] Fetch complete for environment: [bold]{env}[/bold]"
        )
        console.print(
            f"  • Matching users found: [bold yellow]{total_count}[/bold yellow]"
        )
        console.print(f"    • Excluded Provider(s): {parsed_providers}")
        console.print(f"    • Excluded License(s): {parsed_licenses}")
        console.print(f"    • Excluded Role(s): {parsed_roles}\n")

        if export_csv:
            utils_ops.export_to_csv(users, export_csv)
            console.print(
                f"[green]✓[/green] Complete item ledger successfully exported to [bold]{export_csv}[/bold]\n"
            )

    except Exception as e:
        console.print(f"[red]Error fetching users:[/red] {e}")
        raise typer.Exit(code=1)


@audit_app.command("public-items")
def cmd_public_items(
    item_types: Optional[list[str]] = typer.Option(
        None,
        "--type",
        "-t",
        help="Specific item types to filter by. Can be passed multiple times.",
    ),
    env: str = typer.Option("agol", "--env", help="Environment key in .env."),
    export_csv: Optional[str] = typer.Option(
        None, "--export-csv", help="Filename to export results to CSV"
    ),
):
    """Audits environment for content shared publicly.

    Examples:
      esri-cli audit public-items
      esri-cli audit public-items --type "Web Map" --type "Feature Layer"
    """
    gis = _connect(env)
    try:
        pub_items = audit_ops.public_items(gis, item_types=item_types)
        total_count = len(pub_items)

        if total_count == 0:
            console.print(
                f"\n[green]✓[/green] Audit complete for environment: [bold]{env}[/bold]"
            )
            console.print(
                "[yellow]ℹ[/yellow] No public items were found matching your criteria.\n"
            )
            return

        type_counts = Counter(item.type for item in pub_items)
        owner_counts = Counter(item.owner for item in pub_items)

        type_table = Table(
            title="Public Items by Content Type", title_justify="left", show_footer=True
        )
        type_table.add_column("Item Type", footer="Total Unique Types")
        type_table.add_column(
            "Count", justify="right", footer=str(total_count), style="cyan"
        )

        # Sort items by highest count first
        for item_type, count in type_counts.most_common():
            type_table.add_row(item_type, str(count))

        # 5. Construct the Owner breakdown table
        owner_table = Table(
            title="Public Items by Content Owner",
            title_justify="left",
            show_footer=True,
        )
        owner_table.add_column("Owner Username", footer="Total Public Items")
        owner_table.add_column(
            "Count", justify="right", footer=str(total_count), style="yellow"
        )

        for owner, count in owner_counts.most_common():
            owner_table.add_row(owner, str(count))

        console.print(
            f"\n[green]✓[/green] Audit complete for environment: [bold]{env}[/bold]\n"
        )
        console.print(type_table)
        console.print("")  # Spacer
        console.print(owner_table)
        console.print("")  # Spacer

        if export_csv:
            utils_ops.export_to_csv(pub_items, export_csv)
            console.print(
                f"[green]✓[/green] Complete item ledger successfully exported to [bold]{export_csv}[/bold]\n"
            )

    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)


@audit_app.command("broken-deps")
def cmd_broken_dependencies(
    env: str = typer.Option("agol", "--env", help="Environment key in .env."),
    export_csv: Optional[str] = typer.Option(
        None, "--export-csv", help="Filename to export broken items results to CSV"
    ),
):
    """Audits environment for items with broken layers, deleted sources, or dead URLs.

    Examples:
      esri-cli audit broken-deps
      esri-cli audit broken-deps --export-csv broken_report.csv
    """
    gis = _connect(env)
    try:
        console.print(f"\nRunning diagnostics on environment: [bold]{env}[/bold]...")
        broken_items = audit_ops.broken_dependencies(gis)
        total_count = len(broken_items)

        if total_count == 0:
            console.print(
                f"[green]✓[/green] Audit complete for environment: [bold]{env}[/bold]"
            )
            console.print(
                "[green]✓[/green] Clean bill of health! No broken dependencies found.\n"
            )
            return

        type_counts = Counter(item.type for item in broken_items)
        owner_counts = Counter(item.owner for item in broken_items)

        type_table = Table(
            title="Broken Dependencies by Content Type",
            title_style="bold red",
            title_justify="left",
            show_footer=True,
        )
        type_table.add_column("Item Type", footer="Total Broken Items")
        type_table.add_column(
            "Count", justify="right", footer=str(total_count), style="red"
        )

        for item_type, count in type_counts.most_common():
            type_table.add_row(item_type, str(count))

        owner_table = Table(
            title="Broken Dependencies by Content Owner",
            title_style="bold magenta",
            title_justify="left",
            show_footer=True,
        )
        owner_table.add_column("Owner Username", footer="Total Affected Assets")
        owner_table.add_column(
            "Count", justify="right", footer=str(total_count), style="magenta"
        )

        for owner, count in owner_counts.most_common():
            owner_table.add_row(owner, str(count))

        console.print(
            f"Audit complete! Found [bold red]{total_count}[/bold red] broken items.\n"
        )
        console.print(type_table)
        console.print("")  # Spacer
        console.print(owner_table)
        console.print("")  # Spacer

        if export_csv:
            utils_ops.export_to_csv(broken_items, export_csv)
            console.print(
                f"[green]✓[/green] Broken dependency ledger successfully exported to [bold]{export_csv}[/bold]\n"
            )

    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)


@audit_app.command(name="sharing")
def sharing_audit(
    username: Optional[str] = typer.Option(
        None, "--username", "-u", help="Scope to a single user. Omit for org-wide."
    ),
    env: str = typer.Option("agol", "--env", help="Environment key in .env."),
    export_txt: Optional[str] = typer.Option(
        None, "--export-txt", help="Filename prefix for a .txt export to ~/Downloads."
    ),
):
    """Audit item sharing permissions (Public, Org, Private) across the org or for one user."""
    gis = _connect(env)
    results = audit_ops.sharing_audit(gis, username=username or "")

    if not results:
        console.print("[yellow]No items found or user not found.[/yellow]")
        raise typer.Exit(1)

    total = results["total_items"]
    public = results["public_count"]
    org = results["org_count"]
    private = results["private_count"]

    # avoids ZeroDivisionError if org is empty.
    def pct(n):
        return f"{round(n / total * 100, 1)}%" if total else "—"

    table = Table(
        title=f"Sharing Audit — {results['scope']}", show_lines=False, show_edge=True
    )
    table.add_column("Access Level", style="bold")
    table.add_column("Count", justify="right", style="cyan")
    table.add_column("% of Total", justify="right")

    # Color-code access levels so public items stand out immediately.
    table.add_row("[red]Public[/red]", str(public), pct(public))
    table.add_row("[yellow]Org[/yellow]", str(org), pct(org))
    table.add_row("[dim]Private[/dim]", str(private), pct(private))
    table.add_row("[bold]Total[/bold]", str(total), "100%", end_section=True)

    console.print(table)

    if export_txt:
        # Build a plain-text version of the same data — no markup needed here
        # since we're writing to a file, not a terminal.
        lines = [
            f"Scope:   {results['scope']}",
            "",
            f"{'Access Level':<15} {'Count':>8}  {'% of Total':>10}",
            "-" * 38,
            f"{'Public':<15} {public:>8}  {pct(public):>10}",
            f"{'Org':<15} {org:>8}  {pct(org):>10}",
            f"{'Private':<15} {private:>8}  {pct(private):>10}",
            "-" * 38,
            f"{'Total':<15} {total:>8}  {'100%':>10}",
        ]
        utils_ops.export_to_txt("\n".join(lines), export_txt)
        console.print(
            f"[green]✓[/green] Text report saved — prefix: [bold]{export_txt}[/bold]"
        )


@audit_app.command(name="roles")
def users_by_role(
    env: str = typer.Option("agol", "--env", help="Environment key in .env."),
    export_txt: Optional[str] = typer.Option(
        None, "--export-txt", help="Filename prefix for a .txt export to ~/Downloads."
    ),
):
    """Breakdown of users grouped by their assigned role."""
    gis = _connect(env)
    results = audit_ops.users_by_role(gis)

    if not results:
        console.print("[yellow]No role data returned.[/yellow]")
        return

    table = Table(title="Users by Role", show_lines=False)
    table.add_column("Role", style="cyan")
    table.add_column("Users", justify="right")

    total = sum(results.values())
    sorted_rows = sorted(results.items(), key=lambda x: x[1], reverse=True)

    for role, count in sorted(results.items(), key=lambda x: x[1], reverse=True):
        table.add_row(role or "none", str(count))

    table.add_section()
    table.add_row("[bold]Total[/bold]", f"[bold]{total}[/bold]")
    console.print(table)

    if export_txt:
        lines = [
            f"{'Role':<40} {'Users':>8}",
            "-" * 50,
        ]
        for role, count in sorted_rows:
            lines.append(f"{(role or 'none'):<40} {count:>8}")
        lines += ["-" * 50, f"{'Total':<40} {total:>8}"]
        utils_ops.export_to_txt("\n".join(lines), export_txt)
        console.print(
            f"[green]✓[/green] Text report saved — prefix: [bold]{export_txt}[/bold]"
        )


@audit_app.command(name="licenses")
def users_by_license_type(
    env: str = typer.Option("agol", "--env", help="Environment key in .env."),
    export_txt: Optional[str] = typer.Option(
        None, "--export-txt", help="Filename prefix for a .txt export to ~/Downloads."
    ),
):
    """Breakdown of users grouped by license type."""
    gis = _connect(env)
    results = audit_ops.users_by_license_type(gis)

    if not results:
        console.print("[yellow]No license data returned.[/yellow]")
        return

    table = Table(title="Users by License Type", show_lines=False)
    table.add_column("License Type ID", style="cyan")
    table.add_column("Users", justify="right")

    total = sum(results.values())
    sorted_rows = sorted(results.items(), key=lambda x: x[1], reverse=True)

    for license_id, count in sorted(results.items(), key=lambda x: x[1], reverse=True):
        table.add_row(license_id or "none", str(count))

    table.add_section()
    table.add_row("[bold]Total[/bold]", f"[bold]{total}[/bold]")
    console.print(table)

    if export_txt:
        lines = [
            f"{'License Type ID':<35} {'Users':>8}",
            "-" * 45,
        ]
        for license_id, count in sorted_rows:
            lines.append(f"{(license_id or 'none'):<35} {count:>8}")
        lines += ["-" * 45, f"{'Total':<35} {total:>8}"]
        utils_ops.export_to_txt("\n".join(lines), export_txt)
        console.print(
            f"[green]✓[/green] Text report saved — prefix: [bold]{export_txt}[/bold]"
        )


@audit_app.command(name="license-usage")
def licenses_threshold(
    env: str = typer.Option("agol", "--env", help="Environment key in .env."),
    export_txt: Optional[str] = typer.Option(
        None, "--export-txt", help="Filename prefix for a .txt export to ~/Downloads."
    ),
):
    """Check remaining license pool capacity against current usage."""
    gis = _connect(env)
    results = audit_ops.license_threshold(gis)

    summary = results.pop("summary", {})

    table = Table(title="License Pool Usage", show_lines=True)
    table.add_column("License ID", style="dim", no_wrap=True)
    table.add_column("Name", style="cyan")
    table.add_column("Assigned", justify="right")
    table.add_column("Purchased", justify="right")
    table.add_column("Available", justify="right")
    table.add_column("Available %", justify="right")

    sorted_rows = sorted(results.items())

    for license_id, info in sorted(results.items()):
        available = info["available"]
        available_pct = info["available_pct"]

        avail_str = str(available)
        if isinstance(available_pct, str) and available_pct != "N/A":
            try:
                pct_val = float(available_pct.strip("%"))
                if pct_val < 10:
                    avail_str = f"[red]{available}[/red]"
                elif pct_val < 25:
                    avail_str = f"[yellow]{available}[/yellow]"
                else:
                    avail_str = f"[green]{available}[/green]"
            except ValueError:
                pass

        table.add_row(
            license_id,
            info["name"] or "—",
            str(info["assigned"]),
            str(info["total_purchased"]),
            avail_str,
            available_pct,
        )

    console.print(table)

    # Summary panel underneath the table.
    if summary:
        lines = [
            f"[bold]Total Assigned:[/bold]   {summary.get('total_assigned', '—')}",
            f"[bold]Total Purchased:[/bold]  {summary.get('total_purchased_limit', '—')}",
            f"[bold]Total Available:[/bold]  {summary.get('total_available_seats', '—')}",
        ]
        console.print(Panel("\n".join(lines), title="Org-Wide Summary", expand=False))

    if export_txt:
        # Column widths chosen to fit typical ArcGIS license ID lengths.
        w = {
            "id": 28,
            "name": 30,
            "assigned": 10,
            "purchased": 10,
            "available": 10,
            "pct": 12,
        }
        header = (
            f"{'License ID':<{w['id']}} "
            f"{'Name':<{w['name']}} "
            f"{'Assigned':>{w['assigned']}} "
            f"{'Purchased':>{w['purchased']}} "
            f"{'Available':>{w['available']}} "
            f"{'Avail %':>{w['pct']}}"
        )
        sep = "-" * len(header)
        lines = [header, sep]

        for license_id, info in sorted_rows:
            lines.append(
                f"{license_id:<{w['id']}} "
                f"{(info['name'] or '—'):<{w['name']}} "
                f"{info['assigned']:>{w['assigned']}} "
                f"{info['total_purchased']:>{w['purchased']}} "
                f"{info['available']:>{w['available']}} "
                f"{info['available_pct']:>{w['pct']}}"
            )

        if summary:
            lines += [
                sep,
                f"Total Assigned:  {summary.get('total_assigned', '—')}",
                f"Total Purchased: {summary.get('total_purchased_limit', '—')}",
                f"Total Available: {summary.get('total_available_seats', '—')}",
            ]

        utils_ops.export_to_txt("\n".join(lines), export_txt)
        console.print(
            f"[green]✓[/green] Text report saved — prefix: [bold]{export_txt}[/bold]"
        )


@audit_app.command(name="provider")
def user_provider_breakdown(
    env: str = typer.Option("agol", "--env", help="Environment key in .env."),
    export_txt: Optional[str] = typer.Option(
        None, "--export-txt", help="Filename prefix for a .txt export to ~/Downloads."
    ),
):
    """Breakdown of users by authentication provider (ArcGIS vs enterprise/SAML)."""
    gis = _connect(env)
    results = audit_ops.user_provider_breakdown(gis)

    if not results:
        console.print("[yellow]No provider data returned.[/yellow]")
        return

    table = Table(title="Users by Auth Provider", show_lines=False)
    table.add_column("Provider", style="cyan")
    table.add_column("Users", justify="right")

    total = sum(results.values())
    sorted_rows = sorted(results.items(), key=lambda x: x[1], reverse=True)

    for provider, count in sorted(results.items(), key=lambda x: x[1], reverse=True):
        table.add_row(provider or "unknown", str(count))

    table.add_section()
    table.add_row("[bold]Total[/bold]", f"[bold]{total}[/bold]")
    console.print(table)

    if export_txt:
        lines = [
            f"{'Provider':<30} {'Users':>8}",
            "-" * 40,
        ]
        for provider, count in sorted_rows:
            lines.append(f"{(provider or 'unknown'):<30} {count:>8}")
        lines += ["-" * 40, f"{'Total':<30} {total:>8}"]
        utils_ops.export_to_txt("\n".join(lines), export_txt)
        console.print(
            f"[green]✓[/green] Text report saved — prefix: [bold]{export_txt}[/bold]"
        )


@audit_app.command(name="disabled")
def disabled_users(
    env: str = typer.Option("agol", "--env", help="Environment key in .env."),
    export_csv: Optional[str] = typer.Option(
        None, "--export-csv", help="Path to export the output as a CSV file."
    ),
):
    """List all disabled user accounts in the organization."""
    gis = _connect(env)
    results = audit_ops.disabled_users(gis)

    if export_csv:
        utils_ops.export_to_csv(results, export_csv)
        console.print(f"[green]✓[/green] Exported to [bold]{export_csv}[/bold]")
        return

    if not results:
        console.print("[green]No disabled accounts found.[/green]")
        return

    table = Table(title=f"Disabled Accounts ({len(results)})", show_lines=True)
    table.add_column("Username", style="cyan", no_wrap=True)
    table.add_column("Full Name")
    table.add_column("Email")
    table.add_column("License Type")
    table.add_column("Created")
    table.add_column("Last Login")
    table.add_column("Days Since Login", justify="right")
    table.add_column("Provider")

    for u in results:
        days = (
            str(u.daysSinceLastLogin) if u.daysSinceLastLogin is not None else "Never"
        )
        table.add_row(
            u.username,
            u.fullName,
            u.email,
            u.userLicenseType,
            u.created,
            u.lastLogin or "Never",
            days,
            u.provider,
        )

    console.print(table)


@audit_app.command(name="new-items")
def new_items(
    days: int = typer.Option(7, help="Lookback window in days."),
    env: str = typer.Option("agol", "--env", help="Environment key in .env."),
    export_csv: Optional[str] = typer.Option(
        None, "--export-csv", help="Optional CSV destination file path."
    ),
):
    """List content items created within the last N days."""
    gis = _connect(env)
    results = audit_ops.new_items(gis, days=days)

    if export_csv:
        utils_ops.export_to_csv(results, export_csv)
        console.print(f"[green]✓[/green] Exported to [bold]{export_csv}[/bold]")
        return

    if not results:
        console.print(f"[yellow]No new items found in the last {days} days.[/yellow]")
        return

    table = Table(
        title=f"New Items — Last {days} Days ({len(results)})", show_lines=True
    )
    table.add_column("ID", style="dim", no_wrap=True)
    table.add_column("Title", style="cyan")
    table.add_column("Type")
    table.add_column("Owner")
    table.add_column("Access")
    table.add_column("Created")

    for item in results:
        # Color the access column so public items catch the eye.
        access_str = item.access or "—"
        if access_str == "public":
            access_str = f"[red]{access_str}[/red]"
        elif access_str == "org":
            access_str = f"[yellow]{access_str}[/yellow]"

        table.add_row(
            item.id,
            item.title,
            item.type,
            item.owner,
            access_str,
            item.created or "—",
        )

    console.print(table)


@audit_app.command(name="new-users")
def new_users(
    days: int = typer.Option(7, help="Lookback window in days."),
    env: str = typer.Option("agol", "--env", help="Environment key in .env."),
    export_csv: Optional[str] = typer.Option(
        None, "--export-csv", help="Optional CSV destination file path."
    ),
):
    """List user accounts provisioned within the last N days."""
    gis = _connect(env)
    results = audit_ops.new_users(gis, days=days)

    if export_csv:
        utils_ops.export_to_csv(results, export_csv)
        console.print(f"[green]✓[/green] Exported to [bold]{export_csv}[/bold]")
        return

    if not results:
        console.print(f"[yellow]No new users found in the last {days} days.[/yellow]")
        return

    table = Table(
        title=f"New Users — Last {days} Days ({len(results)})", show_lines=True
    )
    table.add_column("Username", style="cyan", no_wrap=True)
    table.add_column("Full Name")
    table.add_column("Email")
    table.add_column("Role")
    table.add_column("License Type")
    table.add_column("Provider")
    table.add_column("Created")

    for u in results:
        table.add_row(
            u.username,
            u.fullName,
            u.email,
            u.role,
            u.userLicenseType,
            u.provider,
            u.created or "—",
        )

    console.print(table)


@audit_app.command(name="new-groups")
def new_groups(
    days: int = typer.Option(7, help="Lookback window in days."),
    env: str = typer.Option("agol", "--env", help="Environment key in .env."),
    export_csv: Optional[str] = typer.Option(
        None, "--export-csv", help="Optional CSV destination file path."
    ),
):
    """List groups created within the last N days."""
    gis = _connect(env)
    results = audit_ops.new_groups(gis, days=days)

    if export_csv:
        utils_ops.export_to_csv(results, export_csv)
        console.print(f"[green]✓[/green] Exported to [bold]{export_csv}[/bold]")
        return

    if not results:
        console.print(f"[yellow]No new groups found in the last {days} days.[/yellow]")
        return

    table = Table(
        title=f"New Groups — Last {days} Days ({len(results)})", show_lines=True
    )
    table.add_column("ID", style="dim", no_wrap=True)
    table.add_column("Title", style="cyan")
    table.add_column("Owner")
    table.add_column("Access")
    table.add_column("Members", justify="right")
    table.add_column("Items", justify="right")
    table.add_column("Protected")
    table.add_column("Created")

    for g in results:
        table.add_row(
            g.id,
            g.title,
            g.owner,
            g.access,
            str(g.member_count),
            str(g.item_count),
            "Yes" if g.protected else "No",
            g.created or "—",
        )

    console.print(table)


@audit_app.command(name="whats-new")
def new_assets_report(
    days: int = typer.Option(7, help="Unified lookback window in days."),
    env: str = typer.Option("agol", "--env", help="Environment key in .env."),
    export_csv: bool = typer.Option(
        False, "--export-csv", help="Export each section to its own CSV in ~/Downloads."
    ),
):
    """Combined 'What's New' dashboard — users, groups, and content in one view.

    Use --export-csv to dump all three sections to separate CSVs with every
    field included (not just the columns shown on screen).

    Examples:
        esri-cli audit whats-new
        esri-cli audit whats-new --days 30 --export-csv
    """
    gis = _connect(env)

    with console.status(f"Pulling activity for the last [bold]{days}[/bold] days..."):
        report = audit_ops.new_assets_report(gis, days=days)

    users = report.get("users", [])
    groups = report.get("groups", [])
    items = report.get("items", [])

    # ── Summary panel at the top ──────────────────────────────────────────
    summary_lines = [
        f"[bold]Period:[/bold]        Last {days} days",
        f"[bold]New Users:[/bold]     {len(users)}",
        f"[bold]New Groups:[/bold]    {len(groups)}",
        f"[bold]New Items:[/bold]     {len(items)}",
    ]
    console.print(
        Panel(
            "\n".join(summary_lines),
            title="[bold cyan]What's New[/bold cyan]",
            expand=False,
        )
    )
    print()
    # ── Users mini-table ──────────────────────────────────────────────────
    if users:
        u_table = Table(
            title=f"New Users ({len(users)})",
            show_lines=False,
            box=None,
            pad_edge=False,
        )
        u_table.add_column("Username", style="cyan", no_wrap=True)
        u_table.add_column("Full Name")
        u_table.add_column("Role")
        u_table.add_column("License")
        u_table.add_column("Created")
        for u in users:
            u_table.add_row(
                u.username, u.fullName, u.role, u.userLicenseType, u.created or "—"
            )
        console.print(u_table)
    else:
        console.print("[dim]No new users.[/dim]")
    print()
    # ── Groups mini-table ─────────────────────────────────────────────────
    if groups:
        g_table = Table(
            title=f"New Groups ({len(groups)})",
            show_lines=False,
            box=None,
            pad_edge=False,
        )
        g_table.add_column("Title", style="cyan")
        g_table.add_column("Owner")
        g_table.add_column("Access")
        g_table.add_column("Created")
        for g in groups:
            g_table.add_row(g.title, g.owner, g.access, g.created or "—")
        console.print(g_table)
    else:
        console.print("[dim]No new groups.[/dim]")

    # ── Items mini-table ──────────────────────────────────────────────────
    if items:
        i_table = Table(
            title=f"New Items ({len(items)})",
            show_lines=False,
            box=None,
            pad_edge=False,
        )
        i_table.add_column("Title", style="cyan")
        i_table.add_column("Type")
        i_table.add_column("Owner")
        i_table.add_column("Access")
        i_table.add_column("Created")
        for item in items:
            access_str = item.access or "—"
            if access_str == "public":
                access_str = f"[red]{access_str}[/red]"
            elif access_str == "org":
                access_str = f"[yellow]{access_str}[/yellow]"
            i_table.add_row(
                item.title, item.type, item.owner, access_str, item.created or "—"
            )
        console.print(i_table)
    else:
        console.print("[dim]No new items.[/dim]")
    print()

    if export_csv:
        utils_ops.export_whats_new_csv(report)
        console.print(
            "[green]✓[/green] Exported to [bold]~/Downloads[/bold] — new_users, new_groups, new_items CSVs."
        )


# ===========================================================================
# CONTENT commands
# ===========================================================================


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------
@content_app.command("find")
def cmd_find_item(
    item_id: Optional[str] = typer.Option(
        None, "--id", "-i", help="Item ID (exact match)."
    ),
    title: Optional[str] = typer.Option(None, "--title", "-t", help="Item title."),
    owner: Optional[str] = typer.Option(None, "--owner", "-o", help="Owner username."),
    env: str = typer.Option("agol", "--env", help="Environment key in .env."),
    export_csv: Optional[str] = typer.Option(
        None, "--export-csv", help="Filename to export results to CSV"
    ),
):
    """Search for content items by ID, title, and/or owner.

    All filters are AND-ed. At least one is required.

    Examples:
        esri-cli content find --title "Flood Zones"
        esri-cli content find --owner jdoe --title "Survey"
        esri-cli content find --id abc123def456abc123def456abc12345
    """
    if not any([item_id, title, owner]):
        console.print(
            "[yellow]Provide at least one of --id, --title, --owner.[/yellow]"
        )
        raise typer.Exit(1)

    gis = _connect(env)
    results = content_ops.find_item(gis, item_id=item_id, title=title, owner=owner)

    if not results:
        console.print("[yellow]No items found matching those criteria.[/yellow]")
        return

    table = Table(title=f"Items ({len(results)} found)", show_lines=True)
    table.add_column("ID", style="dim", no_wrap=True)
    table.add_column("Title", style="cyan")
    table.add_column("Type")
    table.add_column("Owner")
    table.add_column("Access")
    table.add_column("Modified")

    for item in results:
        access_str = item.access or "—"
        if access_str == "public":
            access_str = f"[red]{access_str}[/red]"
        elif access_str == "org":
            access_str = f"[yellow]{access_str}[/yellow]"

        table.add_row(
            item.id,
            item.title,
            item.type,
            item.owner,
            access_str,
            item.modified or "—",
        )

    console.print(table)

    if export_csv:
        utils_ops.export_to_csv(results, export_csv)
        typer.echo(f"Data exported to {export_csv}")


@content_app.command("details")
def cmd_item_details(
    item_id: str = typer.Argument(..., help="Item ID to look up."),
    env: str = typer.Option("agol", "--env", help="Environment key in .env."),
):
    """Show full details for a single item.

    Example:
        esri-cli content details abc123def456abc123def456abc12345
    """
    gis = _connect(env)

    try:
        item = content_ops.item_details(gis, item_id)
    except ValueError as e:
        console.print(f"[red]Not found:[/red] {e}")
        raise typer.Exit(1)

    access_str = item.access or "—"
    if access_str == "public":
        access_str = f"[red]{access_str}[/red]"
    elif access_str == "org":
        access_str = f"[yellow]{access_str}[/yellow]"

    lines = [
        f"[bold]ID:[/bold]          {item.id}",
        f"[bold]Title:[/bold]       {item.title}",
        f"[bold]Type:[/bold]        {item.type}",
        f"[bold]Owner:[/bold]       {item.owner}",
        f"[bold]Access:[/bold]      {access_str}",
        f"[bold]Created:[/bold]     {item.created or '—'}",
        f"[bold]Modified:[/bold]    {item.modified or '—'}",
        f"[bold]Tags:[/bold]        {', '.join(item.tags) if item.tags else '—'}",
        f"[bold]Description:[/bold] {item.description or '—'}",
        f"[bold]URL:[/bold]         {item.url or '—'}",
    ]
    console.print(
        Panel("\n".join(lines), title=f"[cyan]{item.title}[/cyan]", expand=False)
    )


@content_app.command("ownership-report")
def cmd_content_ownership_report(
    top_n: int = typer.Option(
        25,
        "--top",
        "-n",
        help="Number of users to show, sorted by item count descending.",
    ),
    exclude_users: Optional[str] = typer.Option(
        None,
        "--exclude",
        "-x",
        help="Comma-separated usernames to exclude. esri_ accounts are always excluded.",
    ),
    item_types: Optional[str] = typer.Option(
        None,
        "--type",
        "-t",
        help="Comma-separated item types to filter by. e.g. 'Web Map,Feature Service'",
    ),
    owner: Optional[str] = typer.Option(
        None, "--owner", "-o", help="Scope the entire report to a single username."
    ),
    export_csv: Optional[str] = typer.Option(
        None,
        "--export-csv",
        help="Filename prefix to export results to CSV in ~/Downloads.",
    ),
    env: str = typer.Option("agol", "--env", help="Environment key in .env."),
):
    """Show content ownership ranked by item count, plus a breakdown by item type.

    When --owner is provided, the ownership table is skipped and you get a
    per-type breakdown scoped to just that user — useful for auditing a single
    account before offboarding or reassignment.

    esri_ system accounts are always excluded from the ownership table.

    Examples:
        esri-cli content ownership-report
        esri-cli content ownership-report --top 10
        esri-cli content ownership-report --type "Web Map,Feature Service"
        esri-cli content ownership-report --owner jdoe
        esri-cli content ownership-report --owner jdoe --type "Web Map"
        esri-cli content ownership-report --exclude "svc_account" --export-csv owners
    """
    gis = _connect(env)

    exclude_list = (
        [u.strip() for u in exclude_users.split(",")] if exclude_users else None
    )
    type_list = [t.strip() for t in item_types.split(",")] if item_types else None

    # ── Fetch raw items once — both tables are built from the same pull ───
    # Build query up front so we can reuse the result for both tables.
    if type_list:
        type_clauses = " OR ".join(f'type:"{t}"' for t in type_list)
        query = f"({type_clauses})"
    else:
        query = "*"

    if owner:
        query = f"{query} AND owner:{owner}" if query != "*" else f"owner:{owner}"

    with console.status("Fetching items..."):
        try:
            all_items = gis.content.search(query=query, max_items=-1, outside_org=False)
        except Exception as e:
            console.print(f"[red bold]Error:[/red bold] {e}")
            raise typer.Exit(1)

    if not all_items:
        console.print("[yellow]No items found matching those criteria.[/yellow]")
        return

    # ── Active filter label (shown as table caption) ──────────────────────
    filter_parts = []
    if owner:
        filter_parts.append(f"owner: {owner}")
    if type_list:
        filter_parts.append(f"type: {', '.join(type_list)}")
    if exclude_list:
        filter_parts.append(f"excluding: {', '.join(exclude_list)}")
    if not owner:
        filter_parts.append("esri_ always excluded")
    filter_label = (
        "  |  ".join(filter_parts) if filter_parts else "all items, esri_ excluded"
    )

    # ── Exclusion helper ──────────────────────────────────────────────────
    excluded = {u.lower() for u in (exclude_list or [])}

    def _should_exclude(o: str) -> bool:
        o = (o or "").lower()
        return o.startswith("esri_") or o in excluded

    # ── Table 1: Ownership (skipped when --owner is set) ──────────────────
    if not owner:
        counts: Counter = Counter(
            item_owner
            for item in all_items
            if not _should_exclude(
                item_owner := (getattr(item, "owner", None) or "unknown")
            )
        )

        top_owners = counts.most_common(top_n if top_n > 0 else None)
        ownership_rows = [
            {"rank": i + 1, "username": u, "item_count": c}
            for i, (u, c) in enumerate(top_owners)
        ]

        owner_table = Table(
            title=f"Content Ownership — Top {top_n}",
            caption=filter_label,
            show_lines=False,
        )
        owner_table.add_column("Rank", justify="right", style="dim")
        owner_table.add_column("Username", style="cyan", no_wrap=True)
        owner_table.add_column("Item Count", justify="right")

        for row in ownership_rows:
            owner_table.add_row(
                str(row["rank"]), row["username"], str(row["item_count"])
            )

        total_shown = sum(r["item_count"] for r in ownership_rows)
        owner_table.add_section()
        owner_table.add_row(
            "",
            f"[bold]Total (top {len(ownership_rows)})[/bold]",
            f"[bold]{total_shown}[/bold]",
        )

        console.print(owner_table)
        console.print()

    # ── Table 2: Breakdown by item type ───────────────────────────────────
    # Filter out excluded owners before counting types, consistent with above.
    type_counts: Counter = Counter(
        getattr(item, "type", None) or "Unknown"
        for item in all_items
        if owner or not _should_exclude(getattr(item, "owner", None) or "")
    )

    type_title = f"Item Type Breakdown — {owner}" if owner else "Item Type Breakdown"
    type_table = Table(title=type_title, caption=filter_label, show_lines=False)
    type_table.add_column("Item Type", style="cyan")
    type_table.add_column("Count", justify="right")
    type_table.add_column("% of Total", justify="right")

    total_items = sum(type_counts.values())

    for item_type, count in type_counts.most_common():
        pct = f"{round(count / total_items * 100, 1)}%" if total_items else "—"
        type_table.add_row(item_type, str(count), pct)

    type_table.add_section()
    type_table.add_row(
        "[bold]Total[/bold]", f"[bold]{total_items}[/bold]", "[bold]100%[/bold]"
    )

    console.print(type_table)

    # ── CSV export ────────────────────────────────────────────────────────
    if export_csv:
        from pathlib import Path
        from datetime import datetime
        import csv

        downloads = Path.home() / "Downloads"
        timestamp = datetime.now().strftime("%Y%m%d")

        # Export ownership table (when not scoped to a single owner).
        if not owner:
            owners_path = downloads / f"{export_csv}_by_owner_{timestamp}.csv"
            with open(owners_path, mode="w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(
                    f, fieldnames=["rank", "username", "item_count"]
                )
                writer.writeheader()
                writer.writerows(ownership_rows)
            console.print(
                f"[green]✓[/green] Owners exported to [bold]{owners_path}[/bold]"
            )

        # Always export the type breakdown.
        types_path = downloads / f"{export_csv}_by_type_{timestamp}.csv"
        with open(types_path, mode="w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["item_type", "count"])
            writer.writeheader()
            writer.writerows(
                {"item_type": t, "count": c} for t, c in type_counts.most_common()
            )
        console.print(f"[green]✓[/green] Types exported to [bold]{types_path}[/bold]")


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------


@content_app.command("update-metadata")
def cmd_update_metadata(
    item_id: str = typer.Argument(..., help="Item ID to update."),
    title: Optional[str] = typer.Option(None, "--title", "-t", help="New title."),
    description: Optional[str] = typer.Option(
        None, "--description", "-d", help="New description."
    ),
    snippet: Optional[str] = typer.Option(
        None, "--snippet", "-s", help="New short summary (shown in search results)."
    ),
    tags: Optional[str] = typer.Option(
        None,
        "--tags",
        help="Replacement tag list, comma-separated. Overwrites existing tags.",
    ),
    env: str = typer.Option("agol", "--env", help="Environment key in .env."),
):
    """Update an item's title, description, snippet, and/or tags.

    Tags are a full replacement — pass the complete desired list, not just
    the ones you want to add.

    Examples:
        esri-cli content update-metadata <id> --title "New Title"
        esri-cli content update-metadata <id> --tags "gis,flood,2026" --snippet "Updated flood zones"
    """
    if not any([title, description, snippet, tags]):
        console.print(
            "[yellow]Provide at least one of --title, --description, --snippet, --tags.[/yellow]"
        )
        raise typer.Exit(1)

    gis = _connect(env)
    tag_list = [t.strip() for t in tags.split(",")] if tags else None

    try:
        content_ops.update_metadata(
            gis,
            item=item_id,
            title=title,
            description=description,
            snippet=snippet,
            tags=tag_list,
        )
        console.print(
            f"[green]✓[/green] Metadata updated for item [dim]{item_id}[/dim]."
        )
    except ValueError as e:
        console.print(f"[red bold]Error:[/red bold] {e}")
        raise typer.Exit(1)


@content_app.command("update-thumbnail")
def cmd_update_thumbnail(
    item_id: str = typer.Argument(..., help="Item ID to update."),
    thumbnail_path: str = typer.Argument(
        ..., help="Local path to the image file (JPEG or PNG, max 1MB)."
    ),
    env: str = typer.Option("agol", "--env", help="Environment key in .env."),
):
    """Set or replace the thumbnail for an item.

    Example:
        esri-cli content update-thumbnail abc123 C:/images/thumb.png
    """
    gis = _connect(env)

    try:
        content_ops.update_thumbnail(gis, item=item_id, thumbnail_path=thumbnail_path)
        console.print(
            f"[green]✓[/green] Thumbnail updated for item [dim]{item_id}[/dim]."
        )
    except FileNotFoundError as e:
        console.print(f"[red bold]File not found:[/red bold] {e}")
        raise typer.Exit(1)
    except ValueError as e:
        console.print(f"[red bold]Error:[/red bold] {e}")
        raise typer.Exit(1)


@content_app.command("delete")
def cmd_delete_item(
    item_id: str = typer.Argument(..., help="Item ID to delete."),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Check the item is resolvable without deleting."
    ),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt."),
    env: str = typer.Option("agol", "--env", help="Environment key in .env."),
):
    """Permanently delete an item. Cannot be undone.

    Use --dry-run first to confirm the item exists before committing.
    Check dependencies with 'esri-cli content dependencies <id>' if you're
    not sure what else might be using this item.

    Examples:
        esri-cli content delete abc123 --dry-run
        esri-cli content delete abc123 --yes
    """
    gis = _connect(env)

    if dry_run:
        try:
            content_ops.delete_item(gis, item_id, dry_run=True)
            console.print(
                f"[green]✓ Dry run passed.[/green] Item '{item_id}' is resolvable and can be deleted."
            )
        except ValueError as e:
            console.print(f"[yellow]Dry run failed:[/yellow] {e}")
        return

    if not yes:
        confirmed = typer.confirm(
            f"Really delete item '{item_id}'? This cannot be undone."
        )
        if not confirmed:
            console.print("[dim]Aborted.[/dim]")
            raise typer.Exit(0)

    try:
        content_ops.delete_item(gis, item_id)
        console.print(f"[green]✓[/green] Deleted item [dim]{item_id}[/dim].")
    except ValueError as e:
        console.print(f"[red bold]Error:[/red bold] {e}")
        raise typer.Exit(1)


@content_app.command("move")
def cmd_move_item(
    item_id: str = typer.Argument(..., help="Item ID to move."),
    to_folder: str = typer.Argument(
        ..., help="Destination folder name. Use '/' for root."
    ),
    owner: Optional[str] = typer.Option(
        None,
        "--owner",
        "-o",
        help="Item owner username (required when moving another user's content as admin).",
    ),
    env: str = typer.Option("agol", "--env", help="Environment key in .env."),
):
    """Move an item to a different folder.

    The source folder is resolved automatically — you only need to specify
    the destination. Pass --owner when moving content that belongs to another
    user (requires admin privileges).

    Examples:
        esri-cli content move abc123 "Flood Analysis"
        esri-cli content move abc123 / --owner jdoe
    """
    gis = _connect(env)

    try:
        content_ops.move_item(gis, item=item_id, to_folder=to_folder, owner=owner)
        console.print(
            f"[green]✓[/green] Item [dim]{item_id}[/dim] moved to folder [bold]{to_folder}[/bold]."
        )
    except ValueError as e:
        console.print(f"[red bold]Error:[/red bold] {e}")
        raise typer.Exit(1)


@content_app.command("copy")
def cmd_copy_item(
    item_id: str = typer.Argument(..., help="Item ID to copy."),
    title: Optional[str] = typer.Option(
        None,
        "--title",
        "-t",
        help="Title for the copy. Defaults to 'Copy of <original>'.",
    ),
    folder: Optional[str] = typer.Option(
        None, "--folder", "-f", help="Destination folder for the copy."
    ),
    owner: Optional[str] = typer.Option(
        None,
        "--owner",
        "-o",
        help="Place the copy under a different owner (requires admin).",
    ),
    env: str = typer.Option("agol", "--env", help="Environment key in .env."),
):
    """Copy an item, optionally with a new title, into a specific folder or under a different owner.

    Examples:
        esri-cli content copy abc123
        esri-cli content copy abc123 --title "Flood Zones v2" --folder "Archive"
        esri-cli content copy abc123 --owner jdoe --folder "Shared Work"
    """
    gis = _connect(env)

    try:
        new_item = content_ops.copy_item(
            gis, item=item_id, title=title, folder=folder, owner=owner
        )
        console.print(
            f"[green]✓[/green] Copied to [cyan]{new_item.title}[/cyan] (ID: [dim]{new_item.id}[/dim])."
        )
    except ValueError as e:
        console.print(f"[red bold]Error:[/red bold] {e}")
        raise typer.Exit(1)


@content_app.command("create-folder")
def cmd_create_folder(
    folder_name: str = typer.Argument(..., help="Name of the folder to create."),
    owner: Optional[str] = typer.Option(
        None,
        "--owner",
        "-o",
        help="Create the folder under this user (defaults to current user).",
    ),
    env: str = typer.Option("agol", "--env", help="Environment key in .env."),
):
    """Create a new content folder.

    If the folder already exists, the existing folder info is returned without
    error — safe to call idempotently.

    Examples:
        esri-cli content create-folder "Flood Analysis"
        esri-cli content create-folder "Shared Work" --owner jdoe
    """
    gis = _connect(env)

    try:
        result = content_ops.create_folder(gis, folder_name=folder_name, owner=owner)
        folder_id = result.get("id", "—")
        console.print(
            f"[green]✓[/green] Folder [cyan]{folder_name}[/cyan] ready (ID: [dim]{folder_id}[/dim])."
        )
    except ValueError as e:
        console.print(f"[red bold]Error:[/red bold] {e}")
        raise typer.Exit(1)


@content_app.command("delete-folder")
def cmd_delete_folder(
    folder_name: str = typer.Argument(..., help="Name of the folder to delete."),
    owner: Optional[str] = typer.Option(
        None, "--owner", "-o", help="Folder owner (defaults to current user)."
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Show what would be deleted without actually deleting."
    ),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt."),
    env: str = typer.Option("agol", "--env", help="Environment key in .env."),
):
    """Delete a folder and all its contents. Cannot be undone.

    Use --dry-run first — it reports exactly how many items are inside the
    folder so you know what you're about to lose.

    Examples:
        esri-cli content delete-folder "Old Projects" --dry-run
        esri-cli content delete-folder "Old Projects" --yes
        esri-cli content delete-folder "Old Projects" --owner jdoe --yes
    """
    gis = _connect(env)

    if dry_run:
        try:
            content_ops.delete_folder(
                gis, folder_name=folder_name, owner=owner, dry_run=True
            )
            console.print(
                f"[green]✓ Dry run complete.[/green] Check logs for item count inside '{folder_name}'."
            )
        except ValueError as e:
            console.print(f"[yellow]Dry run failed:[/yellow] {e}")
        return

    if not yes:
        confirmed = typer.confirm(
            f"Really delete folder '{folder_name}' and all its contents? This cannot be undone."
        )
        if not confirmed:
            console.print("[dim]Aborted.[/dim]")
            raise typer.Exit(0)

    try:
        content_ops.delete_folder(gis, folder_name=folder_name, owner=owner)
        console.print(
            f"[green]✓[/green] Deleted folder [bold]{folder_name}[/bold] and its contents."
        )
    except ValueError as e:
        console.print(f"[red bold]Error:[/red bold] {e}")
        raise typer.Exit(1)


# ---------------------------------------------------------------------------
# Sharing and Access
# ---------------------------------------------------------------------------


@content_app.command("set-owner")
def cmd_update_item_owner(
    item_id: str = typer.Argument(..., help="Item ID to reassign."),
    new_owner: str = typer.Argument(..., help="Username of the new owner."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt."),
    env: str = typer.Option("agol", "--env", help="Environment key in .env."),
):
    """Reassign ownership of an item to a different user.

    Example:
        esri-cli content set-owner abc123 jdoe
    """
    gis = _connect(env)

    if not yes:
        confirmed = typer.confirm(f"Reassign item '{item_id}' to '{new_owner}'?")
        if not confirmed:
            console.print("[dim]Aborted.[/dim]")
            raise typer.Exit(0)

    try:
        content_ops.update_item_owner(gis, item=item_id, new_owner=new_owner)
        console.print(
            f"[green]✓[/green] Item [dim]{item_id}[/dim] ownership transferred to [cyan]{new_owner}[/cyan]."
        )
    except ValueError as e:
        console.print(f"[red bold]Error:[/red bold] {e}")
        raise typer.Exit(1)


@content_app.command("share")
def cmd_share_item(
    item_id: str = typer.Argument(..., help="Item ID to share."),
    access: Optional[str] = typer.Option(
        None, "--access", "-a", help="Access level: private, org, or public."
    ),
    groups: Optional[str] = typer.Option(
        None,
        "--groups",
        "-g",
        help="Comma-separated list of group IDs or titles to share with.",
    ),
    env: str = typer.Option("agol", "--env", help="Environment key in .env."),
):
    """Share an item with groups and/or change its access level.

    --access and --groups can be used together or independently.

    Examples:
        esri-cli content share abc123 --access org
        esri-cli content share abc123 --groups "GIS Team,abc456def789"
        esri-cli content share abc123 --access public --groups "abc456def789"
    """
    if not any([access, groups]):
        console.print("[yellow]Provide at least one of --access or --groups.[/yellow]")
        raise typer.Exit(1)

    gis = _connect(env)
    group_list = [g.strip() for g in groups.split(",")] if groups else None

    try:
        content_ops.share_item(gis, item=item_id, groups=group_list, access=access)
        parts = []
        if access:
            parts.append(f"access → [bold]{access}[/bold]")
        if group_list:
            parts.append(f"groups → [bold]{', '.join(group_list)}[/bold]")
        console.print(
            f"[green]✓[/green] Item [dim]{item_id}[/dim] shared: {', '.join(parts)}."
        )
    except ValueError as e:
        console.print(f"[red bold]Error:[/red bold] {e}")
        raise typer.Exit(1)


@content_app.command("unshare")
def cmd_unshare_item(
    item_id: str = typer.Argument(..., help="Item ID to unshare."),
    groups: Optional[str] = typer.Option(
        None,
        "--groups",
        "-g",
        help="Comma-separated group IDs or titles to remove sharing from.",
    ),
    unshare_from_org: bool = typer.Option(
        False,
        "--from-org",
        help="Also remove org/public sharing (sets item back to private).",
    ),
    env: str = typer.Option("agol", "--env", help="Environment key in .env."),
):
    """Remove sharing from an item — specific groups, org/public, or both.

    Examples:
        esri-cli content unshare abc123 --groups "GIS Team"
        esri-cli content unshare abc123 --from-org
        esri-cli content unshare abc123 --groups "abc456" --from-org
    """
    if not any([groups, unshare_from_org]):
        console.print(
            "[yellow]Provide at least one of --groups or --from-org.[/yellow]"
        )
        raise typer.Exit(1)

    gis = _connect(env)
    group_list = [g.strip() for g in groups.split(",")] if groups else None

    try:
        content_ops.unshare_item(
            gis, item=item_id, groups=group_list, unshare_from_org=unshare_from_org
        )
        parts = []
        if group_list:
            parts.append(f"removed from groups: [bold]{', '.join(group_list)}[/bold]")
        if unshare_from_org:
            parts.append("removed from org/public")
        console.print(
            f"[green]✓[/green] Item [dim]{item_id}[/dim] unshared: {', '.join(parts)}."
        )
    except ValueError as e:
        console.print(f"[red bold]Error:[/red bold] {e}")
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
