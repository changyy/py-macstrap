"""macstrap ssh-auth – set up SSH key auth and store sudo credentials for a host."""

from __future__ import annotations

import getpass
import shutil
import subprocess
import sys
from pathlib import Path

import click
from rich.console import Console

from macstrap.store import get_store

console = Console()

# ── SSH key helpers ────────────────────────────────────────────────────────

_KEY_CANDIDATES = [
    "~/.ssh/id_ed25519",
    "~/.ssh/id_rsa",
    "~/.ssh/id_ecdsa",
]


def _find_public_key() -> Path | None:
    for candidate in _KEY_CANDIDATES:
        pub = Path(candidate).expanduser().with_suffix(".pub")
        if pub.exists():
            return pub
    return None


def _generate_key() -> Path:
    key_path = Path("~/.ssh/id_ed25519").expanduser()
    console.print("[dim]  Generating ed25519 SSH key pair...[/]")
    subprocess.run(
        ["ssh-keygen", "-t", "ed25519", "-f", str(key_path), "-N", ""],
        check=True,
    )
    return key_path.with_suffix(".pub")


def _copy_key_to_host(pub_key: Path, user: str, host: str) -> bool:
    """Copy public key to remote host. Returns True on success."""
    console.print(f"\n  Copying public key to [bold]{user}@{host}[/]...")
    console.print(f"  [dim]Using: {pub_key}[/]")

    # Prefer ssh-copy-id (available on macOS and most Linux)
    if shutil.which("ssh-copy-id"):
        result = subprocess.run(
            ["ssh-copy-id", "-i", str(pub_key), f"{user}@{host}"],
        )
        return result.returncode == 0

    # Fallback: manual append via SSH
    pub_key_content = pub_key.read_text().strip()
    result = subprocess.run(
        [
            "ssh", f"{user}@{host}",
            f"mkdir -p ~/.ssh && chmod 700 ~/.ssh && "
            f"echo '{pub_key_content}' >> ~/.ssh/authorized_keys && "
            f"chmod 600 ~/.ssh/authorized_keys",
        ],
    )
    return result.returncode == 0


def _verify_ssh(user: str, host: str) -> bool:
    """Test passwordless SSH works."""
    result = subprocess.run(
        ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5",
         f"{user}@{host}", "true"],
        capture_output=True,
    )
    return result.returncode == 0


# ── Click command ──────────────────────────────────────────────────────────

@click.command("ssh-auth")
@click.argument("host")
@click.option(
    "--user", "-u",
    default=None,
    help="SSH username on the remote host (default: current OS user).",
)
@click.option(
    "--update", is_flag=True,
    help="Update stored sudo password for an already-registered host.",
)
@click.option(
    "--skip-key-copy", is_flag=True,
    help="Skip SSH public key setup (use if passwordless SSH is already working).",
)
def cmd_ssh_auth(host: str, user: str | None, update: bool, skip_key_copy: bool) -> None:
    """Set up SSH key auth and store the sudo password for HOST.

    \b
    Two steps happen automatically:
      1. Copy your SSH public key to HOST (so Ansible can connect without a password)
      2. Store HOST's sudo password in the system credential store

    \b
    HOST can be:
      mac-mini-openclaw.local   (mDNS)
      192.168.1.100             (IPv4)
      localhost

    On macOS the sudo password is saved in Keychain.
    On Linux it is saved in ~/.config/macstrap/ (chmod 600).
    """
    store = get_store()
    effective_user = user or getpass.getuser()

    # ── Guard: already registered ─────────────────────────────────────────
    existing = store.get_pass(host)
    if existing and not update:
        # Check whether SSH also works – if not, still offer key setup
        if _verify_ssh(effective_user, host):
            console.print(
                f"[yellow]⚠[/]  Host [bold]{host}[/] is already registered and SSH works.\n"
                "    Use [cyan]--update[/] to change the sudo password, or\n"
                "    Use [cyan]--skip-key-copy --update[/] to update only the password."
            )
            raise SystemExit(1)
        else:
            console.print(
                f"[yellow]⚠[/]  Host [bold]{host}[/] is already registered but "
                "SSH key auth is not working.\n"
                "    Re-running key copy step...\n"
            )

    console.print(f"\n[bold]Setting up[/] {host}  (user: [cyan]{effective_user}[/])\n")

    # ── Step 1: SSH key setup ─────────────────────────────────────────────
    if not skip_key_copy:
        pub_key = _find_public_key()
        if pub_key is None:
            console.print(
                "[yellow]  No SSH key found.[/] Generating a new ed25519 key pair.\n"
            )
            pub_key = _generate_key()

        console.print(f"[bold]Step 1/2[/]  Copy SSH public key → {host}")
        console.print(
            "  You will be prompted for your [italic]SSH login password[/] "
            "(one-time only).\n"
        )

        ok = _copy_key_to_host(pub_key, effective_user, host)
        if not ok:
            console.print(
                "\n[red]✗[/]  Key copy failed. Check that:\n"
                f"    • [bold]{host}[/] is reachable\n"
                f"    • user [bold]{effective_user}[/] exists on the remote\n"
                "    • SSH password auth is enabled on the remote\n"
                "\n    You can retry with the correct user:  "
                f"[cyan]macstrap ssh-auth {host} --user <username>[/]"
            )
            raise SystemExit(1)

        # Verify
        if _verify_ssh(effective_user, host):
            console.print(f"\n[green]✓[/]  Passwordless SSH to {host} working.")
        else:
            console.print(
                "\n[yellow]⚠[/]  Could not verify passwordless SSH – "
                "continuing anyway.\n"
                "    If macstrap run fails with SSH errors, check that "
                f"[dim]{pub_key}[/] was accepted."
            )
    else:
        console.print("[dim]  Skipping SSH key copy (--skip-key-copy).[/]")
        if not _verify_ssh(effective_user, host):
            console.print(
                f"[yellow]⚠[/]  Warning: passwordless SSH to [bold]{host}[/] "
                "does not appear to be working.\n"
                "    Ansible will likely fail. Re-run without --skip-key-copy."
            )

    # ── Step 2: sudo password ─────────────────────────────────────────────
    console.print(f"\n[bold]Step 2/2[/]  Store sudo password for {host}")
    console.print(
        "  This is the [italic]sudo (become) password[/] used by Ansible, "
        "not the SSH login password.\n"
    )

    sudo_password = click.prompt(
        f"  sudo password for {effective_user}@{host}",
        hide_input=True,
        confirmation_prompt="  Confirm sudo password",
    )

    store.register(host, sudo_password, user=effective_user)

    storage_label = "macOS Keychain" if sys.platform == "darwin" else "~/.config/macstrap"
    console.print(f"\n[green]✓[/]  Sudo password stored in {storage_label}")
    console.print(f"     Key: [dim]macstrap-pass-{host}[/]")
    console.print(f"     SSH user: [dim]{effective_user}[/]")
    console.print(f"\n[bold]All set! Run:[/]")
    console.print(f"  [cyan]macstrap run {host}[/]\n")
