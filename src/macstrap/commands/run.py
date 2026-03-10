"""macstrap run – apply setup to a remote Mac via SSH + Ansible."""

from __future__ import annotations

import getpass
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from macstrap.store import get_store

console = Console()

# ── Package file helpers ───────────────────────────────────────────────────

def _parse_pkg_file(path: Path) -> list[str]:
    """Read a package file, stripping comments and blank lines."""
    if not path.exists():
        return []
    lines = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            lines.append(line)
    return lines


def _read_packages(pkg_dir: Path) -> dict[str, list[str]]:
    return {
        "macports_packages":   _parse_pkg_file(pkg_dir / "packages-macports.txt"),
        "homebrew_packages":   _parse_pkg_file(pkg_dir / "packages-brew.txt"),
        "homebrew_casks":      _parse_pkg_file(pkg_dir / "packages-brew-casks.txt"),
        "npm_global_packages": _parse_pkg_file(pkg_dir / "packages-npm-global.txt"),
        "pip_global_packages": _parse_pkg_file(pkg_dir / "packages-pip-global.txt"),
    }


def _merge_packages(pkg_dirs: list[Path]) -> dict[str, list[str]]:
    """Merge package files from multiple config dirs while preserving order."""
    merged = {
        "macports_packages": [],
        "homebrew_packages": [],
        "homebrew_casks": [],
        "npm_global_packages": [],
        "pip_global_packages": [],
    }
    seen: dict[str, set[str]] = {k: set() for k in merged}

    for pkg_dir in pkg_dirs:
        current = _read_packages(pkg_dir)
        for key, items in current.items():
            for item in items:
                if item not in seen[key]:
                    seen[key].add(item)
                    merged[key].append(item)
    return merged


# ── Ansible workspace builder ──────────────────────────────────────────────

def _ansible_src() -> Path:
    """Path to the bundled Ansible directory inside this package."""
    import macstrap.ansible as _ansible_pkg  # noqa: PLC0415
    return Path(_ansible_pkg.__file__).parent


def _build_workspace(
    tmp: Path,
    host: str,
    user: str,
    packages: dict[str, list[str]],
    password: str,
) -> Path:
    """Copy bundled Ansible files to tmp; inject inventory, vars, and password."""
    # 1. Copy bundled playbook + roles
    shutil.copytree(str(_ansible_src()), str(tmp), dirs_exist_ok=True)

    # 2. Dynamic inventory
    inv_dir = tmp / "inventory"
    inv_dir.mkdir(exist_ok=True)
    (inv_dir / "hosts.ini").write_text(
        f"[macmini]\n{host} ansible_user={user}\n"
    )

    # 3. group_vars from package files
    #    Written as plain YAML to avoid pulling in PyYAML directly
    #    (ansible-core already provides it at runtime).
    gv_dir = tmp / "group_vars" / "all"
    gv_dir.mkdir(parents=True, exist_ok=True)

    def _yaml_list(items: list[str]) -> str:
        if not items:
            # Space before [] is required — without it PyYAML parses
            # "key:[]" as a plain scalar string, not an empty list.
            return " []\n"
        return "\n" + "".join(f"  - {i}\n" for i in items)

    pkg_yml = "---\n"
    for key, items in packages.items():
        pkg_yml += f"{key}:{_yaml_list(items)}\n"
    (gv_dir / "packages.yml").write_text(pkg_yml)

    # 4. Become password file (chmod 600)
    pass_file = tmp / ".become_pass"
    pass_file.write_text(password + "\n")
    pass_file.chmod(0o600)

    return pass_file


# ── community.general collection ──────────────────────────────────────────

def _ensure_collection() -> None:
    """Install community.general if it is not already present."""
    result = subprocess.run(
        ["ansible-galaxy", "collection", "list", "community.general"],
        capture_output=True,
        text=True,
    )
    if "community.general" not in result.stdout:
        console.print("[dim]  Installing community.general collection (one-time)...[/]")
        subprocess.run(
            ["ansible-galaxy", "collection", "install", "community.general"],
            check=True,
        )


# ── Pretty summary panel ───────────────────────────────────────────────────

def _print_summary(
    host: str,
    user: str,
    config_dirs: list[Path],
    packages: dict[str, list[str]],
    tags: tuple[str, ...],
    check: bool,
) -> None:
    t = Table(show_header=False, box=None, padding=(0, 1))
    t.add_column(style="dim")
    t.add_column()
    t.add_row("host", f"[bold]{host}[/]")
    t.add_row("user", f"[bold]{user}[/]")
    t.add_row("config", "\n".join(str(d) for d in config_dirs))
    if tags:
        t.add_row("tags", ", ".join(tags))
    if check:
        t.add_row("mode", "[yellow]dry run (--check)[/]")
    for key, items in packages.items():
        if items:
            label = key.replace("_packages", "").replace("_", "-")
            t.add_row(label, f"{len(items)} package(s)")
    console.print(Panel(t, title="[bold]macstrap run[/]", border_style="cyan"))
    console.print()


# ── Click command ──────────────────────────────────────────────────────────

@click.command("run")
@click.argument("host", required=False)
@click.option(
    "--user", "-u",
    default=None,
    help="SSH username (default: current OS user).",
)
@click.option(
    "--tag", "-t",
    multiple=True,
    help="Only run roles matching these tags (repeatable).",
)
@click.option(
    "--check", is_flag=True,
    help="Dry run – show what would change without applying.",
)
@click.option(
    "--dir", "--config", "package_dir",
    multiple=True,
    show_default=True,
    type=click.Path(file_okay=False),
    help="Config directory containing packages-*.txt files (repeatable).",
)
def cmd_run(
    host: str | None,
    user: str | None,
    tag: tuple[str, ...],
    check: bool,
    package_dir: tuple[str, ...],
) -> None:
    """Run Mac setup on HOST via SSH.

    \b
    HOST can be:
      mac-mini-openclaw.local   (mDNS, default if omitted)
      192.168.1.100             (IPv4)

    If HOST is omitted, uses the default target from the credential store.

    \b
    Examples:
      macstrap run
      macstrap run mac-mini-openclaw.local
      macstrap run 192.168.1.100 --user mac-mini
      macstrap run --config my-openclaw-setup 192.168.1.101
      macstrap run --dir my-mac-mini --dir my-openclaw-setup 192.168.1.101
      macstrap run mac-mini-openclaw.local --tag homebrew
      macstrap run mac-mini-openclaw.local --check
    """
    store = get_store()

    # ── Resolve host (support user@host syntax) ────────────────────────────
    raw_host = host or store.get_target()
    if not raw_host:
        console.print(
            "[red]✗[/]  No host specified and no default target found.\n"
            "    Run [cyan]macstrap ssh-auth <host>[/] first, or pass HOST explicitly."
        )
        raise SystemExit(1)

    # Parse optional user@host syntax
    user_from_arg: str | None = None
    if raw_host and "@" in raw_host:
        user_from_arg, effective_host = raw_host.split("@", 1)
    else:
        effective_host = raw_host

    # ── Resolve SSH user (priority: --user flag > user@host > stored > local OS user)
    effective_user = user or user_from_arg or store.get_user(effective_host) or getpass.getuser()

    # ── Retrieve become (sudo) password ───────────────────────────────────
    password = store.get_pass(effective_host)
    if not password:
        console.print(
            f"[red]✗[/]  No credentials found for [bold]{effective_host}[/].\n"
            f"    Run [cyan]macstrap ssh-auth {effective_host}[/] to register it."
        )
        raise SystemExit(1)

    # ── Locate ansible-playbook ────────────────────────────────────────────
    ansible_pb = shutil.which("ansible-playbook")
    if not ansible_pb:
        console.print(
            "[red]✗[/]  ansible-playbook not found in PATH.\n"
            "    This should have been installed with macstrap – try:\n"
            "    [cyan]pip install --upgrade macstrap[/]"
        )
        raise SystemExit(1)

    # ── Read package files ─────────────────────────────────────────────────
    pkg_dirs = [Path(p).resolve() for p in (package_dir or (".",))]
    packages = _merge_packages(pkg_dirs)
    total_pkgs = sum(len(v) for v in packages.values())
    if total_pkgs == 0:
        console.print(
            "[yellow]⚠[/]  No packages found in config dirs:\n"
            f"    [dim]{', '.join(str(p) for p in pkg_dirs)}[/]\n"
            "    Run [cyan]macstrap init[/] to create template package files.\n"
            "    Continuing – roles that need no packages will still run.\n"
        )

    # ── Print summary ──────────────────────────────────────────────────────
    _print_summary(effective_host, effective_user, pkg_dirs, packages, tag, check)

    # ── Ensure community.general collection ───────────────────────────────
    _ensure_collection()

    # ── Build temp workspace and run ansible-playbook ─────────────────────
    with tempfile.TemporaryDirectory(prefix="macstrap-") as tmp_str:
        tmp = Path(tmp_str)

        pass_file = _build_workspace(
            tmp, effective_host, effective_user, packages, password
        )

        cmd: list[str] = [
            ansible_pb,
            "playbook.yml",
            "-i", "inventory/hosts.ini",
            # Do NOT pass --become globally: tasks that need sudo already have
            # become: true individually. A global --become would run everything
            # as root, which breaks tools like Homebrew that refuse to run as root.
            "--become-password-file", str(pass_file),
        ]
        if check:
            cmd.append("--check")
        if tag:
            cmd.extend(["--tags", ",".join(tag)])

        result = subprocess.run(cmd, cwd=str(tmp))

    sys.exit(result.returncode)
