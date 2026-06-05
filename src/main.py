"""
main.py — ArcGIS Admin CLI
--------------------------
Entry point for the CLI. Using Typer to build a multi-command app broken
into sub-apps per domain (users, groups, content, etc.). Rich handles all
terminal output so we get tables, colors, and panels instead of raw print().

Run with:
    python main.py --help
    python main.py user find --email jdoe@example.com
    python main.py user create --username jdoe ...

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
from rich import print as rprint

from .auth import load_config, gis_conn
from . import users as user_ops

# ---------------------------------------------------------------------------
# Logging setup — INFO to file, WARNING+ to stderr so it doesn't pollute
# Rich's output. Adjust level here rather than scattered across modules.
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    handlers=[
        logging.FileHandler("arcgis_cli.log"),
        # Keep the console handler at WARNING so Rich owns the terminal.
        logging.StreamHandler(sys.stderr),
    ],
)
logging.getLogger("arcgis").setLevel(logging.ERROR)
log = logging.getLogger(__name__)

# Rich console — used everywhere for pretty output.
console = Console()

# ---------------------------------------------------------------------------
# Root app + sub-apps
# Each domain gets its own app so commands stay organized:
#   python main.py user ...
#   python main.py group ...   (future)
#   python main.py content ... (future)
# ---------------------------------------------------------------------------
app = typer.Typer(
    name="arcgis-admin",
    help="ArcGIS Online / Portal administration CLI.",
    no_args_is_help=True,
)

user_app = typer.Typer(help="User management commands.", no_args_is_help=True)
app.add_typer(user_app, name="user")

# Placeholders — wire these up when you add the modules.
# group_app = typer.Typer(help="Group management commands.")
# app.add_typer(group_app, name="group")


# ---------------------------------------------------------------------------
# Shared auth helper
# Every command calls this once. Keeps the "get a GIS object" boilerplate
# out of each individual command function.
# ---------------------------------------------------------------------------
def _connect(env: str) -> GIS:
    """Load credentials for `env` and return an authenticated GIS object.

    Exits with a clean error message if credentials are missing or the
    connection fails — no raw tracebacks in the user's terminal.
    """
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
# SEARCH commands
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

    All provided filters are AND-ed together, so narrowing them down gives
    fewer results. At least one filter is required.

    Example:
        python main.py user find --email jdoe@example.com
        python main.py user find --lastname Smith --env portal
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

    # Build a Rich table — much easier to scan than a wall of text.
    table = Table(title=f"Users ({len(results)} found)", show_lines=True)
    table.add_column("Username", style="cyan", no_wrap=True)
    table.add_column("Full Name")
    table.add_column("Email")
    table.add_column("Role")
    table.add_column("User Type")
    table.add_column("Created")

    for u in results:
        table.add_row(
            u.username,
            u.fullName,
            u.email,
            u.role,
            u.userLicenseType,
            u.created or "—",
        )

    console.print(table)


@user_app.command("details")
def cmd_user_details(
    username: str = typer.Argument(..., help="Username to look up."),
    env: str = typer.Option("agol", "--env", help="Environment key in .env."),
):
    """Show full details for a single user in a formatted panel.

    Example:
        python main.py user details jdoe
    """
    gis = _connect(env)

    try:
        u = user_ops.user_details(gis, username)
    except ValueError as e:
        console.print(f"[red]Not found:[/red] {e}")
        raise typer.Exit(1)

    # Panel gives us a nice box with a title — good for single-record views.
    detail_lines = [
        f"[bold]Username:[/bold]  {u.username}",
        f"[bold]Full Name:[/bold] {u.fullName}",
        f"[bold]Email:[/bold]     {u.email}",
        f"[bold]Role:[/bold]      {u.role}",
        f"[bold]User Type:[/bold] {u.userLicenseType}",
        f"[bold]Created:[/bold]   {u.created or '—'}",
        f"[bold]Disabled:[/bold]  {'Yes' if u.disabled else 'No'}",
        f"[bold]Provider:[/bold]  {u.provider}",
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
        python main.py user folders jdoe
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
# LIFECYCLE commands
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
        python main.py user create -u jdoe -f Jane -l Doe -e jdoe@co.com --password Secret1!
        python main.py user create -u jdoe -f Jane -l Doe -e jdoe@co.com --idp jdoe@corp.ad
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

    If the user owns content or groups, you must pass --reassign-to so we
    know where to move their stuff before deleting. Use --dry-run first to
    see whether it's safe.

    Examples:
        python main.py user delete jdoe --dry-run
        python main.py user delete jdoe --reassign-to admin_user --yes
    """
    gis = _connect(env)

    # Dry run: just check, don't ask for confirmation.
    if dry_run:
        try:
            user_ops.delete_user(gis, username, dry_run=True)
            console.print(
                f"[green]✓ Dry run passed.[/green] User '{username}' can be safely deleted."
            )
        except ValueError as e:
            console.print(f"[yellow]Dry run failed:[/yellow] {e}")
        return

    # Real deletion: confirm unless --yes was passed. Destructive ops should
    # require the user to explicitly say "I know what I'm doing."
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
        python main.py user set-role jdoe org_publisher
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
        python main.py user set-type jdoe creatorUT
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
# ACCESS / SECURITY commands
# ---------------------------------------------------------------------------


@user_app.command("disable")
def cmd_disable_user(
    username: str = typer.Argument(..., help="Username to disable."),
    env: str = typer.Option("agol", "--env", help="Environment key in .env."),
):
    """Disable a user account (they can no longer sign in).

    Example:
        python main.py user disable jdoe
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
        python main.py user enable jdoe
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

    This won't work on enterprise/IdP-backed accounts — those passwords
    are managed by the identity provider, not ArcGIS.

    Example:
        python main.py user reset-password jdoe --password NewSecret1!
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
    cannot have an IdP username set.

    Example:
        python main.py user set-idp jdoe jdoe@corp.onmicrosoft.com
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
# OFFBOARDING commands
# ---------------------------------------------------------------------------


@user_app.command("check-deps")
def cmd_check_dependencies(
    username: str = typer.Argument(..., help="Username to inspect."),
    env: str = typer.Option("agol", "--env", help="Environment key in .env."),
):
    """Check what a user owns before deletion or offboarding.

    Prints a summary of their items, folders, and group memberships so you
    know what needs to be reassigned before you can delete the account.

    Example:
        python main.py user check-deps jdoe
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

    This is the step to run before deleting an offboarded employee's account.
    It moves both root-level items and folder contents, recreating folders on
    the target user's account as needed.

    Example:
        python main.py user transfer --from jdoe --to admin_user
        python main.py user transfer --from jdoe --to admin_user --no-groups --yes
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
# Future sub-apps go here:
#
#   @group_app.command("list") ...
#   @content_app.command("search") ...
#
# Then wire them in near the top:
#   app.add_typer(group_app, name="group")
# ===========================================================================


if __name__ == "__main__":
    app()
