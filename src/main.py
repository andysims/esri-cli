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
from typing import Optional

import typer
from arcgis.gis import GIS
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from .auth import load_config, gis_conn
from . import users as user_ops
from . import groups as group_ops

# ---------------------------------------------------------------------------
# Logging — INFO goes to file, WARNING+ to stderr so Rich owns stdout cleanly.
# ---------------------------------------------------------------------------
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

app.add_typer(user_app, name="user")
app.add_typer(group_app, name="group")

# content_app = typer.Typer(help="Content management commands.")
# app.add_typer(content_app, name="content")


# ---------------------------------------------------------------------------
# Shared auth helper — called once at the top of every command.
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

    for item in items:
        table.add_row(
            item.id,
            item.title,
            item.type,
            item.owner,
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
# Future domains:
#
#   content_app = typer.Typer(help="Content management commands.")
#   app.add_typer(content_app, name="content")
#
#   audit_app = typer.Typer(help="Audit and reporting commands.")
#   app.add_typer(audit_app, name="audit")
# ===========================================================================


if __name__ == "__main__":
    app()
