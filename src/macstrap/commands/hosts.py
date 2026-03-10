"""macstrap list / delete – manage registered hosts."""

from __future__ import annotations

import sys

import click
from rich.console import Console
from rich.table import Table

from macstrap.store import get_store

console = Console()


@click.command("list")
def cmd_list() -> None:
    """List all registered hosts and their credential status."""
    store = get_store()

    storage_label = "macOS Keychain" if sys.platform == "darwin" else "~/.config/macstrap"
    target = store.get_target()
    hosts = store.get_hosts()

    console.print(f"\n[bold]macstrap[/] credential store  [dim]({storage_label})[/]")
    console.print(f"  Default target: [cyan]{target or '(none)'}[/]\n")

    if not hosts:
        console.print("  [dim]No hosts registered. Run [cyan]macstrap ssh-auth <host>[/] to add one.[/]")
        console.print()
        return

    table = Table(show_header=True, header_style="bold", box=None, padding=(0, 2))
    table.add_column("Host")
    table.add_column("User")
    table.add_column("Password")
    table.add_column("")

    for host in hosts:
        has_pass = store.get_pass(host) is not None
        ssh_user = store.get_user(host) or "[dim](not set)[/]"
        pass_status = "[green]✓ stored[/]" if has_pass else "[red]✗ missing[/]"
        default_marker = "[dim]← default[/]" if host == target else ""
        table.add_row(host, ssh_user, pass_status, default_marker)

    console.print(table)
    console.print()


@click.command("delete")
@click.argument("host")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation prompt.")
def cmd_delete(host: str, yes: bool) -> None:
    """Remove credentials for HOST from the store."""
    store = get_store()

    if not store.get_pass(host) and host not in store.get_hosts():
        console.print(f"[yellow]⚠[/]  Host [bold]{host}[/] is not registered.")
        raise SystemExit(1)

    if not yes:
        click.confirm(f"  Delete credentials for {host}?", abort=True)

    store.unregister(host)
    console.print(f"[green]✓[/]  Deleted credentials for [bold]{host}[/]")
    console.print()


@click.command("delete-all")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation prompt.")
def cmd_delete_all(yes: bool) -> None:
    """Remove ALL macstrap credentials from the store."""
    store = get_store()
    hosts = store.get_hosts()

    if not hosts:
        console.print("[dim]Nothing to delete.[/]")
        return

    console.print(f"\n[bold red]This will delete credentials for {len(hosts)} host(s):[/]")
    for h in hosts:
        console.print(f"  · {h}")
    console.print()

    if not yes:
        click.confirm("  Proceed?", abort=True)

    for h in hosts:
        store.unregister(h)
    store.delete_target()

    console.print(f"[green]✓[/]  All macstrap credentials deleted.")
    console.print()
