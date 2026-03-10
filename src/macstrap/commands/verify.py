"""macstrap verify – check which packages are installed on the remote Mac."""

from __future__ import annotations

import getpass
import subprocess
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from macstrap.commands.run import _read_packages
from macstrap.store import get_store

console = Console()


# ── Shell script builder ────────────────────────────────────────────────────

# (name, check_cmd, version_cmd)
# check_cmd exit 0  → tool is present
# version_cmd output → shown as version string (may be empty)
_TOOL_CHECKS: list[tuple[str, str, str]] = [
    # Use absolute path: /opt/homebrew/bin is NOT in the default SSH PATH
    ("brew",    'test -x /opt/homebrew/bin/brew',
                '/opt/homebrew/bin/brew --version 2>/dev/null | head -1'),
    ("port",    'test -x /opt/local/bin/port',
                '/opt/local/bin/port version 2>/dev/null | head -1'),
    ("nvm",     'test -s "$HOME/.nvm/nvm.sh"',
                'nvm --version 2>/dev/null'),
    ("node",    'command -v node',
                'node --version 2>/dev/null'),
    # Docker Desktop CLI lands in /usr/local/bin (added to PATH in script header)
    ("docker",  'command -v docker',
                'docker --version 2>/dev/null'),
    # /usr/bin/java is a macOS stub that fails at runtime; check Homebrew openjdk
    ("java",    'test -x /opt/homebrew/opt/openjdk/bin/java',
                '/opt/homebrew/opt/openjdk/bin/java -version 2>&1 | head -1'),
    ("python3", 'command -v python3',
                'python3 --version 2>/dev/null'),
]


def _build_check_script(packages: dict[str, list[str]]) -> str:
    """Return a bash script that prints TOOL:/PKG: tagged lines for each check."""
    lines: list[str] = [
        "#!/bin/bash",
        "# Extend PATH: SSH non-interactive sessions only get /usr/bin:/bin etc.",
        'export PATH="/opt/homebrew/bin:/opt/homebrew/sbin:/usr/local/bin:/opt/local/bin:$PATH"',
        '[ -s "$HOME/.nvm/nvm.sh" ] && source "$HOME/.nvm/nvm.sh" 2>/dev/null',
        "",
        "# --- Tool checks ---",
    ]

    for name, check_cmd, ver_cmd in _TOOL_CHECKS:
        lines += [
            f'if {check_cmd} >/dev/null 2>&1; then',
            f'  _ver=$({ver_cmd})',
            f'  echo "TOOL:{name}:ok:$_ver"',
            f'else',
            f'  echo "TOOL:{name}:missing:"',
            f'fi',
        ]

    lines += ["", "# --- Package checks ---"]

    for pkg in packages.get("macports_packages", []):
        lines += [
            f'if /opt/local/bin/port installed {pkg} 2>/dev/null | grep -q "  {pkg} @"; then',
            f'  echo "PKG:macports:{pkg}:ok"',
            f'else',
            f'  echo "PKG:macports:{pkg}:missing"',
            f'fi',
        ]

    for pkg in packages.get("homebrew_packages", []):
        lines += [
            f'if /opt/homebrew/bin/brew list --formula {pkg} >/dev/null 2>&1; then',
            f'  echo "PKG:brew:{pkg}:ok"',
            f'else',
            f'  echo "PKG:brew:{pkg}:missing"',
            f'fi',
        ]

    for pkg in packages.get("homebrew_casks", []):
        lines += [
            f'if /opt/homebrew/bin/brew list --cask {pkg} >/dev/null 2>&1; then',
            f'  echo "PKG:cask:{pkg}:ok"',
            f'else',
            f'  echo "PKG:cask:{pkg}:missing"',
            f'fi',
        ]

    for pkg in packages.get("npm_global_packages", []):
        lines += [
            f'if npm list -g {pkg} >/dev/null 2>&1; then',
            f'  echo "PKG:npm:{pkg}:ok"',
            f'else',
            f'  echo "PKG:npm:{pkg}:missing"',
            f'fi',
        ]

    for pkg in packages.get("pip_global_packages", []):
        lines += [
            f'if pip3 show {pkg} >/dev/null 2>&1; then',
            f'  echo "PKG:pip:{pkg}:ok"',
            f'else',
            f'  echo "PKG:pip:{pkg}:missing"',
            f'fi',
        ]

    return "\n".join(lines) + "\n"


# ── Output parsing ──────────────────────────────────────────────────────────

_TOOL_ORDER = [name for name, _, _ in _TOOL_CHECKS]

_PKG_TYPE_META: dict[str, tuple[str, str]] = {
    "macports": ("macports_packages",   "MacPorts"),
    "brew":     ("homebrew_packages",   "Homebrew"),
    "cask":     ("homebrew_casks",      "Homebrew Cask"),
    "npm":      ("npm_global_packages", "npm global"),
    "pip":      ("pip_global_packages", "pip global"),
}
_PKG_TYPE_ORDER = list(_PKG_TYPE_META.keys())


def _parse_output(
    stdout: str,
) -> tuple[dict[str, tuple[bool, str]], dict[tuple[str, str], bool]]:
    tool_results: dict[str, tuple[bool, str]] = {t: (False, "") for t in _TOOL_ORDER}
    pkg_results: dict[tuple[str, str], bool] = {}

    for line in stdout.splitlines():
        parts = line.split(":", 3)
        if not parts:
            continue
        kind = parts[0]
        if kind == "TOOL" and len(parts) >= 3:
            name, status = parts[1], parts[2]
            ver = parts[3].strip() if len(parts) > 3 else ""
            tool_results[name] = (status == "ok", ver)
        elif kind == "PKG" and len(parts) >= 4:
            ptype, pkg, status = parts[1], parts[2], parts[3]
            pkg_results[(ptype, pkg)] = status == "ok"

    return tool_results, pkg_results


# ── Rich display ────────────────────────────────────────────────────────────

def _print_results(
    tool_results: dict[str, tuple[bool, str]],
    pkg_results: dict[tuple[str, str], bool],
    packages: dict[str, list[str]],
) -> bool:
    """Print verify results. Returns True if any packages are missing."""
    any_missing = False

    # Tools section
    console.print("[bold]  Tools[/]")
    for name in _TOOL_ORDER:
        ok, ver = tool_results.get(name, (False, ""))
        icon = "[green]✓[/]" if ok else "[dim]✗[/]"
        ver_str = f"[dim]{ver}[/]" if ver else "[dim]not found[/]"
        console.print(f"  {icon}  [cyan]{name:<10}[/] {ver_str}")
    console.print()

    # Packages section
    total = sum(
        len(packages.get(meta[0], [])) for meta in _PKG_TYPE_META.values()
    )

    if total == 0:
        console.print(
            "  [dim]No packages configured – run [cyan]macstrap init[/cyan]"
            " to create package list files.[/]"
        )
        return False

    for ptype in _PKG_TYPE_ORDER:
        pkg_key, label = _PKG_TYPE_META[ptype]
        pkgs = packages.get(pkg_key, [])
        if not pkgs:
            continue
        ok_count = sum(1 for p in pkgs if pkg_results.get((ptype, p), False))
        console.print(f"[bold]  {label}[/] [dim]({ok_count}/{len(pkgs)})[/]")
        for pkg in pkgs:
            ok = pkg_results.get((ptype, pkg), False)
            icon = "[green]✓[/]" if ok else "[red]✗[/]"
            note = "" if ok else "  [red dim](missing)[/]"
            console.print(f"  {icon}  {pkg}{note}")
            if not ok:
                any_missing = True
        console.print()

    # Summary line
    installed = sum(1 for v in pkg_results.values() if v)
    missing   = sum(1 for v in pkg_results.values() if not v)
    if missing == 0:
        console.print(f"  [green]✓[/]  All {installed} package(s) verified.")
    else:
        console.print(
            f"  [yellow]⚠[/]  {installed} installed, [red bold]{missing} missing[/]."
        )

    return any_missing


# ── Click command ───────────────────────────────────────────────────────────

@click.command("verify")
@click.argument("host", required=False)
@click.option("--user", "-u", default=None, help="SSH username.")
@click.option(
    "--dir", "--config", "package_dir",
    default=".",
    show_default=True,
    type=click.Path(file_okay=False),
    help="Config directory containing packages-*.txt files.",
)
def cmd_verify(host: str | None, user: str | None, package_dir: str) -> None:
    """Verify that packages in packages-*.txt are installed on HOST.

    \b
    Connects to HOST via SSH, runs a check script, and prints a ✓/✗ report
    for every tool and package.  Exits with code 1 if anything is missing.

    \b
    Examples:
      macstrap verify
      macstrap verify user-macmini.local
      macstrap verify 192.168.1.100 --user mac-mini
    """
    store = get_store()

    # ── Resolve host / user ────────────────────────────────────────────────
    raw_host = host or store.get_target()
    if not raw_host:
        console.print(
            "[red]✗[/]  No host specified and no default target.\n"
            "    Run [cyan]macstrap ssh-auth <host>[/] first."
        )
        raise SystemExit(1)

    user_from_arg: str | None = None
    if "@" in raw_host:
        user_from_arg, effective_host = raw_host.split("@", 1)
    else:
        effective_host = raw_host

    effective_user = (
        user or user_from_arg or store.get_user(effective_host) or getpass.getuser()
    )

    # ── Header ─────────────────────────────────────────────────────────────
    t = Table(show_header=False, box=None, padding=(0, 1))
    t.add_column(style="dim")
    t.add_column()
    t.add_row("host", f"[bold]{effective_host}[/]")
    t.add_row("user", f"[bold]{effective_user}[/]")
    console.print(Panel(t, title="[bold]macstrap verify[/]", border_style="cyan"))
    console.print()

    # ── Build and run check script ─────────────────────────────────────────
    pkg_dir  = Path(package_dir).resolve()
    packages = _read_packages(pkg_dir)
    script   = _build_check_script(packages)

    console.print("[dim]  Connecting…[/]\n")
    result = subprocess.run(
        [
            "ssh",
            "-o", "BatchMode=yes",
            "-o", "ConnectTimeout=10",
            f"{effective_user}@{effective_host}",
            "bash -s",
        ],
        input=script,
        capture_output=True,
        text=True,
    )

    if result.returncode != 0 and not result.stdout.strip():
        console.print(f"[red]✗[/]  SSH connection failed:\n{result.stderr}")
        raise SystemExit(1)

    # ── Parse and display ──────────────────────────────────────────────────
    tool_results, pkg_results = _parse_output(result.stdout)
    has_missing = _print_results(tool_results, pkg_results, packages)
    sys.exit(1 if has_missing else 0)
